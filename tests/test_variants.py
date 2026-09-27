"""Variants and remixes (variants.py): the published default is untouched,
names never collide, and a typo can't quietly render the default."""
import pytest
import yaml

import variants as V

DEFAULTS = {"year": "wy2024", "bpm": 72, "mode": None, "mute": [], "gains": {}, "seed": 2024}


def test_no_flags_is_the_published_render():
    P, Y, name, meta = V.setup("granby", DEFAULTS, [])
    assert P == DEFAULTS and name == "granby_wy2024" and meta == {} and Y.label == "WY2024"


def test_a_year_alone_is_its_own_track_not_a_variant():
    P, Y, name, meta = V.setup("granby", DEFAULTS, ["wy2019"])
    assert name == "granby_wy2019" and meta == {} and Y.n_days == 365


def test_named_variant(tmp_path, monkeypatch):
    (tmp_path / "granby.yaml").write_text(yaml.safe_dump({"frozen": {"mode": "Dorian", "note": "n"}}))
    monkeypatch.setattr(V, "VARIANTS", tmp_path)
    P, _, name, meta = V.setup("granby", DEFAULTS, ["--variant", "frozen"])
    assert P["mode"] == "Dorian" and name == "granby_wy2024__frozen"
    assert meta["variant"] == "frozen" and meta["overrides"] == {"mode": "Dorian"}


def test_unknown_parameter_is_refused():
    with pytest.raises(SystemExit):
        V.setup("granby", DEFAULTS, ["--set", "bmp=60"])


def test_ad_hoc_overrides_get_a_distinct_stable_name():
    a = V.setup("granby", DEFAULTS, ["--set", "bpm=60"])[2]
    b = V.setup("granby", DEFAULTS, ["--set", "bpm=60"])[2]
    c = V.setup("granby", DEFAULTS, ["--set", "bpm=66"])[2]
    assert a == b != c and a.startswith("granby_wy2024__set-")


def test_remix_renders_under_its_own_id_and_checks_its_parent(tmp_path):
    spec = {"remix": "granby-wy2024-dusk", "parent": {"piece": "granby", "track": "granby-wy2024", "version": "1.0"},
            "changes": {"bpm": 60}, "credits": [{"name": "test", "role": "remix"}]}
    f = tmp_path / "r.yaml"
    f.write_text(yaml.safe_dump(spec))
    P, _, name, meta = V.setup("granby", DEFAULTS, ["--remix", str(f)])
    assert name == "granby_wy2024_dusk" and P["bpm"] == 60 and meta["parent"]["version"] == "1.0"
    with pytest.raises(SystemExit):
        V.setup("okanagan", DEFAULTS, ["--remix", str(f)])  # not this piece's remix


def test_bus_settings_checks_layer_names():
    base = {"piano": {"gain": 1.0}, "perc": {"gain": 2.0}}
    assert V.bus_settings(base, {"gains": {"perc": 1.0}})["perc"]["gain"] == 1.0
    with pytest.raises(SystemExit):
        V.bus_settings(base, {"mute": ["drums"]})
