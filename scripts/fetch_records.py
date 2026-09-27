"""
Fetch any Water Survey of Canada station or ECCC climate station into data/,
in the same cached-JSON shape the pieces read (records.wsc_series,
records.climate_series). Generalized 2026-09-27 from fetch_okanagan.py.

  python fetch_records.py wsc 08NN002 granby --years 2010-2024
  python fetch_records.py eccc 1100 billings --years 2010-2024
  python fetch_records.py wsc 08NN002 granby --years 2023-2024 --out /tmp/x

Writes data/<name>_<station>_<y0>_<y1>.json (hydrometric daily means: discharge,
level, and their symbols such as "Ice Conditions") or
data/<name>_<stn_id>_climate_<y0>_<y1>.json (daily climate). An existing file
is left alone; delete it to re-fetch. Station numbers: the WSC station
search (https://wateroffice.ec.gc.ca) for hydrometric, and the ECCC
climate-stations collection's STN_ID for climate (not the Climate ID).

Data: Environment and Climate Change Canada, via the MSC GeoMet OGC API.
Contains information licensed under the Open Government Licence - Canada.
Before rendering a new year, check coverage: records.coverage(series, Year).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_okanagan import ogc_all  # paging + retries against api.weather.gc.ca

DATA = Path(__file__).resolve().parent.parent / "data"


def fetch(kind, station, name, y0, y1, out=DATA):
    out.mkdir(parents=True, exist_ok=True)
    if kind == "wsc":
        p = out / f"{name}_{station}_{y0}_{y1}.json"
        coll, q = "hydrometric-daily-mean", {"STATION_NUMBER": station}
    else:
        p = out / f"{name}_{station}_climate_{y0}_{y1}.json"
        coll, q = "climate-daily", {"STN_ID": station}
    if p.exists():
        print(f"{p.name} exists; delete it to re-fetch")
        return p
    feats = ogc_all(coll, dict(q, datetime=f"{y0}-01-01/{y1}-12-31"))
    if not feats:
        raise SystemExit(f"no {kind} records for {station} in {y0}-{y1}: check the station number")
    p.write_text(json.dumps(feats))
    dates = sorted(f["properties"]["DATE" if kind == "wsc" else "LOCAL_DATE"][:10] for f in feats)
    print(f"{p.name}: {len(feats)} days, {dates[0]} to {dates[-1]}")
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=["wsc", "eccc"], help="wsc: hydrometric station; eccc: climate station")
    ap.add_argument("station", help="WSC station number (08NN002) or ECCC climate STN_ID (1100)")
    ap.add_argument("name", help="short name for the file, e.g. granby")
    ap.add_argument("--years", default="2010-2024", help="first-last calendar year, e.g. 2010-2024")
    ap.add_argument("--out", type=Path, default=DATA)
    a = ap.parse_args()
    y0, _, y1 = a.years.partition("-")
    fetch(a.kind, a.station, a.name, int(y0), int(y1 or y0), a.out)


if __name__ == "__main__":
    main()
