"""
ARCTIC YEAR: fetch + process (spec 261007-arctic-year-spec.md, section 10; claims in arctic/research/).

Inputs (all public; raw files are kept in $SONIFICATION_RAW/arctic, default rendered/raw/arctic):
  daily extent    NSIDC Sea Ice Index v4 (G02135) N_seaice_extent_daily_v4.0.csv      10.7265/a98x-0f50
  regional daily  NSIDC Sea Ice Index v4 regional daily workbook (extent, km2)
  PIOMAS volume   UW PSC PIOMAS monthly mean volume (M, a model-assimilated series; Zhang and Rothrock 2003)
  Barrow CO2      NOAA GML in-situ monthly, BRW (CC0)
  GISTEMP zonal   NASA GISS ZonAnn.Ts+dSST (64N-90N and global annual anomalies)
  global SST      NOAA NCEI Climate at a Glance, already fetched for the Climate Pair (data/climate/raw)

Output (data/arctic/): arctic_daily.json
  dates        every day 1978-10-26 .. last day of record (ISO)
  observed     per day, 1 if a real observation, 0 if linearly filled (every-other-day era and the 1987-88 gap)
  total        total extent, M km2
  regions      ten regions, extent M km2, same grid; order = voice order, Beaufort west .. Baffin east (see REGIONS)
  piomas_1000km3      monthly volume (1000 km3) {YYYY-MM: v}
  co2_brw_ppm         monthly ppm {YYYY-MM: v}
  gistemp      {year: {arctic: C, global: C}}
  sst_global_anom_c   monthly anomaly {YYYY-MM: C}
  sources      list of dicts (name, url, label R/D/M)

Run: python scripts/fetch_arctic.py [--refetch]   (needs the packages in arctic-bside/requirements-fetch.txt)
"""
import csv
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("SONIFICATION_RAW", ROOT / "rendered" / "raw")) / "arctic"
OUT = ROOT / "data" / "arctic"
RAW.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

URLS = {
    "daily.csv": "https://noaadata.apps.nsidc.org/NOAA/G02135/north/daily/data/N_seaice_extent_daily_v4.0.csv",
    "regional.xlsx": "https://noaadata.apps.nsidc.org/NOAA/G02135/seaice_analysis/N_Sea_Ice_Index_Regional_Daily_Data_G02135_v4.0.xlsx",
    "piomas.csv": "https://psc.apl.uw.edu/wordpress/wp-content/uploads/schweiger/ice_volume/PIOMAS.monthly.Current.v2.1.csv",
    "brw.txt": "https://gml.noaa.gov/aftp/data/trace_gases/co2/in-situ/surface/txt/co2_brw_surface-insitu_1_ccgg_MonthlyData.txt",
    "zon.csv": "https://data.giss.nasa.gov/gistemp/tabledata_v4/ZonAnn.Ts+dSST.csv",
}

# voice order: Pacific side west to east, then the Eurasian shelf, then the Atlantic doorway, then the Archipelago and Baffin
REGIONS = [("Beaufort", "Beaufort"), ("Chukchi", "Chukchi"), ("East-Siberian", "East Siberian"), ("Laptev", "Laptev"),
           ("Kara", "Kara"), ("Barents", "Barents"), ("Greenland", "Greenland Sea"),
           ("CanadianArchipelago", "Canadian Archipelago"), ("Baffin", "Baffin Bay"), ("Central-Arctic", "Central Arctic")]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def get(name, refetch=False):
    p = RAW / name
    if refetch or not p.exists():
        print("fetching", name)
        req = urllib.request.Request(URLS[name], headers={"User-Agent": "sonification-workbench (research; contact via repo)"})
        p.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    return p


def fill(vals):
    """Linear fill of None between observations; leading/trailing None stay None. -> (list, observed flags)"""
    obs = [v is not None for v in vals]
    idx = [i for i, o in enumerate(obs) if o]
    out = list(vals)
    for a, b in zip(idx[:-1], idx[1:]):
        for i in range(a + 1, b):
            out[i] = vals[a] + (vals[b] - vals[a]) * (i - a) / (b - a)
    return out, [int(o) for o in obs]


def main():
    refetch = "--refetch" in sys.argv
    import openpyxl

    # ---- total extent (every other day until 20 Aug 1987, one gap 2 Dec 1987 - 13 Jan 1988)
    tot = {}
    for ln in csv.reader(open(get("daily.csv", refetch))):
        try:
            y, m, d = int(ln[0]), int(ln[1]), int(ln[2])
        except ValueError:
            continue
        tot[dt.date(y, m, d)] = float(ln[3])
    first, last = min(tot), max(tot)
    days = [first + dt.timedelta(i) for i in range((last - first).days + 1)]
    total, observed = fill([tot.get(d) for d in days])
    print("days", len(days), first, last, "observed", sum(observed))

    # ---- regional daily (sheet "<Name>-Extent-km^2": rows month/day, columns years)
    wb = openpyxl.load_workbook(get("regional.xlsx", refetch), read_only=True, data_only=True)
    regions = {}
    for key, label in REGIONS:
        ws = wb[f"{key}-Extent-km^2"]
        rows = list(ws.iter_rows(values_only=True))
        years = [c for c in rows[0][2:]]
        month = None
        cell = {}
        for r in rows[1:]:
            if r[0]:
                month = MONTHS.index(r[0]) + 1
            day = r[1]
            if day is None:
                continue
            for y, v in zip(years, r[2:]):
                if v is not None and isinstance(y, int):
                    cell[(y, month, int(day))] = float(v) / 1e6
        series, _ = fill([cell.get((d.year, d.month, d.day)) for d in days])
        regions[key] = {"label": label, "extent": [None if v is None else round(v, 4) for v in series]}
        print(f"  {key:20s} {sum(v is not None for v in cell.values())} obs  max {max(cell.values()):.2f}")
    # the regional workbook starts later than the total; leading None become the first value, so the ice year can start whole
    for k, r in regions.items():
        v = r["extent"]
        f = next(x for x in v if x is not None)
        r["extent"] = [f if x is None else x for x in v]

    # ---- monthly / annual series
    piomas = {}
    for ln in csv.reader(open(get("piomas.csv", refetch))):
        try:
            y = int(float(ln[0]))
        except ValueError:
            continue
        for m, v in enumerate(ln[1:13], 1):
            try:
                if float(v) > 0:        # the file pads the current year with -1
                    piomas[f"{y}-{m:02d}"] = float(v)
            except ValueError:
                pass
    co2 = {}
    for ln in open(get("brw.txt", refetch)):
        if ln.startswith(("site_code", "#")) or len(ln.split()) < 11:
            continue
        p = ln.split()
        v = float(p[10])
        if v > 0:
            co2[f"{int(p[1])}-{int(p[2]):02d}"] = v
    gis = {}
    for ln in csv.reader(open(get("zon.csv", refetch))):
        try:
            y = int(ln[0])
        except ValueError:
            continue
        g = ln[1]   # columns: Year, Glob, NHem, SHem, 24N-90N, 24S-24N, 90S-24S, 64N-90N
        gis[y] = {"arctic": float(ln[7]) if ln[7] not in ("***", "") else None, "global": float(g)}
    sst = {}   # optional: the Climate Pair's global ocean temperature file, if it has been fetched. The B-side and the picture do not use it.
    sp = ROOT / "data" / "climate" / "raw" / "global_ocean_sst.csv"
    if sp.exists():
        for ln in sp.read_text().splitlines():
            p = ln.split(",")
            if len(p) == 2 and p[0].isdigit() and len(p[0]) == 6:
                sst[f"{p[0][:4]}-{p[0][4:]}"] = float(p[1])
    else:
        print("note: no", sp, "- sst_global_anom_c is left empty (only the main piece's ladder layer needs it)")

    out = {
        "dates": [d.isoformat() for d in days], "observed": observed, "total": [round(v, 4) for v in total],
        "regions": regions, "region_order": [k for k, _ in REGIONS],
        "piomas_1000km3": piomas, "co2_brw_ppm": co2, "gistemp": gis, "sst_global_anom_c": sst,
        "sources": [
            {"name": "NSIDC Sea Ice Index v4 (G02135), daily and regional daily", "doi": "10.7265/a98x-0f50", "label": "R",
             "note": "extent only; 25 km passive microwave; every other day before 1987-08-20, gap 1987-12-02..1988-01-13 filled linearly (observed=0)"},
            {"name": "PIOMAS monthly mean ice volume v2.1, UW Polar Science Center", "label": "M", "note": "model with assimilated concentration and SST"},
            {"name": "NOAA GML Barrow CO2 in-situ monthly (CC0)", "label": "R"},
            {"name": "NASA GISS GISTEMP v4 zonal annual means, 64N-90N and global", "label": "R"},
            {"name": "NOAA NCEI Climate at a Glance, global ocean surface temperature anomaly", "label": "R"}],
    }
    (OUT / "arctic_daily.json").write_text(json.dumps(out, separators=(",", ":")))
    print("wrote", OUT / "arctic_daily.json", round((OUT / "arctic_daily.json").stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
