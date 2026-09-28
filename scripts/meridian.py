"""
MERIDIAN CHORUS, layer 1: daylight (2026-09-27). Spec: 260927-meridian-chorus-spec.md.

    python meridian.py                    # 100 W, Dec 2023 - Dec 2024 solstices, a week per 8-s breath (~7 min)
    python meridian.py --variant long     # 3 days per breath (~16 min), also cut into four movements
    python meridian.py --set meridian=-120

Thirteen voices stand on one meridian, one every 15 degrees from the North
Pole to the South Pole, and sing through one year from solstice to solstice.
Each breath of the piece is a block of days, and plays ONE day from midnight
to midnight: a voice sounds while the sun is up where it stands, swells in
through civil twilight, and while its sun is down only a faint in-breath is
heard. Every point on a meridian shares solar noon, so all thirteen notes
centre on the same instant, mid-breath: the chorus breathes together. At the
equinoxes every voice is about 12 hours long (a unison); at the solstices one
pole holds a note through the whole breath while the other only breathes.

LAYER          DATA (all D: computed from solar geometry, solar.py)         SOUND
note           sun above -0.833 deg (sunrise/sunset)                        organ + strings + sung voice on the voice's pitch, full level
twilight       sun between -6 and -0.833 deg                                the note swells in / fades out at up to 30% level
vowel          sun's altitude                                               the sung voice opens from "oo" to "ah" as the sun climbs
in-breath      sun below the horizon, fading out through twilight           filtered-noise inhale, very quiet, peaking at midnight;
                                                                            steady at the poles (no daily rise and fall there)

PITCH (register "north-high", chord "pentatonic"): the voices are notes of the
D major pentatonic (D E F# A B), D at both poles and the equator, north above
and south below, D2..D6. No two are a semitone or tritone apart, so any subset
is consonant (the wind-chime principle), while the subset that is sounding
colours the season. A "triad" chord (D F# A only) is kept for comparison.

LAYER 2 (2026-09-27, GW: "air temp and sea temp and sea ice ... we may need more
space in the main chorus"). Off by default, so layer 1 renders unchanged; the
layer-2 variants turn it on (variants/meridian.yaml). Data: fetch_meridian.py.
To make room, the chorus is un-doubled: each medium gets its own family.

LAYER   DATA (per breath: the mean over its block of days)          SOUND
light   daylight, as layer 1                                        the sung voice (the chorus proper)
air     ERA5 daily max 2 m temperature (D)                          the organ's registration: cold is one dark rank, warm
                                                                     adds the octave rank and opens the tone (heat as energy)
        ERA5 daily min 2 m temperature (D)                          the in-breath: a warm night adds a lower, fuller band
sea     NOAA OISST sea surface temperature (R), ocean voices        a low string voice an octave under the parallel, heard
                                                                     day AND night (the ocean doesn't sleep); warm is fuller
ice     NOAA/NSIDC sea-ice concentration (R), 4 polar voices        a lid on the sea voice (ice quiets it) and a high glass
                                                                     shimmer, as loud as the ice is dense
"Warm" is one direction throughout: more energy, a fuller and brighter sound.
`air_scale` "absolute" puts every voice on one thermometer (-40..35 C), so the
equator is always brighter than the poles; "seasonal" stretches each voice's own
year over the full range, so every parallel's seasons are equally audible.
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

DEFAULTS = {
    "year": "ds2023",          # solstice framing: Dec 2023 solstice to Dec 2024 solstice
    "meridian": -100.0,        # degrees east; 100 W
    "days_per_breath": 7,
    "breath_s": 8.0,
    "register": "north-high",  # or "poles-high": the equator lowest, both poles highest
    "chord": "pentatonic",     # or "triad": D, F#, A only
    "timbre": {"organ": 1.0, "strings": 0.8, "voice": 0.7},
    "twilight": True,
    "breath_level": 0.018,
    "movements": False,        # also cut the render into four movements at the solstices and equinoxes
    "layers": ["daylight"],    # layer 2 adds "air", "sea", "ice" (data from fetch_meridian.py)
    "air_scale": "absolute",   # or "seasonal": each voice's own year spans the full range
    "air_range": [-40.0, 35.0],
    "sea_range": [-2.0, 30.0],
    "sea_octave": -1,          # the sea voice an octave under its parallel; 0 = the parallel's own note
    "sea_level": 1.1,
    "ice_level": 0.12,
    "sea_floor": False,        # True: the sea on its own floor under the chorus (SEA_FLOOR), not under each parallel
    "hemisphere": False,       # True: north left and south right, and each hemisphere fuller in its own summer
    "breath_tone": "air",      # or "dark": a quieter, lower in-breath (breath, not hiss)
    "glass_range": [84, 96],
    "mute": [],
    "gains": {},
    "seed": 2023,
}

LATS = [90, 75, 60, 45, 30, 15, 0, -15, -30, -45, -60, -75, -90]
PITCH = {  # MIDI, by (register, chord). D at both poles and the equator in north-high.
    # pentatonic (D E F# A B): no semitone or tritone between any two notes, so any subset is
    # consonant, but which voices sound changes the colour: long northern days (upper voices)
    # lean suspended and open, long southern days (lower voices) lean toward B minor.
    ("north-high", "pentatonic"): dict(zip(LATS, [86, 81, 76, 71, 69, 64, 62, 59, 57, 52, 47, 42, 38])),
    ("north-high", "triad"): dict(zip(LATS, [86, 81, 78, 74, 69, 66, 62, 57, 54, 50, 45, 42, 38])),
    ("poles-high", "pentatonic"): dict(zip(LATS, [74, 69, 64, 59, 57, 52, 50, 52, 57, 59, 64, 69, 74])),
    ("poles-high", "triad"): dict(zip(LATS, [74, 69, 66, 62, 57, 54, 50, 54, 57, 62, 66, 69, 74])),
    # "wide" (layer 2.1, 09-27): the sky sits wholly above the sea floor, D4..A6, 13 distinct notes, so no
    # voice shares a pitch with another voice or with the sea (GW: "a lot of unison ... hard to hear separation")
    ("north-high", "wide"): dict(zip(LATS, [93, 90, 88, 86, 83, 81, 78, 76, 74, 71, 69, 66, 62])),
}
SEA_FLOOR = {  # layer 2.1: the sea's own register, open intervals low (D1 A1 D2), closer higher (F#2 A2 D3 F#3 A3);
    # ordered by each sea's mean temperature, warmest highest. 90 N's sea is lidded by ice all year: the glass carries it.
    15: 57, 0: 54, -15: 50, -30: 45, -45: 42, -60: 38, 75: 33, -75: 26,
}
PLACES = {  # 100 W; spec section 2 (unverified place facts are marked there)
    90: ("North Pole", "sea ice"), 75: ("Bathurst Island, Nunavut", "land, sea ice"),
    60: ("Nunavut-Manitoba boundary", "land"), 45: ("near Gettysburg, South Dakota", "land"),
    30: ("Edwards Plateau, Texas", "land"), 15: ("Pacific, south of Acapulco", "ocean"),
    0: ("Equatorial Pacific, cold tongue", "ocean"), -15: ("Southeast Pacific", "ocean"),
    -30: ("Southeast Pacific", "ocean"), -45: ("Southern Ocean", "ocean"),
    -60: ("Southern Ocean", "ocean, sea ice"), -75: ("Pine Island Glacier basin", "ice sheet"),
    -90: ("South Pole", "ice sheet"),
}
CTRL = 200  # control rate (Hz) for the envelopes, interpolated to audio


def solar_track(Y_, P, n_breaths):
    """Per-control-sample hour angle and declination for the whole piece.
    Breath k plays one day, the block's middle day, at that day's noon
    declination, so each note is symmetric about the shared noon. Around
    midnight (the outer 10% of a breath) the declination blends halfway to its
    neighbours', so a voice in polar day doesn't step between breaths."""
    dpb, B = P["days_per_breath"], P["breath_s"]
    noon_utc = 12 - P["meridian"] / 15.0
    d_k = np.array([solar.declination(Y_.start + dt.timedelta(k * dpb + dpb // 2), noon_utc)
                    for k in range(n_breaths)])
    t = np.arange(int(n_breaths * B * CTRL)) / CTRL
    k = np.minimum(n_breaths - 1, (t // B).astype(int))
    frac = (t / B) % 1.0                                   # 0 = midnight, 0.5 = noon
    hour_angle = (frac - 0.5) * 360.0
    prev = d_k[np.maximum(k - 1, 0)]
    nxt = d_k[np.minimum(k + 1, n_breaths - 1)]
    here = d_k[k]
    w_in = np.clip((0.1 - frac) / 0.1, 0, 1) * 0.5          # 0.5 at midnight, 0 by 10% into the breath
    w_out = np.clip((frac - 0.9) / 0.1, 0, 1) * 0.5
    decl = here + w_in * (prev - here) + w_out * (nxt - here)
    return t, hour_angle, decl, frac


def envelopes(lat, hour_angle, decl, frac, twilight):
    """-> (note level, vowel openness, in-breath level), each 0..1 at the control rate.
    The note is full whenever the sun is up (sun's centre above -0.833 deg), so its
    length is the day's length at every latitude; with `twilight` it also swells in
    and out at 30% through civil twilight, as the in-breath fades out and back in.
    The in-breath pulses once a breath, peaking at midnight, as deeply as the sun's
    daily rise and fall at that latitude (cos lat): at a pole, where the sun circles
    at one height, it is one steady breath."""
    alt = solar.altitude(lat, decl, hour_angle)
    up = (alt >= solar.SUNRISE).astype(float)
    if twilight:
        tw = np.clip((alt - solar.CIVIL) / (solar.SUNRISE - solar.CIVIL), 0, 1)
        note = np.where(up > 0, 1.0, 0.3 * tw ** 1.5)
        night = (1 - tw) * (1 - up)
    else:
        note = up
        night = 1 - up
    k = int(0.08 * CTRL)                                             # 80 ms smoothing: no clicks at a hard edge
    note = np.convolve(np.pad(note, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), "same")[k:-k]
    vowel = np.clip(alt / 40.0, 0, 1)
    depth = np.cos(np.radians(lat))
    inhale = night * (1 - depth * (0.5 - 0.5 * np.cos(2 * np.pi * frac)))
    return note, vowel, inhale


def to_audio(x, n):
    return np.interp(np.arange(n) / SR, np.arange(len(x)) / CTRL, x).astype(np.float32)


def sung_voice(midi, n, vowel, rng):
    """A small synthesized choir on one pitch: three saws with their own slow
    vibrato, through 'oo' and 'ah' formant filters, crossfaded by `vowel`
    (0..1 at audio rate). Not a sample of any real voice."""
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


def strings_for(K, midi):
    return K["bass"] if midi < 45 else K["cello"] if midi < 60 else K["vln"]


def movement_cuts(Y_, P, n_breaths):
    """Breath indices of the March equinox, June solstice and September equinox:
    the breaths whose played day is nearest each event, found from the declination
    at local noon on every day of the year."""
    dpb = P["days_per_breath"]
    noon_utc = 12 - P["meridian"] / 15.0
    decl = np.array([solar.declination(Y_.start + dt.timedelta(d), noon_utc) for d in range(Y_.n_days)])
    events = [d for d in range(1, Y_.n_days) if (decl[d] > 0) != (decl[d - 1] > 0)]   # the equinoxes
    events.append(int(np.argmax(decl)))                                                  # the June solstice
    return sorted({min(n_breaths - 1, int(round((d - dpb // 2) / dpb))) for d in events})


DATA = Path(__file__).resolve().parent.parent / "data" / "meridian"


def covariates(Y_, P, n_breaths):
    """-> {lat: {"tmax", "tmin", "sst", "ice": per-breath arrays (block means) or None},
    plus "filled" / "ice_filled": days interpolated across OISST's gaps and the sea-ice
    days dropped by fetch_meridian.py (land-spillover filter)}. Breath k's block is
    days k*dpb .. (k+1)*dpb - 1, like the daylight's."""
    lon = P["meridian"]
    j = json.loads((DATA / f"meridian_{abs(lon):.0f}{'w' if lon < 0 else 'e'}_{Y_.label.lower()}.json").read_text())
    dpb = P["days_per_breath"]
    days = [str(Y_.start + dt.timedelta(d)) for d in range(Y_.n_days)]

    def daily(dates, vals):
        m = dict(zip(dates, vals))
        x = np.array([np.nan if m.get(d) is None else m[d] for d in days], dtype=float)
        gap = np.isnan(x)
        if gap.all():
            return None, 0
        idx = np.arange(len(x))
        x[gap] = np.interp(idx[gap], idx[~gap], x[~gap])   # OISST has a few missing days; SST changes slowly
        return x, int(gap.sum())

    def blocks(x):
        return None if x is None else np.array([x[k * dpb:(k + 1) * dpb].mean() for k in range(n_breaths)])

    out = {}
    for lat in LATS:
        v = j["voices"][str(lat)]
        a = v["air"]
        tmax, _ = daily(a["date"], a["max"])
        tmin, _ = daily(a["date"], a["min"])
        sst, filled = daily(v["sst"]["date"], v["sst"]["sst"]) if v.get("sst") else (None, 0)
        ice, ice_filled = daily(v["ice"]["date"], v["ice"]["conc"]) if v.get("ice") else (None, 0)
        out[lat] = {"tmax": blocks(tmax), "tmin": blocks(tmin), "sst": blocks(sst), "ice": blocks(ice),
                    "filled": filled, "ice_filled": ice_filled, "src": {k: {kk: vv for kk, vv in v[k].items() if not isinstance(vv, list) or kk == "cell"}
                                             for k in ("air", "sst", "ice") if v.get(k)}}
    return out


def warmth(x, lo, hi):
    return np.clip((np.asarray(x) - lo) / (hi - lo), 0, 1)


def per_breath_curve(vals, B, t):
    """A per-breath value as a control-rate curve, linear between breath centres (noon)."""
    return np.interp(t, (np.arange(len(vals)) + 0.5) * B, vals)


def lowpass(x, hz):
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(2, min(hz, SR * 0.45), "lowpass", fs=SR, output="sos"), x, axis=0).astype(np.float32)


def glass(midi, n, level, rng):
    """Sea ice's shimmer: a bowed-glass tone (two sines a fraction of a hertz apart,
    so it beats slowly, plus the glass's inharmonic 2.76 partial), amplitude `level`
    (0..1, audio rate)."""
    t = np.arange(n) / SR
    f = float(Y.midi_hz(midi))
    beat = rng.uniform(0.25, 0.6)
    x = (np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) + 0.6 * np.sin(2 * np.pi * (f + beat) * t)
         + 0.18 * np.sin(2 * np.pi * 2.756 * f * t + rng.uniform(0, 6.28)))
    # it glints rather than drones: slow, irregular swells between 35% and 100% (texture, not data)
    k = np.cumsum(rng.standard_normal(int(n / SR * 2) + 2))
    k = (k - k.min()) / (np.ptp(k) + 1e-9)
    glint = 0.35 + 0.65 * np.interp(t, np.arange(len(k)) / 2, k) ** 2
    return (x / 2.2 * level * glint).astype(np.float32)


def season_fullness(lat, Y_, P, n_breaths):
    """0 in a voice's own midwinter, 1 in its midsummer: that breath's day length on the
    latitude's own range (0.5 where the year barely changes it, near the equator)."""
    dpb = P["days_per_breath"]
    dl = np.array([solar.day(lat, Y_.start + dt.timedelta(k * dpb + dpb // 2))["daylength"] for k in range(n_breaths)])
    return np.full(n_breaths, 0.5) if np.ptp(dl) < 1.0 else (dl - dl.min()) / np.ptp(dl)


def fold(midi, lo=84, hi=96):
    while midi < lo:
        midi += 12
    while midi > hi:
        midi -= 12
    return midi


def main():
    P, Y_, NAME, META = V.setup("meridian", DEFAULTS)
    OUT, HEAVY = W.LIGHT_OUT / "meridian", W.HEAVY_OUT / "meridian"
    OUT.mkdir(parents=True, exist_ok=True)
    HEAVY.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(P["seed"])
    np.random.seed(P["seed"])
    print(f"seeds: {P['seed']}")

    B_s, dpb = float(P["breath_s"]), int(P["days_per_breath"])
    n_breaths = -(-Y_.n_days // dpb)
    tail = 7.0
    n = int((n_breaths * B_s + tail) * SR)
    print(f"{NAME}: {Y_.label} {Y_.start}..{Y_.end}, {n_breaths} breaths x {B_s} s = {n_breaths * B_s / 60:.1f} min")

    t, hour_angle, decl, frac = solar_track(Y_, P, n_breaths)
    pitch = PITCH[(P["register"], P["chord"])]
    K = S.vsco_kit()
    organ = Instrument("Keys/Organ/Quiet", glob="NT5_Man3Quiet_*.wav",
                       mapping=lambda nm: (int(nm.split("_")[2]) - 86, 1))  # file number - 86 = MIDI (FFT-checked 09-27)
    tim = P["timbre"]
    B = {k: Bus(k, n, **kw) for k, kw in V.bus_settings({
        "organ": dict(gain=1.6 * tim.get("organ", 0), hp=60, send=0.45),
        "strings": dict(gain=0.5 * tim.get("strings", 0), hp=50, send=0.5),
        "voice": dict(gain=0.9 * tim.get("voice", 0), hp=120, send=0.6),
        "breath": dict(gain=1.0, hp=300, send=0.3),
        **({"sea": dict(gain=P["sea_level"], hp=35, send=0.55)} if "sea" in P["layers"] else {}),
        **({"ice": dict(gain=P["ice_level"], hp=500, send=0.7)} if "ice" in P["layers"] else {}),
    }, P).items()}
    L2 = set(P["layers"]) - {"daylight"}
    COV = covariates(Y_, P, n_breaths) if L2 else None

    env_out, rows, warm_out, sea_out = {}, [], {}, {}
    for i, lat in enumerate(LATS):
        midi = pitch[lat]
        note, vowel, inhale = envelopes(lat, hour_angle, decl, frac, P["twilight"])
        env_out[lat] = note
        a_note, a_vowel, a_in = (to_audio(x, n) for x in (note, vowel, inhale))
        pan = (0.28 if i % 2 else -0.28) * (abs(lat) / 90) ** 0.5
        if P["hemisphere"]:  # north on the left, south on the right, the equator in the middle
            pan = -np.sign(lat) * (0.12 + 0.5 * abs(lat) / 90)
            full = to_audio(per_breath_curve(season_fullness(lat, Y_, P, n_breaths), B_s, t), n)
        vel = 0.55
        span = n_breaths * B_s + 1.0
        if L2:
            c = COV[lat]
            lo, hi = P["air_range"]
            if P["air_scale"] == "seasonal":
                lo, hi = min(c["tmin"].min(), c["tmax"].min()), max(c["tmin"].max(), c["tmax"].max())
            w_day = to_audio(per_breath_curve(warmth(c["tmax"], lo, hi), B_s, t), n)[:, None]
            w_night = to_audio(per_breath_curve(warmth(c["tmin"], lo, hi), B_s, t), n)
            warm_out[lat] = {"day": warmth(c["tmax"], lo, hi), "night": warmth(c["tmin"], lo, hi)}
        if tim.get("organ", 0):
            x = S.sustain(organ, midi, vel, span, rng, seg=9.0, xf=2.0, release=1.0)[:n]
            if "air" in L2:
                # registration by air temperature: cold = one rank, darkened; warm = + the octave rank, open
                x4 = (S.sustain(organ, midi + 12, vel * 0.8, span, rng, seg=9.0, xf=2.0, release=1.0)[:n]
                      if midi + 12 <= 98 else np.zeros_like(x))   # the organ's top: no octave rank above D7
                dark = lowpass(x, 1.6 * float(Y.midi_hz(midi)))
                x = (1 - w_day[:len(x)]) * dark + w_day[:len(x)] * (x + 0.45 * x4[:len(x)])
            B["organ"].add(x * a_note[:len(x), None], 0, pan=pan)
        if tim.get("strings", 0):
            x = S.sustain(strings_for(K, midi), midi, vel, span, rng)[:n]
            B["strings"].add(x * a_note[:len(x), None], 0, pan=-pan)
        if tim.get("voice", 0):
            if P["hemisphere"]:  # fuller and more open in its own summer, withdrawn to "oo" in its winter
                x = sung_voice(midi, n, a_vowel * (0.55 + 0.45 * full), rng) * a_note * (0.6 + 0.6 * full)
                B["voice"].add(Y.stereo(x * 0.5, width=0.3), 0, pan=pan * 0.8)
            else:
                x = sung_voice(midi, n, a_vowel, rng) * a_note
                B["voice"].add(Y.stereo(x * 0.5, width=0.3), 0, pan=pan * 0.5)
        f0 = float(Y.midi_hz(midi))
        if P["breath_tone"] == "dark":  # breath, not hiss: a low band, about 8 dB down
            air = Y.bandpass(rng.standard_normal(n), 250, min(2600, max(900, 2 * f0)))
            B["breath"].add(Y.stereo(air * a_in * P["breath_level"] * 0.4, width=0.5), 0, pan=pan)
        else:
            air = Y.bandpass(rng.standard_normal(n), min(9000, max(500, 3 * f0)), min(14000, max(2500, 12 * f0)))
            B["breath"].add(Y.stereo(air * a_in * P["breath_level"], width=0.5), 0, pan=pan)
        if "air" in L2:  # a warm night breathes fuller: a lower band, near the voice's own register
            body = Y.bandpass(rng.standard_normal(n), max(120, 1.2 * f0), min(6000, max(900, 4 * f0)))
            B["breath"].add(Y.stereo(body * a_in * w_night * P["breath_level"] * 1.3, width=0.5), 0, pan=pan)
        if L2:
            fade = np.minimum(1, np.minimum(np.arange(n) / (2 * SR), (n - np.arange(n)) / (5 * SR))).astype(np.float32)
        if "ice" in L2 and c["ice"] is not None:
            ice_a = to_audio(per_breath_curve(c["ice"], B_s, t), n)
        else:
            ice_a = np.zeros(n, dtype=np.float32)
        sea_pitch = (SEA_FLOOR.get(lat) if P["sea_floor"] else midi + 12 * P["sea_octave"]) if L2 else None
        if "sea" in L2 and c["sst"] is not None and sea_pitch is not None:
            # the ocean doesn't sleep: a low string voice under the parallel, day and night;
            # warm water is fuller and louder, and sea ice puts a lid on it
            ps = sea_out[lat] = sea_pitch
            w_sea = to_audio(per_breath_curve(warmth(c["sst"], *P["sea_range"]), B_s, t), n)
            xs = S.sustain(strings_for(K, ps), ps, 0.45, span, rng, seg=6.0, xf=1.8)[:n]
            dark = lowpass(xs, 1.5 * float(Y.midi_hz(ps)))
            ws = w_sea[:len(xs), None]
            lid = (1 - 0.85 * ice_a) * (0.55 + 0.45 * w_sea) * fade
            B["sea"].add(((1 - ws) * dark + ws * xs) * lid[:len(xs), None], 0, pan=pan * 0.7 if P["hemisphere"] else -pan)
            warm_out[lat]["sea"] = warmth(c["sst"], *P["sea_range"])
        if "ice" in L2 and c["ice"] is not None:
            pi_ = fold(midi, *P["glass_range"])
            B["ice"].add(Y.stereo(glass(pi_, n, ice_a * fade, rng) * 0.35, width=0.6), 0, pan=pan * 1.5)
        print(f"  {lat:+3d}: MIDI {midi}" + (f"  sea {sea_pitch}" if L2 and c["sst"] is not None and "sea" in L2 and sea_pitch else "")
              + (f"  ice {fold(midi, *P['glass_range'])}" if L2 and c["ice"] is not None and "ice" in L2 else ""))

    irs = {"hall": make_ir(5.5, bright=0.5, seed=23)}
    mix, stems = S.master([b for k, b in B.items() if k not in P["mute"]], irs, HEAVY / f"{NAME}.wav",
                          stems_dir=HEAVY / f"{NAME}_stems")
    S.to_mp3(HEAVY / f"{NAME}.wav", OUT / f"{NAME}.mp3")

    # --------------------------------------------------------- score + data --
    breaths = []
    for k in range(n_breaths):
        d = Y_.start + dt.timedelta(k * dpb + dpb // 2)
        days = [solar.day(lat, d) for lat in LATS]
        breaths.append({"breath": k, "t": round(k * B_s, 2), "date": str(d), "declination": round(days[0]["declination"], 3),
                        "voices": [[round(x["daylength"], 3), round(x["twilight"], 3), x["sunrise"] and round(x["sunrise"], 3),
                                    x["sunset"] and round(x["sunset"], 3), round(x["noon_altitude"], 2)] for x in days]})
    cuts = movement_cuts(Y_, P, n_breaths)
    score = {"name": NAME, "meridian": P["meridian"], "year": Y_.label, "start": str(Y_.start), "end": str(Y_.end),
             "days_per_breath": dpb, "breath_s": B_s, "n_breaths": n_breaths, "duration_s": n / SR,
             "register": P["register"], "chord": P["chord"], "timbre": tim, "twilight": P["twilight"],
             "voices": [{"lat": lat, "midi": pitch[lat], "place": PLACES[lat][0], "surface": PLACES[lat][1]} for lat in LATS],
             "voice_columns": ["daylength_h", "twilight_h", "sunrise_solar_h", "sunset_solar_h", "noon_altitude_deg"],
             "breaths": breaths, "movement_cuts_breath": cuts,
             "stem_rms_db": {k: float(20 * np.log10(np.sqrt((v ** 2).mean()) + 1e-12)) for k, v in stems.items()}}
    if L2:
        r = lambda a, nd=2: None if a is None else [round(float(x), nd) for x in a]
        score["layers"] = P["layers"]
        score["air_scale"], score["air_range"], score["sea_range"] = P["air_scale"], P["air_range"], P["sea_range"]
        score["sea_octave"] = P["sea_octave"]
        score["sea_pitch"] = {str(k): v for k, v in sea_out.items()}
        score["sea_floor"], score["hemisphere"], score["breath_tone"] = P["sea_floor"], P["hemisphere"], P["breath_tone"]
        score["covariate_columns"] = ["air_max_c", "air_min_c", "sst_c", "ice_frac"]
        score["covariates"] = {str(lat): {"air_max_c": r(COV[lat]["tmax"], 1), "air_min_c": r(COV[lat]["tmin"], 1),
                                          "sst_c": r(COV[lat]["sst"]), "ice_frac": r(COV[lat]["ice"]),
                                          "sst_days_interpolated": COV[lat]["filled"],
                                          "ice_days_interpolated": COV[lat]["ice_filled"], "sources": COV[lat]["src"]}
                               for lat in LATS}
        score["warmth"] = {str(lat): {k: r(v, 3) for k, v in w.items()} for lat, w in warm_out.items()}
    if META:
        score["variant"] = META
    with open(OUT / f"{NAME}_score.json", "w") as fh:
        json.dump(score, fh, indent=1)

    # the visual's loudness track: each voice's note envelope at 8 Hz (exactly what shapes its sound)
    step = CTRL // 8
    viz = {k: v for k, v in score.items() if k != "stem_rms_db"}
    viz["env_hz"] = 8
    viz["env"] = [[int(round(100 * x)) for x in env_out[lat][::step]] for lat in LATS]
    viz["audio"] = f"{NAME}.mp3"
    (OUT / f"{NAME}_viz.json").write_text(json.dumps(viz, separators=(",", ":")))

    if P["movements"]:
        # cut at midnight (a breath boundary) with no fades, so the four play back to back without a seam;
        # only the first opens and the last closes (both already faded by the master)
        # loudness-normalize the whole piece once, then cut, so the movements keep one level across the joins
        norm = HEAVY / f"{NAME}_norm.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(HEAVY / f"{NAME}.wav"),
                        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(SR), str(norm)], check=True)
        full, _ = S.sf.read(norm)
        edges = [0] + [c * B_s for c in cuts] + [len(full) / SR]
        for m, (a, b) in enumerate(zip(edges[:-1], edges[1:]), 1):
            w = HEAVY / f"{NAME}_movement{m}.wav"
            S.sf.write(w, full[int(round(a * SR)):int(round(b * SR))].astype(np.float32), SR)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(w), "-b:a", "192k",
                            str(OUT / f"{NAME}_movement{m}.mp3")], check=True)
            print(f"  movement {m}: {a / 60:.1f}-{b / 60:.1f} min")
    print(f"cuts at breaths {cuts}; stems dBFS", {k: round(v, 1) for k, v in score["stem_rms_db"].items()})


if __name__ == "__main__":
    main()
