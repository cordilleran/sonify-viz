"""
Sample-based instruments, mixing buses, and convolution reverb for the
seasonal pilots (2026-09-24). Replaces "synthesize every sound from sine
waves" with recorded acoustic instruments (VSCO 2 CE, CC0) + real bird
recordings (Commons, CC BY-SA). See samples_manifest.csv.

Pieces:
  Instrument   - folder of pitched samples -> note(midi, vel, dur)
  OneShots     - folder of unpitched hits  -> hit(name_prefix, vel)
  Bus          - stereo track with gain/EQ/pan and a reverb send
  make_ir      - synthetic stereo impulse response (room/hall), bright/dark
  master       - sum buses, apply reverb returns, gentle glue compression
"""
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, fftconvolve

from dsp_core import SR, SAMPLES  # SAMPLES: repo samples/ unless SONIFICATION_SAMPLES is set
VSCO = SAMPLES / "vsco2ce"
NOTE_IDX = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6,
            "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}


def name_to_midi(name, octave_offset=0):
    m = re.search(r"(?<![A-Za-z])([A-G][#b]?)(-?\d)(?!\d)", name)
    if not m:
        return None
    return 12 * (int(m.group(2)) + 1 + octave_offset) + NOTE_IDX[m.group(1)]


@lru_cache(maxsize=None)
def load(path):
    x, sr = sf.read(str(path), always_2d=True, dtype="float32")
    if sr != SR:
        raise ValueError(f"{path}: sr {sr}")
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    return x[:, :2]


def estimate_f0(x, sr=SR, fmin=25, fmax=2000):
    """Autocorrelation f0 over the loudest 0.4 s of the sample (after attack)."""
    m = x.mean(axis=1)
    start = int(0.15 * sr)
    seg = m[start:start + int(0.4 * sr)]
    seg = seg - seg.mean()
    ac = fftconvolve(seg, seg[::-1])[len(seg) - 1:]
    lo, hi = int(sr / fmax), int(sr / fmin)
    neg = np.flatnonzero(ac[:hi] < 0)          # skip the zero-lag lobe: for low notes it otherwise
    lo = max(lo, int(neg[0])) if len(neg) else lo  # wins (a 55 Hz tone read as 2 kHz; test_sound.py)
    lag = lo + np.argmax(ac[lo:hi])
    return sr / lag


class Instrument:
    """Pitched sampled instrument. Picks the nearest recorded note (and the
    dynamic layer nearest `vel`), then repitches by resampling. Resampling
    also shortens/lengthens the note - fine for shifts of +-2-3 semitones,
    which is all a well-sampled set needs."""

    def __init__(self, folder, glob="*.wav", octave_offset=0, mapping=None, dyn_regex=r"_v(\d)",
                 gain=1.0, attack_trim=0.0):
        self.folder = VSCO / folder if not Path(folder).is_absolute() else Path(folder)
        self.gain = gain
        self.attack_trim = attack_trim
        self.zones = []  # (midi, dyn, path)
        for p in sorted(self.folder.glob(glob)):
            if mapping:
                midi, dyn = mapping(p.name)
            else:
                midi = name_to_midi(p.stem, octave_offset)
                d = re.search(dyn_regex, p.stem)
                dyn = int(d.group(1)) if d else 1
            if midi is not None:
                self.zones.append((midi, dyn, p))
        if not self.zones:
            raise FileNotFoundError(self.folder)
        self.dyns = sorted({z[1] for z in self.zones})

    def _pick(self, midi, vel, rng):
        want_dyn = self.dyns[min(len(self.dyns) - 1, int(vel * len(self.dyns)))]
        cands = [z for z in self.zones if z[1] == want_dyn] or self.zones
        best = min(abs(z[0] - midi) for z in cands)
        pool = [z for z in cands if abs(z[0] - midi) == best]
        return pool[rng.integers(len(pool))] if rng is not None else pool[0]

    def note(self, midi, vel=0.7, dur=None, release=0.6, rng=None):
        src_midi, _, path = self._pick(midi, vel, rng)
        x = load(path)
        if self.attack_trim:
            x = x[int(self.attack_trim * SR):]
        ratio = 2 ** ((midi - src_midi) / 12.0)
        if dur is not None:  # don't resample audio we're about to cut off
            x = x[: int((dur + release) * SR * ratio) + 2]
        if abs(ratio - 1) > 1e-4:
            n_out = int(len(x) / ratio)
            idx = np.arange(n_out) * ratio
            x = np.stack([np.interp(idx, np.arange(len(x)), x[:, c]) for c in range(2)], axis=1)
        if dur is not None:
            n = int((dur + release) * SR)
            x = x[:n].copy()
            r = int(release * SR)
            if len(x) > r:
                x[-r:] *= np.linspace(1, 0, r)[:, None] ** 2
        # velocity -> level (dynamic layers already carry the timbre change)
        return x * (0.35 + 0.65 * vel) * self.gain


class OneShots:
    def __init__(self, folder=VSCO / "Percussion", glob="*.wav"):
        self.files = sorted(Path(folder).glob(glob))

    def hit(self, prefix, vel=0.7, rng=None):
        pool = [f for f in self.files if f.name.startswith(prefix)]
        if not pool:
            raise FileNotFoundError(prefix)
        p = pool[rng.integers(len(pool))] if rng is not None else pool[0]
        return load(p) * vel


# ---------------------------------------------------------------- birds ----
@lru_cache(maxsize=None)
def bird_phrases(name, min_len=0.6, max_len=4.0, top=12):
    """Decode a Commons bird recording, high-pass it (drop wind/traffic rumble),
    and cut it into its loudest song phrases. Returns a list of stereo arrays."""
    src = next((SAMPLES / "birds").glob(name + ".*"))
    wav = SAMPLES / "birds" / "_decoded" / (name + ".wav")
    wav.parent.mkdir(exist_ok=True)
    if not wav.exists():
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-ar", str(SR), "-ac", "2", str(wav)],
                       check=True)
    x = load(wav)
    x = sosfilt(butter(4, 900, "highpass", fs=SR, output="sos"), x, axis=0)
    env = np.convolve(np.abs(x.mean(axis=1)), np.ones(2205) / 2205, mode="same")
    thr = np.percentile(env, 80)
    on = env > thr
    # merge gaps < 0.25 s
    phrases, i, n = [], 0, len(on)
    while i < n:
        if on[i]:
            j = i
            gap = 0
            while j < n and gap < int(0.25 * SR):
                gap = 0 if on[j] else gap + 1
                j += 1
            a, b = max(0, i - int(0.08 * SR)), min(n, j)
            if (b - a) / SR >= min_len:
                seg = x[a:a + int(max_len * SR)].copy()
                f = min(len(seg) // 4, int(0.05 * SR))
                seg[:f] *= np.linspace(0, 1, f)[:, None]
                seg[-f:] *= np.linspace(1, 0, f)[:, None]
                phrases.append((env[a:b].mean(), seg))
            i = j
        else:
            i += 1
    phrases.sort(key=lambda t: -t[0])
    out = [p / (np.abs(p).max() + 1e-9) for _, p in phrases[:top]]
    if not out:
        raise ValueError(f"no phrases found in {name}")
    return out


# ---------------------------------------------------------------- buses ----
def eq(x, hp=None, lp=None):
    if hp:
        x = sosfilt(butter(2, hp, "highpass", fs=SR, output="sos"), x, axis=0)
    if lp:
        x = sosfilt(butter(2, lp, "lowpass", fs=SR, output="sos"), x, axis=0)
    return x


def pan_stereo(x, pan):
    """pan -1..1, equal-power. x is (n,2)."""
    a = (pan + 1) * np.pi / 4
    return x * np.array([np.cos(a), np.sin(a)]) * np.sqrt(2)


class Bus:
    def __init__(self, name, n, gain=1.0, hp=None, lp=None, send=0.0, ir="hall"):
        self.name, self.gain, self.hp, self.lp, self.send, self.ir = name, gain, hp, lp, send, ir
        self.buf = np.zeros((n, 2), dtype=np.float32)

    def add(self, x, at, gain=1.0, pan=0.0):
        at = int(at)
        if at >= len(self.buf) or at < 0:
            return
        x = x[: len(self.buf) - at]
        if pan:
            x = pan_stereo(x, pan)
        self.buf[at:at + len(x)] += x * gain

    def processed(self):
        return eq(self.buf, self.hp, self.lp) * self.gain


def make_ir(seconds=3.2, bright=0.5, predelay=0.02, seed=7):
    """Synthetic stereo hall IR: decorrelated noise per channel with a
    frequency-dependent decay (highs die ~3x faster than lows, as in a real
    room), plus a handful of early reflections. `bright` 0..1 sets the
    high-band share - 'snow on the ground' uses a dark, short one."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = np.zeros((n, 2))
    bands = [(None, 400, 1.0), (400, 2500, 0.7), (2500, None, 0.35)]
    for lo, hi, life in bands:
        for c in range(2):
            b = rng.standard_normal(n)
            b = eq(b[:, None], hp=lo, lp=hi)[:, 0]
            t60 = seconds * life * (1.0 if lo is None else (0.5 + 0.5 * bright))
            w = 1.0 if lo is None else (0.4 + 0.8 * bright) * (0.7 if hi is None else 1.0)
            ir[:, c] += b * np.exp(-6.9 * t / t60) * w
    for k in range(8):
        d = int((predelay + rng.uniform(0.005, 0.07)) * SR)
        ir[d, rng.integers(2)] += rng.uniform(0.3, 0.8) * (-1) ** k
    pd = int(predelay * SR)
    ir = np.concatenate([np.zeros((pd, 2)), ir])[:n]
    fade = np.linspace(1, 0, int(0.2 * SR)) ** 2
    ir[-len(fade):] *= fade[:, None]
    return ir / np.sqrt((ir ** 2).sum(axis=0).mean())


def convolve_reverb(x, ir):
    return np.stack([fftconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)], axis=1)


def glue(x, thresh_db=-14, ratio=2.0, attack=0.02, release=0.3):
    """Very gentle RMS bus compressor, block-based, so the whole mix breathes
    together without any one layer punching through."""
    blk = 1024
    n = len(x)
    rms = np.sqrt(np.convolve((x ** 2).mean(axis=1), np.ones(blk) / blk, mode="same") + 1e-12)
    db = 20 * np.log10(rms)
    over = np.maximum(0, db - thresh_db)
    gr_db = -over * (1 - 1 / ratio)
    # smooth gain reduction (attack/release one-pole)
    g = np.empty(n)
    a_c, r_c = np.exp(-1 / (attack * SR)), np.exp(-1 / (release * SR))
    cur = 0.0
    for i in range(0, n, 64):  # control-rate smoothing, 64-sample hops
        tgt = gr_db[i]
        c = a_c if tgt < cur else r_c
        cur = c * cur + (1 - c) * tgt
        g[i:i + 64] = cur
    return x * (10 ** (g / 20))[:, None]


def master(buses, irs, out_wav, stems_dir=None, ir_env=None, wet_gain=0.35):
    """ir_env: optional {ir_name: per-sample 0..1 envelope}. Every bus send
    goes to EVERY reverb, and the envelopes crossfade between them - e.g.
    'open' hall vs 'snow' (dark, short) following snow on the ground."""
    n = len(buses[0].buf)
    dry = np.zeros((n, 2))
    send_sum = np.zeros((n, 2))
    stems = {}
    for b in buses:
        y = b.processed()
        dry += y
        send_sum += y * b.send
        stems[b.name] = y
        if stems_dir:
            Path(stems_dir).mkdir(parents=True, exist_ok=True)
            sf.write(Path(stems_dir) / f"{b.name}.flac", (y / 4).astype(np.float32), SR)
    send_sum = eq(send_sum, hp=180)
    wet = np.zeros((n, 2))
    for k, ir in irs.items():
        env = ir_env[k][:, None] if ir_env else 1.0 / len(irs)
        wet += convolve_reverb(send_sum, ir) * env * wet_gain
    mix = glue(dry + wet)
    mix = mix / (np.abs(mix).max() + 1e-9) * 0.89
    f = int(3 * SR)
    mix[:f] *= np.linspace(0, 1, f)[:, None]
    mix[-int(6 * SR):] *= np.linspace(1, 0, int(6 * SR))[:, None] ** 1.5
    sf.write(out_wav, mix.astype(np.float32), SR)
    return mix, stems


def to_mp3(wav, mp3):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-ar", "44100", "-b:a", "192k", str(mp3)], check=True)


def vsco_kit():
    """The pilot instrument set. octave_offset=1 where VSCO names notes with
    C3 = middle C (verified 2026-09-24 by autocorrelation f0 against the
    filename: cello, violins, contrabass, flute, marimba, glock read exactly
    12 semitones high vs. their labels; piano + harp matched as-is)."""
    import re as _re
    piano_map = lambda n: (21 + 2 * int(_re.search(r"_(\d+)\.wav$", n).group(1)),
                           int(_re.search(r"dyn(\d)", n).group(1)))
    return {
        "piano": Instrument("Keys/Upright Piano", gain=0.9, mapping=piano_map),
        "bass": Instrument("Strings/Solo Contrabass/SusNV", octave_offset=1),
        "bpizz": Instrument("Strings/Solo Contrabass/Pizz", octave_offset=1),
        "cello": Instrument("Strings/Cello Section/susvib", octave_offset=1),
        "cpizz": Instrument("Strings/Cello Section/pizzT", octave_offset=1),
        "vln": Instrument("Strings/Violin Section/susVib", octave_offset=1),
        "vpizz": Instrument("Strings/Violin Section/Pizz", octave_offset=1),
        "flute": Instrument("Woodwinds/Flute/susNV", octave_offset=1),
        "harp": Instrument("Strings/Harp"),
        "glock": Instrument("Percussion/Glock", octave_offset=1),
        "marimba": Instrument("Percussion/Marimba", octave_offset=1),
        "perc": OneShots(),
    }


def sustain(ins, midi, vel, dur, rng, seg=4.5, xf=1.2, release=1.5):
    """Hold a sampled note longer than its recording by re-articulating
    overlapping takes with crossfades (string sections do exactly this in
    real life - players change bow at different times). Moved here from
    seasonal.py on 2026-09-27."""
    n = int((dur + release) * SR)
    out = np.zeros((n, 2), dtype=np.float32)
    t = 0.0
    first = True
    while t < dur:
        piece = ins.note(midi, vel, dur=min(seg, dur - t) + xf, release=xf, rng=rng)
        if not first:
            f = min(len(piece), int(xf * SR))
            piece = piece.copy()
            # skip the new take's bow attack and fade it in under the old one
            piece[:f] *= np.linspace(0, 1, f)[:, None]
        a = int(t * SR)
        piece = piece[: n - a]
        out[a:a + len(piece)] += piece
        t += seg
        first = False
    r = int(release * SR)
    out[-r:] *= np.linspace(1, 0, r)[:, None] ** 2
    return out
