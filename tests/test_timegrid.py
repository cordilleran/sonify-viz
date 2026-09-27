"""The water-year time grid and the per-bar reductions (seasonal.py)."""
import datetime as dt

import numpy as np

import seasonal as W


def test_water_year_calendar():
    assert W.DAYS[0] == dt.date(2023, 10, 1)
    assert W.DAYS[-1] == dt.date(2024, 9, 30)  # WY2024 is a leap water year: 366 days
    assert W.N_BARS == 122 and W.DAYS_PER_BAR == 3


def test_grid_timing_matches_the_paper():
    g = W.Grid(72)  # Granby: 3.33 s per bar
    assert abs(g.bar - 10 / 3) < 1e-9
    assert abs(g.dur - (122 * 10 / 3 + 10)) < 1e-9
    g = W.Grid(64)  # Okanagan: 3.75 s per bar
    assert abs(g.bar - 3.75) < 1e-9
    assert g.s(1) == int(3.75 * W.SR)
    assert abs(g.day_to_time(3) - g.bar) < 1e-9


def test_grid_jitter_is_seeded():
    g = W.Grid(72)
    a = [g.s(b, 1, 12, np.random.default_rng(5)) for b in range(10)]
    b = [g.s(b, 1, 12, np.random.default_rng(5)) for b in range(10)]
    assert a == b and min(a) >= 0


def test_per_bar_mean_and_sum():
    x = np.arange(W.N_DAYS, dtype=float)
    m = W.per_bar(x)
    assert len(m) == W.N_BARS and m[0] == 1.0
    assert W.per_bar(np.ones(W.N_DAYS), "sum")[5] == 3.0


def test_smooth_preserves_constants_and_edges():
    assert np.allclose(W.smooth(np.full(50, 2.5), 7), 2.5)
    ramp = np.linspace(0, 1, 50)
    s = W.smooth(ramp, 5)
    assert len(s) == 50 and abs(s[25] - ramp[25]) < 1e-9


def test_norm01_clips_to_unit_range():
    rng = np.random.default_rng(0)
    y = W.norm01(rng.normal(size=1000))
    assert y.min() == 0 and y.max() == 1


def test_doy_percentile_normal_is_one_half():
    series = {str(dt.date(y, 1, 1) + dt.timedelta(i)): 5.0 for y in range(2010, 2025) for i in range(365)}
    p = W.doy_percentile(series)
    assert np.allclose(p, 0.5)
