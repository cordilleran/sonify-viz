"""
Render manifest and verification (2026-09-27): the backbone of track versions.

`renders.lock.json` (repo root) holds one entry per track (and variant): its
version, the script and arguments that render it, the seed, SHA-256 hashes of
the engine code, of every data file and sample the render opened, and of every
file it wrote. A version changes when the music changes; this file proves when
it didn't.

  python renders.py lock  TRACK VERSION -- SCRIPT [ARGS...]   render, check, record
  python renders.py verify [TRACK ...]                         re-render, compare (all if none named)
  python renders.py list

Both `lock` and `verify` render into a scratch folder (SONIFICATION_HEAVY,
_LIGHT and _SITE_AUDIO point there), so the published files are never
overwritten. `lock` also requires the scratch render to match the files in
place, so a lock always describes the audio that exists. Code is pinned by
content hash rather than a git commit: the lock is written before the commit,
and the hashes also hold outside the repository.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LOCK = ROOT / "renders.lock.json"
ENGINE = ["dsp_core.py", "timegrid.py", "harmony.py", "records.py", "seasonal.py", "sampler.py", "synth.py", "solar.py"]
PY = sys.executable

# Run SCRIPT with an audit hook that logs every file it opens for reading.
_RUNNER = r"""
import sys, os, runpy
log = open(os.environ["RENDERS_OPEN_LOG"], "w")
def hook(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        mode = args[1] if len(args) > 1 and isinstance(args[1], str) else "r"
        if "r" in mode and "+" not in mode:
            log.write(os.fspath(args[0]) if not isinstance(args[0], bytes) else args[0].decode() )
            log.write("\n"); log.flush()
sys.addaudithook(hook)
import soundfile  # samples open through libsndfile, which the audit hook doesn't see
_init = soundfile.SoundFile.__init__
def _logged(self, file, mode="r", *a, **k):
    if isinstance(file, (str, os.PathLike)) and "r" in mode and "+" not in mode:
        log.write(os.fspath(file) + "\n"); log.flush()
    _init(self, file, mode, *a, **k)
soundfile.SoundFile.__init__ = _logged
try:  # parquet tables open through pyarrow's C++ readers, also unseen by the hook
    import pyarrow.parquet as _pq
    _rt = _pq.read_table
    def _read_table(source, *a, **k):
        if isinstance(source, (str, os.PathLike)):
            log.write(os.fspath(source) + "\n"); log.flush()
        return _rt(source, *a, **k)
    _pq.read_table = _read_table
except ImportError:
    pass
script, *rest = sys.argv[1:]
sys.argv = [script] + rest
sys.path.insert(0, os.path.dirname(os.path.abspath(script)))
runpy.run_path(script, run_name="__main__")
"""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_lock():
    return json.loads(LOCK.read_text()) if LOCK.exists() else {"tracks": {}}


def save_lock(lock):
    LOCK.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")


def render(script, args, scratch):
    """Render into `scratch`; return ({relpath: sha} of outputs, sorted input paths, log text)."""
    env = dict(os.environ)
    env.update(SONIFICATION_HEAVY=str(scratch / "heavy"), SONIFICATION_LIGHT=str(scratch / "light"),
               SONIFICATION_SITE_AUDIO=str(scratch / "site_audio"), RENDERS_OPEN_LOG=str(scratch / "opened.txt"))
    r = subprocess.run([PY, "-c", _RUNNER, str(HERE / script), *args], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"render failed: {script} {' '.join(args)}\n{r.stdout[-2000:]}\n{r.stderr[-3000:]}")
    outputs = {}
    for kind in ("heavy", "light", "site_audio"):
        base = scratch / kind
        for p in sorted(base.rglob("*")) if base.exists() else []:
            if p.is_file():
                outputs[f"{kind}/{p.relative_to(base)}"] = sha256(p)
    opened = sorted({Path(line).resolve() for line in (scratch / "opened.txt").read_text().splitlines() if line})
    return outputs, opened, r.stdout


def in_place(rel):
    """Where an output's published copy lives (the same env overrides the pieces read)."""
    sys.path.insert(0, str(HERE))
    import dsp_core
    kind, _, sub = rel.partition("/")
    return {"heavy": dsp_core.HEAVY_OUT, "light": dsp_core.LIGHT_OUT, "site_audio": dsp_core.SITE_AUDIO}[kind] / sub


def inputs_record(opened):
    """Hash the data files and samples a render opened (not Python's own files)."""
    import dsp_core
    data, samples = {}, hashlib.sha256()
    n_samples = 0
    for p in opened:
        if not p.is_file():
            continue
        if ROOT / "data" in p.parents:
            data[str(p.relative_to(ROOT))] = sha256(p)
        elif Path(dsp_core.SAMPLES).resolve() in p.parents:
            samples.update(f"{p.relative_to(Path(dsp_core.SAMPLES).resolve())}:{sha256(p)}\n".encode())
            n_samples += 1
    return data, {"files": n_samples, "sha256": samples.hexdigest()}


def environment():
    import numpy, scipy, soundfile
    ff = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.split("\n")[0]
    return {"python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
            "soundfile": soundfile.__version__, "ffmpeg": ff}


def cmd_lock(a):
    script_text = (HERE / a.script).read_text()
    seeds = sorted({int(a or b) for a, b in re.findall(r"(?:default_rng|random\.seed)\((\d+)\)|\"seed\":\s*(\d+)", script_text)})
    with tempfile.TemporaryDirectory(prefix="renders-") as tmp:
        outputs, opened, log = render(a.script, a.args, Path(tmp))
        data, samples = inputs_record(opened)
    said = re.search(r"^seeds: ([\d, ]+)$", log, re.M)  # a piece whose seed depends on its arguments says which
    if said:
        seeds = [int(s) for s in said.group(1).split(",")]
    bad = [rel for rel, h in outputs.items() if not in_place(rel).exists() or sha256(in_place(rel)) != h]
    if bad and not a.new:
        raise SystemExit(f"{a.track}: the scratch render differs from the files in place ({len(bad)} of "
                         f"{len(outputs)}), e.g. {bad[:3]}. Re-render in place first, or pass --new.")
    lock = load_lock()
    prev = lock["tracks"].get(a.track, {})
    lock["tracks"][a.track] = {
        "version": a.version, "locked": dt.date.today().isoformat(),
        "script": a.script, "args": a.args, "seeds": seeds,
        "code": {f: sha256(HERE / f) for f in [a.script] + ENGINE},
        "data": data, "samples": samples, "outputs": outputs, "environment": environment(),
    }
    if "--remix" in a.args:  # lineage: the parent it came from and who made it
        sys.path.insert(0, str(HERE))
        import variants
        r = variants.load_remix(ROOT / a.args[a.args.index("--remix") + 1])
        lock["tracks"][a.track].update(parent=r["parent"], credits=r["credits"], keeps=r.get("keeps"))
    if "--variant" in a.args:
        lock["tracks"][a.track]["variant"] = a.args[a.args.index("--variant") + 1]
    if prev and prev.get("version") != a.version:
        lock["tracks"][a.track]["previous"] = {"version": prev["version"], "locked": prev.get("locked")}
    elif prev.get("previous"):  # re-locking the same version keeps its history
        lock["tracks"][a.track]["previous"] = prev["previous"]
    save_lock(lock)
    print(f"{a.track} v{a.version}: {len(outputs)} outputs, {len(data)} data files, {samples['files']} samples locked")


def cmd_verify(a):
    lock = load_lock()["tracks"]
    names = a.tracks or sorted(lock)
    failed = []
    for name in names:
        e = lock[name]
        with tempfile.TemporaryDirectory(prefix="renders-") as tmp:
            outputs, opened, _ = render(e["script"], e["args"], Path(tmp))
            data, samples = inputs_record(opened)
        diff = sorted(set(outputs) ^ set(e["outputs"])) + [k for k in outputs if e["outputs"].get(k, outputs[k]) != outputs[k]]
        code = [f for f, h in e["code"].items() if (HERE / f).exists() and sha256(HERE / f) != h]
        inputs = [f"{f} (" + ("now read" if f not in e["data"] else "no longer read" if f not in data else "changed") + ")"
                  for f in set(data) | set(e["data"]) if data.get(f) != e["data"].get(f)]
        if samples != e["samples"]:
            inputs.append("samples (changed)")
        ok = not diff
        print(f"{'OK  ' if ok else 'FAIL'} {name} v{e['version']}: {len(outputs) - len(diff)}/{len(e['outputs'])} outputs identical"
              + (f"; code changed since lock: {', '.join(code)}" if code else "")
              + (f"; inputs changed: {', '.join(sorted(inputs))}" if inputs else ""))
        if not ok:
            failed.append(name)
            for k in diff[:10]:
                print(f"      differs: {k}")
    if failed:
        raise SystemExit(f"{len(failed)} of {len(names)} tracks did not reproduce")


def cmd_list(a):
    for name, e in sorted(load_lock()["tracks"].items()):
        print(f"{name:40s} v{e['version']:6s} {e['locked']}  {e['script']} {' '.join(e['args'])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lock")
    p.add_argument("track"), p.add_argument("version"), p.add_argument("script"), p.add_argument("args", nargs="*")
    p.add_argument("--new", action="store_true", help="lock a render that has no files in place yet")
    p.set_defaults(func=cmd_lock)
    p = sub.add_parser("verify")
    p.add_argument("tracks", nargs="*")
    p.set_defaults(func=cmd_verify)
    sub.add_parser("list").set_defaults(func=cmd_list)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
