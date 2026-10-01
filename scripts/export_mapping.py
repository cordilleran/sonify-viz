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


def locked_score(track, suffix="_score.json"):
    """The locked render's score (or page-data) JSON, after checking it against the lock."""
    import dsp_core  # the same LIGHT_OUT the renders wrote to
    e = json.loads(LOCK.read_text())["tracks"][track]
    rel = next(k for k in e["outputs"] if k.endswith(suffix))
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


def meridian(track):
    """One row per voice per breath: the sun each voice sings, and (layer 2) the air, sea and ice under it."""
    sc, version = locked_score(track)
    cols, cov, warm = sc["voice_columns"], sc.get("covariates", {}), sc.get("warmth", {})
    def at(a, i):   # one breath of a per-breath series; absent series (land, or layer 1) give None
        return None if not isinstance(a, list) or a[i] is None else float(a[i])

    rows = []
    for b in sc["breaths"]:
        for v, vals in zip(sc["voices"], b["voices"], strict=True):
            i, c, w = b["breath"], cov.get(str(v["lat"]), {}), warm.get(str(v["lat"]), {})
            rows.append({"breath": i, "t": b["t"], "date": dt.date.fromisoformat(b["date"]), "lat": v["lat"],
                         **{n: None if x is None else float(x) for n, x in zip(cols, vals, strict=True)},
                         "air_max_c": at(c.get("air_max_c"), i), "air_min_c": at(c.get("air_min_c"), i),
                         "sst_c": at(c.get("sst_c"), i), "ice_frac": at(c.get("ice_frac"), i),
                         "warmth_day": at(w.get("day"), i), "warmth_night": at(w.get("night"), i)})
    f = pa.float64()
    types = [("breath", pa.int32()), ("t", f), ("date", pa.date32()), ("lat", pa.int32())] + [(n, f) for n in cols]
    if cov:  # layer 1 plays the daylight alone
        types += [("air_max_c", f), ("air_min_c", f), ("sst_c", f), ("ice_frac", f), ("warmth_day", f), ("warmth_night", f)]
    sea = sc.get("sea_pitch", {})
    voices = [{"lat": v["lat"], "place": v["place"], "surface": v["surface"], "midi": v["midi"],
               "sea_midi": sea.get(str(v["lat"]))} for v in sc["voices"]]
    vt = [("lat", pa.int32()), ("place", pa.string()), ("surface", pa.string()), ("midi", pa.int32())] + \
         ([("sea_midi", pa.int32())] if sea else [])
    return version, {"voices": table(voices, vt), "voice_breaths": table(rows, types)}


def superior_ice(track):
    """The page data of the locked render: each region's day, the lake's day, the events and the regions."""
    sc, version = locked_score(track, "_viz.json")
    N, ds, f = sc["n_days"], sc["day_s"], pa.float64()
    dates = [dt.date.fromisoformat(d) for d in sc["dates"]]
    cuts = sc["movement_cuts_day"]
    ren = {"ice": "ice_pct", "sst": "sst_c", "tmean": "air_mean_c", "wind": "wind_max_ms", "wdir": "wind_dir_deg",
           "precip": "precip_mm", "snow": "snow_mm"}
    rd = [{"date": dates[d], "day": d, "t": d * ds, "region": r["id"],
           **{ren[k]: float(sc["region_series"][r["id"]][k][d]) for k in ren}} for d in range(N) for r in sc["regions"]]
    ld = [{"date": dates[d], "day": d, "t": d * ds, "movement": 1 + sum(d >= c for c in cuts),
           "lake_ice_pct": float(sc["lake_ice"][d]), **{f"hist_{k}_pct": float(sc["hist"][k][d]) for k in sc["hist"]},
           "daylength_h": float(sc["daylen"][d]), "turnover": d in sc["turnover_days"]} for d in range(N)]
    ev = [{"region": r["id"], "day": e[0], "kind": "freeze" if e[1] > 0 else "breakup", "size_pp": float(e[2]),
           "offset_days": float(e[3]) if len(e) > 3 else 0.0, "t": (e[0] + (e[3] if len(e) > 3 else 0)) * ds}
          for r in sc["regions"] for e in sc["events"].get(r["id"], [])]
    bd = sc.get("birds", {})
    rg = [{**{k: r[k] for k in ("id", "name", "lon", "lat", "pan", "ice_midi", "water_midi", "drop_midi")},
           "loon_day": (bd.get(r["id"]) or {}).get("loon"), "goose_day": (bd.get(r["id"]) or {}).get("goose")}
          for r in sc["regions"]]
    i32, s_ = pa.int32(), pa.string()
    return version, {
        "regions": table(rg, [("id", s_), ("name", s_), ("lon", f), ("lat", f), ("pan", f), ("ice_midi", i32),
                              ("water_midi", i32), ("drop_midi", i32), ("loon_day", i32), ("goose_day", i32)]),
        "region_days": table(rd, [("date", pa.date32()), ("day", i32), ("t", f), ("region", s_)] + [(v, f) for v in ren.values()]),
        "lake_days": table(ld, [("date", pa.date32()), ("day", i32), ("t", f), ("movement", i32), ("lake_ice_pct", f)] +
                           [(f"hist_{k}_pct", f) for k in sc["hist"]] + [("daylength_h", f), ("turnover", pa.bool_())]),
        "events": table(ev, [("region", s_), ("day", i32), ("kind", s_), ("size_pp", f), ("offset_days", f), ("t", f)])}


def regimes_bside(track):
    """The score of the locked B-side: the four year voices, their weekly series, and what each bar did."""
    sc, version = locked_score(track)
    f, i32, s_ = pa.float64(), pa.int32(), pa.string()
    yrs = [v["year"] for v in sc["voices"]]
    vs = [{"year": v["year"], "regime": v["regime"], "kind": v["kind"], "cycle_steps": v["N"], "pan": v["pan"],
           "entry_pass": i + 1, "hits": v["nhits"]} for i, v in enumerate(sc["voices"])]
    wk = [{"year": v["year"], "week": w, "flow_rel": v["flow"][w], "swe_rel": v["swe"][w], "temp_c": v["temp"][w]}
          for v in sc["voices"] for w in range(52)]
    bars = []
    for b in sc["bars"]:
        r = {"bar": b["ab"] + 1, "pass": b["pass_"], "week": b["week"], "t": round(sc["lead_s"] + b["ab"] * sc["bar_s"], 3),
             "voices_sounding": len(b["k"]), "swe_rel": b["swe"], "melt": b["melt"], "temp_c": b["temp"], "mode": b["mode"],
             "pedal": b["root"], "breakdown": bool(b["brk"]), "lead_k": b["lead_k"], "cutoff_hz": b["cutoff"]}
        for i, y in enumerate(yrs):
            r[f"k_{y}"] = b["k"][i] if i < len(b["k"]) else None
            r[f"rot_{y}"] = b["rot"][i] if i < len(b["rot"]) else None
        bars.append(r)
    return version, {
        "voices": table(vs, [("year", i32), ("regime", s_), ("kind", s_), ("cycle_steps", i32), ("pan", f), ("entry_pass", i32), ("hits", i32)]),
        "weeks": table(wk, [("year", i32), ("week", i32), ("flow_rel", f), ("swe_rel", f), ("temp_c", f)]),
        "bars": table(bars, [("bar", i32), ("pass", i32), ("week", i32), ("t", f), ("voices_sounding", i32)] +
                      [(f"k_{y}", i32) for y in yrs] + [(f"rot_{y}", i32) for y in yrs] +
                      [("swe_rel", f), ("melt", f), ("temp_c", f), ("mode", s_), ("pedal", s_), ("breakdown", pa.bool_()),
                       ("lead_k", i32), ("cutoff_hz", i32)])}


# mapping folder -> (locked track, exporter)
TRACKS = {"granby-wy2024": ("granby-wy2024", water_year), "okanagan-wy2024": ("okanagan-wy2024", water_year),
          "climate-pair-pacific": ("climate-pair-pacific", climate_pair),
          "climate-pair-atlantic": ("climate-pair-atlantic", climate_pair),
          "meridian-layer2-wide-long": ("meridian-chorus-layer2:wide-long", meridian),
          "meridian-daylight": ("meridian-chorus-daylight", meridian),
          "superior-ice": ("icecover-superior-ice:v1", superior_ice),
          "superior-ice-short": ("icecover-superior-ice", superior_ice),
          "regimes-bside": ("regimes-bside", regimes_bside)}


def main():
    for folder, (track, fn) in TRACKS.items():
        version, tables = fn(track)
        d = OUT / folder
        d.mkdir(parents=True, exist_ok=True)
        for name, t in tables.items():
            pq.write_table(t, d / f"{name}.parquet", compression="zstd")
        print(f"{folder} v{version}: " + ", ".join(f"{n} {t.num_rows} rows" for n, t in tables.items()))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
