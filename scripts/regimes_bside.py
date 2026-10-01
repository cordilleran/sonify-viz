"""
EXTENDED B-SIDE, drum-led, from the interior-BC flow regimes (2026-09-30, v1.0).
Reads data/regimes/weekly.json (regional weekly medians derived from the Borealis catchment-mean
forcing, CC BY-SA 4.0); writes the wav to the heavy folder and the mp3 and score JSON to the light
folder (renders.py sets both). Run: python regimes_bside.py

An evocation of a 2000s-2010s London post-minimal idiom (static modal centre, odd-length drum
cycles against a steady 4/4, garage swing, human micro-timing, additive entries, a slow filter
as form). No melody, sample or voice is taken from any record.

TIME   124 bpm, 52 bars per pass = one water year (a week per bar), 5 passes + a 4-bar coda,
       about 8.5 min. 16 steps per bar, swing 0.56 on the off-sixteenths.
VOICES each of four regime years (k=4 exemplars) is one drum voice reading its own year's weekly
       regional flow. Flow -> Euclid(k, N) density and velocity; N = 9, 7, 5, 3 steps, so each cycle
       slides across the bar line. Entry by pass: 1988, 1995, 2012, 2018.
LEAD   harp + marimba cell of 7 sixteenths; Euclid density from the snowmelt rate (weekly fall in
       snow water equivalent), so it sounds only in melt weeks (first heard at 4:17). B natural (Dorian)
       when the week is warm, else B flat (Aeolian). The marimba reads the same pattern three steps
       ahead, an octave down, so it anticipates the harp: the resultant melody.
FILTER low-pass on the high bus (hats, shaker) and the lead follows snowpack (dull under snow, open at
       melt); it cycles once per pass. The drums and sub are not filtered.
SUB    sine pedal D / C / Bb at fixed bars of each pass (a calendar plan, not read from the data);
       level = the flow floor.
DROP   kick and clap drop out from week 38 (late June) in bars where the sounding voices' mean level is low (a breakdown;
       it falls in every pass, so it marks the season more than the year).
Writes bside_score.json for the visual companion page (flow-regimes/).
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

import sampler as S  # noqa: E402
import synth as Y  # noqa: E402
from sampler import Bus, OneShots, SR, make_ir  # noqa: E402

from dsp_core import HEAVY_OUT, LIGHT_OUT, ROOT  # noqa: E402

HEAVY, LIGHT = HEAVY_OUT / "regimes", LIGHT_OUT / "regimes"
HEAVY.mkdir(parents=True, exist_ok=True)
LIGHT.mkdir(parents=True, exist_ok=True)
D = json.loads((ROOT / "data/regimes/weekly.json").read_text())

BPM, SWING = 124, 0.56
STEP = 60 / BPM / 4
BAR = 16 * STEP
PASS_BARS, N_PASS, CODA = 52, 5, 4
LEAD = 2.0
TOTAL_BARS = PASS_BARS * N_PASS + CODA
rng = np.random.default_rng(124)
np.random.seed(124)

# voice: year, cycle length, pan, micro-timing offset (s), rotation step per pass (coprime to N), label, regime
VOICES = [
    dict(year=1988, N=9, pan=-0.35, off=0.000, step=4, kind="timpani", regime="dry"),
    dict(year=1995, N=7, pan=-0.12, off=0.012, step=3, kind="conga", regime="normal"),
    dict(year=2012, N=5, pan=0.12, off=0.022, step=2, kind="logdrum", regime="late, big, wet"),
    dict(year=2018, N=3, pan=0.40, off=-0.014, step=1, kind="shaker", regime="early, dry summer"),
]
for v in VOICES:
    r = D["regional"][str(v["year"])]
    v["flow"], v["swe"], v["temp"] = r["flow"], r["swe"], r["temp"]


def lvl_d(f):  # drum level: 0.12 of own mean -> 0.08, 1 -> 0.77, 2 -> 1
    return float(np.clip((np.log2(max(f, 1e-3)) + 3.4) / 4.4, 0, 1))


def floor_lvl(series, w, k=6):
    f = min(series[max(0, w - k + 1): w + 1])
    return float(np.clip((np.log2(max(f, 1e-3)) + 2.5) / 3.5, 0, 1))


def euclid(k, n):
    return [((i + 1) * k) // n != (i * k) // n for i in range(n)] if k > 0 else [False] * n


def step_time(g):
    """Seconds of global sixteenth g (swung: the second of each pair is late)."""
    pair, odd = divmod(g, 2)
    return LEAD + pair * 2 * STEP + (2 * STEP * SWING if odd else 0.0)


def at(t, extra=0.0):
    return int((t + extra + rng.uniform(-0.004, 0.004)) * SR)


def main():
    n = int((LEAD + TOTAL_BARS * BAR + 9) * SR)
    B = {
        "kit": Bus("kit", n, gain=0.3, hp=30, send=0.15),
        "perc": Bus("perc", n, gain=14.0, hp=50, send=0.3),
        "hi": Bus("hi", n, gain=7.0, hp=300, send=0.3),
        "lead": Bus("lead", n, gain=5.0, hp=200, send=0.45),
        "sub": Bus("sub", n, gain=0.3, hp=25, send=0.0),
        "foley": Bus("foley", n, gain=2.0, hp=1500, send=0.2),
    }
    K = S.vsco_kit()
    oneshots = K["perc"]
    timp = OneShots(folder=S.VSCO / "Percussion" / "Timpani")
    score = dict(bpm=BPM, bar_s=BAR, lead_s=LEAD, pass_bars=PASS_BARS, bars=[], voices=[], lead_hits=[])
    hits = [[] for _ in VOICES]
    cut_bar = np.zeros(TOTAL_BARS)

    def voice_hit(vi, vel, accent):
        k = VOICES[vi]["kind"]
        if k == "timpani":
            return timp.hit("Timpani1_Hit", 0.55 + 0.4 * vel, rng) * (1.0 if accent else 0.7)
        if k == "conga":
            return oneshots.hit("Conga-HitN" if accent else "Conga-Tap1", 0.3 + 0.6 * vel, rng)
        if k == "logdrum":
            return oneshots.hit("LogDrumLo_MedM" if accent else "LogDrumHi_MedM", 0.3 + 0.6 * vel, rng)
        return oneshots.hit("Triangle3-HitM" if accent else "Tamb1-Shake", 0.25 + 0.5 * vel, rng)

    cells_cool = [69, 77, 76, 74, 79, 82, 84]   # A4 F5 E5 D5 G5 Bb5 C6  (Aeolian)
    for ab in range(TOTAL_BARS):
        p, b = divmod(ab, PASS_BARS)
        coda = ab >= PASS_BARS * N_PASS
        if coda:
            p, b = N_PASS - 1, ab - PASS_BARS * N_PASS
        active = [] if coda else list(range(min(p + 1, len(VOICES))))
        wk = min(b, 51) if not coda else 51
        fl = [VOICES[i]["flow"][wk] for i in active]
        lv = [lvl_d(f) for f in fl]
        mean_l = float(np.mean(lv)) if lv else 0.0
        swe = float(np.mean([VOICES[i]["swe"][wk] for i in active])) if active else 0.0
        temp = float(np.mean([VOICES[i]["temp"][wk] for i in active])) if active else 4.0
        swe_prev = float(np.mean([VOICES[i]["swe"][max(wk - 1, 0)] for i in active])) if active else 0.0
        melt = float(np.clip(max(0.0, swe_prev - swe) / 0.12, 0, 1))
        warm = temp > 10.0
        root = 38 if (coda or b < 26) else 36 if b < 39 else 34
        brk = (not coda) and wk >= 38 and mean_l < 0.40
        cut_bar[ab] = 14000 - 10000 * float(np.clip(swe, 0, 1)) if active else 14000
        t0 = ab * 16
        # --- anchor pulse
        if not coda and not brk:
            for s in (0, 4, 8, 12):
                B["kit"].add(Y.kick(0.6), at(step_time(t0 + s)), gain=0.9)
            for s in (4, 12):
                if p >= 1:
                    B["kit"].add(Y.clap(0.34, rng), at(step_time(t0 + s), 0.024), gain=0.7)
        if not coda:
            for s in range(16):
                vel = 0.2 if s % 2 else 0.12
                if brk and s % 4:
                    continue
                B["hi"].add(Y.hat(vel, False, rng), at(step_time(t0 + s), -0.008), gain=0.8 if not brk else 0.5)
            if p >= 3 and b % 2 == 1:
                B["hi"].add(Y.hat(0.26, True, rng), at(step_time(t0 + 14), -0.008), gain=0.7)
        # --- year voices (Euclid k of N, rotated each pass, slowly within a pass)
        kk, rots = [], []
        for vi in active:
            V = VOICES[vi]
            N = V["N"]
            k_ = int(round(lvl_d(V["flow"][wk]) * N * 0.9)) if lvl_d(V["flow"][wk]) >= 0.12 else 0
            kk.append(k_)
            pat = euclid(k_, N)
            rot = (p * V["step"] + b // 8) % N
            rots.append(rot)
            vel = lvl_d(V["flow"][wk])
            for s in range(16):
                g = t0 + s
                pos = (g + rot) % N
                if pat[pos]:
                    accent = pos == 0 or (g % 4 == 0)
                    t = step_time(g)
                    bus = "hi" if V["kind"] == "shaker" else "perc"
                    B[bus].add(voice_hit(vi, vel, accent), at(t, V["off"]), gain=0.8 if accent else 0.55, pan=V["pan"])
                    hits[vi].append([round(t + V["off"] - LEAD, 3), 1 if accent else 0, round(vel, 2)])
        # --- lead: harp + marimba, Euclid density from melt, only from pass 3
        lead_k = 0
        if (not coda) and p >= 2 and melt > 0.05:
            lead_k = max(1, int(round(melt * 6)))
            pat = euclid(lead_k, 7)
            cell = cells_cool[:5] + [83 if warm else 82] + cells_cool[6:]
            rot = (p * 2 + b // 4) % 7
            for s in range(16):
                g = t0 + s
                i = (g + rot) % 7
                if pat[i]:
                    m = cell[i]
                    t = step_time(g)
                    B["lead"].add(K["harp"].note(m, 0.45 + 0.4 * melt, dur=0.5, release=0.6, rng=rng), at(t), gain=0.9, pan=-0.3)
                    score["lead_hits"].append([round(t - LEAD, 3), m])
                # marimba: the same pattern read three steps ahead (it anticipates the harp), an octave down: the resultant melody
                i2 = (g + rot + 3) % 7
                if pat[i2] and p >= 3:
                    B["lead"].add(K["marimba"].note(cell[i2] - 12, 0.4 + 0.3 * melt, dur=0.4, release=0.5, rng=rng), at(step_time(g)), gain=0.6, pan=0.3)
        # --- sub pedal, retriggered every 2 bars, level = flow floor
        if ab % 2 == 0:
            fls = [floor_lvl(VOICES[i]["flow"], wk) for i in active] or [0.3]
            B["sub"].add(Y.sub_note(root, 2 * BAR + 0.3, vel=0.25 + 0.6 * float(np.mean(fls)), drive=1.8), at(step_time(t0)), gain=1.0)
        # --- foley from pass 4
        if p >= 3 and not coda:
            for _ in range(int(9 * mean_l)):
                x = Y.highpass(rng.standard_normal(int(0.004 * SR)), 4000) * np.exp(-np.arange(int(0.004 * SR)) / (0.0012 * SR))
                B["foley"].add(Y.stereo(x * rng.uniform(0.3, 0.9)), at(step_time(t0) + rng.uniform(0, BAR)), gain=0.6, pan=rng.uniform(-0.6, 0.6))
        # --- coda: one conga per bar, fading
        if coda and b < 4:
            B["perc"].add(oneshots.hit("Conga-HitN", 0.5 * (1 - b / 4), rng), at(step_time(t0 + 8)), gain=0.6, pan=-0.12)
        score["bars"].append(dict(ab=ab, pass_=(p + 1) if not coda else 6, week=wk, flow=[round(f, 3) for f in fl], k=kk, rot=rots,
                                  swe=round(swe, 3), melt=round(melt, 3), temp=round(temp, 1), mode="Dorian" if warm else "Aeolian",
                                  root={38: "D", 36: "C", 34: "Bb"}[root], brk=bool(brk), lead_k=lead_k, cutoff=int(cut_bar[ab])))
        if (ab + 1) % 26 == 0:
            print(f"  bar {ab + 1}/{TOTAL_BARS}", flush=True)

    # the snowpack filter on the high bus: per-sample cutoff interpolated between bar values
    xs = np.arange(n) / SR
    cut = np.interp(xs, LEAD + (np.arange(TOTAL_BARS) + 0.5) * BAR, cut_bar)
    B["hi"].buf = Y.swept_lowpass(B["hi"].buf, cut).astype(np.float32)
    B["lead"].buf = Y.swept_lowpass(B["lead"].buf, np.clip(cut * 1.3, 3000, 16000)).astype(np.float32)

    irs = {"hall": make_ir(3.6, bright=0.5, seed=124)}
    wav = HEAVY / "bside_regimes.wav"
    mix, stems = S.master(list(B.values()), irs, wav)
    fr, mono = int(0.5 * SR), mix.mean(axis=1)
    rep = {}
    for k, v in stems.items():
        m = v.mean(axis=1); nf = len(m) // fr
        a = np.sqrt((m[:nf * fr].reshape(nf, fr) ** 2).mean(1)); mr = np.sqrt((mono[:nf * fr].reshape(nf, fr) ** 2).mean(1))
        on = a > 10 ** (-70 / 20)
        rep[k] = (round(float(on.mean()) * 100), round(float(20 * np.log10(a[on].mean() / mr[on].mean()))) if on.any() else None)
    print("(share of piece sounding %, active level re mix dB):", rep)
    mp3 = LIGHT / "bside_regimes.mp3"
    dur = len(mix) / SR
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-b:a", "160k", str(mp3)], check=True)
    print(f"{mp3.name}: {dur / 60:.1f} min, {mp3.stat().st_size // 1024} KB")

    score["voices"] = [dict(year=v["year"], N=v["N"], pan=v["pan"], kind=v["kind"], regime=v["regime"], flow=v["flow"], swe=v["swe"], temp=v["temp"], nhits=len(hits[i]))
                       for i, v in enumerate(VOICES)]
    score["duration_s"] = round(dur, 2)
    score["audio_rep"] = {k: list(v) for k, v in rep.items()}
    (LIGHT / "bside_score.json").write_text(json.dumps(score))
    print("score KB", (LIGHT / "bside_score.json").stat().st_size // 1024)


if __name__ == "__main__":
    main()
