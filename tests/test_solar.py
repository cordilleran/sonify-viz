"""solar.py against the sun's position from JPL's DE421 ephemeris (skyfield),
sampled minute by minute along 100 W for 8 dates in 2024 and 13 latitudes
(tests/data/solar_reference.json, made once; the test needs no network),
plus the declination at four hours on each date."""
import datetime as dt
import json
from pathlib import Path

import solar

_FIX = json.loads((Path(__file__).parent / "data" / "solar_reference.json").read_text())
REF, DECL = _FIX["daylength"], _FIX["declination"]
NOON_UTC = 18 + 40 / 60  # local solar noon at 100 W, near enough for the declination


def _ours(r, threshold):
    decl = solar.declination(dt.date.fromisoformat(r["date"]), hour=NOON_UTC)
    return solar.hours_above(r["lat"], decl, threshold), decl


def test_declination_matches_the_ephemeris():
    for key, want in DECL.items():
        d, h = key.split("T")
        assert abs(solar.declination(dt.date.fromisoformat(d), hour=int(h)) - want) < 0.02, key


def test_mid_latitudes_within_three_minutes():
    for r in (r for r in REF if abs(r["lat"]) <= 45):
        dl, _ = _ours(r, solar.SUNRISE)
        assert abs(dl - r["daylength"]) * 60 < 3, r


def test_everywhere_within_a_third_of_a_degree_of_sun():
    """Near the polar circles day length is so sensitive that minutes are the
    wrong yardstick: a tenth of a degree of solar altitude moves hours. So the
    check is that the ephemeris value lies between our day lengths for a
    sunrise line 0.3 deg higher and 0.3 deg lower (plus 3 minutes of sampling
    slack). 0.3 deg covers the declination's drift over half a day and the
    small aberration terms our series leaves out."""
    for r in REF:
        for thr, key in ((solar.SUNRISE, "daylength"), (solar.CIVIL, "civil")):
            _, decl = _ours(r, thr)
            lo = solar.hours_above(r["lat"], decl, thr + 0.3)
            hi = solar.hours_above(r["lat"], decl, thr - 0.3)
            assert lo - 0.05 <= r[key] <= hi + 0.05, (r, key, lo, hi)


def test_poles_and_equator():
    june, dec = dt.date(2024, 6, 20), dt.date(2024, 12, 21)
    assert solar.day(90, june)["daylength"] == 24 and solar.day(90, dec)["daylength"] == 0
    assert solar.day(-90, dec)["daylength"] == 24 and solar.day(-90, june)["daylength"] == 0
    for d in (june, dec, dt.date(2024, 3, 20), dt.date(2024, 9, 22)):
        assert 12.0 < solar.day(0, d)["daylength"] < 12.2  # refraction adds ~7 minutes to the equator's 12 hours


def test_hemispheres_mirror():
    """A latitude's day under a declination equals the opposite latitude's under the opposite declination."""
    for decl in (-23.4, -10, 0, 10, 23.4):
        for lat in (15, 30, 45, 60, 75, 90):
            assert abs(solar.hours_above(lat, decl) - solar.hours_above(-lat, -decl)) < 1e-9
