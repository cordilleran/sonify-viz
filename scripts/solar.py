"""
The sun's geometry for any latitude and date (2026-09-27, for the Meridian
Chorus): declination, altitude through the day, day length and twilight.

dsp_core.day_length_hours uses a one-term declination and the geometric
horizon, which is fine at 49 N but jumps between 0 and 24 hours at the poles
on the equinox. This module follows NOAA's solar calculator (Meeus, Astronomical
Algorithms, ch. 25, the low-precision solar position: good to about 0.01
deg). NOAA's shorter fractional-year Fourier series was tried first and was
off by up to 0.5 deg of declination against the JPL ephemeris, so it isn't
used. The module counts the sun as up when its centre is above -0.833 deg:
0.567 deg of atmospheric refraction at the horizon plus the sun's 0.266 deg
half-width, the standard sunrise definition. Civil twilight is the sun
between -6 deg and that.

Accuracy: declination within 0.02 deg of the ephemeris (tested), so day length to a minute or two at
mid-latitudes; near the polar circles, where the sun grazes the horizon for
days, the first and last day of polar day can shift by a day.
tests/test_solar.py checks it against JPL-ephemeris values (skyfield).

All points on one meridian share solar noon, so for a meridian piece the
hour angle alone places each voice in its day: 0 at noon, +-180 deg at
midnight.
"""
import datetime as dt

import numpy as np

SUNRISE = -0.833   # deg: the sun's centre at sunrise and sunset (refraction + half-width)
CIVIL = -6.0       # deg: the end of civil twilight


def _julian_century(date, hour=12.0):
    """Julian centuries since J2000.0 for `date` at `hour` UTC."""
    jd = date.toordinal() + 1721424.5 + hour / 24.0
    return (jd - 2451545.0) / 36525.0


def _sun(date, hour=12.0):
    """(declination deg, equation of time min), following NOAA's solar
    calculator (Meeus, Astronomical Algorithms, ch. 25, low precision)."""
    T = _julian_century(date, hour)
    L0 = (280.46646 + T * (36000.76983 + 0.0003032 * T)) % 360          # mean longitude
    M = 357.52911 + T * (35999.05029 - 0.0001537 * T)                    # mean anomaly
    e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T)              # orbit eccentricity
    Mr = np.radians(M)
    C = (np.sin(Mr) * (1.914602 - T * (0.004817 + 0.000014 * T)) + np.sin(2 * Mr) * (0.019993 - 0.000101 * T)
         + np.sin(3 * Mr) * 0.000289)                                    # equation of centre
    omega = 125.04 - 1934.136 * T
    lam = L0 + C - 0.00569 - 0.00478 * np.sin(np.radians(omega))         # apparent longitude
    eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60
    eps = eps0 + 0.00256 * np.cos(np.radians(omega))                     # corrected obliquity
    decl = np.degrees(np.arcsin(np.sin(np.radians(eps)) * np.sin(np.radians(lam))))
    y = np.tan(np.radians(eps / 2)) ** 2
    L0r = np.radians(L0)
    eot = 4 * np.degrees(y * np.sin(2 * L0r) - 2 * e * np.sin(Mr) + 4 * e * y * np.sin(Mr) * np.cos(2 * L0r)
                         - 0.5 * y * y * np.sin(4 * L0r) - 1.25 * e * e * np.sin(2 * Mr))
    return float(decl), float(eot)


def declination(date, hour=12.0):
    """The sun's declination in degrees at `hour` UTC; also the subsolar latitude."""
    return _sun(date, hour)[0]


def equation_of_time(date, hour=12.0):
    """Minutes by which true solar noon precedes mean noon."""
    return _sun(date, hour)[1]


def altitude(lat, decl, hour_angle):
    """Solar altitude in degrees. hour_angle in degrees from local solar noon
    (negative before noon). Works on numpy arrays."""
    lat, decl, h = np.radians(lat), np.radians(decl), np.radians(hour_angle)
    s = np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(h)
    return np.degrees(np.arcsin(np.clip(s, -1, 1)))


def hours_above(lat, decl, threshold=SUNRISE):
    """Hours in the day with the sun above `threshold` degrees, for a given
    declination: 0 in polar night, 24 in polar day. Exact at the poles."""
    lat_r, dec_r, t = np.radians(lat), np.radians(decl), np.radians(threshold)
    den = np.cos(lat_r) * np.cos(dec_r)
    if abs(den) < 1e-12:  # at a pole the sun circles at a constant altitude equal to +-declination
        return 24.0 if altitude(lat, decl, 0.0) > threshold else 0.0
    c = (np.sin(t) - np.sin(lat_r) * np.sin(dec_r)) / den
    if c <= -1:
        return 24.0
    if c >= 1:
        return 0.0
    return 2 * np.degrees(np.arccos(c)) / 15.0


def day(lat, date):
    """One day's numbers at `lat`: day length and civil-twilight length (hours),
    sunrise and sunset in local solar time (None in polar day or night), and
    the noon altitude."""
    decl = declination(date)
    up = hours_above(lat, decl, SUNRISE)
    lit = hours_above(lat, decl, CIVIL)
    rise = None if up in (0.0, 24.0) else 12 - up / 2
    return {"daylength": up, "civil": lit, "twilight": (lit - up) / 2, "sunrise": rise,
            "sunset": None if rise is None else 24 - rise, "noon_altitude": float(altitude(lat, decl, 0.0)),
            "declination": float(decl)}
