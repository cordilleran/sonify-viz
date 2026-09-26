"""Visual QA for a pilot render: data lanes vs. per-stem loudness over time.
Lets me (and GW) SEE whether each layer speaks when its data says it should.
usage: python pilot_check_plot.py granby_wy2024"""
import json, sys, glob
from pathlib import Path
import numpy as np, soundfile as sf
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
name = sys.argv[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dsp_core import ROOT, HEAVY_OUT
P = ROOT / "rendered" / "pilots"
FIGS = ROOT / "figs"
FIGS.mkdir(exist_ok=True)
with open(P / f"{name}_score.json") as fh:
    sc = json.load(fh)
days = sc["days"]; t = np.array([d["t"] for d in days])
keys = [k for k in days[0] if k not in ("date", "t") and isinstance(days[0][k], (int, float, bool))]
HEAVY = HEAVY_OUT / "pilots"
stems = sorted(glob.glob(str(HEAVY / f"{name}_stems" / "*.flac")))
fig, ax = plt.subplots(len(keys) + len(stems), 1, figsize=(13, 0.62 * (len(keys) + len(stems))), sharex=True)
for a, k in zip(ax, keys):
    v = np.array([np.nan if d[k] is None else float(d[k]) for d in days])
    a.fill_between(t, v, color="#4a7a96", lw=0); a.set_ylabel(k, rotation=0, ha="right", fontsize=7); a.set_yticks([])
for a, f in zip(ax[len(keys):], stems):
    x, sr = sf.read(f); m = x.mean(1); blk = sr // 4
    r = np.sqrt(np.array([(m[i:i + blk] ** 2).mean() for i in range(0, len(m) - blk, blk)]) + 1e-12)
    db = np.clip(20 * np.log10(r * 4) + 70, 0, None)
    a.fill_between(np.arange(len(db)) * 0.25, db, color="#b0603a", lw=0)
    a.set_ylabel("♪ " + Path(f).stem, rotation=0, ha="right", fontsize=7); a.set_yticks([])
for e_t, e in sc["events"]:
    if not e.startswith(("Mode", "Phase", "Lake phase")):
        for a in ax: a.axvline(e_t, color="k", lw=0.3, alpha=0.3)
ax[-1].set_xlabel("seconds"); plt.tight_layout(h_pad=0.1)
plt.savefig(FIGS / f"{name}_check.png", dpi=80)
