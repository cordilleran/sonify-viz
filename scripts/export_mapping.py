"""
Export each published track's mapping tables (2026-09-27): the score's
per-day features and per-bar musical parameters as parquet, described by a
data dictionary beside them (tracks/mapping/<track>/data-dict.yaml), so every
step from record to sound is named, bounded and checkable.

  python export_mapping.py

The tables come from the score JSON of the locked render, and only if its
SHA-256 matches renders.lock.json, so a mapping table always describes the
audio of the version it names. Values are copied from the score, not
recomputed; the dictionaries say how the piece computed them.

Not exported: the Okanagan's daily Wells Dam counts and temperatures
(Columbia River DART data are not republished here), and the Climate Pair's
yearly ocean heat content (IAP terms unconfirmed). The music still carries
them; the dictionaries say so.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "renders.lock.json"
OUT = ROOT / "tracks" / "mapping"
WITHHELD = {"sockeye", "wells_temp", "ohc_1e22J"}


def locked_score(track):
    """The locked render's score JSON, after checking it against the lock."""
    import dsp_core  # the same LIGHT_OUT the renders wrote to
    e = json.loads(LOCK.read_text())["tracks"][track]
    rel = next(k for k in e["outputs"] if k.endswith("_score.json"))
    p = dsp_core.LIGHT_OUT / rel.partition("/")[2]
    if hashlib.sha256(p.read_bytes()).hexdigest() != e["outputs"][rel]:
        raise SystemExit(f"{track}: {p.name} differs from the locked render; re-render or re-lock first")
    return json.loads(p.read_text()), e["version"]


def table(rows, types):
    """rows: list of dicts -> pyarrow table with the given (name, type) columns, in that order."""
    return pa.table({k: [r[k] for r in rows] for k, _ in types}, schema=pa.schema(types))


def water_year(track):
    sc, version = locked_score(track)
    per_day = [k for k in sc["days"][0] if k not in ("date", "t") and k not in WITHHELD]
    days = [{"date": dt.date.fromisoformat(d["date"]), "bar": i // sc["days_per_bar"], "t": d["t"],
             **{k: d[k] for k in per_day}} for i, d in enumerate(sc["days"])]
    kind = lambda v: pa.bool_() if isinstance(v, bool) else pa.float64()
    dtypes = [("date", pa.date32()), ("bar", pa.int32()), ("t", pa.float64())] + \
             [(k, kind(sc["days"][0][k])) for k in per_day]
    for r in days:
        for k, ty in dtypes[3:]:
            r[k] = None if r[k] is None else (bool(r[k]) if ty == pa.bool_() else float(r[k]))
    btypes = [("bar", pa.int32()), ("t", pa.float64()), ("mode", pa.string()), ("degree", pa.int32()),
              ("phase", pa.string()), ("piano_density", pa.int32())] + \
             ([("held", pa.bool_())] if "held" in sc["bars"][0] else []) + [("perc_drive", pa.float64())]
    return version, {"days": table(days, dtypes), "bars": table(sc["bars"], btypes)}


def climate_pair(track):
    sc, version = locked_score(track)
    years = [{"year": y["year"], "bar": i, "t": round(i * sc["bar_seconds"], 2), "mode": y["mode"],
              "chord_first_half": y["chords"][0], "chord_second_half": y["chords"][1],
              "co2_ppm": y["co2_ppm"], "sst_anom": y["sst_anom"], "ace": float(y["ace"]),
              "seaice_sep_mkm2": y["seaice_sep_mkm2"]} for i, y in enumerate(sc["years_detail"])]
    types = [("year", pa.int32()), ("bar", pa.int32()), ("t", pa.float64()), ("mode", pa.string()),
             ("chord_first_half", pa.int32()), ("chord_second_half", pa.int32()), ("co2_ppm", pa.float64()),
             ("sst_anom", pa.float64()), ("ace", pa.float64()), ("seaice_sep_mkm2", pa.float64())]
    if sc["basin"] != "atlantic":  # only the Atlantic piece plays the sea ice
        types = [x for x in types if x[0] != "seaice_sep_mkm2"]
    return version, {"years": table(years, types)}


TRACKS = {"granby-wy2024": water_year, "okanagan-wy2024": water_year,
          "climate-pair-pacific": climate_pair, "climate-pair-atlantic": climate_pair}


def main():
    for track, fn in TRACKS.items():
        version, tables = fn(track)
        d = OUT / track
        d.mkdir(parents=True, exist_ok=True)
        for name, t in tables.items():
            pq.write_table(t, d / f"{name}.parquet", compression="zstd")
        print(f"{track} v{version}: " + ", ".join(f"{n} {t.num_rows} rows" for n, t in tables.items()))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
