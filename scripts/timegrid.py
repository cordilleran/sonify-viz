"""
Time for the pieces: which days a track covers (Year), how days become bars,
and how bars become seconds (Grid). Split out of seasonal.py on 2026-09-27.

A Year is a run of consecutive days with a start set by its FRAMING:

  water       Oct 1 by default (northern temperate hydrology); named by the
              calendar year it ends in, so WY2024 = Oct 1 2023 - Sep 30 2024.
              Pass start=(month, day) where the water-supply regime differs.
  calendar    Jan 1 - Dec 31.
  solstice    one solstice to the next (December by default, or June).
  lunar       12 lunations from the first new moon on or after an anchor
              date (Jan 1 by default): 354 or 355 days.
  equatorial  a start the track must supply, set by its water-supply regime
              (e.g. the onset of the rains); named like a water year.

Length follows the framing, so leap years, 365-day years and 354-day lunar
years all come out right. One BAR = 3 DAYS; a year whose length isn't a
multiple of 3 ends on a short bar (per_bar averages what that bar has).

Solstice and new-moon times use Meeus, Astronomical Algorithms (2nd ed.),
ch. 27 (mean solstice) and ch. 49 (new moon, main periodic terms); dates are
UTC and good to well under a day (tests/test_timegrid.py checks them against
published times).
"""
import datetime as dt
import math

import numpy as np

from dsp_core import SR, day_length_hours

DAYS_PER_BAR = 3

# ------------------------------------------------------------- astronomy ---

_J2000_ORDINAL_OFFSET = 1721424.5  # JD of 0001-01-01 00:00 is ordinal 1 + this


def _jd_to_datetime(jd):
    """Julian day -> UTC datetime (ignores the ~70 s TT-UT difference)."""
    days = jd - _J2000_ORDINAL_OFFSET
    ordinal = int(math.floor(days))
    return dt.datetime.fromordinal(ordinal) + dt.timedelta(days=days - ordinal)


def solstice(year, which="december"):
    """UTC datetime of the June or December solstice in `year` (Meeus table 27.B,
    valid 2000-3000; the periodic terms are left out, which costs minutes)."""
    Y = (year - 2000) / 1000
    if which == "december":
        jde = 2451900.05952 + 365242.74049 * Y - 0.06223 * Y**2 - 0.00823 * Y**3 + 0.00032 * Y**4
    elif which == "june":
        jde = 2451716.56767 + 365241.62603 * Y + 0.00325 * Y**2 + 0.00888 * Y**3 - 0.00030 * Y**4
    else:
        raise ValueError(f"solstice: which must be 'december' or 'june', not {which!r}")
    return _jd_to_datetime(jde)


def _new_moon_jde(k):
    """Meeus ch. 49: JDE of new moon number k (k = 0 near 2000-01-06)."""
    T = k / 1236.85
    jde = (2451550.09766 + 29.530588861 * k + 0.00015437 * T**2
           - 0.000000150 * T**3 + 0.00000000073 * T**4)
    E = 1 - 0.002516 * T - 0.0000074 * T**2
    r = math.radians
    M = r(2.5534 + 29.10535670 * k - 0.0000014 * T**2 - 0.00000011 * T**3)
    Mp = r(201.5643 + 385.81693528 * k + 0.0107582 * T**2 + 0.00001238 * T**3 - 0.000000058 * T**4)
    F = r(160.7108 + 390.67050284 * k - 0.0016118 * T**2 - 0.00000227 * T**3 + 0.000000011 * T**4)
    Om = r(124.7746 - 1.56375588 * k + 0.0020672 * T**2 + 0.00000215 * T**3)
    s = math.sin
    jde += (-0.40720 * s(Mp) + 0.17241 * E * s(M) + 0.01608 * s(2 * Mp) + 0.01039 * s(2 * F)
            + 0.00739 * E * s(Mp - M) - 0.00514 * E * s(Mp + M) + 0.00208 * E**2 * s(2 * M)
            - 0.00111 * s(Mp - 2 * F) - 0.00057 * s(Mp + 2 * F) + 0.00056 * E * s(2 * Mp + M)
            - 0.00042 * s(3 * Mp) + 0.00042 * E * s(M + 2 * F) + 0.00038 * E * s(M - 2 * F)
            - 0.00024 * E * s(2 * Mp - M) - 0.00017 * s(Om))
    return jde


def new_moons_from(anchor, n):
    """UTC datetimes of the first `n` new moons whose UTC date is on or after `anchor`."""
    k = math.floor((anchor.year + (anchor.timetuple().tm_yday - 1) / 365.25 - 2000) * 12.3685) - 1
    out = []
    while len(out) < n:
        t = _jd_to_datetime(_new_moon_jde(k))
        if t.date() >= anchor:
            out.append(t)
        k += 1
    return out


# ------------------------------------------------------------------ year ---

FRAMINGS = ("water", "calendar", "solstice", "lunar", "equatorial")


class Year:
    """The days one track covers: `start` (inclusive) to `end` (exclusive)."""

    def __init__(self, start, end, framing, label):
        if framing not in FRAMINGS:
            raise ValueError(f"unknown framing {framing!r}; one of {FRAMINGS}")
        self.start, self.end, self.framing, self.label = start, end, framing, label
        self.n_days = (end - start).days
        self.days = [start + dt.timedelta(i) for i in range(self.n_days)]
        self.n_bars = -(-self.n_days // DAYS_PER_BAR)

    def __repr__(self):
        return f"Year({self.label}: {self.start} to {self.days[-1]}, {self.n_days} days, {self.n_bars} bars)"

    # --- framings -----------------------------------------------------------

    @classmethod
    def water(cls, year, start=(10, 1)):
        """Water year `year`, ending in calendar year `year` (WY2024 = Oct 2023 - Sep 2024)."""
        s = dt.date(year if start == (1, 1) else year - 1, *start)
        tag = "" if start == (10, 1) else f"@{start[0]:02d}-{start[1]:02d}"
        return cls(s, s.replace(year=s.year + 1), "water", f"WY{year}{tag}")

    @classmethod
    def calendar(cls, year):
        return cls(dt.date(year, 1, 1), dt.date(year + 1, 1, 1), "calendar", f"CY{year}")

    @classmethod
    def solstice(cls, year, which="december"):
        """From the `which` solstice of `year` to the same solstice a year later."""
        s, e = solstice(year, which).date(), solstice(year + 1, which).date()
        return cls(s, e, "solstice", f"{'DS' if which == 'december' else 'JS'}{year}")

    @classmethod
    def lunar(cls, year, anchor=None):
        """12 lunations from the first new moon on or after `anchor` (default Jan 1 of `year`)."""
        moons = new_moons_from(anchor or dt.date(year, 1, 1), 13)
        return cls(moons[0].date(), moons[12].date(), "lunar", f"LY{moons[0].date():%Y%m%d}")

    @classmethod
    def equatorial(cls, year, start):
        """A year set by the local water-supply regime; `start` = (month, day) is required."""
        s = dt.date(year if start == (1, 1) else year - 1, *start)
        return cls(s, s.replace(year=s.year + 1), "equatorial", f"EY{year}@{start[0]:02d}-{start[1]:02d}")

    @classmethod
    def parse(cls, spec):
        """'wy2024', 'wy2024@07-01', 'cy2024', 'ds2023', 'js2024', 'ly2024',
        'ly2024@2024-02-10', 'ey2024@11-01' -> Year. Used by the pieces' --year flag."""
        s = spec.strip().lower()
        head, _, at = s.partition("@")
        kind, num = head[:2], int(head[2:])
        md = tuple(int(p) for p in at.split("-")) if at else None
        if kind == "wy":
            return cls.water(num, md or (10, 1))
        if kind == "cy":
            return cls.calendar(num)
        if kind in ("ds", "js"):
            return cls.solstice(num, "december" if kind == "ds" else "june")
        if kind == "ly":
            return cls.lunar(num, dt.date(*md) if md else None)
        if kind == "ey":
            if not md:
                raise ValueError("an equatorial year needs its start: ey2024@MM-DD")
            return cls.equatorial(num, md)
        raise ValueError(f"can't read year spec {spec!r}")

    # --- day helpers --------------------------------------------------------

    def doy_index(self, doy):
        """Index into `days` of calendar day-of-year `doy` (1-366); the first
        occurrence if the year spans two of them. ValueError if it isn't in the year."""
        for i, d in enumerate(self.days):
            if d.timetuple().tm_yday == doy:
                return i
        raise ValueError(f"day-of-year {doy} isn't in {self.label}")

    def daylength(self, lat):
        """Astronomical day length (hours) at latitude `lat` for each day."""
        return np.array([day_length_hours(d.timetuple().tm_yday, lat) for d in self.days])


WY2024 = Year.water(2024)  # the default: every piece before 2026-09-27 was WY2024

# ------------------------------------------------------------------ grid ---


class Grid:
    def __init__(self, bpm, n_bars=WY2024.n_bars, beats_per_bar=4, tail_s=10.0):
        self.bpm = bpm
        self.beat = 60.0 / bpm
        self.bar = self.beat * beats_per_bar
        self.n_bars = n_bars
        self.dur = n_bars * self.bar + tail_s
        self.n = int(self.dur * SR)

    def t(self, bar, beat=0.0):
        return (bar + beat / 4.0) * self.bar

    def s(self, bar, beat=0.0, jitter_ms=0.0, rng=None):
        j = (rng.normal(0, jitter_ms) / 1000.0) if (rng is not None and jitter_ms) else 0.0
        return max(0, int((self.t(bar, beat) + j) * SR))

    def day_to_time(self, day_float):
        return day_float / DAYS_PER_BAR * self.bar


def per_bar(x, how="mean"):
    """Daily array -> one value per bar (mean, sum, max...). A short last bar
    (years that aren't a multiple of 3 days) reduces over the days it has."""
    x = np.asarray(x)
    n_bars = -(-len(x) // DAYS_PER_BAR)
    pad = n_bars * DAYS_PER_BAR - len(x)
    if pad == 0:
        return getattr(x.reshape(n_bars, DAYS_PER_BAR), how)(axis=1)
    x = np.concatenate([x.astype(float), np.full(pad, np.nan)]).reshape(n_bars, DAYS_PER_BAR)
    return getattr(np, "nan" + how)(x, axis=1)


# --------------------------------------------------------- daily helpers ---

def norm01(x, lo_pct=2, hi_pct=98):
    lo, hi = np.percentile(x, lo_pct), np.percentile(x, hi_pct)
    return np.clip((x - lo) / (hi - lo + 1e-12), 0, 1)


def smooth(x, win):
    k = np.ones(win) / win
    xp = np.concatenate([np.full(win, x[0]), x, np.full(win, x[-1])])
    return np.convolve(xp, k, mode="same")[win:-win]


def events_from_flag(flag, min_gap=3):
    """Onset/offset day indices of runs in a boolean daily flag, merging gaps
    shorter than `min_gap` days (so one mild afternoon doesn't 'break up' the
    ice and re-freeze it the next day)."""
    f = flag.astype(bool).copy()
    idx = np.flatnonzero(f)
    for a, b in zip(idx[:-1], idx[1:]):
        if 1 < b - a <= min_gap:
            f[a:b] = True
    on = np.flatnonzero(f & ~np.r_[False, f[:-1]])
    off = np.flatnonzero(f & ~np.r_[f[1:], False])
    return list(zip(on, off)), f


def fmt_time(sec):
    return f"{int(sec // 60)}:{int(sec % 60):02d}"
