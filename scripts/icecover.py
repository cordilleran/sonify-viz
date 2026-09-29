"""
SUPERIOR ICE YEAR (2026-09-28). Spec: 260928-icecover-superior-spec.md. Data: fetch_icecover.py.

    python icecover.py                    # 1 Nov 2025 - 15 Jun 2026, 1.5 s per day (~5.7 min)
    python icecover.py --variant long     # 3 s per day (~11.4 min), also cut into four movements
    python icecover.py --set layers=[ice,water]

Lake Superior is cut into eight regions (Voronoi wedges round eight anchor points). Each region is a voice:
its pitch reads the map from west (low) to east (high) on the D major pentatonic, its pan follows longitude,
and the chord that is sounding at any moment is the ice pattern on the map. One ice season plays at
`day_s` seconds per day.

LAYER    DATA                                                  SOUND                                        REGISTER
ice      region ice concentration (R)                          bowed-glass tone, louder as the ice thickens D5-F#6, one note a region
events   3-day-smoothed daily change in region ice (D)        freeze: a brief glass ping and tick; breakup: ping at the region's ice note+12;
                                                               a low sub drop with a crack                  drop D2-F#3
water    region surface temperature (R)                        four low cello/bass voices (a pair of regions D2-F#3
                                                               each), fuller as it warms, lidded by ice
turnover lake-mean surface temperature crossing 4 C (D)       one soft sub drop, on the crossing day       D2
air      lake-mean daily air temperature (R, ERA5)             organ bed, registration follows warmth       A3 D4 A4
sun      day length at 47.6 N (D); shortwave radiation (R)     synthesized choir, opens oo to ah            B3 F#4
wind     lake-wide peak wind of the eight regions (R)          one filtered-noise bed, gale gated, panned    noise <1.4 kHz
                                                               toward the windiest region
snow     region snowfall (R)                                   sparse dry high ticks, unpitched             noise 3-8 kHz
rain     region liquid precipitation (D)                       soft harp drops                              D3-F#4
birds    S: timing from ice-off and warmth (D)                 Common Loon and Canada Goose recordings      samples
ghost    2008-2025 median lake-wide ice (D), optional          a quiet detuned glass tone                   A6
"""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sampler as S
from sampler import Bus, Instrument, make_ir, SR
import dsp_core as W
import solar
import synth as Y
import variants as V

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "icecover"
CTRL = 200  # control rate (Hz) for the envelopes, interpolated to audio

DEFAULTS = {
    "year": "cy2025",          # only its label is used; the data's own window (superior_daily.json) sets the days
    "day_s": 1.5,              # seconds per day
    "layers": ["ice", "events", "water", "air", "sun", "wind", "snow", "rain", "birds"],
    "ice_pitch": [74, 76, 78, 81, 83, 86, 88, 90],      # D5 E5 F#5 A5 B5 D6 E6 F#6, west to east
    "water_pitch": [38, 45, 50, 54],                    # D2 A2 D3 F#3: four voices, west to east, two regions each
    "drop_pitch": [38, 40, 42, 45, 47, 50, 52, 54],     # breakup drops, one per region: D2 E2 F#2 A2 B2 D3 E3 F#3
    "turnover_c": 4.0,
    "rain_pitch": [50, 52, 54, 57, 59, 62, 64, 66],     # the region's own pitch class, two octaves under the ice
    "organ_pitch": [57, 62, 69],
    "choir_pitch": [59, 66],
    "ghost_pitch": 93,
    "up_pp": 4.0, "down_pp": 4.0, "smooth_days": 3, "gap_days": 3,   # freeze and breakup event rules
    "glass_gate": [2.0, 8.0],  # a region's glass is silent below 2 % ice, full from 8 %
    "water_range": [0.0, 12.0], "air_range": [-20.0, 10.0],
    "gains": {}, "mute": [],
    "movements": False,
    "seed": 2026,
    # v1.0 options (2026-09-28, each chosen by ear from A/B pairs; the `v1` variant turns them on). The defaults
    # reproduce v0.2 byte for byte, so its locked renders still verify.
    "crackle": "v02",          # v02 | a: pan jitter, width by distance | c: a + distance gain 1/(r+eps)^q, a short delay and early reflections
    "stagger": False,          # same-day events at least 80 ms apart, at most 4 a day
    "tilt_db": 0.0,            # trim per step up the west-to-east pitch map (ice glass and pings), e.g. -0.5
    "coda": "none",            # none | a: ghost holds a low floor after the data, long fade | c: a + other layers thin, end-of-data pulse
    "drone": False,            # deep water near 4 C under the ice: a constant low hum (D), left alone at the end
    "tail_s": 7.0,             # seconds after the last day
    # v0.2 bug, found 2026-09-28: the ghost's phase summed in float32, so its pitch stepped (1792, 1536, then 2048 Hz
    # instead of A6 = 1760 Hz) and froze to silence after ~350 s. True sums in float64. False only to reproduce v0.2.
    "ghost_phase64": False,
}

LAYER_BUSES = {   # bus -> settings; a layer may feed several buses
    "ice":   dict(gain=0.9, hp=350, send=0.7),
    "pings": dict(gain=0.75, hp=500, send=0.85),
    "drops": dict(gain=0.4, hp=30, send=0.6),
    "water": dict(gain=1.6, hp=35, send=0.5),
    "turnover": dict(gain=0.65, hp=30, send=0.5),
    "organ": dict(gain=0.6, hp=60, send=0.45),
    "choir": dict(gain=0.4, hp=120, send=0.6),
    "wind":  dict(gain=0.4, hp=150, send=0.3),
    "snow":  dict(gain=0.8, hp=500, send=0.7),
    "rain":  dict(gain=1.7, hp=200, send=0.6),
    "birds": dict(gain=0.3, hp=300, send=0.55),
    "birds_far": dict(gain=0.3, hp=300, send=0.95),   # distant calls: darker, quieter, mostly reverb
    "ghost": dict(gain=0.3, hp=500, send=0.7),
    "pings_far": dict(gain=0.75, hp=500, send=1.0),  # crackle (c): the wet share of distant events
    "drops_far": dict(gain=0.4, hp=30, send=1.0),
    "marker": dict(gain=0.5, hp=30, send=0.6),        # coda (c): the end-of-data pulse
    "deep": dict(gain=0.5, hp=30, send=0.4),          # drone: deep water near 4 C
}
LAYER_TO_BUS = {"ice": ["ice"], "events": ["pings", "drops"], "water": ["water", "turnover"], "air": ["organ"], "sun": ["choir"],
                "wind": ["wind"], "snow": ["snow"], "rain": ["rain"], "birds": ["birds", "birds_far"], "ghost": ["ghost", "marker"], "turnover": ["turnover"], "deep": ["deep"]}


# -------------------------------------------------------------------- data --
def load():
    """-> dict with dates, day arrays per region (None filled), region order west to east, lake series."""
    d = json.loads((DATA / "superior_daily.json").read_text())
    regs = json.loads((DATA / "superior_regions.json").read_text())
    order = sorted(regs, key=lambda r: r["centroid"][0])
    ids = [r["id"] for r in order]
    N = d["n"]

    def arr(v):
        a = np.array([np.nan if x is None else x for x in v], dtype=float)
        if np.isnan(a).all():
            return np.zeros(N)
        g = np.isnan(a)
        a[g] = np.interp(np.flatnonzero(g), np.flatnonzero(~g), a[~g])
        return a

    R = {i: {k: arr(v) for k, v in d["regions"][i].items()} for i in ids}
    lons = np.array([r["centroid"][0] for r in order])
    # half longitude, half rank: three regions sit near -88 degrees, and pure longitude would stack their pans
    pan = 0.5 * np.interp(lons, (lons.min(), lons.max()), (-0.7, 0.7)) + 0.5 * np.linspace(-0.7, 0.7, len(lons))
    return {"dates": d["dates"], "N": N, "ids": ids, "names": {r["id"]: r["name"] for r in order},
            "lon": dict(zip(ids, lons)), "lat": {r["id"]: r["centroid"][1] for r in order},
            "pan": dict(zip(ids, pan)), "R": R, "lake_ice": arr(d["lake_ice"]), "lake_sst": arr(d["lake_sst"]),
            "hist": {k: arr(v) for k, v in d["hist"].items()}, "cur_peak": d["cur_peak"],
            "cur_peak_day": d["cur_peak_day"], "start": dt.date.fromisoformat(d["dates"][0]),
            "source": d["source"]}


def smooth_days(x, w):
    if w <= 1:
        return np.asarray(x, dtype=float)
    k = np.ones(w) / w
    p = w // 2
    return np.convolve(np.pad(x, (p, w - 1 - p), mode="edge"), k, "valid")


def detect_events(ice, up=4.0, down=4.0, smooth=3, gap=3):
    """Freeze and breakup events from one region's daily ice series (percent).
    Change = day-to-day difference of the `smooth`-day mean. A freeze fires on a change >= `up`
    points, a breakup on a change <= -`down`; each kind has a refractory period of `gap` days.
    -> [(day index, +1 freeze / -1 breakup, size in points)], in time order."""
    s = smooth_days(np.asarray(ice, dtype=float), smooth)
    delta = np.diff(s, prepend=s[0])
    out, last = [], {1: -10 ** 6, -1: -10 ** 6}
    for d, x in enumerate(delta):
        kind = 1 if x >= up else -1 if x <= -down else 0
        if kind and d - last[kind] >= gap:
            out.append((d, kind, float(abs(x))))
            last[kind] = d
    return out


def movement_days(lake, cur_peak_day, dates):
    """Day indices of the three movement cuts: the first day lake ice holds above 10 %, the season peak,
    the last day above 2 % after the peak."""
    peak = dates.index(cur_peak_day)
    on = int(np.argmax(lake >= 10)) if (lake >= 10).any() else 0
    after = np.flatnonzero(lake[peak:] >= 2)
    off = int(peak + after[-1] + 1) if len(after) else peak + 1
    return [on, peak, off]


def ghost_carrier(f0, cents, phase64=False):
    """A sine at f0 detuned by a time-varying number of cents. The phase is the running sum of the frequency;
    f(t)*t would sweep the tone by t*f'(t), hundreds of hertz late in the piece. The sum must be float64 (and is
    wrapped per cycle): in float32 it loses the per-sample step within a minute (v0.2 bug, see DEFAULTS)."""
    if phase64:
        cyc = np.cumsum(f0 * 2 ** (np.asarray(cents, dtype=np.float64) / 1200) / SR)
        return np.sin(2 * np.pi * (cyc % 1.0)).astype(np.float32)
    return np.sin(2 * np.pi * np.cumsum(f0 * 2 ** (cents / 1200)) / SR)


def bird_days(ice, tmax, peak_day, dates):
    """Symbolic timing (S) derived from data: loons return the first day after the region's own ice peak
    that its ice is below 5 % and its daily high above 5 C; geese, the first day after 1 March that its high
    is above 0 C and its ice below 50 %. -> (loon day or None, goose day or None)."""
    loon = next((d for d in range(peak_day, len(ice)) if ice[d] < 5 and tmax[d] > 5), None)
    m1 = next((i for i, x in enumerate(dates) if x >= "2026-03-01"), 0)
    goose = next((d for d in range(m1, len(ice)) if tmax[d] > 0 and ice[d] < 50), None)
    return loon, goose


# ------------------------------------------------------------------- sound --
def to_audio(x, n):
    return np.interp(np.arange(n) / SR, np.arange(len(x)) / CTRL, x).astype(np.float32)


def warmth(x, lo, hi):
    return np.clip((np.asarray(x) - lo) / (hi - lo), 0, 1)


def lowpass(x, hz):
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(2, min(hz, SR * 0.45), "lowpass", fs=SR, output="sos"), x, axis=0).astype(np.float32)


# glass, sung_voice: copied from meridian.py so this piece's lock does not depend on that file
def glass(midi, n, level, rng):
    t = np.arange(n) / SR
    f = float(Y.midi_hz(midi))
    beat = rng.uniform(0.25, 0.6)
    x = (np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) + 0.6 * np.sin(2 * np.pi * (f + beat) * t)
         + 0.18 * np.sin(2 * np.pi * 2.756 * f * t + rng.uniform(0, 6.28)))
    k = np.cumsum(rng.standard_normal(int(n / SR * 2) + 2))
    k = (k - k.min()) / (np.ptp(k) + 1e-9)
    glint = 0.35 + 0.65 * np.interp(t, np.arange(len(k)) / 2, k) ** 2
    return (x / 2.2 * level * glint).astype(np.float32)


def sung_voice(midi, n, vowel, rng):
    t = np.arange(n) / SR
    f0 = float(Y.midi_hz(midi))
    src = np.zeros(n)
    for j in range(3):
        rate, depth, det = rng.uniform(4.6, 5.8), rng.uniform(0.003, 0.006), rng.uniform(-6, 6)
        f = f0 * 2 ** (det / 1200) * (1 + depth * np.sin(2 * np.pi * rate * t + rng.uniform(0, 6.28)))
        src += Y.osc("saw", f, n)
    src = src / 3 + 0.03 * rng.standard_normal(n)
    out = np.zeros(n)
    for vw, w in (("oo", 1 - vowel), ("ah", vowel)):
        y = np.zeros(n)
        for fc, g in zip(Y.VOWELS[vw], (1.0, 0.6, 0.25)):
            bw = 0.12 * fc + 60
            y += g * Y.bandpass(src, max(40, fc - bw), fc + bw, order=2)
        out += y * w
    return out.astype(np.float32)


def ping(midi, vel, rng, dur=1.2):
    """Freeze: a brief brittle glass ping (a sine plus the glass's inharmonic 2.756 partial, ~0.35 s decay)
    and a 30 ms filtered-noise tick."""
    t = np.arange(int(dur * SR)) / SR
    f = float(Y.midi_hz(midi))
    x = (np.sin(2 * np.pi * f * t) * np.exp(-t / 0.35) + 0.3 * np.sin(2 * np.pi * 2.756 * f * t) * np.exp(-t / 0.12))
    tick = Y.bandpass(rng.standard_normal(len(t)), 3000, 6500) * np.exp(-t / 0.012) * 0.18
    x[:48] *= np.linspace(0, 1, 48)
    return ((x + tick) * vel * 0.5).astype(np.float32)


def drop(midi, vel, rng, dur=2.2):
    """Breakup: a low sub drop (sine with a fast pitch fall) and a short band-limited crack."""
    t = np.arange(int(dur * SR)) / SR
    f = float(Y.midi_hz(midi))
    x = np.sin(2 * np.pi * (f * (1 + 0.6 * np.exp(-t / 0.06))) * t) * np.exp(-t / 0.55)
    crack = Y.bandpass(rng.standard_normal(len(t)), 400, 1400) * np.exp(-t / 0.08) * 0.2
    x[:48] *= np.linspace(0, 1, 48)
    return ((x + crack) * vel).astype(np.float32)


def distant(x, u):
    """An event heard at distance u (0 near .. 1 far): quieter and darker, the reverb send does the rest."""
    return (lowpass(x, 9000 - 7000 * u) * (1 - 0.55 * u)).astype(np.float32)


def early_reflections(x, u, rng):
    """Crackle (c): a distant event arrives late and diffuse. The direct sound is delayed up to 30 ms and a few
    darker reflections follow within 90 ms, more and louder with distance u. -> stereo (n, 2)."""
    pre = int(0.03 * u * SR)
    n = len(x) + pre + int(0.1 * SR)
    y = np.zeros((n, 2), dtype=np.float32)
    y[pre:pre + len(x)] += np.stack([x, x], axis=1)
    dark = lowpass(x, 4000 - 2500 * u)
    for _ in range(2 + int(4 * u)):
        k = pre + int(rng.uniform(0.012, 0.09) * SR)
        g = 0.5 * u * rng.uniform(0.4, 1.0)
        ch = rng.integers(2)
        y[k:k + len(x), ch] += dark * g
    return y


def flake(vel, rng, dur=0.12):
    """One snowflake: a dry, unpitched high tick."""
    t = np.arange(int(dur * SR)) / SR
    x = Y.bandpass(rng.standard_normal(len(t)), 3000, 8000) * np.exp(-t / 0.02)
    x[:24] *= np.linspace(0, 1, 24)
    return (x * vel * 0.4).astype(np.float32)


def smoothstep(x, lo, hi):
    u = np.clip((np.asarray(x, dtype=float) - lo) / (hi - lo), 0, 1)
    return u * u * (3 - 2 * u)


def pan_curve(x, a):
    """Mono x through a time-varying equal-power pan `a` (audio rate, -1..1) -> (n, 2)."""
    th = (np.asarray(a) + 1) * np.pi / 4
    return np.stack([x * np.cos(th), x * np.sin(th)], axis=1) * np.sqrt(2)


def strings_for(K, midi):
    return K["bass"] if midi < 45 else K["cello"] if midi < 60 else K["vln"]


def bus_rms_env(y, hz=8):
    """A stem's loudness at `hz`, in 0..1 of its own peak-ish level (the dashboard's meter)."""
    step = SR // hz
    m = y.shape[0] // step
    e = np.sqrt((y[:m * step].reshape(m, step, -1) ** 2).mean(axis=(1, 2)))
    return e


# -------------------------------------------------------------------- main --
def main():
    P, Y_, NAME, META = V.setup("icecover", DEFAULTS)
    NAME = NAME.replace(Y_.label.lower(), "sup2526")
    OUT, HEAVY = W.LIGHT_OUT / "icecover", W.HEAVY_OUT / "icecover"
    OUT.mkdir(parents=True, exist_ok=True)
    HEAVY.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(P["seed"])
    np.random.seed(P["seed"])
    print(f"seeds: {P['seed']}")

    D = load()
    N, ids, day_s = D["N"], D["ids"], float(P["day_s"])
    tail = float(P["tail_s"])
    dur = N * day_s
    n = int((dur + tail) * SR)
    L = set(P["layers"])
    print(f"{NAME}: {D['dates'][0]}..{D['dates'][-1]}, {N} days x {day_s} s = {dur / 60:.1f} min")

    tctl = np.arange(int((dur + tail) * CTRL)) / CTRL

    def cur(v):          # a daily series as a control-rate curve, linear between day centres
        return np.interp(tctl, (np.arange(N) + 0.5) * day_s, v)

    def aud(v):          # ... and at audio rate
        return to_audio(cur(v), n)

    def at(day, off=0.0):  # sample index of a day's start plus an offset in days
        return int((day + off) * day_s * SR)

    fade = np.minimum(1, np.minimum(np.arange(n) / (2 * SR), (n - np.arange(n)) / (5 * SR))).astype(np.float32)
    K = S.vsco_kit()
    organ = Instrument("Keys/Organ/Quiet", glob="NT5_Man3Quiet_*.wav",
                       mapping=lambda nm: (int(nm.split("_")[2]) - 86, 1))
    used = {b for l in L for b in LAYER_TO_BUS.get(l, [])}
    if P["crackle"] == "c" and "events" in L:
        used |= {"pings_far", "drops_far"}
    if P["coda"] != "c":
        used.discard("marker")
    if P["drone"]:
        used.add("deep")
    B = {k: Bus(k, n, **kw) for k, kw in V.bus_settings({k: v for k, v in LAYER_BUSES.items() if k in used}, P).items()}
    span = dur + 1.0
    lake = D["lake_ice"]
    R = D["R"]
    pan = D["pan"]
    tracks = {"ice": {}, "water": {}, "wind": {}}   # per-region loudness curves for the dashboard
    events_out, wt_r, turn = {}, {}, []
    rng_v1 = np.random.default_rng(P["seed"] + 1)    # the v1 options draw here, so the main stream (and every other layer) is unchanged
    onsets = {}                                      # stagger: day -> onset times (s) already placed

    # ---- per-region voices
    active = np.sum([R[i]["ice"] > P["glass_gate"][1] for i in ids], axis=0)
    density = 1 / np.sqrt(np.maximum(1, active))          # the glass keeps its total energy as more regions freeze
    lo, hi = P["glass_gate"]
    for i, rid in enumerate(ids):
        r = R[rid]
        p = pan[rid]
        ice_f = r["ice"] / 100.0
        lvl = ice_f ** 0.7 * smoothstep(r["ice"], lo, hi) * density
        if "ice" in L:
            tilt = 10 ** (P["tilt_db"] * i / 20)
            B["ice"].add(Y.stereo(glass(P["ice_pitch"][i], n, aud(lvl) * fade, rng) * 0.35 * tilt, width=0.5), 0, pan=p)
            tracks["ice"][rid] = cur(lvl)
        if "events" in L:
            ev = detect_events(r["ice"], P["up_pp"], P["down_pp"], P["smooth_days"], P["gap_days"])
            events_out[rid] = []
            for d, kind, mag in ev:
                vel = float(np.clip(0.45 + 0.55 * (mag - 4.0) / 12.0, 0.45, 1.0))
                off = rng.uniform(0.0, 0.5)
                events_out[rid].append([int(d), int(kind), round(mag, 1), round(float(off), 3)])   # off: the sub-day delay the sound is placed at
                x = ping(P["ice_pitch"][i] + 12, vel, rng) if kind > 0 else drop(P["drop_pitch"][i], vel, rng)
                u = rng.uniform(0, 1)
                x = distant(x, u)
                if kind > 0:
                    x = x * 10 ** (P["tilt_db"] * i / 20)
                pos = at(d, off)
                if P["stagger"]:
                    placed = onsets.setdefault(d, [])
                    if len(placed) >= 4:          # at most four events sound on one day; the rest are not played or shown
                        events_out[rid].pop()
                        continue
                    t = pos / SR
                    while any(abs(t - q) < 0.08 for q in placed):   # at least 80 ms between onsets on the same day
                        t += 0.08
                    placed.append(t)
                    pos = int(t * SR)
                    events_out[rid][-1][3] = round(t / day_s - d, 3)   # the page places the event where it is heard
                if P["crackle"] == "v02":
                    B["pings" if kind > 0 else "drops"].add(Y.stereo(x, width=0.3), pos, pan=p)
                else:
                    pj = float(np.clip(p + rng_v1.uniform(-0.15, 0.15), -1, 1))
                    wd = 0.05 + 0.85 * u
                    if P["crackle"] == "a":
                        B["pings" if kind > 0 else "drops"].add(Y.stereo(x, width=wd), pos, pan=pj)
                    else:
                        dist = 1 + 3 * u                         # distance, 1 (near) .. 4 (far): a choice, not a physical scale
                        g = (1.0 / (dist + 0.25)) ** 0.9 / (1.0 / 1.25) ** 0.9
                        y = early_reflections(x, u, rng_v1) * g
                        wet = 0.15 + 0.75 * u
                        near_b, far_b = ("pings", "pings_far") if kind > 0 else ("drops", "drops_far")
                        B[near_b].add(y * (1 - wet) * 1.6, pos, pan=pj)
                        B[far_b].add(y * wet * 1.6, pos, pan=pj * 0.8)
        sst = warmth(r["sst"], *P["water_range"])
        lid_r = (1 - 0.85 * ice_f) * (0.35 + 0.65 * sst)
        wt_r[rid] = (sst, lid_r)
        tracks["water"][rid] = cur(lid_r)
        tracks["wind"][rid] = cur(warmth(r["wind"], 3.0, 18.0) ** 2)
        if "snow" in L:
            sn = r["snow"]
            for d in range(N):
                for _ in range(rng.poisson(min(6.0, sn[d] * 0.8))):
                    B["snow"].add(Y.stereo(flake(float(rng.uniform(0.3, 0.8)), rng), width=0.2), at(d, rng.uniform(0, 1)), pan=p)
        if "rain" in L:
            liquid = np.maximum(0.0, r["precip"] - 0.7 * r["snow"])
            for d in range(N):
                for _ in range(rng.poisson(min(4.0, liquid[d] * 0.5))):
                    x = K["harp"].note(P["rain_pitch"][i], float(rng.uniform(0.2, 0.5)), dur=1.5, release=0.8, rng=rng)
                    B["rain"].add(x, at(d, rng.uniform(0, 1)), pan=p, gain=0.6)
        print(f"  {rid:9s} ice {P['ice_pitch'][i]} pan {p:+.2f}" + (f"  events {len(events_out[rid])}" if rid in events_out else ""))

    # ---- water: four voices, each the share-weighted mean of two neighbouring regions, west to east
    if "water" in L:
        share = {r["id"]: r["share"] for r in json.loads((DATA / "superior_regions.json").read_text())}
        for v, ps in enumerate(P["water_pitch"]):
            pair = ids[2 * v:2 * v + 2]
            w = np.array([share[i] for i in pair]) / sum(share[i] for i in pair)
            ws_d = sum(wi * wt_r[i][0] for wi, i in zip(w, pair))
            lid_d = sum(wi * wt_r[i][1] for wi, i in zip(w, pair))
            xs = S.sustain(strings_for(K, ps), ps, 0.45, span, rng, seg=6.0, xf=1.8)[:n]
            dark = lowpass(xs, 1.5 * float(Y.midi_hz(ps)))
            wa = aud(ws_d)[:len(xs), None]
            B["water"].add(((1 - wa) * dark + wa * xs) * (aud(lid_d) * fade)[:len(xs), None], 0,
                           pan=float(np.mean([pan[i] for i in pair])) * 0.5)
    if "turnover" in L or "water" in L:
        skin = D["lake_sst"]
        turn = [int(d) for d in range(1, N) if (skin[d - 1] - P["turnover_c"]) * (skin[d] - P["turnover_c"]) < 0]
        for d in turn:
            B["turnover"].add(Y.sub_note(P["water_pitch"][0], 5.0, vel=0.6, r=2.0, drive=1.2), at(d))
        print("  turnover (lake-mean SST crosses 4 C):", [D["dates"][d] for d in turn])
    if "wind" in L:
        rw = np.array([R[i]["wind"] for i in ids])
        gale = warmth(rw.max(axis=0), 6.0, 16.0) ** 1.5
        lead = np.array([pan[ids[k]] for k in rw.argmax(axis=0)])
        x = Y.bandpass(rng.standard_normal(n), 250, 1400) * aud(gale) * fade
        B["wind"].add(pan_curve(x * 0.3, aud(lead)), 0)

    # ---- lake-wide beds
    tmean = np.mean([R[i]["tmean"] for i in ids], axis=0)
    sw = np.mean([R[i]["sw"] for i in ids], axis=0)
    dl = np.array([solar.day(47.6, D["start"] + dt.timedelta(d))["daylength"] for d in range(N)])
    dl_n = (dl - dl.min()) / (np.ptp(dl) + 1e-9)
    if "air" in L:
        wa = aud(warmth(tmean, *P["air_range"]))[:, None]
        for m in P["organ_pitch"]:
            x = S.sustain(organ, m, 0.55, span, rng, seg=9.0, xf=2.0, release=1.0)[:n]
            x4 = S.sustain(organ, m + 12, 0.45, span, rng, seg=9.0, xf=2.0, release=1.0)[:n]
            dark = lowpass(x, 1.6 * float(Y.midi_hz(m)))
            w = wa[:len(x)]
            B["organ"].add(((1 - w) * dark + w * (x + 0.45 * x4[:len(x)])) * fade[:len(x), None], 0, pan=0.0)
    if "sun" in L:
        a_dl = aud(0.15 + 0.85 * dl_n ** 1.5)
        vowel = aud(warmth(sw, 2.0, 25.0))
        for j, m in enumerate(P["choir_pitch"]):
            x = sung_voice(m, n, vowel, rng) * a_dl * fade
            B["choir"].add(Y.stereo(x * 0.5, width=0.4), 0, pan=(-0.25, 0.25)[j % 2])
    bird_out = {}
    if "birds" in L:
        loons, geese = S.bird_phrases("common_loon"), S.bird_phrases("canada_goose")
        bird_out = {}

        def bird(x, pos, pn, g, near=False):
            """A call at a random distance (the arrival call is always near): far calls go to a wetter bus, darker
            and quieter, with a slow swell in and out, as if heard across the water."""
            u = 0.0 if near else rng.uniform(0, 1)
            if u < 0.45:
                B["birds"].add(x, pos, pan=pn, gain=g * (1 - 0.6 * u))
            else:
                y = lowpass(x, 5500 - 3500 * u)
                env = np.minimum(1, np.minimum(np.arange(len(y)) / (0.25 * len(y)), (len(y) - np.arange(len(y))) / (0.35 * len(y))))
                B["birds_far"].add((y * env[:, None] if y.ndim == 2 else y * env).astype(np.float32), pos, pan=pn * 0.7, gain=g * (0.55 - 0.35 * u))
        for i, rid in enumerate(ids):
            r = R[rid]
            loon_d, goose_d = bird_days(r["ice"], r["tmax"], int(np.argmax(r["ice"])), D["dates"])
            bird_out[rid] = {"loon": loon_d, "goose": goose_d}
            if loon_d is not None:
                for d in range(loon_d, N):
                    if rng.random() < 0.18 or d == loon_d:      # the arrival day always sounds, so the dashboard's mark is heard
                        bird(loons[rng.integers(len(loons))], at(d, rng.uniform(0, 1)), pan[rid], 0.5, near=d == loon_d)
            if goose_d is not None:
                for d in range(goose_d, min(N, goose_d + 25)):
                    if rng.random() < 0.08 or d == goose_d:
                        bird(geese[rng.integers(len(geese))], at(d, rng.uniform(0, 1)), pan[rid], 0.45, near=d == goose_d)
            print(f"  birds {rid:9s} loon from {D['dates'][loon_d] if loon_d is not None else '-'}"
                  f"  goose from {D['dates'][goose_d] if goose_d is not None else '-'}")
    if "ghost" in L:
        med = D["hist"]["med"] / 100.0
        gap = np.abs(lake - D["hist"]["med"]) / 100.0
        f0 = float(Y.midi_hz(P["ghost_pitch"]))
        glv = med ** 0.7
        if P["coda"] != "none":
            # symbolic coda (S): after the median's last audible day the ghost holds a low floor through open water,
            # then fades over the tail after the last day of data
            floor = 0.2
            last = int(np.flatnonzero(glv >= floor)[-1]) if (glv >= floor).any() else 0
            glv = glv.copy()
            glv[last:] = np.maximum(glv[last:], floor)
            gl = aud(glv)
            ta = np.arange(n) / SR
            gfade = np.clip(1 - (ta - dur) / max(tail - 2.0, 1.0), 0, 1) ** 1.5   # fades out 2 s before the end of the tail
            lvl = gl * np.minimum(1, ta / 2) * gfade
        else:
            lvl = aud(glv) * fade
        cents = aud(gap * 40.0)
        x = ghost_carrier(f0, cents, P["ghost_phase64"]) * lvl * 0.3
        B["ghost"].add(Y.stereo(x, width=0.5), 0, pan=0.0)
        if P["coda"] == "c":
            B["marker"].add(Y.sub_note(P["water_pitch"][0], 3.0, vel=0.35, r=2.5, drive=1.1), int(dur * SR))   # the data end here
    if P["drone"]:
        # deep water sits near 4 C (the density maximum) under the ice all winter: known physics (D), not measured here
        ta = np.arange(n) / SR
        f = float(Y.midi_hz(26))
        x = (np.sin(2 * np.pi * f * ta) + 0.35 * np.sin(2 * np.pi * 2 * f * ta + 1.0) + 0.3 * np.sin(2 * np.pi * (2 * f + 0.2) * ta)
             + 0.12 * np.sin(2 * np.pi * 3 * f * ta))
        env = np.minimum(1, np.minimum(ta / 6, (n / SR - ta) / 8))
        B["deep"].add(Y.stereo((x * env * 0.05).astype(np.float32), width=0.2), 0, pan=0.0)

    if P["coda"] == "c":
        # the other layers thin over the open-water movement, so the ghost is what remains
        c3 = movement_days(lake, D["cur_peak_day"], D["dates"])[2]
        thin = to_audio(np.interp(tctl, (c3 * day_s, dur), (1.0, 0.3)), n)[:, None]
        for k, b in B.items():
            if k not in ("ghost", "marker", "deep"):
                b.buf *= thin

    # ---- master: the room tightens and darkens as the lake freezes
    ice_env = aud(np.clip(lake / 60.0, 0, 1) * 0.8)
    irs = {"open": make_ir(5.5, bright=0.5, seed=23), "iced": make_ir(2.2, bright=0.2, seed=31)}
    mix, stems = S.master([b for k, b in B.items() if k not in P["mute"]], irs, HEAVY / f"{NAME}.wav",
                          stems_dir=HEAVY / f"{NAME}_stems", ir_env={"open": 1 - ice_env, "iced": ice_env})
    S.to_mp3(HEAVY / f"{NAME}.wav", OUT / f"{NAME}.mp3")

    # ---- score + viz
    cuts = movement_days(lake, D["cur_peak_day"], D["dates"])
    rd = lambda a, nd=1: [round(float(x), nd) for x in a]
    score = {"name": NAME, "start": D["dates"][0], "end": D["dates"][-1], "n_days": N, "day_s": day_s,
             "duration_s": n / SR, "layers": P["layers"], "regions": [
                 {"id": i, "name": D["names"][i], "lon": round(float(D["lon"][i]), 3), "lat": round(float(D["lat"][i]), 3),
                  "pan": round(float(pan[i]), 3), "ice_midi": P["ice_pitch"][k], "water_midi": P["water_pitch"][k // 2], "drop_midi": P["drop_pitch"][k]}
                 for k, i in enumerate(ids)],
             "movement_cuts_day": cuts, "movement_names": ["Freeze-up", "Ice-in", "Long melt", "Open water"],
             "events": events_out, "turnover_days": turn, "birds": {k: v for k, v in (bird_out.items() if "birds" in L else [])}, "event_rules": {k: P[k] for k in ("up_pp", "down_pp", "smooth_days", "gap_days")},
             "source": D["source"], "cur_peak": D["cur_peak"], "cur_peak_day": D["cur_peak_day"],
             "stem_rms_db": {k: float(20 * np.log10(np.sqrt((v ** 2).mean()) + 1e-12)) for k, v in stems.items()}}
    if META:
        score["variant"] = META
    (OUT / f"{NAME}_score.json").write_text(json.dumps(score, indent=1))
    step = CTRL // 8
    viz = {k: v for k, v in score.items() if k != "stem_rms_db"}
    viz["env_hz"] = 8
    viz["dates"] = D["dates"]
    viz["lake_ice"] = rd(lake)
    viz["hist"] = {k: rd(v) for k, v in D["hist"].items()}
    viz["daylen"] = [round(float(x), 2) for x in dl]   # hours, at 47.6 N (D)
    viz["region_series"] = {i: {k: rd(R[i][k], 1) for k in ("ice", "sst", "tmean", "wind", "wdir", "precip", "snow")}
                            for i in ids}
    viz["env"] = {k: {i: [int(round(100 * x)) for x in v[::step]] for i, v in tr.items()} for k, tr in tracks.items() if tr}
    viz["stem_env"] = {k: [round(float(x), 4) for x in bus_rms_env(v)] for k, v in stems.items()}
    viz["audio"] = f"{NAME}.mp3"
    (OUT / f"{NAME}_viz.json").write_text(json.dumps(viz, separators=(",", ":")))

    if P["movements"]:
        norm = HEAVY / f"{NAME}_norm.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(HEAVY / f"{NAME}.wav"),
                        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(SR), str(norm)], check=True)
        full, _ = S.sf.read(norm)
        edges = [0] + [c * day_s for c in cuts] + [len(full) / SR]
        for m, (a, b) in enumerate(zip(edges[:-1], edges[1:]), 1):
            w = HEAVY / f"{NAME}_movement{m}.wav"
            S.sf.write(w, full[int(round(a * SR)):int(round(b * SR))].astype(np.float32), SR)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(w), "-b:a", "192k",
                            str(OUT / f"{NAME}_movement{m}.mp3")], check=True)
            print(f"  movement {m}: {a / 60:.1f}-{b / 60:.1f} min")
    print("cuts at days", cuts, [D["dates"][c] for c in cuts])
    print("stems dBFS", {k: round(v, 1) for k, v in score["stem_rms_db"].items()})


if __name__ == "__main__":
    main()
