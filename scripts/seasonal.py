"""
Shared engine for the water-year pilots (2026-09-24): data -> daily features
-> a bar grid -> harmony. The two pilot scripts (pilot_granby_wy2024.py,
pilot_okanagan_wy2024.py) decide WHAT each layer means; this file holds the
parts they share.

Time model: one water year (Oct 1 - Sep 30) = 366 days. One BAR = 3 DAYS, so
the year is 122 bars. At 64-72 bpm that is ~7 minutes. The bar is the unit a
listener feels; the day is the unit the data comes in.

Music-theory model (written up for GW in the listening guide):
  MODES ordered dark -> bright. Neighbours differ by exactly ONE note, so
  sliding one step along this ladder is the smallest possible change of mood.
  The season sets a base brightness (day length); the anomaly vs. that day's
  15-year normal nudges it one step darker (drought/low) or brighter (high).
"""
import csv, io, json, datetime as dt
from functools import lru_cache
from pathlib import Path

import numpy as np

from dsp_core import day_length_hours, HEAVY_OUT  # noqa: F401  (HEAVY_OUT: used by the pilots as W.HEAVY_OUT)

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
SR = 44100

WY_START = dt.date(2023, 10, 1)
N_DAYS = 366
DAYS = [WY_START + dt.timedelta(i) for i in range(N_DAYS)]
DAYS_PER_BAR = 3
N_BARS = N_DAYS // DAYS_PER_BAR  # 122

# ------------------------------------------------------------------ data ---

@lru_cache(maxsize=None)
def _load(fname):
    """Parse a cached pull once per run (the climate file is read for four variables)."""
    with open(DATA / fname) as fh:
        return json.load(fh)


def wsc_series(fname, key="DISCHARGE", years=range(2010, 2025)):
    """dict date->value for a cached ECCC hydrometric pull."""
    out, sym = {}, {}
    for f in _load(fname):
        p = f["properties"]
        if p.get(key) is not None:
            out[p["DATE"][:10]] = float(p[key])
        sym[p["DATE"][:10]] = p.get(key + "_SYMBOL_EN")
    return out, sym


def climate_series(fname, key):
    out = {}
    for f in _load(fname):
        p = f["properties"]
        if p.get(key) is not None:
            out[p["LOCAL_DATE"][:10]] = float(p[key])
    return out


def wy(series, fill="interp"):
    """Pull the pilot water year out of a date->value dict as an array."""
    x = np.array([series.get(str(d), np.nan) for d in DAYS], dtype=float)
    if fill == "interp" and np.isnan(x).any():
        ok = ~np.isnan(x)
        if ok.sum() == 0:
            return np.zeros(N_DAYS)
        x = np.interp(np.arange(N_DAYS), np.flatnonzero(ok), x[ok])
    elif fill == "zero":
        x = np.nan_to_num(x)
    return x


def doy_percentile(series, halfwin=7):
    """For each pilot day: where does this year's value sit among ALL years'
    values within +-halfwin days of the same calendar day? 0..1. This is the
    'is it normal for the time of year' signal - the anomaly, not the level."""
    by_doy = {}
    for k, v in series.items():
        d = dt.date.fromisoformat(k)
        by_doy.setdefault(d.timetuple().tm_yday, []).append(v)
    out = np.full(N_DAYS, 0.5)
    for i, d in enumerate(DAYS):
        v = series.get(str(d))
        if v is None:
            continue
        doy = d.timetuple().tm_yday
        pool = []
        for o in range(-halfwin, halfwin + 1):
            pool += by_doy.get((doy - 1 + o) % 366 + 1, [])
        pool = np.array(pool)
        out[i] = (pool < v).mean() + 0.5 * (pool == v).mean()
    return out


def doy_index(doy):
    """Index into DAYS of a calendar day-of-year (1-366) falling in the pilot
    water year: Oct-Dec days belong to its first calendar year, Jan-Sep to its second."""
    y = WY_START.year if doy >= WY_START.timetuple().tm_yday else WY_START.year + 1
    return (dt.date(y, 1, 1) + dt.timedelta(doy - 1) - WY_START).days


def norm01(x, lo_pct=2, hi_pct=98):
    lo, hi = np.percentile(x, lo_pct), np.percentile(x, hi_pct)
    return np.clip((x - lo) / (hi - lo + 1e-12), 0, 1)


def smooth(x, win):
    k = np.ones(win) / win
    xp = np.concatenate([np.full(win, x[0]), x, np.full(win, x[-1])])
    return np.convolve(xp, k, mode="same")[win:-win]


def daylength(lat):
    return np.array([day_length_hours(d.timetuple().tm_yday, lat) for d in DAYS])


def modis_gpp_daily(name):
    """MODIS MOD17A2HGF 8-day GPP at a point -> daily array for the pilot
    year, plus a 0..1 version scaled by the 2015-2024 95th percentile.
    Returns (None, None) if the pull isn't cached (caller falls back to a
    growing-degree-day model and says so)."""
    p = DATA / f"modis_gpp_{name}_2015_2024.json"
    if not p.exists():
        return None, None
    with open(p) as fh:
        rows = json.load(fh)["rows"]
    dates, vals = [], []
    for r in rows:
        v = [x for x in r["data"] if x < 32761]
        if v:
            dates.append(dt.date.fromisoformat(r["date"]) + dt.timedelta(4))  # composite centre
            vals.append(np.mean(v) * 0.0001 / 8 * 1000)  # g C m-2 day-1
    t = np.array([(d - WY_START).days for d in dates])
    v = np.array(vals)
    daily = np.interp(np.arange(N_DAYS), t, v)
    return daily, np.clip(daily / np.percentile(v, 95), 0, 1)


def growing_degree_days(tmean, base=5.0):
    return np.cumsum(np.maximum(0, tmean - base))


def dart_sockeye(years=(2023, 2024)):
    """Wells Dam daily adult sockeye + Wells water temperature (C) for the
    pilot water year. Counting season is May-Nov; off-season days = 0 / NaN."""
    raw = _load("wells_dam_sockeye_2015_2024.json")
    cnt, temp = {}, {}
    for y in years:
        for r in csv.DictReader(io.StringIO(raw[str(y)])):
            d = r.get("Date") or ""
            if not d.startswith(str(y)):
                continue
            cnt[d] = max(0.0, float(r["Sock"] or 0))
            if r["TempC"]:
                temp[d] = float(r["TempC"])
    return wy(cnt, fill="zero"), np.array([temp.get(str(d), np.nan) for d in DAYS])


# ---------------------------------------------------------------- theory ---

MODES = [  # dark -> bright; each differs from its neighbour by one note
    ("Phrygian",   [0, 1, 3, 5, 7, 8, 10]),
    ("Aeolian",    [0, 2, 3, 5, 7, 8, 10]),
    ("Dorian",     [0, 2, 3, 5, 7, 9, 10]),
    ("Mixolydian", [0, 2, 4, 5, 7, 9, 10]),
    ("Ionian",     [0, 2, 4, 5, 7, 9, 11]),
    ("Lydian",     [0, 2, 4, 6, 7, 9, 11]),
]


def degree_to_midi(deg, mode_idx, tonic):
    steps = MODES[mode_idx][1]
    o, d = divmod(deg, 7)
    return tonic + 12 * o + steps[d]


def chord(deg, mode_idx, tonic, extensions=(0, 2, 4, 8)):
    """Stack thirds on scale degree `deg`: 0,2,4 = triad; 6 = 7th; 8 = 9th.
    Default is an add9 (no 7th) - the open, 'cinematic' colour.

    Two consonance guards (the chime clashes in track 04 were this class of
    problem):
      - a DIMINISHED triad (root-to-5th = 6 semitones) is swapped for the
        chord a third below, which contains the same upper notes plus a
        stable root (Bdim -> G, the textbook substitution);
      - a 9th that lands a half step above the root (b9) is swapped for the
        7th, which is colour rather than clash."""
    if (degree_to_midi(deg + 4, mode_idx, tonic) - degree_to_midi(deg, mode_idx, tonic)) % 12 == 6:
        deg -= 2
    root = degree_to_midi(deg, mode_idx, tonic)
    out = []
    for e in extensions:
        m = degree_to_midi(deg + e, mode_idx, tonic)
        if e == 8 and (m - root) % 12 == 1:
            m = degree_to_midi(deg + 6, mode_idx, tonic)
        out.append(m)
    return out


def voice_lead(prev, target_pcs, lo, hi):
    """Place each target pitch-class in [lo,hi] as close as possible to the
    previous voicing, so the hands move as little as possible between chords
    (the single biggest reason chord changes sound smooth rather than jumpy)."""
    out = []
    for i, pc in enumerate(target_pcs):
        ref = prev[i] if prev and i < len(prev) else (lo + hi) // 2
        cands = [m for m in range(lo, hi + 1) if m % 12 == pc % 12]
        out.append(min(cands, key=lambda m: abs(m - ref)))
    return sorted(out)


def mode_track(season_bright, anomaly, lo=1, hi=5, phrase=8, max_step=1, floor=1, ceil=5):
    """Per-bar mode index. season_bright/anomaly are per-bar 0..1 / -0.5..0.5.
    Changes only at phrase boundaries (every `phrase` bars) and by at most one
    step, so the listener hears a slow drift, never a lurch. `floor`=1 keeps
    Phrygian (whose b2 sits a half step above the tonic) out by default."""
    target = lo + season_bright * (hi - lo) + np.clip(anomaly * 2.4, -1.2, 1.2)
    out = np.zeros(len(target), dtype=int)
    cur = int(np.clip(round(target[0]), floor, ceil))
    for b in range(len(target)):
        if b % phrase == 0:
            t = int(round(np.mean(target[b:b + phrase])))
            cur += int(np.clip(t - cur, -max_step, max_step))
            cur = int(np.clip(cur, floor, ceil))
        out[b] = cur
    return out


# ------------------------------------------------------------------ grid ---

class Grid:
    def __init__(self, bpm, n_bars=N_BARS, beats_per_bar=4, tail_s=10.0):
        self.bpm = bpm
        self.beat = 60.0 / bpm
        self.bar = self.beat * beats_per_bar
        self.n_bars = n_bars
        self.dur = n_bars * self.bar + tail_s
        self.n = int(self.dur * SR)

    def t(self, bar, beat=0.0):
        return (bar + beat / 4.0) * self.bar

    def s(self, bar, beat=0.0, jitter_ms=0.0, rng=None):
        j = (rng.normal(0, jitter_ms) / 1000.0) if (rng is not None and jitter_ms) else 0.0
        return max(0, int((self.t(bar, beat) + j) * SR))

    def day_to_time(self, day_float):
        return day_float / DAYS_PER_BAR * self.bar


def per_bar(x, how="mean"):
    x = np.asarray(x)[: N_BARS * DAYS_PER_BAR].reshape(N_BARS, DAYS_PER_BAR)
    return getattr(x, how)(axis=1)


def events_from_flag(flag, min_gap=3):
    """Onset/offset day indices of runs in a boolean daily flag, merging gaps
    shorter than `min_gap` days (so one mild afternoon doesn't 'break up' the
    ice and re-freeze it the next day)."""
    f = flag.astype(bool).copy()
    idx = np.flatnonzero(f)
    for a, b in zip(idx[:-1], idx[1:]):
        if 1 < b - a <= min_gap:
            f[a:b] = True
    on = np.flatnonzero(f & ~np.r_[False, f[:-1]])
    off = np.flatnonzero(f & ~np.r_[f[1:], False])
    return list(zip(on, off)), f


def sustain(ins, midi, vel, dur, rng, seg=4.5, xf=1.2, release=1.5):
    """Hold a sampled note longer than its recording by re-articulating
    overlapping takes with crossfades (string sections do exactly this in
    real life - players change bow at different times)."""
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


def fmt_time(sec):
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def phase_bars(phase_day, min_run=6):
    """Daily phase labels -> one label per bar (majority vote), then any run
    shorter than `min_run` bars is absorbed into the run before it, so the
    progression doesn't flip back and forth on a two-day wobble."""
    raw = []
    for b in range(N_BARS):
        v, c = np.unique(phase_day[b * DAYS_PER_BAR:(b + 1) * DAYS_PER_BAR], return_counts=True)
        raw.append(v[np.argmax(c)])
    runs, i = [], 0
    while i < N_BARS:
        j = i
        while j < N_BARS and raw[j] == raw[i]:
            j += 1
        runs.append([raw[i], i, j])
        i = j
    merged = []
    for r in runs:
        if merged and (r[2] - r[1] < min_run or merged[-1][0] == r[0]):
            merged[-1][2] = r[2]
        else:
            merged.append(r)
    return [ph for ph, a, z in merged for _ in range(a, z)]


def chord_track(bar_phase, prog, bars_per_chord):
    """Walk each phase's chord loop; a new phase restarts its loop at the top."""
    chords, pos, cur = [], 0, None
    for b, ph in enumerate(bar_phase):
        if b % bars_per_chord == 0:
            if ph != cur:
                cur, pos = ph, 0
            else:
                pos = (pos + 1) % len(prog[cur])
        chords.append(prog[cur][pos])
    return chords


def fire_bars(intensity_bar, rate, phase=0.5):
    """Integrate-and-fire: accumulate intensity*rate per bar and fire a motif
    each time the total crosses 1. Deterministic, so a sparse layer always
    speaks in proportion to its data (random per-bar gating left the Granby
    whitefish layer completely silent on one 2026-09-24 render: ~5% odds
    over its short window)."""
    acc, out = phase, []
    for b, v in enumerate(intensity_bar):
        acc += v * rate
        if acc >= 1:
            out.append(b)
            acc -= 1
    return set(out)
