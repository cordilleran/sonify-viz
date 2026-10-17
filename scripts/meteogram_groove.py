"""Weather groove from an ECMWF AIFS point series (6-hourly, 15 days; fetch_aifs_open.py): marching-band-and-bass percussion groove, consonant, layered.

One bar of 4/4 per six-hour step (four bars a day), 16 steps a bar, 126 bpm, swing 0.54 on the off-sixteenths, small per-voice drag.
D Dorian when the 2 m temperature is 3 C or more, else D Aeolian. No Phrygian, no saturation on the groove (the heavy chug layer was dropped).

  sun (downward shortwave, a 6 h mean ending at each stamp, against the run's best moment) -> pulse. v1.1: the six-hour value is spread along that
                    window's own daylight curve (clear-sky sine of the sun's height, as in Meridian Chorus, smoothed so sunrise and sunset round off), scaled so the
                    window mean is the model's value; each hit's loudness follows that curve step by step: offbeat hats from d 0.05, backbeat kicks from d 0.2,
                    snare from d 0.4, shaker from d 0.2, hat sixteenths from d 0.45
  rain mm + snow cm per step, over 4 (capped at 1) = weight hv -> from hv >= 0.2 the Karoryfer kit (kick, snare, hat, ghost notes); crash
                    when hv first passes 0.5, on a day's first bar with hv > 0.1, and on the first bar of the song
  rain       -> log drums + marimba, Euclid density 3 to 9 of 16 (rain-driven), rotating by bar
  snow       -> glock, triangle, bell tree on onset
  10 m wind  -> speed: conga Euclid density 3 to 9 of 16; direction: accent steps (S/E 45-225: 1,4,7,10,13; W 225-290: 1,5,8,11,14; N: 1,4,8,11,14)
  700 hPa wind -> cello pizzicato Euclid density 2 to 8; shear (angle between 10 m and 700 hPa directions) -> harp counter-line a third (<60),
                    fifth (<120) or seventh above
  temperature -> mode; harp up an octave from 6 C; T minus dew point -> harp loudness
  pressure level -> drifts a four-bar chord loop (Aeolian i-VI-iv-VII, Dorian i-IV-VII-IV) by up to two scale degrees; diminished triads skipped
  pressure fall of 3 hPa or more in 6 h -> the drone's third becomes a fourth (a suspension)
  swing of 6 hPa or more in 6 h -> fall: timpani hit and the tuba stepping fifth to root; rise: timpani roll and a violin triad
  cloud      -> violin pad; chord -> tuba riff, contrabass root, quiet low cello drone
  v1.1: a four-bar lead-in and a four-bar wrap-out (drone, harp, Bear Sax; no kit). Bear Sax an octave under the chord root: held under a falling-pressure
                    suspension (3 hPa or more), and on a 6 hPa fall a sub drop plus the sax sliding down a fifth
  v1.2: night hand drums (on by default, --no-night turns them off): as the sun pulse fades at dusk a loose heartbeat comes up, low conga and log drum on
                    per-step probabilities (beat 1 most likely, then the "and" of 3), brushed tambourine on the off-eighths, humanized +-10 ms; density follows 10 m wind
                    (0.7x calm to 1.4x at 40 km/h); level is the complement of the sun gate and of the rain weight, so a storm still belongs to the kit
  Not used in the sound: 850 hPa temperature and the derived freezing level (kept in the score only).
If the table has no wind columns the 6 h pressure change stands in for the conga density.
Run: <venv>/python scripts/meteogram_groove.py AIFS.json NAME [--bpm 126] [--bars 61] [--no-night]
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

import solar  # noqa: E402
from sampler import Bus, SR, make_ir, master, sustain  # noqa: E402
from dsp_core import HEAVY_OUT, LIGHT_OUT  # noqa: E402
from meteogram_kit import build_kit, glide  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("data")
ap.add_argument("name")
ap.add_argument("--bpm", type=float, default=126)
ap.add_argument("--bars", type=int, default=61)
ap.add_argument("--event-hpa", type=float, default=6.0)
ap.add_argument("--no-night", dest="night", action="store_false", help="leave out the night hand-drum layer (v1.1 sound)")
A = ap.parse_args()

OUT = LIGHT_OUT / "meteogram"  # under SONIFICATION_LIGHT, so renders.py can lock the outputs
HEAVY = HEAVY_OUT / "meteogram"
HEAVY.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

BEAT = 60 / A.bpm
STEP = BEAT / 4
BAR = 4 * BEAT
SWING = 0.54
LEAD_BARS = 4
OUT_BARS = 4
LEAD = LEAD_BARS * BAR
OUTRO = OUT_BARS * BAR
PED = 38  # D2
DORIAN = [0, 2, 3, 5, 7, 9, 10]
AEOLIAN = [0, 2, 3, 5, 7, 8, 10]
rng = np.random.default_rng(1016)
DRAG = {"kick": 0.0, "snare": 0.024, "log": 0.022, "conga": 0.012, "hat": -0.008, "shake": -0.014, "tuba": 0.004}


def euclid(k, n):
    return [((i * k) % n) < k for i in range(n)]


def snap(midi, scale):
    base = PED % 12
    return min(((12 * o + base + d) for o in range(-1, 9) for d in scale), key=lambda m: abs(m - midi))


LOOPS = {"Aeolian": [0, 5, 3, 6], "Dorian": [0, 3, 6, 3]}  # i-VI-iv-VII and i-IV-VII-IV, one chord a bar, four bars a day
NOTE = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def dmidi(mode, d, base):
    """MIDI note of scale degree d (any integer, 0 = tonic) above base; stays in the mode."""
    return base + mode[d % 7] + 12 * (d // 7)


def fade_in(x, secs=0.4):
    n = min(len(x), int(secs * SR))
    x = x.copy()
    x[:n] *= np.linspace(0, 1, n)[:, None] ** 2
    return x


def chord_degree(i, h, mname):
    cdrift = int(np.clip(round((h["slp"] - 1013) / 8), -2, 2))
    dr = (LOOPS[mname][i % 4] + cdrift) % 7
    if dr == (1 if mname == "Aeolian" else 5):  # the one diminished triad in the mode: step past it
        dr = (dr + 1) % 7
    return dr


def step_time(s):
    return s * STEP + (STEP * (SWING - 0.5) * 2 if s % 2 else 0.0)


def subdrop(midi, dur=4.0, sweep=5.0, vel=0.7):
    """Sine sub drop (the Superior turnover idea): the root glides down `sweep` semitones, soft attack, exponential decay, a little drive for audible harmonics."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 440 * 2 ** ((midi - 69 - sweep * (1 - np.exp(-t / (dur / 3)))) / 12)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.minimum(t / 0.03, 1) * np.exp(-t / (dur / 3))
    x = np.tanh(1.6 * x) * vel
    return np.stack([x, x], axis=1).astype(np.float32)


def sun_envelope(stamps, sw, lat, lon, tz_h=-5):
    """Fine-grained sunshine curve, W/m2, one value per minute from 6 h before the first stamp.
    The shortwave value is a 6 h mean ending at each stamp (ssrd accumulation differenced) (checked: 6 h clear-sky means end near the model values, an instantaneous reading would be
    positive at 19:00 local in October, when the sun is down). The curve is the clear-sky shape (sine of the sun's height, the Meridian Chorus
    solar code), times a cloud factor per window that makes each window's mean equal the model's value, the factor interpolated between windows;
    a 40 min smoothing rounds sunrise and sunset. -> (minutes array start datetime, E)"""
    t0 = dt.datetime.strptime(stamps[0][:16].replace("T", " "), "%Y-%m-%d %H:%M") - dt.timedelta(hours=6)
    nmin = (len(stamps) + 1) * 360
    tt = [t0 + dt.timedelta(minutes=m) for m in range(nmin)]
    clear = np.zeros(nmin)
    for m, t in enumerate(tt):
        utc = t - dt.timedelta(hours=tz_h)
        h = utc.hour + utc.minute / 60
        decl, eot = solar.declination(utc.date(), h), solar.equation_of_time(utc.date(), h)
        alt = solar.altitude(lat, decl, 15 * (h - (12 - lon / 15 - eot / 60)))
        clear[m] = 1361 * 0.75 * max(np.sin(np.radians(alt)), 0.0) ** 1.15
    kt = np.full(len(stamps), np.nan)
    cen = np.array([i * 360 + 180 for i in range(len(stamps))])  # window i covers minutes i*360 .. i*360+359 (the six hours before stamp i)
    for i in range(len(stamps)):
        cm = clear[i * 360:(i + 1) * 360].mean()
        if cm > 5:
            kt[i] = np.clip(sw[i] / cm, 0, 1.25)
    ok = ~np.isnan(kt)
    ktm = np.interp(np.arange(nmin), cen[ok], kt[ok])
    E = clear * ktm
    k = 40
    E = np.convolve(np.pad(E, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), "same")[k:-k]
    return t0, E


def load_series():
    d = json.loads(Path(A.data).read_text())["series"]
    g = lambda k: np.array([v for _, v in d[k]], dtype=float)  # noqa: E731
    stamps = [t for t, _ in d["Temp."]]
    n = min(A.bars, len(stamps))
    tmp, dpt, t850, cloud, slp, sw = g("Temp.")[:n], g("Dew point")[:n], g("850mb")[:n], g("Cloud Cover")[:n], g("Pressure")[:n], g("Downward Shortwave")[:n]
    rain = np.maximum(np.diff(g("Ttl Rain"), prepend=g("Ttl Rain")[0])[:n], 0)
    snow = np.maximum(np.diff(g("Ttl Snow"), prepend=g("Ttl Snow")[0])[:n], 0)
    rate = np.array([slp[min(i + 1, n - 1)] - slp[i] for i in range(n)])
    wind = "10m Wind" in d and "700mb Wind" in d
    ws10 = np.array([r[1] for r in d["10m Wind"]][:n], float) if wind else None
    wd10 = np.array([r[2] for r in d["10m Wind"]][:n], float) if wind else None
    ws700 = np.array([r[1] for r in d["700mb Wind"]][:n], float) if wind else None
    wd700 = np.array([r[2] for r in d["700mb Wind"]][:n], float) if wind else None
    H = []
    for i in range(n):
        tot = rain[i] + snow[i]  # rain mm, snow cm: about 1 mm water per cm of snow, so the sum is a rough water-equivalent
        extra = {}
        if wind:
            sh = abs((wd700[i] - wd10[i] + 180) % 360 - 180)
            extra = dict(ws=ws10[i], wd=wd10[i], ws700=ws700[i], wd700=wd700[i], shear=float(sh))
        H.append(dict(t=stamps[i].replace("T", " ").replace("Z", ""), tmp=tmp[i], dpt=dpt[i], cloud=cloud[i], slp=slp[i], rate=rate[i], sw=sw[i], rain=rain[i], snow=snow[i],
                      hv=float(np.clip(tot / 4.0, 0, 1)), fz_m=1520 + t850[i] / 6.5 * 1000, **extra))
    return H


def main():
    H = load_series()
    K = build_kit()
    nb = len(H)
    n = int((LEAD + nb * BAR + OUTRO + 7) * SR)
    B = {
        "kit": Bus("kit", n, gain=2.6, hp=35, send=0.1),
        "perc": Bus("perc", n, gain=5.0, hp=120, send=0.2),
        "hi": Bus("hi", n, gain=4.5, hp=500, send=0.35),
        "mallet": Bus("mallet", n, gain=2.0, hp=150, send=0.3),
        "harp": Bus("harp", n, gain=2.3, hp=120, send=0.35),
        "strings": Bus("strings", n, gain=0.8, hp=60, send=0.5),
        "drone": Bus("drone", n, gain=0.5, hp=40, lp=1400, send=0.4),
        "bass": Bus("bass", n, gain=0.45, hp=30, send=0.05),
        "timp": Bus("timp", n, gain=2.5, hp=30, send=0.3),
        "cym": Bus("cym", n, gain=3.5, hp=300, send=0.25),
        "sax": Bus("sax", n, gain=0.45, hp=28, send=0.2),
    }
    meta = json.loads(Path(A.data).read_text()).get("point", {})
    _, E = sun_envelope([h["t"] for h in H], [h["sw"] for h in H], meta.get("lat", 49.21), meta.get("lon", -68.14))
    emax = float(E.max())
    dstep = lambda i, s: float(min(E[min(len(E) - 1, int(i * 360 + (s + 0.5) * 22.5))] / emax * 1.15, 1.0))  # noqa: E731  a dome per day, topped by that day's own sunshine against the run's best
    ss_ = lambda x, a, b: float(np.clip((x - a) / (b - a), 0, 1) ** 2 * (3 - 2 * np.clip((x - a) / (b - a), 0, 1)))  # noqa: E731  smoothstep
    score = dict(bar_s=BAR, lead_s=LEAD, outro_s=OUTRO, bpm=A.bpm, version="groove-v1.2", time_note="stamp labels are local clock time at a fixed UTC-5 (written with a Z for compatibility), not UTC", wind="10 m and 700 hPa wind from the table when present, else |6 h pressure change| stands in",
                 event_hpa=A.event_hpa, bars=[])
    prev_hv = 0.0
    for i, h in enumerate(H):
        t0 = LEAD + i * BAR
        at = lambda s, key=None, off=0.0: int((t0 + step_time(s) + DRAG.get(key, 0.0) + off + rng.normal(0, 0.003)) * SR)  # noqa: E731
        hv = h["hv"]
        dsteps = [dstep(i, s) for s in range(16)]
        day = 0.35 + 0.65 * float(np.mean(dsteps))
        mode = DORIAN if h["tmp"] >= 3 else AEOLIAN
        mname = "Dorian" if h["tmp"] >= 3 else "Aeolian"
        rate = h["rate"]
        # harmony: a four-bar loop per day, drifted up or down the scale by up to two degrees as pressure rises or falls; every pitched voice takes chord tones
        dr = chord_degree(i, h, mname)
        sus = rate <= -3  # falling pressure: the third becomes a suspended fourth, resolved when the pressure turns
        ct = lambda x, base: dmidi(mode, dr + x, base)  # noqa: E731
        chord = NOTE[ct(0, PED) % 12] + ("sus4" if sus else "")
        k_con = int(np.clip(round(np.interp(h["ws"], [0, 40], [3, 9])), 3, 9)) if "ws" in h else int(np.clip(round(3 + abs(rate)), 3, 9))
        wd = h.get("wd")  # accent set for the conga line by 10 m wind direction (labels arbitrary): S/E, W, N
        acc = (0, 3, 6, 9, 12) if wd is None or 45 <= wd < 225 else ((0, 4, 7, 10, 13) if wd < 290 else (0, 3, 7, 10, 13))
        # --- drum anchor: daylight (shortwave) is the pulse of the calm days, rain and snow bring the full kit.
        # v1.1: every hit's loudness follows the day's sunshine curve step by step (smoothstep gates, not a switch per bar), so the pulse swells and fades
        if hv < 0.2:
            for s in (0, 8):
                B["kit"].add(K["perc"].hit("BDrumNewhit_v3", 0.5, rng), at(s, "kick"), gain=0.6)
                B["kit"].add(K["kick"].hit(0.3 + 0.2 * dsteps[s], rng), at(s, "kick"), gain=0.7)
            for s in (4, 12):
                g = ss_(dsteps[s], 0.2, 0.45)
                if g > 0.03:
                    B["kit"].add(K["kick"].hit(0.3 + 0.2 * dsteps[s], rng), at(s, "kick"), gain=0.7 * g)
                g = ss_(dsteps[s], 0.4, 0.65)
                if g > 0.03:
                    B["kit"].add(K["snare"].hit(0.3 + 0.15 * dsteps[s], rng), at(s, "snare"), gain=0.6 * g)
            for s in range(16):
                ds = dsteps[s]
                g = ss_(ds, 0.05, 0.35) if s % 4 == 2 else ss_(ds, 0.45, 0.75)  # offbeat eighths first, the other sixteenths when the sun is strong
                if g > 0.03:
                    B["hi"].add(K["hat"].hit(0.2 + 0.25 * (s % 4 == 2), rng), at(s, "hat"), gain=0.45 * g * (0.5 + 0.5 * ds), pan=0.15)
        else:
            beats = (0, 4, 8, 12) if (hv > 0.35 or abs(rate) >= 4) else (0, 8)
            for s in beats:
                B["kit"].add(K["kick"].hit(0.4 + 0.5 * hv, rng), at(s, "kick"), gain=0.9)
            B["kit"].add(K["snare"].hit(0.45 + 0.4 * hv, rng), at(4, "snare"), gain=0.8)
            B["kit"].add(K["snare"].hit(0.5 + 0.4 * hv, rng), at(12, "snare"), gain=0.85)
            gk = 5 + int(round(4 * hv))
            for s, on in enumerate(euclid(gk, 16)):  # drumline ghost notes
                if on and s % 4 != 0:
                    B["perc"].add(K["perc"].hit("Snare2-taps", 0.25 + 0.3 * hv, rng), at(s, "snare"), gain=0.45)
            for s in range(0, 16, 2):
                B["hi"].add(K["hat"].hit(0.35 + 0.2 * (s % 4 == 2), rng), at(s, "hat"), gain=0.5 * (0.5 + 0.5 * dsteps[s]), pan=0.15)
        if (hv >= 0.5 > prev_hv) or (i % 4 == 0 and hv > 0.1) or i == 0:
            B["cym"].add(K["perc"].hit("cymbal-crash1_mf" if hv < 0.6 else "cymbal-crash1_ff", 0.7, rng), at(0), gain=0.5)
        prev_hv = hv
        # --- conga cycle: pressure change as busyness
        for s, on in enumerate(euclid(k_con, 16)):
            if on:
                ss = (s + i) % 16
                B["perc"].add(K["perc"].hit("Quinto-HitN" if ss in acc else "Conga-HitN", 0.28 + 0.25 * (ss in acc), rng), at(ss, "conga"), gain=0.5)
        # --- rain: log drums + marimba
        if h["rain"] > 0.1:
            kr = int(np.clip(3 + round(h["rain"] * 1.5), 3, 9))
            for s, on in enumerate(euclid(kr, 16)):
                if on:
                    ss = (s + 3 * i) % 16
                    B["perc"].add(K["perc"].hit("LogDrumHi_MedM" if ss % 2 else "LogDrumLo_MedM", 0.45, rng), at(ss, "log"), gain=0.6)
                    if s % 2 == 0:
                        m = ct([0, 2, 4, 7, 4, 2, 0][(ss * 3 + i) % 7], 62)
                        B["mallet"].add(K["marimba"].note(m, 0.4, dur=0.3, release=0.4, rng=rng), at(ss, "log"), gain=0.5, pan=-0.3)
        # --- snow: glock, triangle, ring, bell tree on onset
        if h["snow"] > 0.1:
            ks = int(np.clip(3 + round(h["snow"]), 3, 7))
            for s, on in enumerate(euclid(ks, 16)):
                if on:
                    ss = (s + 5 * i) % 16
                    m = ct([0, 2, 4, 7, 4, 2, 0][(ss + i) % 7], 79 - 7)
                    B["hi"].add(K["glock"].note(m, 0.3 + 0.2 * day, dur=0.4, release=0.8, rng=rng), at(ss, "hat"), gain=0.5, pan=0.35)
                    if s % 2:
                        B["hi"].add(K["perc"].hit("Triangle3-HitM", 0.3, rng), at(ss, "hat"), gain=0.3 * day, pan=-0.2)
            if (i == 0 or H[i - 1]["snow"] <= 0.1):
                B["hi"].add(K["perc"].hit("BellTree_Stroke1", 0.5, rng), at(0), gain=0.5, pan=0.2)
        # --- shaker (daylight): light 16ths
        for s in range(16):
            g = max(ss_(dsteps[s], 0.2, 0.5), 1.0 if hv > 0.15 else 0.0)
            if g > 0.03:
                B["hi"].add(K["perc"].hit("Tamb1-Shake", 0.12 + 0.12 * (s % 4 == 2), rng), at(s, "shake"), gain=0.5 * max(day, dsteps[s]) * g, pan=0.1)
        # --- night hand drums (default; --no-night leaves them out): the sun pulse hands off at dusk to a loose, wind-driven heartbeat of low conga, log drum and brushed tambourine.
        # Own random stream so the rest of the render is untouched; hits are drawn from per-step probabilities, humanized +-10 ms; quiet when rain brings the kit.
        if A.night:
            nr = np.random.default_rng(2610 + i)
            dens = float(np.interp(h.get("ws", 10), [0, 40], [0.7, 1.4]))
            for s_, p_ in ((0, 0.9), (3, 0.22), (6, 0.3), (8, 0.5), (10, 0.7), (12, 0.28), (14, 0.25), (15, 0.18)):
                w = (1 - ss_(dsteps[s_], 0.05, 0.4)) * (1 - hv)
                if w > 0.03 and nr.random() < p_ * dens * w:
                    tt = int((t0 + step_time(s_) + DRAG.get("conga", 0.0) + nr.normal(0, 0.010)) * SR)
                    nm = "LogDrumLo_MedM" if s_ in (0, 8) else "Conga-HitN"
                    B["perc"].add(K["perc"].hit(nm, 0.4 + 0.25 * nr.random(), nr), tt, gain=0.85 * (0.5 + 0.5 * w), pan=-0.1)
            for s_ in (2, 6, 10, 14):
                w = (1 - ss_(dsteps[s_], 0.05, 0.4)) * (1 - hv)
                if w > 0.03 and nr.random() < 0.55 * dens * w:
                    tt = int((t0 + step_time(s_) + nr.normal(0, 0.010)) * SR)
                    B["hi"].add(K["perc"].hit("Tamb1-Shake", 0.25 + 0.15 * nr.random(), nr), tt, gain=0.6 * w, pan=0.15)
        # --- bass: tuba riff on the chord root and fifth, contrabass root each bar, and a quiet low cello drone with its suspension
        root, fifth = ct(0, PED + 12), ct(4, PED + 12)
        riff = euclid(5, 8)
        for j, on in enumerate(riff):
            if on:
                B["bass"].add(K["tuba_s"].note(fifth if j in (3, 6) else root, 0.55 + 0.3 * hv, dur=STEP * 1.6, release=0.1, rng=rng), at(j * 2, "tuba"), gain=0.9)
        B["bass"].add(fade_in(K["cb"].note(ct(0, PED), 0.45, dur=BAR * 1.05, release=0.5, rng=rng), 0.25), at(0), gain=0.8)
        dv = 0.4 * (1 - 0.5 * hv)
        for tone, vel_, g_ in ((ct(0, PED + 12), dv, 1.0), (ct(4, PED + 12), dv * 0.8, 0.8), (ct(3 if sus else 2, PED + 12), dv * (0.9 if sus else 0.6), 0.7)):
            B["drone"].add(fade_in(K["cello"].note(tone, vel_, dur=BAR * 1.2, release=0.6, rng=rng), 0.5), at(0), gain=g_)
        root_lo = ct(0, PED) - 12  # Bear Sax an octave under the chord root
        if -A.event_hpa < rate <= -3:  # a suspension bar: the deep reed holds the root
            B["sax"].add(fade_in(K["bsax"].note(root_lo, 0.45, dur=BAR * 1.0, release=0.5, rng=rng), 0.3), at(0), gain=0.8)
        event = None
        if abs(rate) >= A.event_hpa:
            amt = min(abs(rate) / 10.0, 1.0)
            if rate > 0:
                event = "rise"
                B["timp"].add(K["roll"].hit("", 0.6 + 0.4 * amt, rng), at(0), gain=0.9)
                for j, x_ in enumerate((0, 2, 4)):
                    v = K["vln"].note(ct(x_, PED + 24), 0.35 + 0.3 * amt, dur=BAR * 1.1, release=0.6, rng=rng)
                    B["strings"].add(fade_in(v, 0.6), at(0, off=0.12 * j), gain=0.5)
            else:
                event = "fall"
                B["timp"].add(K["timp"].hit("Timpani", 0.6 + 0.4 * amt, rng), at(0), gain=1.0)
                B["sax"].add(subdrop(ct(0, PED), dur=4.0 + 2 * amt, sweep=5, vel=0.5 + 0.3 * amt), at(0), gain=0.9)
                B["sax"].add(glide(K["bsax"].note(root_lo, 0.55 + 0.3 * amt, dur=BAR * 1.2, release=0.6, rng=rng), -7), at(0), gain=1.0)
                for half, x_ in enumerate((4, 0)):  # the tuba steps down fifth to root
                    tb = K["tuba_l"].note(ct(x_, PED), 0.5 + 0.4 * amt, dur=BAR * 0.5, release=0.3, rng=rng)
                    B["bass"].add(tb, at(0, off=half * BAR * 0.5), gain=0.7)
        # --- wind aloft (700 hPa): cello pizzicato ostinato, density from speed; shear (10 m vs 700 hPa direction) sets the harp counter-line interval
        if "ws700" in h:
            k7 = int(np.clip(round(np.interp(h["ws700"], [10, 100], [2, 8])), 2, 8))
            for s_, on in enumerate(euclid(k7, 16)):
                if on:
                    B["strings"].add(K["cpizz"].note(ct([0, 2, 4, 7][(s_ + i) % 4], PED + 24), 0.45, dur=0.3, release=0.3, rng=rng), at((s_ + 2 * i) % 16), gain=0.45, pan=0.35)
        # --- harp cell in 7 sixteenths, cloud pad
        decay = float(np.interp(max(h["tmp"] - h["dpt"], 0), [0.5, 8], [0.6, 0.25]))
        oct_up = 12 if h["tmp"] >= 6 else 0
        for s in range(0, 16, 1):
            if euclid(5, 7)[s % 7] and s < 14:
                m = ct([0, 2, 4, 7, 4, 2, 1][(s + i) % 7], 62 + oct_up)
                B["harp"].add(K["harp"].note(m, 0.4 + 0.2 * decay, dur=0.45, release=0.5, rng=rng), at(s), gain=0.7, pan=-0.2)
                if "shear" in h:
                    iv = 2 if h["shear"] < 60 else (4 if h["shear"] < 120 else 6)
                    m2 = ct([0, 2, 4, 7, 4, 2, 1][(s + i) % 7] + iv, 62 + oct_up)
                    B["harp"].add(K["harp"].note(m2, 0.3, dur=0.4, release=0.5, rng=rng), at(s, off=0.01), gain=0.4, pan=0.2)
        if h["cloud"] >= 20 and i % 2 == 0:
            B["strings"].add(sustain(K["vln"], ct(4, PED + 12), 0.2 + 0.4 * h["cloud"] / 100, BAR * 2.2, rng, seg=3.5, xf=0.9, release=1.0), at(0), gain=0.5, pan=0.2)
        score["bars"].append(dict(i=i, t=h["t"], tmp=round(h["tmp"], 1), dpt=round(h["dpt"], 1), cloud=round(h["cloud"]), slp=round(h["slp"], 1), rate3=round(rate, 2),
                                  precip=round(h["rain"] + h["snow"], 2), rain=round(h["rain"], 2), snow=round(h["snow"], 2), fz_m=round(h["fz_m"]), mode=mname, chord=chord,
                                  hv=round(hv, 2), p_event=event, sun=[round(x, 2) for x in dsteps], conga_k=k_con, sw=round(h['sw']), **({k: round(h[k]) for k in ('ws', 'wd', 'ws700', 'shear')} if 'ws' in h else {})))
    # --- lead-in and wrap-out (v1.1): drone, harp and the deep reed on the first and last chords; no kit
    def frame(i, h):
        mname = "Dorian" if h["tmp"] >= 3 else "Aeolian"
        mode = DORIAN if h["tmp"] >= 3 else AEOLIAN
        dr = chord_degree(i, h, mname)
        return (lambda x, base: dmidi(mode, dr + x, base)), mode

    ct0, _ = frame(0, H[0])
    for tone, vel_, g_ in ((ct0(0, PED + 12), 0.35, 1.0), (ct0(4, PED + 12), 0.28, 0.8), (ct0(2, PED + 12), 0.22, 0.7)):
        B["drone"].add(fade_in(K["cello"].note(tone, vel_, dur=LEAD + BAR * 0.5, release=1.2, rng=rng), 2.5), int(0.1 * SR), gain=g_)
    B["bass"].add(fade_in(K["cb"].note(ct0(0, PED), 0.4, dur=LEAD, release=0.6, rng=rng), 2.0), int(BAR * 1.0 * SR), gain=0.8)
    B["sax"].add(fade_in(sustain(K["bsax"], ct0(0, PED) - 12, 0.4, LEAD + BAR * 0.2, rng, seg=3.5, xf=0.9, release=0.8), 2.5), int(0.2 * SR), gain=0.9)
    for bar in range(1, LEAD_BARS):  # the harp walks up the chord, then the song's own cell begins
        for q in range(4 if bar < 3 else 8):
            step = BEAT * (1 if bar < 3 else 0.5)
            m = ct0([0, 2, 4, 7, 4, 2, 0, 2][q + (4 if bar == 2 else 0)], 62)
            B["harp"].add(K["harp"].note(m, 0.3 + 0.08 * bar, dur=0.5, release=0.6, rng=rng), int((bar * BAR + q * step) * SR), gain=0.7, pan=-0.2)
    for bar in (2, 3):  # shaker and soft kick come in, as a pulse before the pulse
        for q in range(4 * (bar - 1) * 2):
            tq = bar * BAR + q * BEAT / ((bar - 1) * 2)
            B["hi"].add(K["perc"].hit("Tamb1-Shake", 0.1 + 0.05 * bar, rng), int(tq * SR), gain=0.35 * (bar - 1), pan=0.1)
    B["strings"].add(fade_in(sustain(K["vln"], ct0(4, PED + 12), 0.25, LEAD, rng, seg=3.5, xf=0.9, release=1.0), 3.0), int(BAR * 1.0 * SR), gain=0.5, pan=0.2)
    ctl, _ = frame(nb - 1, H[-1])
    T0 = LEAD + nb * BAR
    for tone, vel_, g_ in ((ctl(0, PED + 12), 0.35, 1.0), (ctl(4, PED + 12), 0.28, 0.8), (ctl(2, PED + 12), 0.22, 0.7)):
        B["drone"].add(fade_in(K["cello"].note(tone, vel_, dur=OUTRO, release=3.5, rng=rng), 0.5), int(T0 * SR), gain=g_)
    B["bass"].add(fade_in(K["cb"].note(ctl(0, PED), 0.4, dur=OUTRO * 0.6, release=2.5, rng=rng), 0.25), int(T0 * SR), gain=0.8)
    B["timp"].add(K["timp"].hit("Timpani", 0.5, rng), int(T0 * SR), gain=0.8)
    for q, x_ in enumerate([7, 4, 2, 0, -3, -5]):  # the harp steps down and rings out
        B["harp"].add(K["harp"].note(ctl(x_, 62), 0.4 - 0.04 * q, dur=0.8, release=1.6, rng=rng), int((T0 + BEAT * 1.5 * q) * SR), gain=0.7, pan=-0.2)
    B["strings"].add(fade_in(sustain(K["vln"], ctl(4, PED + 12), 0.3, OUTRO * 0.7, rng, seg=3.5, xf=0.9, release=2.5), 0.8), int(T0 * SR), gain=0.5, pan=0.2)
    last = sustain(K["bsax"], ctl(0, PED) - 12, 0.5, BAR * 2.0, rng, seg=3.5, xf=0.9, release=1.0)  # the reed's last slide: down a fifth, slowly
    B["sax"].add(fade_in(glide(last, -7), 0.4), int((T0 + 0.1) * SR), gain=1.0)
    B["sax"].add(subdrop(ctl(0, PED), dur=6.0, sweep=7, vel=0.5), int((T0 + BAR * 1.5) * SR), gain=0.8)
    wav = HEAVY / f"{A.name}.wav"
    mix, stems = master(list(B.values()), {"hall": make_ir(2.4, bright=0.5, seed=1016)}, wav)
    mp3 = OUT / f"{A.name}.mp3"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-b:a", "160k", str(mp3)], check=True)  # noqa: S603,S607  fixed argument list, no shell
    score["duration_s"] = round(len(mix) / SR, 1)
    (OUT / f"{A.name}_score.json").write_text(json.dumps(score))
    fr = int(0.5 * SR)
    mono = mix.mean(axis=1)
    rep = {}
    for k_, v in stems.items():
        m = v.mean(axis=1)
        nf = len(m) // fr
        a = np.sqrt((m[:nf * fr].reshape(nf, fr) ** 2).mean(1))
        mr = np.sqrt((mono[:nf * fr].reshape(nf, fr) ** 2).mean(1))
        on = a > 10 ** (-70 / 20)
        rep[k_] = (round(float(on.mean()) * 100), round(float(20 * np.log10(a[on].mean() / mr[on].mean()))) if on.any() else None)
    print("share sounding %, level re mix dB:", rep)
    ev = [b["p_event"] for b in score["bars"]]
    print("hv>0.2: %d bars, >0.5: %d; events rise %d fall %d; rate range %.1f..%.1f hPa/6h; hv:" % (
        sum(h["hv"] > 0.2 for h in H), sum(h["hv"] > 0.5 for h in H), ev.count("rise"), ev.count("fall"), min(h["rate"] for h in H), max(h["rate"] for h in H)),
        " ".join("%.1f" % h["hv"] for h in H))
    print(mp3, round(len(mix) / SR, 1), "s", mp3.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
