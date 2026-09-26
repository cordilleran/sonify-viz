"""
PILOT A - Granby River, water year 2023-24 (Oct 1 2023 - Sep 30 2024).
Key of D, 72 bpm, 1 bar = 3 days, ~7 minutes.

A warm El Nino winter: the Granby gauge flagged only 28 ice days, in broken
episodes, and the freshet came early and small (peak 147 m3/s vs 465 in the
2010-24 record). The piece should sound like a year that never fully
committed to winter.

LAYER             DATA (R = retrieved, D = derived, S = simulated)       SOUND
piano ostinato    Granby flow, in-year level (R)                        density: half notes -> 8ths
harmony / mode    day length (D) + Granby flow vs 15-yr normal (R)      mode brightness, 1 step per 8 bars
progression       hydrologic phase from Granby flow (D)                 which 4-chord loop plays
bass / cello      Granby flow (R)                                       contrabass root; cello 5th above at high flow
string pad        MODIS GPP, Granby valley (R) [GDD fallback (D)]       violins swell with plant productivity
ice               WSC "Ice Conditions" flag (R) + Billings temp (R)     freeze: glock + bowed cymbal; crackle + singing-ice
                                                                        chirps while frozen; breakup: cymbal swell + harp
rain / snow       Billings TOTAL_RAIN / TOTAL_SNOW (R)                  rain = harp drops, snow = glockenspiel flakes
reverb space      Billings snow on ground (R)                           snow cover = dark, short room (snow absorbs sound)
hand percussion   Burrell Creek flow + flashiness (R)                   tumba/conga/shaker, tresillo 3-3-2 at peak
redband trout     spawning window from temp proxy + season (S)          flute: short rising figure
whitefish         fall spawning window from temp proxy (S)              cello pizzicato: falling figure
birds             typical phenology windows (S timing, R recordings)     dipper (winter), thrush + bank swallow (summer)
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sampler as S
from sampler import Bus, bird_phrases, make_ir, SR
import seasonal as W
from seasonal import DAYS, N_DAYS, N_BARS, per_bar, smooth, norm01
from dsp_core import ice_crinkle_grain


def main():
    OUT = W.HERE / "rendered" / "pilots"
    OUT.mkdir(parents=True, exist_ok=True)
    HEAVY = W.HEAVY_OUT / "pilots"  # WAV + stems (large) live in runtime
    HEAVY.mkdir(parents=True, exist_ok=True)
    NAME = "granby_wy2024"
    rng = np.random.default_rng(2024)
    np.random.seed(2024)  # the ice grain helper uses the global RNG; seed it so renders repeat exactly

    TONIC = 50  # D3
    BPM = 72
    g = W.Grid(BPM)
    print(f"{N_BARS} bars, {g.dur / 60:.1f} min")

    # --------------------------------------------------------------- features --
    q_all, q_sym = W.wsc_series("granby_08NN002_2010_2024.json")
    b_all, _ = W.wsc_series("burrell_08NN023_2010_2024.json")
    clim = "billings_1100_climate_2010_2024.json"
    q = W.wy(q_all)
    qn = norm01(np.log(q))                                   # in-year level 0..1
    qpct = W.doy_percentile(q_all)                           # vs. 15-yr normal
    ice = np.array([q_sym.get(str(d)) == "Ice Conditions" for d in DAYS])
    bq = W.wy(b_all)
    bn = norm01(np.log(bq))
    bflash = norm01(np.abs(np.diff(np.log(bq), prepend=np.log(bq[0]))))
    T = W.wy(W.climate_series(clim, "MEAN_TEMPERATURE"))
    rain = W.wy(W.climate_series(clim, "TOTAL_RAIN"), fill="zero")
    snow = W.wy(W.climate_series(clim, "TOTAL_SNOW"), fill="zero")
    sog = W.wy(W.climate_series(clim, "SNOW_ON_GROUND"), fill="zero")
    DL = W.daylength(49.03)
    gpp, gppn = W.modis_gpp_daily("granby_valley")
    GPP_SOURCE = "MODIS MOD17A2HGF (retrieved)"
    if gpp is None:
        gdd = W.growing_degree_days(T)
        gppn = np.clip(smooth(np.maximum(0, T - 5), 21) / 12, 0, 1) * (gdd > 60)
        GPP_SOURCE = "growing-degree proxy from Billings temperature (derived; MODIS pull unavailable)"
    doy = np.array([d.timetuple().tm_yday for d in DAYS])
    Tproxy = smooth(T, 14)  # stand-in for water temperature (no Granby stream temp on record)

    # ---------------------------------------------------------------- harmony --
    bright = per_bar(0.7 * norm01(DL, 0, 100) + 0.3 * norm01(smooth(T, 15)))
    anom = per_bar(smooth(qpct, 15)) - 0.5
    modes = W.mode_track(bright, anom, lo=1, hi=4)

    # phase uses LINEAR flow share of the year's peak (log flow, used for the
    # piano, would call a 20 m3/s February bump a "peak")
    qlin = smooth(q / q.max(), 9)
    dq = np.gradient(qlin)
    phase_day = np.where(ice | ((qlin < 0.1) & ((doy > 300) | (doy < 60))), "dormant",
                 np.where(qlin > 0.5, "peak",
                 np.where((dq > 0.004) & (qlin > 0.1), "rising",
                 np.where((dq < -0.003) & (qlin > 0.15), "recession", "low"))))
    PROG = {  # scale degrees (0 = tonic). Each loop is 4 chords x 2 bars.
        "dormant":   [0, 5, 0, 3],   # i  VI  i  iv   - still, circling home
        "rising":    [0, 3, 4, 5],   # i  iv  v  VI   - climbs, doesn't resolve
        "peak":      [5, 3, 0, 4],   # VI iv  i  v    - wide, 'anthemic'
        "recession": [0, 6, 5, 3],   # i  VII VI iv   - bass steps down: letting go
        "low":       [0, 3, 0, 5],   # i  iv  i  VI   - sparse, late-summer
    }
    bar_phase = W.phase_bars(phase_day, min_run=6)
    chords = W.chord_track(bar_phase, PROG, bars_per_chord=2)

    # ------------------------------------------------------------ instruments --
    K = S.vsco_kit()
    piano, bass, cello, cpizz, vln = K["piano"], K["bass"], K["cello"], K["cpizz"], K["vln"]
    flute, harp, glock, perc = K["flute"], K["harp"], K["glock"], K["perc"]

    n = g.n
    B = {k: Bus(k, n, **kw) for k, kw in {
        "piano":  dict(gain=1.0, hp=70, send=0.35),
        "bass":   dict(gain=0.55, lp=900, send=0.12),
        "pad":    dict(gain=0.28, hp=220, send=0.6),
        "ice":    dict(gain=1.5, hp=500, send=0.5),
        "precip": dict(gain=1.05, hp=250, send=0.55),
        "perc":   dict(gain=2.0, hp=60, send=0.15),
        "fish":   dict(gain=0.24, hp=150, send=0.5),
        "birds":  dict(gain=0.2, hp=900, send=0.35),
    }.items()}
    events = []  # (seconds, label) -> listening guide


    def mark(sec, text):
        events.append((round(sec, 1), text))


    def tones(b, lo, hi, prev=None, ext=(0, 2, 4, 8)):
        return W.voice_lead(prev, W.chord(chords[b], modes[b], TONIC, ext), lo, hi)


    # ---------------------------------------------------------- piano + bass --
    PATTERN = [0, 2, 3, 2, 1, 2, 3, 2]  # indexes into the 4-note voicing, low->high
    DENSITY = {0: [0, 4], 1: [0, 2, 4, 6], 2: list(range(8)), 3: list(range(8))}
    qn_bar, dl_bar = per_bar(qn), per_bar(norm01(DL, 0, 100))
    prev = None
    for b in range(N_BARS):
        v = tones(b, 55, 77, prev)
        prev = v
        lvl = int(np.sqrt(qn_bar[b]) * 3.99)
        base_vel = 0.28 + 0.3 * dl_bar[b] + 0.15 * qn_bar[b]
        for step in DENSITY[lvl]:
            vel = np.clip(base_vel + (0.1 if step in (0, 4) else 0) + rng.normal(0, 0.03), 0.1, 0.95)
            B["piano"].add(piano.note(v[PATTERN[step]], vel, dur=g.beat * 1.3, release=0.9, rng=rng),
                           g.s(b, step * 0.5, jitter_ms=7, rng=rng), pan=-0.1 + 0.05 * (PATTERN[step] - 1.5))
            if lvl == 3 and step in (3, 7):  # a soft upper-octave echo at full flow
                B["piano"].add(piano.note(v[PATTERN[step]] + 12, vel * 0.5, dur=g.beat, release=0.8, rng=rng),
                               g.s(b, step * 0.5 + 0.25, jitter_ms=5, rng=rng), pan=0.25)
        # left hand: low root each bar (the 'ground' under the ostinato)
        root_lo = W.voice_lead(None, [W.degree_to_midi(chords[b], modes[b], TONIC)], 38, 50)[0]
        B["piano"].add(piano.note(root_lo, 0.35 + 0.2 * qn_bar[b], dur=g.bar * 0.9, release=1.2, rng=rng),
                       g.s(b, 0, jitter_ms=4, rng=rng), pan=-0.2)
        if b % 2 == 0:  # chord change -> sustained strings
            vel = 0.3 + 0.5 * qn_bar[b]
            B["bass"].add(W.sustain(bass, root_lo - 12 if root_lo > 45 else root_lo, vel, g.bar * 2, rng),
                          g.s(b), gain=0.9)
            if qn_bar[b] > 0.5:
                B["bass"].add(W.sustain(cello, root_lo + 7, vel * 0.8, g.bar * 2, rng), g.s(b), gain=0.5, pan=0.2)

    # ------------------------------------------------------ plant productivity --
    gpp_bar = per_bar(gppn)
    prev = None
    for b in range(0, N_BARS, 2):
        if gpp_bar[b] < 0.08:
            prev = None
            continue
        v = tones(b, 64, 86, prev, ext=(2, 4, 8))
        prev = v
        for i, m in enumerate(v):
            B["pad"].add(W.sustain(vln, m, 0.2 + 0.6 * gpp_bar[b], g.bar * 2, rng), g.s(b), gain=gpp_bar[b] ** 1.2,
                         pan=(-0.5, 0.1, 0.5)[i])
    first_green = next((b for b in range(N_BARS) if gpp_bar[b] >= 0.08 and b > 40), None)  # spring, not the October tail

    # ------------------------------------------------------------------- ice --
    runs, _ = W.events_from_flag(ice, min_gap=3)
    for on, off in runs:
        b = on // 3
        top = tones(b, 79, 96)[::-1]
        for i, m in enumerate(top[:3]):  # descending glock: the surface closing
            B["ice"].add(glock.note(m, 0.45, dur=1.5, release=2.0, rng=rng), g.s(b, i * 0.5), gain=0.7, pan=0.3 - 0.3 * i)
        B["ice"].add(perc.hit("susCymb1-bow", 0.5, rng), g.s(b), gain=0.6)
        mark(g.day_to_time(on), f"Ice forms on the Granby ({DAYS[on]:%b %d}) - glockenspiel + bowed cymbal")
        for d in range(on, off + 1):
            cold = np.clip(-T[d] / 15, 0.1, 1)
            t0 = g.day_to_time(d)
            for _ in range(int(3 + 10 * cold)):
                grain = ice_crinkle_grain(SR, dur=0.03, intensity=cold)[:, None].repeat(2, 1)
                B["ice"].add(grain * 0.25, (t0 + rng.uniform(0, g.day_to_time(1))) * SR, pan=rng.uniform(-0.8, 0.8))
            if T[d] < -4 and rng.random() < 0.45:  # 'singing ice': dispersive descending chirp
                L = 1.6
                tt = np.arange(int(L * SR)) / SR
                f = 2400 * np.exp(-tt * 1.6) + 350
                chirp = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 2.2) * (1 - np.exp(-tt * 60))
                B["ice"].add(chirp[:, None].repeat(2, 1) * 0.18, (t0 + rng.uniform(0, 1)) * SR, pan=rng.uniform(-0.6, 0.6))
        bo = min(off + 1, N_DAYS - 1)
        swell = perc.hit("susCymb1-cresc-Median", 0.6, rng)
        t_break = g.day_to_time(bo)
        t_freeze = g.day_to_time(on) + 1.0
        B["ice"].add(swell, max(t_freeze * SR, t_break * SR - len(swell) * 0.8), gain=0.6 if off - on >= 3 else 0.3)
        arp = tones(bo // 3, 57, 91)
        arp = sorted(set(arp + [m + 12 for m in arp]))
        for i, m in enumerate(arp):  # rising harp: the river opening
            B["ice"].add(harp.note(m, 0.5, rng=rng), t_break * SR + i * 0.09 * SR, gain=0.6, pan=-0.4 + 0.1 * i)
        mark(t_break, f"Ice breaks up ({DAYS[bo]:%b %d}) - cymbal swell + rising harp")

    # -------------------------------------------------------------- rain/snow --
    for d in range(N_DAYS):
        b = min(d // 3, N_BARS - 1)
        t0 = g.day_to_time(d)
        if rain[d] > 0.2:
            pool = tones(b, 67, 91)
            for _ in range(min(9, int(round(1.6 * np.sqrt(rain[d]))))):
                B["precip"].add(harp.note(int(rng.choice(pool)), rng.uniform(0.25, 0.55), rng=rng),
                                (t0 + rng.uniform(0, g.day_to_time(1))) * SR, pan=rng.uniform(-0.7, 0.7))
        if snow[d] > 0.2:
            pool = tones(b, 81, 98)
            for _ in range(min(7, int(round(1.3 * np.sqrt(snow[d]))))):
                B["precip"].add(glock.note(int(rng.choice(pool)), 0.22, dur=1.0, release=2.5, rng=rng),
                                (t0 + rng.uniform(0, g.day_to_time(1))) * SR, gain=0.6, pan=rng.uniform(-0.8, 0.8))
    big_rain = int(np.argmax(rain))
    mark(g.day_to_time(big_rain), f"Wettest day, {rain[big_rain]:.0f} mm rain ({DAYS[big_rain]:%b %d}) - harp shower")
    big_snow = int(np.argmax(snow))
    mark(g.day_to_time(big_snow), f"Biggest snowfall, {snow[big_snow]:.0f} cm ({DAYS[big_snow]:%b %d}) - glockenspiel flurry")

    # ------------------------------------------------------- hand percussion --
    active = np.clip((smooth(qn, 7) - 0.25) / 0.2, 0, 1)
    drive = np.sqrt(np.clip(0.6 * bn + 0.4 * bflash, 0, 1)) * active
    drive_bar = per_bar(drive)
    SW = 0.12  # swing: offbeat 8ths land a little late
    for b in range(N_BARS):
        lv = drive_bar[b]
        if lv < 0.12:
            continue
        for step in range(8):
            beat = step * 0.5 + (SW * 0.5 if step % 2 else 0)
            at = lambda: g.s(b, beat, jitter_ms=6, rng=rng)
            if step in (0, 5):
                B["perc"].add(perc.hit("Tumba-HitN", 0.5 + 0.4 * lv, rng), at(), pan=-0.3)
            if lv > 0.3 and (step in (2, 6) or (lv > 0.6 and step == 3)):
                B["perc"].add(perc.hit("Conga-HitN", 0.4 + 0.4 * lv, rng), at(), pan=0.25)
            if lv > 0.45 and step % 2:
                B["perc"].add(perc.hit("Tamb1-Shake", 0.15 + 0.25 * lv, rng), at(), pan=0.45)
            if lv > 0.5 and step == 7:
                B["perc"].add(perc.hit("Quinto-Tap1", 0.3, rng), at(), pan=0.5)
            if lv > 0.78 and step in (0, 3, 6):  # tresillo 3-3-2 against the 4/4
                B["perc"].add(perc.hit("LogDrumLo", 0.55, rng), at(), pan=-0.5)
    peak_d = int(np.argmax(q))
    mark(g.day_to_time(peak_d), f"Freshet peak, {q[peak_d]:.0f} m3/s ({DAYS[peak_d]:%b %d}) - full ostinato + tresillo drums")
    first_perc = next((b for b in range(N_BARS) if drive_bar[b] >= 0.12), None)
    if first_perc is not None:
        mark(g.t(first_perc), f"Burrell Creek wakes ({DAYS[first_perc * 3]:%b %d}) - hand drums enter")

    # ------------------------------------------------------------------- fish --
    in_window = lambda a, b_: ((doy >= a) & (doy <= b_)).astype(float)
    trout = np.exp(-((Tproxy - 8) / 2.5) ** 2) * in_window(91, 181) * (qn > 0.3)
    whitefish = np.exp(-((Tproxy - 4.5) / 2.0) ** 2) * in_window(288, 344)
    tr_bar, wf_bar = per_bar(trout), per_bar(whitefish)
    first_t = first_w = None
    tr_fire, wf_fire = W.fire_bars(tr_bar, 0.6), W.fire_bars(wf_bar, 0.75)
    for b in range(N_BARS):
        if b in tr_fire:
            v = tones(b, 72, 90, ext=(4, 7, 8))  # 5th -> octave -> 9th, rising
            for i, m in enumerate(sorted(v)):
                B["fish"].add(flute.note(m, 0.5, dur=(0.45 if i < 2 else 1.6) * g.beat * 2, release=0.6, rng=rng),
                              g.s(b, 1 + i * 0.5, jitter_ms=5, rng=rng), pan=0.35)
            first_t = first_t if first_t is not None else b
        if b in wf_fire:
            v = sorted(tones(b, 50, 64, ext=(0, 2, 4)), reverse=True)
            for i, m in enumerate(v):
                B["fish"].add(cpizz.note(m, 0.55, rng=rng), g.s(b, 2 + i * 0.5, jitter_ms=5, rng=rng), pan=-0.35)
            first_w = first_w if first_w is not None else b
    if first_t is not None:
        mark(g.t(first_t), f"Redband trout spawning window opens ({DAYS[first_t * 3]:%b %d}, simulated) - flute figure")
    if first_w is not None:
        mark(g.t(first_w), f"Mountain whitefish spawning ({DAYS[first_w * 3]:%b %d}, simulated) - cello pizzicato")

    # ------------------------------------------------------------------ birds --
    BIRDS = [  # (recording, day-of-year window, max prob per bar, gain) - typical timing, not observations
        ("american_dipper", (335, 366), 0.2, 0.7), ("american_dipper", (1, 75), 0.2, 0.7),
        ("swainsons_thrush_a", (140, 205), 0.35, 0.9), ("swainsons_thrush_b", (140, 205), 0.2, 0.9),
        ("bank_swallow", (125, 215), 0.18, 0.5),
    ]
    for name, (a, z), p, gain in BIRDS:
        phr = bird_phrases(name)
        fire = W.fire_bars(per_bar(in_window(a, z)), p, phase=rng.uniform(0.3, 0.9))
        for b in range(N_BARS):
            if b in fire:
                x = phr[rng.integers(len(phr))]
                B["birds"].add(x * gain, g.s(b, rng.uniform(0, 3)), pan=rng.uniform(-0.7, 0.7))
    mark(g.day_to_time(W.doy_index(140)), "Swainson's thrush arrives (typical ~May 20)")

    # ---------------------------------------------------------------- master --
    snowcov = np.clip(smooth(sog, 5) / 25, 0, 1)
    t_day = np.arange(n) / SR / g.day_to_time(1)
    snow_env = np.interp(t_day, np.arange(N_DAYS), snowcov)
    irs = {"open": make_ir(3.4, bright=0.65), "snow": make_ir(1.4, bright=0.1, seed=11)}
    mix, stems = S.master(list(B.values()), irs, HEAVY / f"{NAME}.wav", stems_dir=HEAVY / f"{NAME}_stems",
                          ir_env={"open": 1 - snow_env, "snow": snow_env})
    S.to_mp3(HEAVY / f"{NAME}.wav", OUT / f"{NAME}.mp3")

    # ------------------------------------------------------ score + guide ----
    for b in range(0, N_BARS, 8):
        if b == 0 or modes[b] != modes[b - 8]:
            mark(g.t(b), f"Mode -> {W.MODES[modes[b]][0]} ({DAYS[b * 3]:%b %d})")
    for b in range(1, N_BARS):
        if bar_phase[b] != bar_phase[b - 1]:
            mark(g.t(b), f"Phase -> {bar_phase[b]} ({DAYS[b * 3]:%b %d})")
    if first_green is not None:
        mark(g.t(first_green), f"Green-up: string pad enters ({DAYS[first_green * 3]:%b %d}; {GPP_SOURCE.split(' (')[0]})")
    events.sort()
    level = {k: float(20 * np.log10(np.sqrt((v ** 2).mean()) + 1e-12)) for k, v in stems.items()}
    score = {
        "name": NAME, "bpm": BPM, "tonic": "D", "bar_seconds": g.bar, "days_per_bar": 3,
        "duration_s": g.dur, "gpp_source": GPP_SOURCE,
        "days": [{"date": str(d), "t": round(g.day_to_time(i), 2), "flow": round(float(q[i]), 2),
                  "flow_pct_normal": round(float(qpct[i]), 3), "burrell": round(float(bq[i]), 3),
                  "ice": bool(ice[i]), "temp": round(float(T[i]), 1), "rain": float(rain[i]), "snow": float(snow[i]),
                  "snow_on_ground": float(sog[i]), "daylength": round(float(DL[i]), 2), "gpp_norm": round(float(gppn[i]), 3),
                  "trout_sim": round(float(trout[i]), 3), "whitefish_sim": round(float(whitefish[i]), 3)}
                 for i, d in enumerate(DAYS)],
        "bars": [{"bar": b, "t": round(g.t(b), 2), "mode": W.MODES[modes[b]][0], "degree": int(chords[b]),
                  "phase": bar_phase[b], "piano_density": int(np.sqrt(qn_bar[b]) * 3.99),
                  "perc_drive": round(float(drive_bar[b]), 3)} for b in range(N_BARS)],
        "events": events, "stem_rms_db": level,
    }
    with open(OUT / f"{NAME}_score.json", "w") as fh:
        json.dump(score, fh, indent=1)
    print("\n".join(f"{W.fmt_time(t)}  {e}" for t, e in events))
    print("stem RMS dBFS:", {k: round(v, 1) for k, v in level.items()})


if __name__ == "__main__":
    main()
