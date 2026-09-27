"""The year as a parameter (timegrid.Year): framings, lengths, and the
astronomy the solstice and lunar framings rest on."""
import datetime as dt

import numpy as np
import pytest

import records as R
import timegrid as T


def test_wy2024_is_the_default_and_unchanged():
    y = T.WY2024
    assert (y.start, y.days[-1], y.n_days, y.n_bars) == (dt.date(2023, 10, 1), dt.date(2024, 9, 30), 366, 122)
    assert y.label == "WY2024"


@pytest.mark.parametrize("spec, first, last, n_days", [
    ("wy2023", dt.date(2022, 10, 1), dt.date(2023, 9, 30), 365),        # not a leap water year
    ("wy2024", dt.date(2023, 10, 1), dt.date(2024, 9, 30), 366),
    ("wy2024@07-01", dt.date(2023, 7, 1), dt.date(2024, 6, 30), 366),  # a July water year
    ("cy2023", dt.date(2023, 1, 1), dt.date(2023, 12, 31), 365),
    ("cy2024", dt.date(2024, 1, 1), dt.date(2024, 12, 31), 366),
    ("ds2023", dt.date(2023, 12, 22), dt.date(2024, 12, 20), 365),     # solstice to solstice
    ("js2024", dt.date(2024, 6, 20), dt.date(2025, 6, 20), 366),
    ("ly2024", dt.date(2024, 1, 11), dt.date(2024, 12, 29), 354),      # 12 lunations
    ("ey2024@11-01", dt.date(2023, 11, 1), dt.date(2024, 10, 31), 366),
])
def test_framings_start_and_length(spec, first, last, n_days):
    y = T.Year.parse(spec)
    assert (y.days[0], y.days[-1], y.n_days) == (first, last, n_days)
    assert y.days == [first + dt.timedelta(i) for i in range(n_days)]  # consecutive, no gaps
    assert y.n_bars == -(-n_days // 3)


def test_labels_differ_when_the_start_differs():
    labels = {T.Year.parse(s).label for s in ["wy2024", "wy2024@07-01", "ey2024@10-01", "cy2024"]}
    assert len(labels) == 4


def test_equatorial_needs_its_start():
    with pytest.raises(ValueError):
        T.Year.parse("ey2024")


@pytest.mark.parametrize("year, which, published", [
    (2023, "december", dt.datetime(2023, 12, 22, 3, 27)),
    (2024, "december", dt.datetime(2024, 12, 21, 9, 21)),
    (2024, "june", dt.datetime(2024, 6, 20, 20, 51)),
    (2025, "june", dt.datetime(2025, 6, 21, 2, 42)),
])
def test_solstice_within_fifteen_minutes_of_published(year, which, published):
    assert abs(T.solstice(year, which) - published) < dt.timedelta(minutes=15)


def test_new_moons_within_fifteen_minutes_of_published():
    published = [dt.datetime(2023, 12, 12, 23, 32), dt.datetime(2024, 1, 11, 11, 57),
                 dt.datetime(2024, 2, 9, 22, 59), dt.datetime(2024, 12, 1, 6, 21),
                 dt.datetime(2025, 1, 29, 12, 36)]
    for p in published:
        got = T.new_moons_from(p.date(), 1)[0]
        assert abs(got - p) < dt.timedelta(minutes=15), (p, got)


def test_doy_index_matches_the_old_wy2024_arithmetic():
    y = T.WY2024
    for doy in (1, 71, 140, 274, 365):  # 366 (Dec 31 2024) falls outside WY2024
        i = y.doy_index(doy)
        assert y.days[i].timetuple().tm_yday == doy
    with pytest.raises(ValueError):
        y.doy_index(366)


def test_per_bar_short_last_bar():
    x = np.arange(365, dtype=float)  # 121 full bars + one 2-day bar
    m = T.per_bar(x)
    assert len(m) == 122 and m[-1] == 363.5
    assert T.per_bar(np.ones(365), "sum")[-1] == 2.0


def test_records_follow_the_year():
    y = T.Year.parse("cy2023")
    series = {str(d): float(i) for i, d in enumerate(y.days)}
    assert np.array_equal(R.in_year(series, year=y), np.arange(365.0))
    assert R.coverage(series, year=y) == 1.0 and R.coverage(series) < 1.0  # WY2024 only overlaps 3 months
