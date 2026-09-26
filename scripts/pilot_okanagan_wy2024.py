"""
PILOT B - Okanagan, water year 2023-24 (Oct 1 2023 - Sep 30 2024).
Key of F, 64 bpm, 1 bar = 3 days, ~7.7 minutes. Slower tempo and HALF the
harmonic rhythm of the Granby pilot (a chord every 4 bars, not 2), because a
big regulated lake changes slowly.

A drought year on the lake (it rose only ~0.7 m and peaked ~1 m below 2017)
that was ALSO a very large sockeye return at Wells Dam (491k, the most in the
2015-24 counts). Low water and many fish in the same summer.

LAYER             DATA (R = retrieved, D = derived, S = simulated)        SOUND
lake drone        Okanagan Lake level at Kelowna 08NM083 (R)              F pedal (contrabass), cello 5th while filling
harmony / mode    day length (D) + lake level vs 15-yr normal (R)         mode brightness
progression       lake phase: winter / filling / full / drawdown (D)      which 4-chord loop plays
piano ostinato    Okanagan River at Penticton 08NM050 = dam outflow (R)   density follows the release; when the
                                                                          outflow is held flat the pattern is played
                                                                          strictly, unvaried
soft percussion   Okanagan River near Oliver 08NM085 (R)                  log drum / conga / shaker
sockeye           Wells Dam daily adult sockeye count, DART (R)           marimba runs climbing the scale
thermal stress    Wells Dam water temperature, DART (R)                   a held high violin note above 18 C
sockeye spawning  Oct window near Oliver, scaled by run size (S)          cello pizzicato, low and falling
string pad        MODIS GPP, Summerland bench (R)                         violins swell with plant productivity
rain / snow       Summerland CS precip + temperature split (R/D)          harp drops / glockenspiel flakes
frost             Summerland CS mean temp < -8 C (R)                      ice crackle (Jan 2024 arctic outbreak)
air / space       Summerland CS min relative humidity (R)                 humid = long hall, dry = short bright room
birds             typical phenology windows (S timing, R recordings)      meadowlark (spring), sandhill cranes (passage)
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
    NAME = "okanagan_wy2024"
    rng = np.random.default_rng(1997)
    np.random.seed(1997)  # the ice grain helper uses the global RNG; seed it so renders repeat exactly

    TONIC = 53  # F3
    BPM = 64
    g = W.Grid(BPM, tail_s=12.0)
    print(f"{N_BARS} bars, {g.dur / 60:.1f} min")

    # --------------------------------------------------------------- features --
    lake_all, _ = W.wsc_series("okanagan_lake_kelowna_08NM083_2010_2024.json", key="LEVEL")
    pen_all, _ = W.wsc_series("okanagan_river_penticton_08NM050_2010_2024.json")
    oli_all, _ = W.wsc_series("okanagan_river_oliver_08NM085_2010_2024.json")
    clim = "summerland_cs_979_climate_2010_2024.json"
    lake = W.wy(lake_all)
    lake_n = norm01(lake, 0, 100)
    lake_pct = W.doy_percentile(lake_all)
    pen = W.wy(pen_all)
    pen_n = norm01(pen, 0, 100)
    oli = W.wy(oli_all)
    oli_n = norm01(np.log(oli))
    T = W.wy(W.climate_series(clim, "MEAN_TEMPERATURE"))
    precip = W.wy(W.climate_series(clim, "TOTAL_PRECIPITATION"), fill="zero")
    rain = np.where(T > 1.0, precip, 0.0)
    snow = np.where(T <= 1.0, precip, 0.0)  # mm water equivalent
    hum = W.wy(W.climate_series(clim, "MIN_REL_HUMIDITY"))
    DL = W.daylength(49.6)
    gpp, gppn = W.modis_gpp_daily("summerland")
    GPP_SOURCE = "MODIS MOD17A2HGF (retrieved)"
    if gpp is None:
        gppn = np.clip(smooth(np.maximum(0, T - 5), 21) / 12, 0, 1)
        GPP_SOURCE = "temperature proxy (derived; MODIS pull unavailable)"
    sock, wells_T = W.dart_sockeye()
    doy = np.array([d.timetuple().tm_yday for d in DAYS])

    # ---------------------------------------------------------------- harmony --
    bright = per_bar(0.75 * norm01(DL, 0, 100) + 0.25 * norm01(smooth(T, 15)))
    anom = per_bar(smooth(lake_pct, 15)) - 0.5
    modes = W.mode_track(bright, anom, lo=1, hi=4, phrase=8)

    ls_ = smooth(lake, 7)
    dl_ = np.gradient(ls_) * 100  # cm/day
    phase_day = np.where(dl_ > 0.4, "filling",
                 np.where(lake_n > 0.85, "full",
                 np.where(dl_ < -0.25, "drawdown", "winter")))
    PROG = {  # 4 chords x 4 bars each (16-bar loops)
        "winter":   [0, 5, 3, 5],   # i  VI  iv  VI  - rocking, patient
        "filling":  [0, 2, 3, 4],   # i  III iv  v   - bass climbs with the water
        "full":     [5, 2, 6, 0],   # VI III VII i   - broad; the VII->i 'Aeolian cadence'
        "drawdown": [0, 6, 5, 4],   # i  VII VI  v   - bass walks down
    }
    bar_phase = W.phase_bars(phase_day, min_run=8)
    chords = W.chord_track(bar_phase, PROG, bars_per_chord=4)

    K = S.vsco_kit()
    piano, bass, cello, cpizz, vln = K["piano"], K["bass"], K["cello"], K["cpizz"], K["vln"]
    harp, glock, marimba, perc = K["harp"], K["glock"], K["marimba"], K["perc"]

    n = g.n
    B = {k: Bus(k, n, **kw) for k, kw in {
        "piano":  dict(gain=1.0, hp=70, send=0.4),
        "drone":  dict(gain=0.8, lp=800, send=0.15),
        "pad":    dict(gain=0.19, hp=220, send=0.6),
        "fish":   dict(gain=0.95, hp=120, send=0.4),
        "heat":   dict(gain=0.22, hp=400, send=0.7),
        "precip": dict(gain=1.05, hp=250, send=0.55),
        "frost":  dict(gain=1.5, hp=500, send=0.5),
        "perc":   dict(gain=1.8, hp=60, send=0.18),
        "birds":  dict(gain=0.26, hp=700, send=0.4),
    }.items()}
    events = []


    def mark(sec, text):
        events.append((round(sec, 1), text))


    def tones(b, lo, hi, prev=None, ext=(0, 2, 4, 8)):
        return W.voice_lead(prev, W.chord(chords[b], modes[b], TONIC, ext), lo, hi)


    # ---------------------------------------------------------- lake drone ----
    F_PEDAL = 29  # F1 - the lake is a pedal point: the same low note under every chord
    lake_bar, dlake_bar = per_bar(lake_n), per_bar(dl_)
    for b in range(0, N_BARS, 4):
        vel = 0.3 + 0.5 * lake_bar[b]
        B["drone"].add(W.sustain(K["bass"], F_PEDAL + 12, vel, g.bar * 4, rng), g.s(b))
        if dlake_bar[b] > 0.3:  # filling: the cello adds the 5th
            B["drone"].add(W.sustain(cello, F_PEDAL + 19, vel * 0.8, g.bar * 4, rng), g.s(b), gain=0.5, pan=0.2)

    # -------------------------------------------------------- piano / outflow --
    PATTERN = [0, 2, 3, 2, 1, 2, 3, 1]
    DENSITY = {0: [0, 4], 1: [0, 2, 4, 6], 2: list(range(8)), 3: list(range(8))}
    pen_bar = per_bar(pen_n)
    # 'held' = the dam kept outflow within +-3% over the surrounding two weeks
    rel_var = np.array([np.ptp(pen[max(0, i - 7):i + 8]) / pen[max(0, i - 7):i + 8].mean() for i in range(N_DAYS)])
    held = per_bar(rel_var < 0.06)
    dl_bar = per_bar(norm01(DL, 0, 100))
    prev = None
    fixed_vel = None
    for b in range(N_BARS):
        v = tones(b, 57, 79, prev)
        prev = v
        lvl = int(np.sqrt(pen_bar[b]) * 3.99)
        strict = held[b] > 0.5
        base = 0.26 + 0.3 * dl_bar[b] + 0.15 * pen_bar[b]
        for step in DENSITY[lvl]:
            if strict:  # the dam's hand: identical, mechanical repetition
                vel, jit = base + (0.08 if step in (0, 4) else 0), 0.0
            else:
                vel, jit = base + (0.1 if step in (0, 4) else 0) + rng.normal(0, 0.04), 9.0
            B["piano"].add(piano.note(v[PATTERN[step]], float(np.clip(vel, 0.1, 0.9)), dur=g.beat * 1.4, release=1.0, rng=rng),
                           g.s(b, step * 0.5, jitter_ms=jit, rng=rng), pan=-0.1 + 0.06 * (PATTERN[step] - 1.5))
        if b % 4 == 0:
            root = W.voice_lead(None, [W.degree_to_midi(chords[b], modes[b], TONIC)], 41, 53)[0]
            B["piano"].add(piano.note(root, 0.4, dur=g.bar * 2, release=1.5, rng=rng), g.s(b), pan=-0.2)
    # mark the regulated flow's biggest step changes
    steps = [i for i in range(7, N_DAYS - 7) if abs(pen[i + 3:i + 7].mean() - pen[i - 6:i - 2].mean()) > 2.5]
    last = -99
    for i in steps:
        if i - last > 20:
            mark(g.day_to_time(i), f"Penticton dam release changes {pen[i - 4]:.0f} -> {pen[i + 5]:.0f} m3/s ({DAYS[i]:%b %d})")
            last = i
    first_held = next((b for b in range(N_BARS) if held[b] > 0.5), None)

    # ---------------------------------------------------------- string pad ----
    gpp_bar = per_bar(gppn)
    prev = None
    for b in range(0, N_BARS, 2):
        if gpp_bar[b] < 0.08:
            prev = None
            continue
        v = tones(b, 65, 88, prev, ext=(2, 4, 8))
        prev = v
        for i, m in enumerate(v):
            B["pad"].add(W.sustain(vln, m, 0.2 + 0.6 * gpp_bar[b], g.bar * 2, rng), g.s(b), gain=gpp_bar[b] ** 1.2,
                         pan=(-0.5, 0.1, 0.5)[i])
    first_green = next((b for b in range(N_BARS) if gpp_bar[b] >= 0.08 and b > 40), None)

    # -------------------------------------------------------------- sockeye ----
    sock_bar = per_bar(sock, "sum")
    cum = np.cumsum(sock_bar) / max(sock_bar.sum(), 1)
    for b in range(N_BARS):
        c = sock_bar[b]
        if c < 5:
            continue
        k = int(min(12, round(1.7 * np.log1p(c / 40))))
        if k == 0:
            continue
        # climb through the chord's own tones (never a passing note that could rub),
        # starting higher as the run progresses: the season's fish moving upstream
        arp = sorted({m + 12 * o for m in W.chord(chords[b], modes[b], TONIC) for o in range(-1, 3)})
        arp = [m for m in arp if 60 <= m <= 96]
        start = int(cum[b] * (len(arp) - 6))
        slots = np.sort(rng.choice(16, size=min(k, 16), replace=False))
        for j, sl in enumerate(slots):
            m = arp[min(start + j, len(arp) - 1)]
            B["fish"].add(marimba.note(m, float(np.clip(0.3 + 0.05 * k + rng.normal(0, 0.05), 0.2, 0.9)), rng=rng),
                          g.s(b, sl * 0.25, jitter_ms=4, rng=rng), pan=float(np.clip(-0.6 + 0.1 * j, -0.7, 0.7)))
    pk = int(np.argmax(sock))
    fs = next((i for i in range(N_DAYS) if sock[i] > 0 and DAYS[i].year == 2024), None)
    if fs is not None:
        mark(g.day_to_time(fs), f"First sockeye of the 2024 run pass Wells Dam ({DAYS[fs]:%b %d}) - marimba")
    mark(g.day_to_time(pk), f"Sockeye peak at Wells: {sock[pk]:,.0f} fish in one day ({DAYS[pk]:%b %d})")

    # thermal stress: Wells water temperature (a real measurement) above 18 C
    wt = np.nan_to_num(wells_T, nan=0.0)
    stress = np.clip((smooth(wt, 5) - 18.0) / 2.5, 0, 1)
    st_bar = per_bar(stress)
    for b in range(0, N_BARS, 2):
        if st_bar[b] <= 0.02:
            continue
        m = W.voice_lead(None, [W.degree_to_midi(8, modes[b], TONIC)], 84, 96)[0]  # the 9th, held high
        B["heat"].add(W.sustain(vln, m, 0.3 + 0.5 * st_bar[b], g.bar * 2, rng), g.s(b), gain=st_bar[b])
    hs = next((i for i in range(N_DAYS) if stress[i] > 0.05), None)
    if hs is not None:
        mark(g.day_to_time(hs), f"Wells water passes 18 C ({DAYS[hs]:%b %d}) - held high violin: thermal stress")
        wmax = int(np.nanargmax(wells_T))
        mark(g.day_to_time(wmax), f"Warmest water at Wells, {wells_T[wmax]:.1f} C ({DAYS[wmax]:%b %d})")

    # spawning near Oliver (simulated timing, scaled by the run that produced it)
    runs_size = {2023: 136956, 2024: 491039}
    spawn = sum(runs_size[y] / 491039 * np.exp(-0.5 * (np.array([(d - W.dt.date(y, 10, 15)).days for d in DAYS]) / 9) ** 2)
                for y in runs_size)
    sp_bar = per_bar(spawn)
    sp_fire = W.fire_bars(sp_bar, 2.2)
    for b in range(N_BARS):
        if b in sp_fire:
            v = sorted(tones(b, 41, 57, ext=(0, 2, 4)), reverse=True)
            for i, m in enumerate(v):
                B["fish"].add(cpizz.note(m, 0.5, rng=rng), g.s(b, 1 + i * 0.75, jitter_ms=5, rng=rng), gain=0.8, pan=-0.35)
    mark(0.0, "Oct 2023: the 2023 sockeye spawning near Oliver (timing simulated) - low cello pizzicato")

    # ------------------------------------------------------- soft percussion --
    active = np.clip((smooth(oli_n, 7) - 0.3) / 0.25, 0, 1)
    drive = np.sqrt(np.clip(oli_n, 0, 1)) * active
    drive_bar = per_bar(drive)
    SW = 0.1
    for b in range(N_BARS):
        lv = drive_bar[b]
        if lv < 0.12:
            continue
        for step in range(8):
            beat = step * 0.5 + (SW * 0.5 if step % 2 else 0)
            at = lambda: g.s(b, beat, jitter_ms=6, rng=rng)
            if step in (0, 6) and lv > 0.12:
                B["perc"].add(perc.hit("LogDrumLo", 0.35 + 0.35 * lv, rng), at(), pan=-0.3)
            if lv > 0.35 and step in (3, 4):
                B["perc"].add(perc.hit("LogDrumHi", 0.25 + 0.3 * lv, rng), at(), pan=0.3)
            if lv > 0.5 and step % 2:
                B["perc"].add(perc.hit("Tamb1-Shake", 0.12 + 0.2 * lv, rng), at(), pan=0.45)
            if lv > 0.7 and step in (2, 7):
                B["perc"].add(perc.hit("Conga-Tap1", 0.35, rng), at(), pan=0.15)
    po = int(np.argmax(oli))
    mark(g.day_to_time(po), f"Okanagan River at Oliver peaks, {oli[po]:.0f} m3/s ({DAYS[po]:%b %d}) - fullest percussion")

    # ------------------------------------------------------ precip + frost ----
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
            for _ in range(min(7, int(round(1.8 * np.sqrt(snow[d]))))):
                B["precip"].add(glock.note(int(rng.choice(pool)), 0.22, dur=1.0, release=2.5, rng=rng),
                                (t0 + rng.uniform(0, g.day_to_time(1))) * SR, gain=0.6, pan=rng.uniform(-0.8, 0.8))
        if T[d] < -8:
            cold = np.clip((-T[d] - 8) / 12, 0.15, 1)
            for _ in range(int(4 + 12 * cold)):
                grain = ice_crinkle_grain(SR, dur=0.03, intensity=cold)[:, None].repeat(2, 1)
                B["frost"].add(grain * 0.25, (t0 + rng.uniform(0, g.day_to_time(1))) * SR, pan=rng.uniform(-0.8, 0.8))
    cold_d = int(np.argmin(T))
    mark(g.day_to_time(cold_d), f"Coldest day, {T[cold_d]:.1f} C ({DAYS[cold_d]:%b %d}) - frost crackle")

    # ------------------------------------------------------------------ birds --
    in_window = lambda a, z: ((doy >= a) & (doy <= z)).astype(float)
    BIRDS = [("western_meadowlark_a", (70, 197), 0.3, 0.9), ("western_meadowlark_b", (70, 197), 0.2, 0.9),
             ("sandhill_crane", (92, 116), 0.45, 0.8), ("sandhill_crane", (254, 285), 0.45, 0.8)]
    for name, (a, z), p, gain in BIRDS:
        phr = bird_phrases(name)
        fire = W.fire_bars(per_bar(in_window(a, z)), p, phase=rng.uniform(0.3, 0.9))
        for b in range(N_BARS):
            if b in fire:
                B["birds"].add(phr[rng.integers(len(phr))] * gain, g.s(b, rng.uniform(0, 3)), pan=rng.uniform(-0.7, 0.7))
    mark(0.0, "Early Oct: sandhill cranes passing over (typical timing)")
    mark(g.day_to_time(W.doy_index(71)), "Western meadowlark returns (typical ~Mar 10)")

    # ---------------------------------------------------------------- master --
    humid = np.clip((smooth(hum, 7) - 20) / 50, 0, 1)
    t_day = np.arange(n) / SR / g.day_to_time(1)
    h_env = np.interp(t_day, np.arange(N_DAYS), humid)
    irs = {"open": make_ir(4.0, bright=0.5, seed=3), "dry": make_ir(1.2, bright=0.8, seed=5)}
    mix, stems = S.master(list(B.values()), irs, HEAVY / f"{NAME}.wav", stems_dir=HEAVY / f"{NAME}_stems",
                          ir_env={"open": h_env, "dry": 1 - h_env})
    S.to_mp3(HEAVY / f"{NAME}.wav", OUT / f"{NAME}.mp3")

    for b in range(0, N_BARS, 8):
        if b == 0 or modes[b] != modes[b - 8]:
            mark(g.t(b), f"Mode -> {W.MODES[modes[b]][0]} ({DAYS[b * 3]:%b %d})")
    for b in range(1, N_BARS):
        if bar_phase[b] != bar_phase[b - 1]:
            mark(g.t(b), f"Lake phase -> {bar_phase[b]} ({DAYS[b * 3]:%b %d})")
    if first_green is not None:
        mark(g.t(first_green), f"Green-up: string pad enters ({DAYS[first_green * 3]:%b %d}; {GPP_SOURCE.split(' (')[0]})")
    if first_held is not None:
        mark(g.t(first_held), f"Outflow held flat by the dam ({DAYS[first_held * 3]:%b %d}) - piano turns strict")
    lk = int(np.argmax(lake))
    mark(g.day_to_time(lk), f"Lake peaks at gauge {lake[lk]:.2f} m ({DAYS[lk]:%b %d}); 2017 reached 3.01")
    events.sort()
    level = {k: float(20 * np.log10(np.sqrt((v ** 2).mean()) + 1e-12)) for k, v in stems.items()}
    score = {
        "name": NAME, "bpm": BPM, "tonic": "F", "bar_seconds": g.bar, "days_per_bar": 3,
        "duration_s": g.dur, "gpp_source": GPP_SOURCE,
        "days": [{"date": str(d), "t": round(g.day_to_time(i), 2), "lake_level": round(float(lake[i]), 3),
                  "lake_pct_normal": round(float(lake_pct[i]), 3), "penticton": round(float(pen[i]), 2),
                  "oliver": round(float(oli[i]), 2), "sockeye": float(sock[i]),
                  "wells_temp": None if np.isnan(wells_T[i]) else float(wells_T[i]),
                  "temp": round(float(T[i]), 1), "rain": float(rain[i]), "snow_we": float(snow[i]),
                  "humidity_min": round(float(hum[i]), 0), "daylength": round(float(DL[i]), 2),
                  "gpp_norm": round(float(gppn[i]), 3), "spawn_sim": round(float(spawn[i]), 3)}
                 for i, d in enumerate(DAYS)],
        "bars": [{"bar": b, "t": round(g.t(b), 2), "mode": W.MODES[modes[b]][0], "degree": int(chords[b]),
                  "phase": bar_phase[b], "piano_density": int(np.sqrt(pen_bar[b]) * 3.99),
                  "held": bool(held[b] > 0.5), "perc_drive": round(float(drive_bar[b]), 3)} for b in range(N_BARS)],
        "events": events, "stem_rms_db": level,
    }
    with open(OUT / f"{NAME}_score.json", "w") as fh:
        json.dump(score, fh, indent=1)
    print("\n".join(f"{W.fmt_time(t)}  {e}" for t, e in events))
    print("stem RMS dBFS:", {k: round(v, 1) for k, v in level.items()})


if __name__ == "__main__":
    main()
