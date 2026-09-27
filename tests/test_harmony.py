"""The harmonic grammar (seasonal.py): the mode ladder, the consonance guards, voice leading,
and the slow-moving tracks that turn data into harmony. Pure functions, no data files."""
import itertools

import numpy as np
import pytest

import seasonal as W

TONICS = [38, 45, 50, 53]  # D2, A2, D3, F3: the keys the pieces use


def test_six_modes_dark_to_bright():
    assert [m[0] for m in W.MODES] == ["Phrygian", "Aeolian", "Dorian", "Mixolydian", "Ionian", "Lydian"]
    for name, steps in W.MODES:
        assert len(steps) == 7 and steps[0] == 0
        assert steps == sorted(steps) and steps[-1] < 12, name


def test_ladder_neighbours_differ_by_one_raised_semitone():
    """Paper §3.4.1: each step up the ladder raises exactly one degree by one semitone."""
    for (_, a), (_, b) in zip(W.MODES, W.MODES[1:]):
        diffs = [(x, y) for x, y in zip(a, b) if x != y]
        assert len(diffs) == 1
        x, y = diffs[0]
        assert y - x == 1


@pytest.mark.parametrize("mode_idx", range(6))
def test_degree_to_midi_octave_wrap(mode_idx):
    for tonic in TONICS:
        for deg in range(-7, 15):
            assert W.degree_to_midi(deg + 7, mode_idx, tonic) == W.degree_to_midi(deg, mode_idx, tonic) + 12
        assert W.degree_to_midi(0, mode_idx, tonic) == tonic


@pytest.mark.parametrize("mode_idx,deg", list(itertools.product(range(6), range(7))))
def test_consonance_guards_exhaustive(mode_idx, deg):
    """Paper §3.4.4: no chord tone a tritone (6) or minor second (1) above the root,
    for every scale degree in every mode, default add9 voicing and with a 7th."""
    for tonic in TONICS:
        for ext in [(0, 2, 4, 8), (0, 2, 4, 6), (0, 4, 8), (0, 2, 4)]:
            c = W.chord(deg, mode_idx, tonic, ext)
            ivs = {(m - c[0]) % 12 for m in c}
            assert 6 not in ivs and 1 not in ivs, (W.MODES[mode_idx][0], deg, ext, c)


def test_diminished_triad_is_substituted():
    """Degree vii of Ionian is diminished; the guard swaps in the chord a third below (V)."""
    ionian = 4
    assert W.chord(6, ionian, 60, (0, 2, 4)) == W.chord(4, ionian, 60, (0, 2, 4))


def test_voice_lead_keeps_pitch_classes_in_range_and_sorted():
    rng = np.random.default_rng(3)
    prev = None
    for _ in range(200):
        target = W.chord(int(rng.integers(0, 7)), int(rng.integers(1, 6)), 50)
        out = W.voice_lead(prev, target, 50, 74)
        assert sorted(m % 12 for m in out) == sorted(m % 12 for m in target)
        assert all(50 <= m <= 74 for m in out)
        assert out == sorted(out)
        prev = out


@pytest.mark.xfail(strict=True, reason=(
    "Known issue, found by this test 2026-09-26: voice_lead matches target tone i to previous voice i, "
    "but the previous voicing is sorted and the target is in chord order, so a repeated chord can be "
    "re-voiced (5 of 62 repeats in Granby WY2024) and motion runs ~2.7x the minimum. Fixing it changes "
    "every render, so it waits for a listening comparison (the Granby v1.1 A/B)."))
def test_voice_lead_moves_minimally_on_a_repeated_chord():
    c = W.chord(0, 2, 50)
    first = W.voice_lead(None, c, 48, 72)
    assert W.voice_lead(first, c, 48, 72) == first


def test_mode_track_moves_only_at_phrase_boundaries_by_one_step():
    n = 122
    season = (1 - np.cos(np.linspace(0, 2 * np.pi, n))) / 2
    anomaly = 0.5 * np.sin(np.linspace(0, 9, n))
    m = W.mode_track(season, anomaly)
    assert m.min() >= 1 and m.max() <= 5  # Phrygian excluded by default
    for b in range(1, n):
        if m[b] != m[b - 1]:
            assert b % 8 == 0
            assert abs(int(m[b]) - int(m[b - 1])) == 1


def test_mode_track_winter_floor_is_aeolian():
    """Paper §3.4.1: at the dark end, a below-normal anomaly cannot push past Aeolian."""
    m = W.mode_track(np.zeros(64), np.full(64, -0.5))
    assert set(m.tolist()) == {1}


def test_phase_bars_absorbs_short_runs():
    days = np.array(["low"] * 60 + ["peak"] * 6 + ["low"] * 60 + ["peak"] * 240)[: W.N_BARS * W.DAYS_PER_BAR]
    bars = W.phase_bars(days, min_run=6)
    assert len(bars) == W.N_BARS
    runs = [len(list(g)) for _, g in itertools.groupby(bars)]
    assert all(r >= 6 for r in runs[1:])
    assert bars[20] == "low"  # the 2-bar peak blip was absorbed


def test_chord_track_restarts_loop_on_phase_change():
    prog = {"a": [0, 3, 4, 5], "b": [5, 3, 0, 4]}
    bars = ["a"] * 8 + ["b"] * 8
    ch = W.chord_track(bars, prog, bars_per_chord=2)
    assert ch[:8] == [0, 0, 3, 3, 4, 4, 5, 5]
    assert ch[8:10] == [5, 5]


def test_fire_bars_is_deterministic_and_proportional():
    x = np.linspace(0, 1, 100)
    a, b = W.fire_bars(x, rate=0.3), W.fire_bars(x, rate=0.3)
    assert a == b
    assert len(a) == int(0.5 + x.sum() * 0.3)
    assert W.fire_bars(np.zeros(50), rate=1.0) == set()
