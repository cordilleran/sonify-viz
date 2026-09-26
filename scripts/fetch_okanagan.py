"""
Fetch the Okanagan pilot's source data into data/ (cached JSON, same shape as
the Granby pulls).

Hydrometric (ECCC OGC API, hydrometric-daily-mean, 2010-2024):
  08NM083  Okanagan Lake at Kelowna      - lake LEVEL (m), the slow regulated signal
  08NM050  Okanagan River at Penticton   - lake outflow DISCHARGE (dam-regulated)
  08NM085  Okanagan River near Oliver    - lower-river DISCHARGE (sockeye reach)
Climate (ECCC OGC API, climate-daily, 2010-2024):
  STN_ID 979   Summerland CS (lakeside, central valley)
Satellite (ORNL DAAC MODIS subset REST API, 2015-2024, 8-day):
  MOD17A2HGF GPP at a Summerland-bench point and the Granby valley point -
  "plant metabolism" retrieved rather than simulated.
Fish (Columbia Basin Research DART, 2015-2024):
  Wells Dam daily adult sockeye counts + water temperature. Wells is on the
  Columbia above the Wenatchee and below the Okanagan confluence, so its
  sockeye are overwhelmingly Okanagan-bound; it is not an Okanagan gauge.
  The raw DART file is not committed to the repo; run `fetch_okanagan.py dart`
  to pull it. Citation: Columbia River DART, Columbia Basin Research,
  University of Washington. Adult Passage Daily Counts.
  https://www.cbr.washington.edu/dart/query/adult_daily
"""
import json, sys, time, urllib.request, urllib.parse
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
OGC = "https://api.weather.gc.ca/collections"


def get(url, tries=4):
    for i in range(tries):
        try:
            # ORNL returns HTTP 500 to urllib's default User-Agent; curl's works
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8.5", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:
            print("  retry", i, e, file=sys.stderr)
            time.sleep(3 * (i + 1))
    raise RuntimeError(url)


def ogc_all(coll, params):
    out, offset = [], 0
    while True:
        q = dict(params, f="json", limit=10000, offset=offset)
        d = json.loads(get(f"{OGC}/{coll}/items?" + urllib.parse.urlencode(q)))
        out += d["features"]
        if len(d["features"]) < 10000:
            return out
        offset += 10000


def hydro(stn, name):
    p = DATA / f"{name}_{stn}_2010_2024.json"
    if p.exists():
        return
    f = ogc_all("hydrometric-daily-mean",
                {"STATION_NUMBER": stn, "datetime": "2010-01-01/2024-12-31"})
    with open(p, "w") as fh:
        json.dump(f, fh)
    print(stn, len(f))


def climate(stn_id, name):
    p = DATA / f"{name}_{stn_id}_climate_2010_2024.json"
    if p.exists():
        return
    f = ogc_all("climate-daily", {"STN_ID": stn_id, "datetime": "2010-01-01/2024-12-31"})
    with open(p, "w") as fh:
        json.dump(f, fh)
    print(stn_id, len(f))


def modis_gpp(lat, lon, name):
    p = DATA / f"modis_gpp_{name}_2015_2024.json"
    if p.exists():
        return
    base = "https://modis.ornl.gov/rst/api/v1/MOD17A2HGF"
    dates = json.loads(get(f"{base}/dates?latitude={lat}&longitude={lon}"))["dates"]
    dates = [d for d in dates if "2015-01-01" <= d["calendar_date"] <= "2024-12-31"]
    rows = []
    for i in range(0, len(dates), 10):
        chunk = dates[i:i + 10]
        q = urllib.parse.urlencode(dict(latitude=lat, longitude=lon,
                                        startDate=chunk[0]["modis_date"], endDate=chunk[-1]["modis_date"],
                                        kmAboveBelow=1, kmLeftRight=1))
        d = json.loads(get(f"{base}/subset?{q}"))
        for s in d["subset"]:
            if s["band"] == "Gpp_500m":
                rows.append({"date": s["calendar_date"], "data": s["data"]})
    with open(p, "w") as fh:
        json.dump({"lat": lat, "lon": lon, "product": "MOD17A2HGF", "band": "Gpp_500m",
                   "units": "kg C m-2 per 8 days, scale 0.0001; fill >= 32761",
                   "rows": rows}, fh)
    print("gpp", name, len(rows))


def dart_sockeye():
    p = DATA / "wells_dam_sockeye_2015_2024.json"
    if p.exists():
        return
    out = {}
    for yr in range(2015, 2025):
        q = urllib.parse.urlencode({"sc": 1, "outputFormat": "csv", "year": yr, "proj": "WEL",
                                    "span": "no", "startdate": "1/1", "enddate": "12/31"})
        txt = get("https://www.cbr.washington.edu/dart/cs/php/rpt/adult_daily.php?" + q).decode()
        out[yr] = txt
    with open(p, "w") as fh:
        json.dump(out, fh)
    print("dart", {k: len(v) for k, v in out.items()})


if __name__ == "__main__":
    what = sys.argv[1:] or ["hydro", "climate", "gpp", "dart"]
    if "hydro" in what:
        hydro("08NM083", "okanagan_lake_kelowna")
        hydro("08NM050", "okanagan_river_penticton")
        hydro("08NM085", "okanagan_river_oliver")
    if "climate" in what:
        climate(979, "summerland_cs")
    if "gpp" in what:
        modis_gpp(49.60, -119.68, "summerland")
        modis_gpp(49.10, -118.45, "granby_valley")
    if "dart" in what:
        dart_sockeye()
