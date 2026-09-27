"""Each published track's mapping tables (tracks/mapping/): present, the same version
as the lock, and free of the records this project doesn't republish."""
import json

import pyarrow.parquet as pq
import yaml

import export_mapping as EM


def test_every_track_has_a_mapping_at_its_locked_version():
    lock = json.loads(EM.LOCK.read_text())["tracks"]
    for track in EM.TRACKS:
        d = yaml.safe_load((EM.OUT / track / "data-dict.yaml").read_text())
        assert d["version"]["number"] == lock[track]["version"] + ".0", track
        for t in d["tables"]:
            cols = pq.read_schema(EM.OUT / track / t["source"]["parquet"]).names
            assert cols == [c["name"] for c in t["columns"]], (track, t["name"])


def test_withheld_records_stay_out():
    for p in EM.OUT.glob("*/*.parquet"):
        assert not set(pq.read_schema(p).names) & EM.WITHHELD, p
