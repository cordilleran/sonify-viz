"""
Build the tidy parquet tables the engine reads and the data dictionary
describes (2026-09-27), from the raw JSON pulls in data/. The JSON files
stay as the original API responses; these tables are the working copy.

  python build_parquet.py        # -> data/parquet/*.parquet

Water year record set (data/water-year.data-dict.yaml):
  stations            one row per station or satellite point
  hydrometric_daily   WSC daily means, one row per station per day
  climate_daily       ECCC daily climate, one row per station per day
  modis_gpp           MODIS 8-day GPP, one row per point, composite and pixel
  wells_dam_daily     DART Wells Dam counts: built only if the raw pull is
                      present, and never published (not ours to redistribute)

Climate Pair record set (data/climate/parquet/data-dict.yaml), from the
parsed files fetch_climate.py writes:
  indices_monthly     CO2, ENSO, PDO, AMO, NAO, SST, GISTEMP, Arctic sea ice
  storms              one row per tropical cyclone, three basins
  volcanoes           the four eruptions the pieces mark
  kettle_annual_peak  Kettle River near Laurier, each year's peak daily flow
  fetched_only_monthly  SILSO sunspots and IAP ocean heat: local only, never
                      published (CC BY-NC; terms unconfirmed)

Values are copied, not transformed: the dictionary describes the data the
agencies published, and the pieces transform it in code (records.py).
"""
import csv
import datetime as dt
import io
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "parquet"

HYDRO = {  # file -> the role the pieces give it
    "granby_08NN002_2010_2024.json": "Granby pilot: discharge (piano, bass), ice flag, phase",
    "burrell_08NN023_2010_2024.json": "Granby pilot: discharge (hand percussion)",
    "okanagan_lake_kelowna_08NM083_2010_2024.json": "Okanagan pilot: lake level (drone, mood)",
    "okanagan_river_penticton_08NM050_2010_2024.json": "Okanagan pilot: dam outflow (piano)",
    "okanagan_river_oliver_08NM085_2010_2024.json": "Okanagan pilot: discharge (percussion)",
}
CLIMATE = {
    "billings_1100_climate_2010_2024.json": "Granby pilot: temperature, rain, snow, snow on ground",
    "summerland_cs_979_climate_2010_2024.json": "Okanagan pilot: temperature, precipitation, humidity",
}
MODIS = {"granby_valley": "Granby pilot: string pad", "summerland": "Okanagan pilot: string pad"}
CLIM_COLS = ["MEAN_TEMPERATURE", "MIN_TEMPERATURE", "MAX_TEMPERATURE", "TOTAL_PRECIPITATION", "TOTAL_RAIN",
             "TOTAL_SNOW", "SNOW_ON_GROUND", "MIN_REL_HUMIDITY"]


def write(name, cols, schema, out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    t = pa.table(cols, schema=schema)
    pq.write_table(t, out / f"{name}.parquet", compression="zstd")
    print(f"{name}: {t.num_rows} rows")


def main():
    st = {k: [] for k in ("station_id", "kind", "name", "latitude", "longitude", "used_for")}
    h = {k: [] for k in ("station_id", "date", "discharge", "discharge_symbol", "level", "level_symbol")}
    for f, role in HYDRO.items():
        feats = json.loads((DATA / f).read_text())
        p0, (lon, lat) = feats[0]["properties"], feats[0]["geometry"]["coordinates"]
        for k, v in zip(st, (p0["STATION_NUMBER"], "hydrometric", p0["STATION_NAME"], lat, lon, role)):
            st[k].append(v)
        for x in feats:  # keep the API's order: records.py reads them in this order
            p = x["properties"]
            h["station_id"].append(p["STATION_NUMBER"]); h["date"].append(dt.date.fromisoformat(p["DATE"][:10]))
            h["discharge"].append(p["DISCHARGE"]); h["discharge_symbol"].append(p["DISCHARGE_SYMBOL_EN"])
            h["level"].append(p["LEVEL"]); h["level_symbol"].append(p["LEVEL_SYMBOL_EN"])
    write("hydrometric_daily", h, pa.schema([("station_id", pa.string()), ("date", pa.date32()),
          ("discharge", pa.float64()), ("discharge_symbol", pa.string()), ("level", pa.float64()),
          ("level_symbol", pa.string())]))

    c = {k: [] for k in ["station_id", "climate_identifier", "date"] + [x.lower() for x in CLIM_COLS]
         + [x.lower() + "_flag" for x in CLIM_COLS]}
    for f, role in CLIMATE.items():
        feats = json.loads((DATA / f).read_text())
        p0, (lon, lat) = feats[0]["properties"], feats[0]["geometry"]["coordinates"]
        for k, v in zip(st, (str(p0["STN_ID"]), "climate", p0["STATION_NAME"], lat, lon, role)):
            st[k].append(v)
        for x in feats:
            p = x["properties"]
            c["station_id"].append(str(p["STN_ID"])); c["climate_identifier"].append(p["CLIMATE_IDENTIFIER"])
            c["date"].append(dt.date.fromisoformat(p["LOCAL_DATE"][:10]))
            for k in CLIM_COLS:
                c[k.lower()].append(None if p[k] is None else float(p[k]))
                c[k.lower() + "_flag"].append(p[k + "_FLAG"])
    write("climate_daily", c, pa.schema([("station_id", pa.string()), ("climate_identifier", pa.string()),
          ("date", pa.date32())] + [(k.lower(), pa.float64()) for k in CLIM_COLS]
          + [(k.lower() + "_flag", pa.string()) for k in CLIM_COLS]))

    m = {k: [] for k in ("station_id", "date", "pixel", "gpp_raw")}
    for name, role in MODIS.items():
        d = json.loads((DATA / f"modis_gpp_{name}_2015_2024.json").read_text())
        for k, v in zip(st, (name, "modis_point", f"MODIS {d['product']} point, {name.replace('_', ' ')}",
                             d["lat"], d["lon"], role)):
            st[k].append(v)
        for r in d["rows"]:
            for i, v in enumerate(r["data"]):
                m["station_id"].append(name); m["date"].append(dt.date.fromisoformat(r["date"]))
                m["pixel"].append(i); m["gpp_raw"].append(int(v))
    write("modis_gpp", m, pa.schema([("station_id", pa.string()), ("date", pa.date32()),
          ("pixel", pa.int32()), ("gpp_raw", pa.int32())]))

    raw = DATA / "wells_dam_sockeye_2015_2024.json"
    if raw.exists():
        w = {k: [] for k in ("date", "sockeye", "water_temp")}
        for y, text in sorted(json.loads(raw.read_text()).items()):
            for r in csv.DictReader(io.StringIO(text)):
                d = r.get("Date") or ""
                if not d.startswith(y):
                    continue
                w["date"].append(dt.date.fromisoformat(d)); w["sockeye"].append(float(r["Sock"] or 0))
                w["water_temp"].append(float(r["TempC"]) if r["TempC"] else None)
        write("wells_dam_daily", w, pa.schema([("date", pa.date32()), ("sockeye", pa.float64()),
              ("water_temp", pa.float64())]))

    write("stations", st, pa.schema([("station_id", pa.string()), ("kind", pa.string()), ("name", pa.string()),
          ("latitude", pa.float64()), ("longitude", pa.float64()), ("used_for", pa.string())]))
    climate()


def climate():
    """The Climate Pair's records: the same values as the parsed JSON, one table each."""
    src, out = DATA / "climate", DATA / "climate" / "parquet"
    month = lambda s: dt.date(int(s[:4]), int(s[5:7]), 1)
    J = json.loads((src / "indices_monthly.json").read_text())
    cols = {"month": [month(m) for m in J["months"]], **J["series"]}
    write("indices_monthly", cols, pa.schema([("month", pa.date32())] + [(k, pa.float64()) for k in J["series"]]),
          out)
    s = {k: [] for k in ("basin", "id", "name", "peak_kt", "peak_time", "category", "ace", "landfall",
                         "min_pressure_mb")}
    for basin in ("atl", "nepac", "wpac"):  # each basin in the order the JSON holds it
        for x in json.loads((src / f"storms_{basin}.json").read_text()):
            s["basin"].append(basin)
            for k in list(s)[1:]:
                s[k].append(dt.datetime.fromisoformat(x[k]) if k == "peak_time" else
                            float(x[k]) if k == "ace" else x[k])
    write("storms", s, pa.schema([("basin", pa.string()), ("id", pa.string()), ("name", pa.string()),
          ("peak_kt", pa.int32()), ("peak_time", pa.timestamp("s")), ("category", pa.int32()), ("ace", pa.float64()),
          ("landfall", pa.bool_()), ("min_pressure_mb", pa.int32())]), out)
    v = J["volcanoes"]
    write("volcanoes", {"date": [dt.date.fromisoformat(x["date"]) for x in v], "name": [x["name"] for x in v],
                        "vei": [x["vei"] for x in v], "cooling": [float(x["cooling"]) for x in v],
                        "note": [x.get("note") for x in v]},
          pa.schema([("date", pa.date32()), ("name", pa.string()), ("vei", pa.int32()), ("cooling", pa.float64()),
                     ("note", pa.string())]), out)
    k = json.loads((src / "kettle_annual_max.json").read_text())
    write("kettle_annual_peak", {"year": [int(y) for y in k], "max_daily_m3s": [r["max_daily_m3s"] for r in k.values()],
                                 "date": [dt.date.fromisoformat(r["date"]) for r in k.values()]},
          pa.schema([("year", pa.int32()), ("max_daily_m3s", pa.float64()), ("date", pa.date32())]), out)
    fo = src / "fetched_only_monthly.json"
    if fo.exists():  # local only: see the module docstring
        F = json.loads(fo.read_text())
        write("fetched_only_monthly", {"month": [month(m) for m in F["months"]], **F["series"]},
              pa.schema([("month", pa.date32())] + [(k, pa.float64()) for k in F["series"]]), out)


if __name__ == "__main__":
    main()
