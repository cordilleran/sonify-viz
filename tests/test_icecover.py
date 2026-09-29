"""Superior Ice Year (icecover.py): the data are well formed, the regions partition the lake, the voices
never share a pitch, event detection follows its rules, and a short render is clean and deterministic."""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import icecover as I

ROOT = Path(__file__).resolve().parent.parent
P = dict(I.DEFAULTS)
D = I.load()
PC = lambda notes: [n % 12 for n in notes]
PENTATONIC = {2, 4, 6, 9, 11}   # D E F# A B


def test_days_dates_and_series_line_up():
    assert D["N"] == len(D["dates"]) == 227
    assert D["dates"][0] == "2025-11-01" and D["dates"][-1] == "2026-06-15"
    for r in D["ids"]:
        for k, v in D["R"][r].items():
            assert len(v) == D["N"], (r, k)
    assert len(D["lake_ice"]) == D["N"] and len(D["lake_sst"]) == D["N"]


def test_ice_is_a_percentage_and_the_peak_is_where_the_data_say():
    for r in D["ids"]:
        ice = D["R"][r]["ice"]
        assert ice.min() >= 0 and ice.max() <= 100, r
    assert 0 <= D["lake_ice"].min() and D["lake_ice"].max() <= 100
    assert D["dates"][int(np.argmax(D["lake_ice"]))] == D["cur_peak_day"]


def test_regions_are_ordered_west_to_east_and_shares_sum_to_one():
    lons = [D["lon"][r] for r in D["ids"]]
    assert lons == sorted(lons) and len(D["ids"]) == 8
    regs = json.loads((ROOT / "data" / "icecover" / "superior_regions.json").read_text())
    assert abs(sum(r["share"] for r in regs) - 1) < 0.01


def test_region_mask_partitions_the_lake():
    meta = json.loads((ROOT / "data" / "icecover" / "superior_grid_meta.json").read_text())
    mask = np.array(meta["region_mask"])
    assert mask.shape[0] == 100 and mask.shape[1] == 285
    regs = json.loads((ROOT / "data" / "icecover" / "superior_regions.json").read_text())
    n = len(regs)
    water = mask[mask >= 0] if mask.min() < 0 else mask[mask != 255]
    assert set(np.unique(water)) <= set(range(n))
    counts = np.bincount(water.astype(int), minlength=n)
    assert (counts > 0).all(), "a region has no cells"
    assert np.allclose(counts / counts.sum(), [r["share"] for r in regs], atol=0.01)


def test_exported_mask_digits_follow_the_west_to_east_region_order():
    import export_icecover as E
    meta = json.loads((ROOT / "data" / "icecover" / "superior_grid_meta.json").read_text())
    mask = E.build_mask(meta)
    cx = []
    for k in range(8):
        cols = [c for row in mask for c, ch in enumerate(row) if ch == str(k)]
        assert cols, k
        cx.append(np.mean(cols))
    assert cx == sorted(cx), "the mask's region digits are not in the viz's west-to-east order"


def test_pans_are_ordered_and_each_region_is_heard_apart():
    pans = [D["pan"][r] for r in D["ids"]]
    assert pans == sorted(pans)
    assert min(np.diff(pans)) > 0.05     # the three regions near -88 degrees are not stacked
    assert -0.75 < pans[0] and pans[-1] < 0.75


def test_no_two_voices_share_a_pitch_in_a_register():
    for key in ("ice_pitch", "drop_pitch", "water_pitch", "rain_pitch", "organ_pitch", "choir_pitch"):
        notes = P[key]
        assert len(set(notes)) == len(notes), key
    # all four registers of the regional voices use the D major pentatonic, so any subset is consonant
    for key in ("ice_pitch", "drop_pitch", "water_pitch", "rain_pitch", "organ_pitch", "choir_pitch"):
        assert set(PC(P[key])) <= PENTATONIC, (key, PC(P[key]))
    # the two pitched regional voices that play in the same register of the mix never share a note:
    # the rain harp is two octaves under the ice glass
    assert max(P["rain_pitch"]) < min(P["ice_pitch"])
    assert [i - r for i, r in zip(P["ice_pitch"], P["rain_pitch"])] == [24] * 8
    assert len(P["ice_pitch"]) == len(D["ids"]) == len(P["drop_pitch"])


def test_sustained_layers_never_share_a_note():
    # the glass, the water strings, the organ, the choir and the ghost are held tones: no MIDI note in two of them.
    # The plucked and struck layers (pings, drops, rain) sit on each region's own pitch class and may coincide with a bed.
    held = [P["ice_pitch"], P["water_pitch"], P["organ_pitch"], P["choir_pitch"], [P["ghost_pitch"]]]
    notes = [n for layer in held for n in layer]
    assert len(notes) == len(set(notes))


def test_ghost_tone_stays_at_its_pitch_when_the_detuning_moves():
    n = I.SR * 300
    t = np.arange(n) / I.SR
    cents = 20 * (0.5 + 0.5 * np.sin(2 * np.pi * t / 40))      # a 20-cent wander over a 300 s piece
    x = I.ghost_carrier(1760.0, cents)
    for a, b in ((0, 60), (200, 260), (240, 300)):             # late in the piece is where f(t)*t would be far off
        seg = x[a * I.SR:b * I.SR]
        f = np.count_nonzero(np.diff(np.signbit(seg))) / (2 * (b - a))
        assert 1755 < f < 1790, (a, b, f)


def test_movement_cuts_survive_a_winter_that_never_reaches_10_percent():
    dates = [f"2025-11-{d:02d}" for d in range(1, 31)]
    lake = np.full(30, 1.0)
    on, peak, off = I.movement_days(lake, dates[7], dates)
    assert 0 <= on <= peak < off <= 30


def test_event_detection_on_a_synthetic_step():
    ice = np.zeros(40)
    ice[10:] = 30           # one 30-point jump on day 10
    ev = I.detect_events(ice, up=4, down=4, smooth=1, gap=3)
    assert ev == [(10, 1, 30.0)]
    fall = np.r_[np.full(20, 60.0), np.full(20, 10.0)]
    ev = I.detect_events(fall, up=4, down=4, smooth=1, gap=3)
    assert [(d, k) for d, k, _ in ev] == [(20, -1)]


def test_event_detection_respects_the_refractory_period():
    ice = np.cumsum(np.r_[np.zeros(5), np.full(20, 6.0), np.zeros(15)])   # six points a day for twenty days
    days = [d for d, k, _ in I.detect_events(ice, up=4, down=4, smooth=1, gap=3)]
    assert len(days) > 1 and all(b - a >= 3 for a, b in zip(days, days[1:]))
    assert I.detect_events(np.full(30, 50.0)) == []      # steady ice fires nothing


def test_smoothing_keeps_the_ends():
    x = np.full(20, 5.0)
    assert np.allclose(I.smooth_days(x, 3), 5.0) and len(I.smooth_days(x, 3)) == 20


def test_real_events_are_time_ordered_and_have_both_kinds():
    all_ev = [(d, k) for r in D["ids"] for d, k, _ in I.detect_events(D["R"][r]["ice"])]
    assert {k for _, k in all_ev} == {1, -1}
    for r in D["ids"]:
        ev = I.detect_events(D["R"][r]["ice"])
        assert [d for d, _, _ in ev] == sorted(d for d, _, _ in ev)


def test_movement_cuts_match_the_data():
    on, peak, off = I.movement_days(D["lake_ice"], D["cur_peak_day"], D["dates"])
    assert on < peak < off < D["N"]
    assert D["lake_ice"][on] >= 10 and (D["lake_ice"][:on] < 10).all()
    assert D["dates"][peak] == D["cur_peak_day"]
    assert D["lake_ice"][off - 1] >= 2 and (D["lake_ice"][off:] < 2).all()


def test_birds_arrive_after_each_regions_own_ice_peak():
    for r in D["ids"]:
        ice = D["R"][r]["ice"]
        peak = int(np.argmax(ice))
        loon, goose = I.bird_days(ice, D["R"][r]["tmax"], peak, D["dates"])
        if loon is not None:
            assert loon >= peak and ice[loon] < 5 and D["R"][r]["tmax"][loon] > 5
        if goose is not None:
            assert D["dates"][goose] >= "2026-03-01" and ice[goose] < 50


def test_glass_gate_is_silent_below_its_lower_edge_and_full_above_its_upper():
    lo, hi = P["glass_gate"]
    assert I.smoothstep(lo - 0.5, lo, hi) == 0 and I.smoothstep(hi + 5, lo, hi) == 1


@pytest.fixture(scope="module")
def short_render(tmp_path_factory):
    out = tmp_path_factory.mktemp("icecover")
    env = dict(os.environ, SONIFICATION_HEAVY=str(out / "heavy"), SONIFICATION_LIGHT=str(out / "light"))
    wavs = []
    for i in range(2):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "icecover.py"), "--set", "day_s=0.12"],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
        if r.returncode:
            pytest.skip(f"the piece could not render here (samples or venv missing): {r.stderr[-300:]}")
        wavs.append(sorted((out / "heavy" / "icecover").glob("*.wav")))
        assert wavs[-1], r.stdout[-300:]
    return out, wavs


def test_short_render_is_clean_and_seeded_deterministic(short_render):
    import soundfile as sf
    out, wavs = short_render
    a, sr = sf.read(str(wavs[0][0]))
    assert a.ndim == 2 and a.shape[1] == 2
    assert np.abs(a).max() < 0.95, "clipping"
    assert a.shape[0] / sr >= D["N"] * 0.12          # the whole season plays, plus the tail
    assert np.isfinite(a).all()
    b, _ = sf.read(str(wavs[1][0]))
    assert a.shape == b.shape and np.allclose(a, b, atol=1e-6)
    score = next((out / "light" / "icecover").glob("*_score.json"))
    viz = next((out / "light" / "icecover").glob("*_viz.json"))
    assert json.loads(score.read_text())["regions"] and json.loads(viz.read_text())["dates"] == D["dates"]
    ev = json.loads(viz.read_text())["events"]
    assert ev and all(len(e) == 4 and 0 <= e[3] <= 0.5 for r in ev.values() for e in r)   # each carries the offset the sound was placed at


def test_ghost_pitch_holds_over_a_long_render():
    """v1.0 fix: with the phase summed in float64 the ghost stays on A6 for the whole piece.
    (In v0.2 the float32 sum stepped the pitch by up to a whole tone and froze after ~350 s.)"""
    from sampler import SR
    n = 400 * SR                  # past the ~350 s where the float32 sum froze
    x = I.ghost_carrier(1760.0, np.zeros(n, np.float32), phase64=True)
    for t in (100, 395):
        s = x[t * SR:(t + 2) * SR] * np.hanning(2 * SR)
        f = np.fft.rfftfreq(16 * SR, 1 / SR)[np.argmax(np.abs(np.fft.rfft(s, 16 * SR)))]
        assert abs(f - 1760.0) < 0.5, (t, f)


def test_early_reflections_grow_with_distance():
    """Crackle (c): a far event arrives later, and more of its energy is in the reflections."""
    rng = np.random.default_rng(1)
    x = np.zeros(4800, np.float32)
    x[0] = 1.0
    near, far = I.early_reflections(x, 0.0, rng), I.early_reflections(x, 1.0, rng)
    first = lambda y: int(np.flatnonzero(np.abs(y).sum(1) > 0.5)[0])
    assert first(far) > first(near)
    tail = lambda y: float(np.abs(y[first(y) + 100:]).sum())
    assert tail(far) > tail(near)


def test_v1_variant_uses_declared_parameters():
    import yaml
    spec = yaml.safe_load((ROOT / "variants" / "icecover.yaml").read_text())["v1"]
    assert set(spec) - {"note"} <= set(I.DEFAULTS)
    assert spec["ghost_phase64"] is True and spec["coda"] == "c" and spec["drone"] is True
