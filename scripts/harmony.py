"""
The harmonic grammar shared by the pieces: pure functions, no I/O. Split out
of seasonal.py on 2026-09-27.

Music-theory model (written up for GW in the listening guide):
  MODES ordered dark -> bright. Neighbours differ by exactly ONE note, so
  sliding one step along this ladder is the smallest possible change of mood.
  The season sets a base brightness (day length); the anomaly vs. that day's
  15-year normal nudges it one step darker (drought/low) or brighter (high).
"""
import numpy as np

from timegrid import DAYS_PER_BAR

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
    """Place each target pitch-class in [lo,hi] near the previous voicing.
    NOTE (2026-09-26 tests): tone i is placed near previous voice i, but the
    previous voicing is sorted and the new chord isn't, so this is not the
    minimal motion its name promises (tests/test_harmony.py, strict xfail).
    The fix changes the music, so it waits for GW's A/B (sprint plan §3)."""
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


def phase_bars(phase_day, min_run=6):
    """Daily phase labels -> one label per bar (majority vote), then any run
    shorter than `min_run` bars is absorbed into the run before it, so the
    progression doesn't flip back and forth on a two-day wobble."""
    n_bars = -(-len(phase_day) // DAYS_PER_BAR)
    raw = []
    for b in range(n_bars):
        v, c = np.unique(phase_day[b * DAYS_PER_BAR:(b + 1) * DAYS_PER_BAR], return_counts=True)
        raw.append(v[np.argmax(c)])
    runs, i = [], 0
    while i < n_bars:
        j = i
        while j < n_bars and raw[j] == raw[i]:
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
