"""
CLIMATE PAIR (2026-09-25): two pieces on one multidecadal grammar, 1958-2025.

    python climate_pair.py pacific
    python climate_pair.py atlantic

GW's brief: atmospheric CO2 (Keeling), SST, ENSO, PDO and storm cycles on a
multidecadal scale; the rising elements in the drone and cello range with
increasing loudness; cyclones and hurricanes in the deeper percussion; moody
without being overly dark. Both pieces share the global layers and differ in
their ocean: the Pacific piece (PDO, West Pacific typhoons and NE+Central
Pacific hurricanes, and the Kettle River's annual peak, a valley that PDO/ENSO
steer) and the Atlantic piece (AMO, NAO, Atlantic hurricanes, Arctic sea ice). ENSO runs through both: El Nino years
bring more Pacific storms and fewer Atlantic ones, and the pair lets you hear it.

TIME: 1 bar = 1 calendar year (68 bars). The bar is felt as four dotted-
quarter beats = the four seasons; the twelve eighth notes are the months.

LAYER          DATA (R retrieved, D derived, S simulated)            SOUND
drone          Mauna Loa CO2, deseasonalized (R)                      D/A drone + organ pedal; level and filter rise
                                                                      with ppm; the seasonal CO2 cycle (R) makes it breathe
cello          global ocean SST anomaly (R)                           cello section on chord tones: 1 -> 3 voices, louder
contrabass     ocean heat content 0-2000 m, IAP v4.2 monthly (R)      solo contrabass under the cellos: the deep ocean
                                                                      filling; root, then root + 5th, louder
chords         ONI (R): El Nino lifts to VI/III, La Nina sinks to iv   half-year chords; neutral years circle i VII i v
month pulse    ONI (R)                                                one note per month; louder in strong ENSO, higher
                                                                      in El Nino, lower in La Nina
mode + pad     PDO (Pacific) / AMO (Atlantic), 3-yr mean (R/D)         Dorian in the warm phase, Aeolian in the cool;
                                                                      synth + violin pad brightens with the index
storms         HURDAT2 / IBTrACS best tracks (R); Pacific: West       tropical storm: bass-drum rub; hurricane: tuned
               Pacific panned left (west), NE Pacific right (east)
                                                                      timpani; major: timpani + concert bass drum + sub
                                                                      boom; Cat 5: tam-tam; landfall: cymbal. Season ACE
                                                                      (D) -> low storm rumble
sunspots       SILSO monthly sunspot number (R)                       high shimmer + glock sparkles (11-year cycle)
heat           GISTEMP global anomaly (R)                             a held high violin once it passes +0.8 C
volcanoes      large eruptions (R dates) + cooling decay (D)          gong; the drone darkens for ~2 years
Pacific only:  Kettle River near Laurier annual peak flow, USGS (R)    spring harp/piano bloom, sized by rank
Atlantic only: NAO (R)                                                winter wind (band noise), stronger when positive
               Arctic sea-ice extent, NSIDC, Nov 1978 on (R)          a high glass voice: breathes with the season,
                                                                      thins (fewer voices) as September ice declines
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sampler as S
from sampler import Instrument, OneShots, Bus, make_ir, SR
import seasonal as W
import synth as Y

BASIN = (sys.argv[1] if len(sys.argv) > 1 else "pacific").lower()
if BASIN not in ("pacific", "atlantic"):
    sys.exit("usage: python climate_pair.py pacific|atlantic")
CFG = {
    # storms: basin -> (pan centre, gain); west on the left, as on a map
    "pacific": dict(name="climate_pacific_1958_2025", tonic=50, key="D", mode_index="pdo",
                    storms={"wpac": (-0.5, 0.3), "nepac": (0.45, 0.75)}, seed=1958, pulse="piano"),
    "atlantic": dict(name="climate_atlantic_1958_2025", tonic=45, key="A", mode_index="amo",
                     storms={"atl": (0.0, 1.0)}, seed=1492, pulse="harp"),
}[BASIN]
NAME, TONIC = CFG["name"], CFG["tonic"]
OUT = W.HERE / "rendered" / "climate"
HEAVY = W.HEAVY_OUT / "climate"
OUT.mkdir(parents=True, exist_ok=True)
HEAVY.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(CFG["seed"])
np.random.seed(CFG["seed"])

DATA = W.HERE / "data" / "climate"
J = json.loads((DATA / "indices_monthly.json").read_text())
MONTHS = J["months"]
NM = len(MONTHS)
Y0 = int(MONTHS[0][:4])
NY = NM // 12
ser = {k: np.array([np.nan if v is None else v for v in a], dtype=float) for k, a in J["series"].items()}
# sunspots (CC BY-NC) and ocean heat (terms unconfirmed) live in their own, uncommitted file
FO = json.loads((DATA / "fetched_only_monthly.json").read_text())
ser.update({k: np.array([np.nan if v is None else v for v in a], dtype=float) for k, a in FO["series"].items()})


def fill(x):
    """Linear interpolation over interior gaps; edges hold the nearest value."""
    x = x.copy()
    ok = np.isfinite(x)
    x[~ok] = np.interp(np.flatnonzero(~ok), np.flatnonzero(ok), x[ok])
    return x


def smooth(x, w):
    return W.smooth(x, w)


def n01(x, lo=None, hi=None):
    lo = np.nanpercentile(x, 2) if lo is None else lo
    hi = np.nanpercentile(x, 98) if hi is None else hi
    return np.clip((x - lo) / (hi - lo), 0, 1)


# ------------------------------------------------------------------ grid ----
BAR = 7.0                     # seconds per year
MONTH = BAR / 12
TAIL = 14.0
DUR = NY * BAR + TAIL
n = int(DUR * SR)
print(f"{BASIN}: {NY} years, {DUR / 60:.1f} min")


def t_of(year_idx, month_frac=0.0):
    return year_idx * BAR + month_frac * MONTH


def t_date(dt):
    y = dt.year - Y0
    frac = (dt.timetuple().tm_yday - 1) / (366 if dt.year % 4 == 0 else 365) * 12
    return t_of(y, frac)


def smp(sec):
    return int(max(0, sec) * SR)


t_month = np.arange(n) / SR / MONTH           # sample -> fractional month index
at_sample = lambda monthly: np.interp(t_month, np.arange(NM) + 0.5, monthly)
events = []


def mark(sec, text):
    events.append((round(sec, 1), text))


# -------------------------------------------------------------- features ----
co2 = fill(ser["co2_ppm"])
co2d = fill(ser["co2_deseason_ppm"])
co2_cycle = co2 - co2d                                    # the biosphere's annual breath (R)
oni = fill(ser["oni"])
sst = fill(ser["sst_global_anom"])
gis = fill(ser["gistemp_anom"])
sun = fill(ser["sunspots"])
idx_raw = ser[CFG["mode_index"]]
idx_ok = np.isfinite(idx_raw)
idx_last = int(np.flatnonzero(idx_ok)[-1])
idx = fill(idx_raw)
idx3 = smooth(idx, 36)
nao = fill(ser["nao"])
ohc = fill(ser["ohc_0_2000_1e22J"])
ice_raw = ser["seaice_extent_mkm2"]
ice_first = int(np.flatnonzero(np.isfinite(ice_raw))[0])     # satellite record begins (Nov 1978)
ice = fill(ice_raw)

co2_n = n01(co2d, 315, 428)                               # fixed endpoints: 1958 -> ~2025
sst_n = n01(sst, -0.25, 1.05)

# volcanic cooling envelope (D): e-folding ~1.2 years after each eruption
volc = np.zeros(NM)
for v in J["volcanoes"]:
    dt = datetime.fromisoformat(v["date"])
    m0 = (dt.year - Y0) * 12 + dt.month - 1
    k = np.arange(NM) - m0
    volc = np.maximum(volc, np.where(k >= 0, np.exp(-k / 14.0) * v.get("cooling", 0.4), 0))

# ---------------------------------------------------------------- harmony ---
# mode per year from the 3-year mean of PDO/AMO with hysteresis: Dorian (warm) / Aeolian (cool)
modes = np.zeros(NY, dtype=int)
HYST = 0.25 * float(np.nanstd(idx3))   # hysteresis scaled to the index (PDO and AMO differ ~4x in range)
cur = 2 if idx3[5] > 0 else 1
for y in range(NY):
    v = idx3[y * 12 + 6]
    if v > HYST:
        cur = 2
    elif v < -HYST:
        cur = 1
    modes[y] = cur
NEUTRAL = [0, 6, 0, 4]            # i VII i v
chords = []                       # per half-year
for h in range(NY * 2):
    o = float(np.mean(oni[h * 6:(h + 1) * 6]))
    if o >= 1.5:
        d = 2                     # III: a strong El Nino lifts furthest
    elif o >= 0.5:
        d = 5                     # VI
    elif o <= -0.5:
        d = 3                     # iv
    else:
        d = NEUTRAL[h % 4]
    chords.append(d)


def tones(h, lo, hi, prev=None, ext=(0, 2, 4, 8)):
    return W.voice_lead(prev, W.chord(chords[h], modes[h // 2], TONIC, ext), lo, hi)


def root(h, lo, hi):
    return W.voice_lead(None, [W.degree_to_midi(chords[h], modes[h // 2], TONIC)], lo, hi)[0]


# ------------------------------------------------------------ instruments ---
K = S.vsco_kit()
piano, harp, cello, vln, glock, cbass = K["piano"], K["harp"], K["cello"], K["vln"], K["glock"], K["bass"]
perc = OneShots()
timp = OneShots(S.VSCO / "Percussion" / "Timpani", glob="*Hit_*.wav")
TIMP_F0 = {1: 41.5, 2: 46.8, 3: 49.5, 4: 52.4, 5: 54.6}     # principal-mode MIDI, FFT-measured 2026-09-25
organ = Instrument("Keys/Organ/Quiet", glob="NT5_PedalQuiet_*.wav",
                   mapping=lambda nm: (int(nm.split("_")[2]) - 28, 1))
pulse_ins = piano if CFG["pulse"] == "piano" else harp

B = {k: Bus(k, n, **kw) for k, kw in {
    "drone":  dict(gain=1.8, hp=25, send=0.3),
    "cello":  dict(gain=1.1, hp=45, send=0.45),
    "deep":   dict(gain=1.8, hp=28, lp=900, send=0.3),       # ocean heat content: contrabass
    "pad":    dict(gain=0.7, hp=140, send=0.6),
    "pulse":  dict(gain=3.6 if CFG["pulse"] == "piano" else 1.7, hp=90, send=0.45),
    "storms": dict(gain=0.8, hp=25, send=0.35),
    "rumble": dict(gain=1.0, hp=30, lp=420, send=0.2),
    "shimmer": dict(gain=0.5, hp=1500, send=0.6),
    "heat":   dict(gain=2.0, hp=500, send=0.5),
    "events": dict(gain=1.3, hp=40, send=0.5),
    "local":  dict(gain=1.5, hp=80, send=0.5),     # Kettle bloom / NAO wind
}.items()}
if BASIN == "atlantic":
    B["ice"] = Bus("ice", n, gain=0.5, hp=1200, send=0.65)   # Arctic sea ice


def repitch(x, semis):
    r = 2 ** (semis / 12)
    idx_ = np.arange(int(len(x) / r)) * r
    return np.stack([np.interp(idx_, np.arange(len(x)), x[:, c]) for c in range(2)], axis=1)


def tuned_timp(target_midi, dyn):
    k = min(TIMP_F0, key=lambda i: abs(((target_midi - TIMP_F0[i] + 6) % 12) - 6))
    shift = ((target_midi - TIMP_F0[k] + 6) % 12) - 6
    try:
        x = timp.hit(f"Timpani{k}_Hit_v{dyn}", 1.0, rng)
    except FileNotFoundError:          # Timpani1 has only v1 and v3
        x = timp.hit(f"Timpani{k}_Hit_v3", 1.0, rng)
    return repitch(x, shift)


# ------------------------------------------------------------ drone (CO2) ---
lvl_m = 0.18 + 0.82 * co2_n ** 1.3                          # rising loudness
cut_m = (160 + 1500 * co2_n ** 1.5) * (1 - volc)            # opens with ppm, darkens after eruptions
breathe_m = n01(co2_cycle, -4, 4)                           # seasonal CO2 cycle, 0..1
B["drone"].add(Y.drone([TONIC - 12, TONIC - 5], n, at_sample(cut_m), at_sample(lvl_m), rng=rng,
                       breathe=at_sample(breathe_m)), 0)
for y in range(NY):                                          # sampled organ pedal joins as CO2 rises
    c = float(np.mean(co2_n[y * 12:(y + 1) * 12]))
    if c > 0.2:
        B["drone"].add(W.sustain(organ, TONIC - 12, 0.5, BAR, rng), smp(t_of(y)), gain=0.25 + 0.9 * (c - 0.2))
for ppm in (350, 400, 420):
    m = int(np.argmax(co2d >= ppm))
    if co2d[m] >= ppm:
        mark(t_of(m // 12, m % 12), f"CO2 passes {ppm} ppm ({MONTHS[m]}) - the drone is louder and more open")

# ------------------------------------------------------------ cello (SST) ---
prev = None
for h in range(NY * 2):
    s_ = float(np.mean(sst_n[h * 6:(h + 1) * 6]))
    nv = 1 + int(s_ > 0.35) + int(s_ > 0.7)
    full = tones(h, 38, 62, prev, ext=(0, 4, 8))
    prev = full
    voices = [full[0]] + ([full[1]] if nv > 1 else []) + ([full[2]] if nv > 2 else [])
    for i, m in enumerate(voices):
        B["cello"].add(W.sustain(cello, m, 0.3 + 0.55 * s_, BAR / 2, rng), smp(t_of(h / 2)),
                       gain=(0.3 + 0.9 * s_ ** 1.2) * (1.0 if i == 0 else 0.75), pan=(-0.2, 0.25, -0.05)[i])
m = int(np.argmax(sst >= 0.5))
mark(t_of(m // 12, m % 12), f"Global SST anomaly passes +0.5 C ({MONTHS[m]}) - cello in three voices")

# ------------------------------------------- contrabass (ocean heat 0-2000 m) --
# GW's note: a second, lower voice for the deep ocean, below the SST cellos.
ohc_n = n01(ohc, float(np.nanmin(ohc)), float(np.nanmax(ohc)))
for h in range(NY * 2):
    o_ = float(np.mean(ohc_n[h * 6:(h + 1) * 6]))
    r_ = root(h, 28, 40)
    notes = [r_] + ([r_ + 7] if o_ > 0.55 else [])
    for i, m in enumerate(notes):
        B["deep"].add(W.sustain(cbass, m, 0.3 + 0.5 * o_, BAR / 2, rng), smp(t_of(h / 2)),
                      gain=(0.15 + 1.0 * o_ ** 1.4) * (1.0 if i == 0 else 0.6), pan=(-0.1, 0.2)[i])
m = int(np.argmax(ohc_n >= 0.55))
mark(t_of(m // 12, m % 12), f"Ocean heat content (0-2000 m) past the halfway mark of its rise ({MONTHS[m]}) - "
                            "the contrabass adds a fifth")

# -------------------------------------------------------- pad (PDO / AMO) ---
prev = None
IDXN = n01(idx3, -1.5 if CFG["mode_index"] == "pdo" else -0.3, 1.5 if CFG["mode_index"] == "pdo" else 0.3)
for h in range(NY * 2):
    mi = h * 6 + 3
    if mi > idx_last + 3:                                    # index no longer updated: the pad falls silent
        break
    v = tones(h, 57, 81, prev, ext=(0, 2, 4, 8))
    prev = v
    b_ = float(IDXN[mi])
    for i, m in enumerate(v):
        B["pad"].add(Y.pad_note(m, BAR / 2, vel=0.35 + 0.2 * b_, cutoff=450 + 2200 * b_, a=1.6, r=2.4, rng=rng),
                     smp(t_of(h / 2)), pan=(-0.5, -0.15, 0.15, 0.5)[i % 4])
    if b_ > 0.45:
        for i, m in enumerate(v[1:]):
            B["pad"].add(W.sustain(vln, m + 12, 0.25 + 0.3 * b_, BAR / 2, rng), smp(t_of(h / 2)),
                         gain=0.35 * b_, pan=(-0.55, 0.0, 0.55)[i % 3])
if idx_last < NM - 1:
    mark(t_of(idx_last // 12, idx_last % 12),
         f"The {CFG['mode_index'].upper()} record ends ({MONTHS[idx_last]}; the index is no longer updated) - "
         "its pad falls silent and the mode holds")
for y in range(1, NY):
    if modes[y] != modes[y - 1]:
        mark(t_of(y), f"{CFG['mode_index'].upper()} phase turns {'warm' if modes[y] == 2 else 'cool'} "
                      f"({Y0 + y}) - {W.MODES[modes[y]][0]}")

# ------------------------------------------------------ month pulse (ENSO) --
PAT = [0, 2, 1, 3, 2, 1, 0, 2, 1, 3, 2, 1]
for mth in range(NM):
    h = mth // 6
    o = oni[mth]
    shift = 12 if o > 1.0 else (-12 if o < -1.0 else 0)
    pool = sorted(tones(h, 60 + shift, 79 + shift))
    note = pool[PAT[mth % 12] % len(pool)]
    vel = float(np.clip(0.22 + 0.28 * min(abs(o), 2.2) / 2.2 + (0.08 if mth % 3 == 0 else 0), 0.1, 0.8))
    at = smp(t_of(mth // 12, mth % 12) + rng.normal(0, 0.006))
    B["pulse"].add(pulse_ins.note(note, vel, dur=MONTH * 1.6, release=1.2, rng=rng), at,
                   pan=0.3 * np.sin(mth * 0.52))
    if abs(o) > 1.0:  # strong events: a quiet synth pluck doubles the pulse an octave up
        B["pulse"].add(Y.pluck_note(note + 12, vel=0.25 * vel, decay=0.35, cutoff=1800, rng=rng), at, pan=-0.3)
for thr, label in ((1.5, "El Nino"), (-1.5, "La Nina")):
    y_prev = -9
    for mth in range(NM):
        if (oni[mth] >= thr if thr > 0 else oni[mth] <= thr) and mth // 12 > y_prev + 1:
            seg = oni[mth:mth + 18]
            pk = mth + int(np.argmax(seg) if thr > 0 else np.argmin(seg))
            mark(t_of(pk // 12, pk % 12), f"Strong {label} ({MONTHS[pk]}, ONI {oni[pk]:+.1f})")
            y_prev = pk // 12

# ---------------------------------------------------------------- storms ----
rumble_env = np.zeros(NM * 8)                                # 1/8-month resolution
duck_hits, duck_depth = [], []
ace_year = np.zeros(NY)
cat_counts = {}
for basin, (pan0, bgain) in CFG["storms"].items():
    storms = json.loads((DATA / f"storms_{basin}.json").read_text())
    cc = np.zeros(6, dtype=int)
    cat5 = []
    for s_ in storms:
        dt = datetime.fromisoformat(s_["peak_time"])
        if dt.year < Y0 or dt.year >= Y0 + NY:
            continue
        t = t_date(dt)
        h = min(int(t / (BAR / 2)), NY * 2 - 1)
        cat = s_["category"]
        cc[cat] += 1
        ace_year[dt.year - Y0] += s_["ace"]
        r_ = root(h, 38, 50)
        at = smp(t + rng.normal(0, 0.01))
        pan = float(np.clip(pan0 + rng.normal(0, 0.25), -0.85, 0.85))
        if cat == 0:
            B["storms"].add(perc.hit("bassdrum_rub", 0.35, rng), at, gain=0.5 * bgain, pan=pan)
        else:
            dyn = 1 if cat <= 1 else (3 if cat == 2 else 4)
            B["storms"].add(tuned_timp(r_ if cat != 2 else r_ + 7, dyn), at, gain=(0.5 + 0.12 * cat) * bgain, pan=pan)
        if cat >= 3:
            B["storms"].add(perc.hit(f"BDrumNewhit_v{min(7, 3 + cat)}", 1.0, rng), at, gain=(0.6 + 0.1 * cat) * bgain,
                            pan=pan * 0.5)
            B["storms"].add(Y.kick(0.6 + 0.08 * cat, f0=38, f_start=90, decay=0.9 + 0.15 * cat, click=0.05), at,
                            gain=0.7 * bgain)
            duck_hits.append(at)
        if cat == 5:
            B["storms"].add(perc.hit("gongHit_f", 1.0, rng), at + int(0.05 * SR), gain=0.55 * bgain, pan=pan * 0.6)
            cat5.append((s_["peak_kt"], t, s_["name"], dt))
        if s_["landfall"] and cat >= 1:
            B["storms"].add(perc.hit("susCymb1-hit_mp", 0.6, rng), at + int(0.03 * SR), gain=(0.25 + 0.05 * cat) * bgain,
                            pan=-pan if len(CFG["storms"]) == 1 else pan)
        k0 = int(t / MONTH * 8)
        w = np.arange(-8, 9)
        lo, hi = max(0, k0 - 8), min(len(rumble_env), k0 + 9)
        rumble_env[lo:hi] += np.sqrt(max(s_["ace"], 0.1)) * np.exp(-0.5 * (w[lo - k0 + 8:hi - k0 + 8] / 4.0) ** 2)
    # the guide names every Cat 5 in a basin with few of them, and the eight strongest where there are many
    for kt, t, nm, dt in (cat5 if len(cat5) <= 40 else sorted(cat5, reverse=True)[:8]):
        mark(t, f"Category 5 ({basin.upper()}): {nm} ({dt:%b %Y}, {kt} kt) - tam-tam")
    last = max(datetime.fromisoformat(s_["peak_time"]) for s_ in storms)
    if last.year < Y0 + NY - 1:
        mark(t_of(last.year + 1 - Y0), f"{basin.upper()} best tracks end {last:%b %Y} (not yet in the archive) - "
                                       "that basin's drums fall silent")
    cat_counts[basin] = cc.tolist()
    print(f"storms {basin} by category", cc.tolist(), f"({len(cat5)} Cat 5)")
rumble_s = np.interp(t_month * 8, np.arange(len(rumble_env)), rumble_env)
rumble_s = rumble_s / (np.percentile(rumble_env[rumble_env > 0], 98) + 1e-9)
B["rumble"].add(Y.noise_band(n, 35, 260, rng=rng) * np.clip(rumble_s, 0, 1.4)[:, None] * 0.35, 0)
top = int(np.argmax(ace_year))
basins = "+".join(b.upper() for b in CFG["storms"])
mark(t_of(top, 6), f"Most active {basins} season by ACE: {Y0 + top} ({ace_year[top]:.0f})")
mark(t_of(1966 - Y0), "1966: routine satellite coverage begins - fewer storms before this is partly fewer observed")

# ------------------------------------------------------ shimmer (sunspots) --
sun_n = n01(smooth(sun, 6), 0, 250)
for h in range(NY * 2):
    s_ = float(np.mean(sun_n[h * 6:(h + 1) * 6]))
    if s_ < 0.12:
        continue
    for m in tones(h, 84, 98, ext=(0, 4, 8))[:2]:
        B["shimmer"].add(Y.pad_note(m, BAR / 2, vel=0.2 + 0.5 * s_, cutoff=6000, a=2.0, r=2.5, rng=rng, voices=3,
                                    detune=6), smp(t_of(h / 2)), gain=s_)
    for _ in range(int(round(6 * s_))):
        m = int(rng.choice(tones(h, 86, 100)))
        B["shimmer"].add(glock.note(m, 0.18, dur=0.8, release=2.0, rng=rng),
                         smp(t_of(h / 2) + rng.uniform(0, BAR / 2)), gain=0.5, pan=rng.uniform(-0.8, 0.8))
for mth in range(24, NM - 24):
    s6 = smooth(sun, 13)
    if s6[mth] == s6[mth - 24:mth + 24].max() and s6[mth] > 80:
        mark(t_of(mth // 12, mth % 12), f"Solar maximum ({MONTHS[mth]}) - the shimmer is fullest")

# ------------------------------------------------------- heat (GISTEMP) -----
gis12 = smooth(gis, 12)
for h in range(NY * 2):
    a = float(np.mean(gis12[h * 6:(h + 1) * 6]))
    if a < 0.8:
        continue
    m = W.voice_lead(None, [W.degree_to_midi(8, modes[h // 2], TONIC)], 81, 93)[0]   # the 9th, held high
    B["heat"].add(W.sustain(vln, m, 0.3, BAR / 2, rng), smp(t_of(h / 2)), gain=min(1.0, (a - 0.8) / 0.5))
m = int(np.argmax(gis12 >= 0.8))
mark(t_of(m // 12, m % 12), f"Global temperature passes +0.8 C vs 1951-80 ({MONTHS[m]}) - a high violin enters")

# -------------------------------------------------------------- volcanoes ---
for v in J["volcanoes"]:
    dt = datetime.fromisoformat(v["date"])
    t = t_date(dt)
    B["events"].add(perc.hit("gongscrape_mf", 0.9, rng), smp(t - 1.2), gain=0.6)
    B["events"].add(perc.hit("gongHit_mf", 0.9, rng), smp(t), gain=0.8)
    mark(t, f"Eruption: {v['name']} ({dt:%b %Y}) - gong; " + v.get("note", "the drone darkens as the aerosols cool the planet"))

# ------------------------------------------------------ local layer ---------
if BASIN == "pacific":
    # GW's note: the Kettle at Laurier (USGS, complete since 1929) replaces the Granby, whose record has a 1958-66 gap
    gr = json.loads((DATA / "kettle_annual_max.json").read_text())
    vals = np.array([v["max_daily_m3s"] for k_, v in gr.items() if Y0 <= int(k_) < Y0 + NY])
    for y in range(NY):
        rec = gr.get(str(Y0 + y))
        if rec is None:
            continue
        dt = datetime.fromisoformat(rec["date"])
        t = t_date(dt)
        p = float((vals < rec["max_daily_m3s"]).mean())
        h = min(int(t / (BAR / 2)), NY * 2 - 1)
        v_ = sorted(tones(h, 55, 86))
        k = 3 + int(round(5 * p))
        for i, m in enumerate((v_ + [x + 12 for x in v_])[:k]):
            B["local"].add(harp.note(m, 0.3 + 0.35 * p, rng=rng), smp(t + i * 0.07), pan=-0.5 + i * 0.12)
        B["local"].add(piano.note(v_[0], 0.3 + 0.3 * p, dur=2.0, release=1.5, rng=rng), smp(t), pan=0.1)
    missing = [Y0 + y for y in range(NY) if str(Y0 + y) not in gr and Y0 + y <= 2024]
    top_y = max(gr, key=lambda k_: gr[k_]["max_daily_m3s"] if Y0 <= int(k_) < Y0 + NY else -1)
    mark(t_date(datetime.fromisoformat(gr[top_y]["date"])),
         f"The Kettle's biggest peak in the span: {gr[top_y]['max_daily_m3s']:.0f} m3/s ({gr[top_y]['date']}) - "
         "the fullest harp bloom")
    if missing:
        mark(t_of(missing[0] - Y0), f"No Kettle record {missing[0]}-{missing[-1]} - the spring bloom is silent")
else:
    wind = np.zeros(NM)
    for mth in range(NM):
        if (mth % 12) in (11, 0, 1, 2):                      # Dec-Mar
            wind[mth] = np.clip(0.25 + 0.3 * nao[mth], 0, 1.2)
    w_s = at_sample(smooth(wind, 2))
    lo_n = Y.noise_band(n, 300, 1400, rng=rng)
    hi_n = Y.noise_band(n, 1400, 4200, rng=np.random.default_rng(99))
    gust = 0.7 + 0.3 * np.sin(2 * np.pi * np.arange(n) / SR / 5.3) * np.sin(2 * np.pi * np.arange(n) / SR / 2.1)
    B["local"].add((lo_n * 0.6 + hi_n * 0.25) * (w_s * gust)[:, None] * 0.22, 0)
    top = int(np.argmax(np.where((np.arange(NM) % 12) < 3, nao, -9)))
    mark(t_of(top // 12, top % 12), f"Strongest winter NAO ({MONTHS[top]}, {nao[top]:+.1f}) - the loudest wind")

    # Arctic sea ice (GW's note: a careful bring-in when the satellite record starts). A glass voice of
    # sine partials on high chord tones: its level follows the monthly extent (the seasonal breath,
    # March max, September min); its number of voices follows that year's September extent, so it
    # thins over the decades. Silent before Nov 1978: no satellite record, and nothing is invented.
    sep = {y: ice[y * 12 + 8] for y in range(NY) if y * 12 + 8 >= ice_first}
    sep_lo, sep_hi = min(sep.values()), max(sep.values())
    lvl_ice = np.where(np.arange(NM) >= ice_first, n01(ice, 3.0, 16.5), 0.0)
    ramp = np.clip((np.arange(NM) - ice_first) / 3.0, 0, 1)            # a three-month fade-in, not a jump
    lvl_ice_s = at_sample(lvl_ice * ramp)
    for h in range(NY * 2):
        m0 = h * 6
        if m0 + 6 <= ice_first:
            continue
        y = h // 2
        sv = sep.get(y, sep.get(y - 1, sep_hi))
        nv = 1 + int(round(3 * (sv - sep_lo) / (sep_hi - sep_lo)))      # 4 voices at the most ice, 1 at the least
        pool = sorted(tones(h, 84, 100, ext=(0, 2, 4, 8)))[:nv]
        L = int((BAR / 2 + 2.5) * SR)
        tt = np.arange(L) / SR
        env = np.minimum(1, tt / 1.5) * np.clip((BAR / 2 + 2.5 - tt) / 2.5, 0, 1)
        for i, m in enumerate(pool):
            f = Y.midi_hz(m)
            trem = 1 + 0.25 * np.sin(2 * np.pi * (0.23 + 0.07 * i) * tt + rng.uniform(0, 6.28))
            x = (np.sin(2 * np.pi * f * tt) + 0.18 * np.sin(2 * np.pi * 2.005 * f * tt)) * env * trem * 0.08
            a0 = smp(t_of(h / 2))
            g_ = lvl_ice_s[a0:a0 + L]
            x = x[:len(g_)] * g_
            B["ice"].add(x[:, None].repeat(2, 1), a0, pan=(-0.6, 0.5, -0.2, 0.25)[i % 4])
    mark(t_of(ice_first // 12, ice_first % 12), f"Satellites begin measuring Arctic sea ice ({MONTHS[ice_first]}) - "
                                                  "a high glass voice fades in")
    y_min = min(sep, key=sep.get)
    mark(t_of(y_min, 8), f"Lowest September sea ice in the record: {Y0 + y_min} ({sep[y_min]:.2f} million km2) - "
                         "the glass voice at its thinnest")

# ----------------------------------------------------- sidechain + echoes ---
duck = Y.sidechain(n, duck_hits, depth=0.35, release=0.6).astype(np.float32)
for k in ("drone", "cello", "pad"):
    B[k].buf *= duck[:, None]
B["pulse"].buf += Y.pingpong(B["pulse"].buf, MONTH * 1.5, fb=0.35, mix=0.3).astype(np.float32)
B["shimmer"].buf += Y.pingpong(B["shimmer"].buf, MONTH, fb=0.5, mix=0.4).astype(np.float32)

# ---------------------------------------------------------------- master ----
irs = {"hall": make_ir(4.5, bright=0.45, seed=21)}
mix, stems = S.master(list(B.values()), irs, HEAVY / f"{NAME}.wav", stems_dir=HEAVY / f"{NAME}_stems", wet_gain=0.42)
S.to_mp3(HEAVY / f"{NAME}.wav", OUT / f"{NAME}.mp3")
AUDIO = W.HERE / "audio"                                      # the site's copy: 160 kbps, encoded from the WAV
AUDIO.mkdir(exist_ok=True)
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(HEAVY / f"{NAME}.wav"), "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-b:a", "160k", str(AUDIO / f"{NAME}.mp3")], check=True)


def active_db(x, thr_db=-50):
    w = int(0.1 * SR)
    m_ = (x ** 2).mean(axis=1)[: len(x) // w * w].reshape(-1, w).mean(axis=1)
    db = 10 * np.log10(m_ + 1e-12)
    on = db > thr_db
    return float(np.median(db[on])) if on.any() else None


def seg_db(x, a, b):
    s_ = x[smp(a):smp(b)]
    return float(10 * np.log10((s_ ** 2).mean() + 1e-12))


events.sort()
level = {k: active_db(v) for k, v in stems.items()}
first10, last10 = seg_db(mix, 5, 75), seg_db(mix, NY * BAR - 70, NY * BAR)
SCORE = {"name": NAME, "basin": BASIN, "key": CFG["key"], "years": [Y0, Y0 + NY - 1], "bar_seconds": BAR,
           "duration_s": DUR, "events": events, "stem_active_db": level,
           "storms_by_category": cat_counts,
           "mix_db_first_decade": first10, "mix_db_last_decade": last10,
           "years_detail": [{"year": Y0 + y, "mode": W.MODES[modes[y]][0], "chords": chords[2 * y:2 * y + 2],
                             "co2_ppm": round(float(np.mean(co2d[y * 12:(y + 1) * 12])), 1),
                             "sst_anom": round(float(np.mean(sst[y * 12:(y + 1) * 12])), 2),
                             "ace": round(float(ace_year[y]), 1),
                             "ohc_1e22J": round(float(np.mean(ohc[y * 12:(y + 1) * 12])), 2),
                             "seaice_sep_mkm2": (round(float(ice_raw[y * 12 + 8]), 2)
                                                 if np.isfinite(ice_raw[y * 12 + 8]) else None)}
                            for y in range(NY)]}
with open(OUT / f"{NAME}_score.json", "w") as fh:
    json.dump(SCORE, fh, indent=1)
print("\n".join(f"{int(t // 60)}:{int(t % 60):02d}  {e}" for t, e in events))
print("stem active dBFS:", {k: (round(v, 1) if v is not None else None) for k, v in level.items()})
print(f"mix loudness first decade {first10:.1f} dB, last decade {last10:.1f} dB")
print("peak", float(np.abs(mix).max()), "nan", bool(np.isnan(mix).any()))
