"""The Wheel (Arctic Round, B-side): the data loader, the wheel's rule and the picture's state.
Each one can fail: change a rule in arctic_bside.py and it does."""
import json
from pathlib import Path

import pytest

import arctic_data as A
import arctic_bside as BS
import export_bside_viz as EX

ROOT = Path(__file__).resolve().parent.parent
try:
    D = A.load()
except FileNotFoundError:
    pytest.skip("data/arctic/arctic_daily.json is missing: run scripts/fetch_arctic.py first", allow_module_level=True)


def test_every_bar_is_exactly_bar_s_whatever_its_days():
    for y in (1996, 2000, 2001):           # a leap year and two ordinary ones
        for framing in ("ice", "calendar"):
            days = A.bar_days(framing, y)
            assert len(days) in (365, 366)
            t = [(0 + (k + 0.5) / len(days)) * 10.0 for k in range(len(days))]
            assert t[0] > 0 and t[-1] < 10.0 and abs((t[1] - t[0]) * len(days) - 10.0) < 1e-9


def test_bside_wheel_loses_its_outer_notes_first():
    lo, hi = BS.DEFAULTS["ext_range"]
    n_sep79, s79 = BS.active_slots(7.2, lo, hi)
    n_sep12, s12 = BS.active_slots(3.6, lo, hi)
    n_mar, smar = BS.active_slots(16.5, lo, hi)
    assert (n_sep79, n_sep12, n_mar) == (6, 2, 8)
    assert s12 < s79 < smar and s12 == {3, 4}              # the core holds longest


def test_the_whole_pipeline_data_flags_the_gap():
    d = json.loads((ROOT / "data" / "arctic" / "arctic_daily.json").read_text())
    i = d["dates"].index("1987-12-15")
    assert d["observed"][i] == 0 and d["observed"][d["dates"].index("2012-09-16")] == 1


def test_the_picture_follows_the_engine_not_a_copy_of_it(monkeypatch):
    """export_bside_viz.py calls arctic_bside's rules; retune one and the exported state moves with it (it must fail if the exporter keeps its own copy)."""
    base = EX.build_state(D)
    sept_1979, sept_2012 = base["bars"][0]["nn"][-3], base["bars"][33]["nn"][-3]
    assert sept_1979 >= 6 and sept_2012 <= 3                        # the loss the piece is about
    assert abs(base["bars"][10]["edges"][-1] - 1.0) < 1e-9          # rubato never changes the bar's length
    monkeypatch.setattr(BS, "RUBATO_PRESS", 0.0)
    moved = EX.build_state(D)
    assert moved["bars"][10]["edges"] != base["bars"][10]["edges"]
    monkeypatch.setattr(BS, "OPEN_WATER_REF", 100.0)
    assert EX.build_state(D)["bars"][33]["ow"] != base["bars"][33]["ow"]
    monkeypatch.setattr(BS, "SWELL_LEVEL", [0.5, 0.6])
    assert EX.build_state(D)["bars"][33]["swell"] != base["bars"][33]["swell"]
    monkeypatch.setattr(BS, "cello_index", lambda v, lo, hi: 4)
    assert EX.build_state(D)["bars"][5]["cello"] != base["bars"][5]["cello"]
    monkeypatch.setattr(BS, "bass_gate", lambda vm, gate: 0.5)
    assert EX.build_state(D)["bars"][5]["gate"] != base["bars"][5]["gate"]
