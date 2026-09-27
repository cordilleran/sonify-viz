"""
A 45-second demo that needs no instrument samples: the Granby River's water
year played by synthesizers, through the same harmony engine as the pieces.

  python demo.py              # WY2024 -> rendered/demo_wy2024.wav (+ .mp3 if ffmpeg is installed)
  python demo.py wy2019       # any year the cached records cover

What you hear (a sketch of pilot_granby_wy2024.py, not a substitute for it):
  pad      the chord, one per 12 days; its mode brightens with day length and
           darkens when the river runs below its 15-year normal
  sub      the chord's root
  plucks   more notes per bar as the river rises, climbing the chord
One demo bar is 6 days, so the year takes about 45 seconds.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harmony as H
import records as R
import synth as Y
from dsp_core import SR, LIGHT_OUT
from sampler import Bus, make_ir, master, to_mp3
from timegrid import Year, norm01, per_bar, smooth

PROG = {  # scale degrees, as in the Granby piece
    "dormant": [0, 5, 0, 3], "rising": [0, 3, 4, 5], "peak": [5, 3, 0, 4],
    "recession": [0, 6, 5, 3], "low": [0, 3, 0, 5],
}
BAR_S = 0.75   # seconds per demo bar
TONIC = 50     # D3


def pairs(x):
    """3-day bars -> 6-day demo bars (mean of each pair)."""
    x = np.asarray(x, dtype=float)
    x = np.concatenate([x, x[-1:]]) if len(x) % 2 else x
    return x.reshape(-1, 2).mean(axis=1)


def main():
    Yr = Year.parse(sys.argv[1] if len(sys.argv) > 1 else "wy2024")
    q_all, _ = R.wsc_series("granby_08NN002_2010_2024.json")
    temp = R.climate_series("billings_1100_climate_2010_2024.json", "MEAN_TEMPERATURE")
    R.check_coverage({"Granby flow": q_all, "Billings temperature": temp}, Yr)
    q = R.in_year(q_all, year=Yr)
    T = R.in_year(temp, year=Yr)
    anom = pairs(per_bar(smooth(R.doy_percentile(q_all, year=Yr), 15))) - 0.5
    bright = pairs(per_bar(0.7 * norm01(Yr.daylength(49.03), 0, 100) + 0.3 * norm01(smooth(T, 15))))
    level = pairs(per_bar(norm01(np.log(q))))
    modes = H.mode_track(bright, anom, lo=1, hi=4, phrase=4)

    qlin = smooth(q / q.max(), 9)
    dq = np.gradient(qlin)
    doy = np.array([d.timetuple().tm_yday for d in Yr.days])
    phase_day = np.where((qlin < 0.1) & ((doy > 300) | (doy < 60)), "dormant",
                np.where(qlin > 0.5, "peak",
                np.where((dq > 0.004) & (qlin > 0.1), "rising",
                np.where((dq < -0.003) & (qlin > 0.15), "recession", "low"))))
    bar_phase = H.phase_bars(phase_day, min_run=6)[::2]
    chords = H.chord_track(bar_phase, PROG, bars_per_chord=2)

    nb = len(modes)
    n = int((nb * BAR_S + 6) * SR)
    rng = np.random.default_rng(7)
    B = {"pad": Bus("pad", n, gain=0.8, hp=150, send=0.5), "sub": Bus("sub", n, gain=0.7, lp=300, send=0.05),
         "pluck": Bus("pluck", n, gain=0.55, hp=300, send=0.35)}
    prev = None
    for b in range(0, nb, 2):
        pcs = H.chord(chords[b], modes[b], TONIC)
        v = H.voice_lead(prev, pcs, 57, 76)
        prev = v
        at = int(b * BAR_S * SR)
        for i, m in enumerate(v):
            B["pad"].add(Y.pad_note(m, 2 * BAR_S, vel=0.5, cutoff=700 + 1800 * level[b], a=0.3, r=0.8, rng=rng), at,
                         pan=(-0.5, -0.15, 0.15, 0.5)[i % 4])
        B["sub"].add(Y.sub_note(H.degree_to_midi(chords[b], modes[b], TONIC) - 12, 2 * BAR_S, vel=0.6), at)
    for b in range(nb):
        k = int(round(level[b] * 4))  # 0-4 plucks per bar as the river rises
        up = sorted({m + 12 * o for m in H.chord(chords[b], modes[b], TONIC) for o in (1, 2)})
        for j in range(k):
            B["pluck"].add(Y.pluck_note(up[min(j + int(level[b] * 3), len(up) - 1)], vel=0.4 + 0.3 * level[b], rng=rng),
                           int((b + j / max(k, 1)) * BAR_S * SR), pan=float(rng.uniform(-0.6, 0.6)))

    out = LIGHT_OUT / f"demo_{Yr.label.lower()}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    master(list(B.values()), {"hall": make_ir(2.8, bright=0.5)}, out)
    try:
        to_mp3(out, out.with_suffix(".mp3"))
    except (FileNotFoundError, OSError):
        pass  # no ffmpeg: the WAV is enough
    print(f"{Yr.label}: {nb} bars of {BAR_S} s -> {out}")
    for b in range(0, nb, 8):
        print(f"  {b * BAR_S:5.1f} s  {Yr.days[min(b * 6, Yr.n_days - 1)]:%b %d}  {H.MODES[modes[b]][0]:10s} {bar_phase[b]}")


if __name__ == "__main__":
    main()
