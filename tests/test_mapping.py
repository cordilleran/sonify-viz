"""Each published track's mapping tables (tracks/mapping/): present, the same version
as the lock, and free of the records this project doesn't republish."""
import json

import pyarrow.parquet as pq
import yaml

import export_mapping as EM


def test_every_track_has_a_mapping_at_its_locked_version():
    lock = json.loads(EM.LOCK.read_text())["tracks"]
    for folder, (track, _) in EM.TRACKS.items():
        d = yaml.safe_load((EM.OUT / folder / "data-dict.yaml").read_text())
        assert d["version"]["number"] == lock[track]["version"] + ".0", folder
        for t in d["tables"]:
            cols = pq.read_schema(EM.OUT / folder / t["source"]["parquet"]).names
            assert cols == [c["name"] for c in t["columns"]], (folder, t["name"])


def test_every_card_has_a_mapping():
    cards = {yaml.safe_load(p.read_text())["id"] for p in (EM.ROOT / "tracks").glob("*.yaml") if p.name != "albums.yaml"}
    assert cards <= set(EM.TRACKS), cards - set(EM.TRACKS)


def test_withheld_records_stay_out():
    for p in EM.OUT.glob("*/*.parquet"):
        assert not set(pq.read_schema(p).names) & EM.WITHHELD, p
