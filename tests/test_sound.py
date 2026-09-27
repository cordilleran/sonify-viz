"""Sound sources (sampler.py, synth.py): pitch parsing and measurement, oscillators,
envelopes, and seeded determinism. No sample files are read."""
import numpy as np
import pytest

import sampler as S
import synth as Y

SR = S.SR


@pytest.mark.parametrize("name,offset,midi", [
    ("Cello_A2_v1.wav", 0, 45), ("piano_C4.wav", 0, 60), ("harp_F#3_ff.wav", 0, 54),
    ("Bb1_sustain.wav", 0, 34), ("glock_C5.wav", 1, 84), ("no_pitch_here.wav", 0, None),
])
def test_name_to_midi(name, offset, midi):
    assert S.name_to_midi(name, offset) == midi


@pytest.mark.parametrize("hz", [55.0, 110.0, 220.0, 440.0])
def test_estimate_f0_on_a_synthetic_tone(hz):
    t = np.arange(int(0.8 * SR)) / SR
    x = np.sin(2 * np.pi * hz * t) + 0.3 * np.sin(2 * np.pi * 2 * hz * t)
    f0 = S.estimate_f0(np.stack([x, x], axis=1))
    assert abs(f0 / hz - 1) < 0.02


@pytest.mark.parametrize("kind", ["sine", "saw", "square", "tri"])
def test_oscillator_pitch_by_fft(kind):
    n = SR
    x = Y.osc(kind, 220.0, n)
    spec = np.abs(np.fft.rfft(x * np.hanning(n)))
    assert abs(np.argmax(spec) - 220) <= 1
    assert np.abs(x).max() < 1.3


def test_midi_hz():
    assert Y.midi_hz(69) == 440.0
    assert abs(Y.midi_hz(57) - 220.0) < 1e-9


def test_adsr_shape():
    n = SR
    e = Y.env_adsr(n, a=0.1, d=0.2, s=0.5, r=0.3)
    assert len(e) == n and e[0] == 0
    assert abs(e[int(0.1 * SR) - 1] - 1) < 0.01
    assert e[-1] < 0.05


def test_seeded_sources_are_deterministic():
    a = Y.supersaw(110.0, 4000, rng=np.random.default_rng(9))
    b = Y.supersaw(110.0, 4000, rng=np.random.default_rng(9))
    assert np.array_equal(a, b)
    assert np.array_equal(S.make_ir(0.5, seed=4), S.make_ir(0.5, seed=4))
    n = 8000
    d1 = Y.drone([50, 57], n, np.full(n, 800.0), np.full(n, 0.5), rng=np.random.default_rng(2))
    d2 = Y.drone([50, 57], n, np.full(n, 800.0), np.full(n, 0.5), rng=np.random.default_rng(2))
    assert np.array_equal(d1, d2) and d1.shape == (n, 2)


def test_drone_pitch_is_fixed_while_level_rises():
    """Paper §4.3: the CO2 drone rises in level, not in pitch."""
    n = 2 * SR
    lvl = np.linspace(0.1, 1.0, n)
    x = Y.drone([50], n, np.full(n, 1200.0), lvl, rng=np.random.default_rng(1))[:, 0]
    early, late = x[: SR // 2], x[-SR // 2:]
    assert np.sqrt((late ** 2).mean()) > 3 * np.sqrt((early ** 2).mean())
    pk = lambda seg: np.argmax(np.abs(np.fft.rfft(seg * np.hanning(len(seg)))))
    assert pk(early) == pk(late)
