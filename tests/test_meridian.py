"""The Meridian Chorus's daylight layer (meridian.py): the envelopes follow the
sun, the chorus shares one noon, and any set of voices is consonant."""
import datetime as dt
import itertools

import numpy as np

import meridian as M
import solar
from timegrid import Year

P = dict(M.DEFAULTS)
Y = Year.parse(P["year"])


def _track(n_breaths=53):
    return M.solar_track(Y, P, n_breaths)


def test_every_voice_is_centred_on_one_noon():
    """Mid-breath is noon for everyone: each note's envelope is symmetric about it."""
    t, ha, decl, frac = _track()
    per = int(P["breath_s"] * M.CTRL)
    for lat in M.LATS:
        note, _, _ = M.envelopes(lat, ha, decl, frac, True)
        for k in range(53):
            # away from midnight, where the declination blends toward the next breath (by design, and
            # 80 ms of click smoothing reaches into it); every note is centred on the one noon
            b = note[k * per:(k + 1) * per][per // 10 + 20:per - per // 10 - 19]
            assert np.allclose(b, b[::-1], atol=1e-3), (lat, k)


def test_polar_day_holds_and_polar_night_only_breathes():
    t, ha, decl, frac = _track()
    per = int(P["breath_s"] * M.CTRL)
    k = 26  # late June
    north, _, n_in = M.envelopes(90, ha, decl, frac, True)
    south, _, s_in = M.envelopes(-90, ha, decl, frac, True)
    assert north[k * per:(k + 1) * per].min() > 0.95 and n_in[k * per:(k + 1) * per].max() < 1e-6
    assert south[k * per:(k + 1) * per].max() < 1e-6 and s_in[k * per:(k + 1) * per].max() > 0.9
    # polar day at 75 N holds through midnight: no dip where the sun runs low (both agy reviewers, 09-27)
    n75, _, _ = M.envelopes(75, ha, decl, frac, True)
    assert n75[k * per:(k + 1) * per].min() > 0.99
    # at a pole the sun circles at one height, so the in-breath is steady, not pulsing
    assert s_in[k * per:(k + 1) * per].std() < 1e-6


def test_note_length_follows_day_length():
    """At every latitude, the share of a breath sung at full voice is the day's
    length / 24, for the breath's own day. Breaths where polar day or night
    begins or ends are skipped: there the midnight blend toward the neighbouring
    breath (by design) moves the edge."""
    t, ha, decl, frac = _track()
    per = int(P["breath_s"] * M.CTRL)
    noon_utc = 12 - P["meridian"] / 15.0
    dpb = P["days_per_breath"]
    dl = lambda lat, k: solar.hours_above(lat, solar.declination(Y.start + dt.timedelta(k * dpb + dpb // 2), noon_utc))
    for lat in M.LATS:
        note, _, _ = M.envelopes(lat, ha, decl, frac, True)  # full voice (>0.5) is the day; twilight is 0.3
        for k in range(1, 52):
            want = dl(lat, k)
            near = [dl(lat, k - 1), want, dl(lat, k + 1)]
            if any(x in (0.0, 24.0) for x in near) and len(set(near)) > 1:  # polar day or night begins or ends
                continue
            got = (note[k * per:(k + 1) * per] > 0.5).mean()
            assert abs(got - want / 24) < 0.03, (lat, k, got, want / 24)  # 3% of a breath, about 40 minutes of the day


def test_movements_cut_at_the_equinoxes_and_june_solstice():
    for dpb in (7, 3):
        p = dict(P, days_per_breath=dpb)
        nb = -(-Y.n_days // dpb)
        cuts = M.movement_cuts(Y, p, nb)
        assert len(cuts) == 3, cuts
        played = [Y.start + dt.timedelta(c * dpb + dpb // 2) for c in cuts]
        for got, want in zip(played, (dt.date(2024, 3, 20), dt.date(2024, 6, 20), dt.date(2024, 9, 22))):
            assert abs((got - want).days) <= dpb, (dpb, got, want)


def test_every_set_of_voices_is_consonant():
    """No two pitches a semitone, a tritone or a major seventh apart, in any octave."""
    for reg, pitches in M.PITCH.items():
        for a, b in itertools.combinations(set(pitches.values()), 2):
            assert abs(a - b) % 12 not in (1, 6, 11), (reg, a, b)


# ---- layer 2 (2026-09-27): air, sea and ice ---------------------------------------------------------

def test_layer_two_is_off_by_default():
    """Layer 1's published parameters are untouched: the default render stays daylight only."""
    assert P["layers"] == ["daylight"]


def test_covariates_are_block_means_with_the_right_voices():
    import json
    n_breaths = -(-Y.n_days // P["days_per_breath"])
    C = M.covariates(Y, P, n_breaths)
    raw = json.loads((M.DATA / "meridian_100w_ds2023.json").read_text())["voices"]
    for lat in M.LATS:
        c = C[lat]
        assert len(c["tmax"]) == n_breaths and np.isfinite(c["tmax"]).all() and np.isfinite(c["tmin"]).all()
        assert (c["tmax"] >= c["tmin"]).all(), lat
        assert (c["sst"] is not None) == ("sst" in raw[str(lat)]), lat
        assert (c["ice"] is not None) == ("ice" in raw[str(lat)]), lat
    # breath 0 is the mean of the year's first 7 days (the air record has no gaps)
    a = raw["45"]["air"]
    assert np.isclose(C[45]["tmax"][0], np.mean(a["max"][:7]))
    # land voices have no sea; the four ice voices are the polar seas
    assert all(C[lat]["sst"] is None for lat in (60, 45, 30, -90))
    assert sorted(lat for lat in M.LATS if C[lat]["ice"] is not None) == [-75, -60, 75, 90]
    assert all(((C[lat]["ice"] >= 0) & (C[lat]["ice"] <= 1)).all() for lat in (90, 75, -60, -75))


def test_every_series_says_where_it_came_from():
    """Spec §7: each source records the cell it used and its distance from the nominal point."""
    import json
    raw = json.loads((M.DATA / "meridian_100w_ds2023.json").read_text())["voices"]
    for lat, v in raw.items():
        for k in ("air", "sst", "ice"):
            if k in v:
                assert v[k]["cell"] and v[k]["distance_km"] < 60, (lat, k)
                assert v[k]["tag"] in ("D", "R") and v[k]["source"]
    assert raw["-90"]["air"]["note"]  # ERA5 stands in for the AMRC station, and says so


def test_warmth_is_monotone_and_clipped():
    x = np.linspace(-80, 60, 141)
    w = M.warmth(x, -40, 35)
    assert w.min() == 0 and w.max() == 1 and (np.diff(w) >= 0).all()


def test_ice_glass_keeps_the_chord():
    """The glass sits high (84-96) on its voice's own pitch class, so the chord stays consonant."""
    for lat in M.LATS:
        m = M.PITCH[("north-high", "pentatonic")][lat]
        g = M.fold(m)
        assert 84 <= g <= 96 and g % 12 == m % 12


def test_wide_voicing_has_no_unisons():
    """Layer 2.1: sky and sea floor never share a pitch; the sky sits wholly above the sea."""
    sky = M.PITCH[("north-high", "wide")]
    assert len(set(sky.values())) == 13 and set(sky.values()).isdisjoint(M.SEA_FLOOR.values())
    assert min(sky.values()) > max(M.SEA_FLOOR.values())
    assert all(v % 12 in (2, 4, 6, 9, 11) for v in list(sky.values()) + list(M.SEA_FLOOR.values()))
    # the sea floor is ordered by warmth: the tropics highest, the ice-bound seas lowest
    assert M.SEA_FLOOR[15] > M.SEA_FLOOR[0] > M.SEA_FLOOR[-15] > M.SEA_FLOOR[-30] > M.SEA_FLOOR[-45] > M.SEA_FLOOR[-60]
