"""
Fetch and parse the records for the climate pair (2026-09-25):
monthly global climate indices 1958-2025, Atlantic and NE/Central Pacific
tropical-cyclone tracks (HURDAT2), and the Granby River's annual maximum
daily flow (the Pacific piece's link back to the valley).

Raw downloads are cached in data/climate/raw/ (skipped if present); parsed
output goes to data/climate/indices_monthly.json and storms_<basin>.json.

Sources (all public; attribution text in the pieces' credits):
  CO2      NOAA GML Mauna Loa monthly mean (Keeling curve)            co2_mm_mlo.txt
  ONI      NOAA CPC Oceanic Nino Index (3-month running Nino-3.4 anomaly, ERSSTv5)
  PDO      NOAA NCEI Pacific Decadal Oscillation (ERSSTv5)
  AMO      NOAA PSL Atlantic Multidecadal Oscillation, unsmoothed, long
  NAO      NOAA CPC North Atlantic Oscillation, monthly standardized
  SST      NOAA NCEI Climate at a Glance: global ocean surface temperature anomaly
  GISTEMP  NASA GISS global land-ocean temperature anomaly (v4)
  Sunspots SILSO (Royal Observatory of Belgium) monthly mean total sunspot number, v2
  HURDAT2  NOAA NHC best tracks: Atlantic and NE+Central Pacific
  IBTrACS  NOAA NCEI v04r01, West Pacific; USA_WIND (JTWC 1-minute) so categories
           match HURDAT2's Saffir-Simpson scale (added 2026-09-25, GW's note)
  Sea ice  NSIDC Sea Ice Index v4 (G02135), Arctic monthly extent, 1978-11 onward
  OHC      IAP (Institute of Atmospheric Physics, CAS) v4.2, global ocean heat content
           0-2000 m, monthly, 10^22 J (Cheng et al. 2024, ESSD 16:3517). Chosen over
           NOAA NCEI's pentadal series: monthly, 1940 on, no splice needed.
  Kettle   USGS 12404500 Kettle River near Laurier, WA: annual peak daily flow, from
           the daily record in ../kettle_laurier_12404500_lowflow.json (GW's note:
           the Kettle replaces the Granby, whose record has a 1958-66 gap)
  Granby   WSC 08NN002 annual statistics via ECCC OGC API (kept; no longer used)

Licence note: SILSO sunspot data are CC BY-NC 4.0, and the IAP heat-content terms
are not yet confirmed, so those two series go to their own file
(fetched_only_monthly.json), which is not committed to the repo.
"""
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
RAW = HERE / "data" / "climate" / "raw"
OUT = HERE / "data" / "climate"
RAW.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "curl/8 (sonification-workbench; personal research)"}
Y0, Y1 = 1958, 2025

SOURCES = {
    "co2_mm_mlo.txt": "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.txt",
    "oni.ascii.txt": "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt",
    "ersst.v5.pdo.dat": "https://www.ncei.noaa.gov/pub/data/cmb/ersst/v5/index/ersst.v5.pdo.dat",
    "amon.us.long.data": "https://psl.noaa.gov/data/correlation/amon.us.long.data",
    "nao.monthly.ascii": "https://www.cpc.ncep.noaa.gov/products/precip/CWlink/pna/norm.nao.monthly.b5001.current.ascii",
    "global_ocean_sst.csv": "https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/global/time-series/globe/ocean/tavg/1/0/1950-2025/data.csv",
    "gistemp_glb.csv": "https://data.giss.nasa.gov/gistemp/tabledata_v4/GLB.Ts+dSST.csv",
    "sunspots_silso.csv": "https://www.sidc.be/SILSO/INFO/snmtotcsv.php",
    "hurdat2_atl.txt": "https://www.nhc.noaa.gov/data/hurdat/hurdat2-1851-2025-091226.txt",
    "hurdat2_nepac.txt": "https://www.nhc.noaa.gov/data/hurdat/hurdat2-nepac-1949-2025-091426.txt",
    "ibtracs_wp.csv": "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/"
                      "v04r01/access/csv/ibtracs.WP.list.v04r01.csv",
    "iap_ohc_v4.2_monthly.txt": "http://www.ocean.iap.ac.cn/ftp/images_files/IAPv4.2_OHC_estimate_update.txt",
    **{f"seaice_N_{m:02d}_extent_v4.0.csv": f"https://noaadata.apps.nsidc.org/NOAA/G02135/north/monthly/data/"
                                           f"N_{m:02d}_extent_v4.0.csv" for m in range(1, 13)},
    "granby_annual_stats.json": "https://api.weather.gc.ca/collections/hydrometric-annual-statistics/items"
                                "?STATION_NUMBER=08NN002&limit=500&f=json",
}

# Large volcanic eruptions in the span, for the "cooling" event layer. Dates are
# the paroxysmal eruption dates as listed by the Smithsonian Global Volcanism
# Program [verify each against GVP before publication].
# cooling = relative weight of the drone-darkening envelope (D, interpretive):
# Pinatubo is the benchmark stratospheric-aerosol cooling of the record; Hunga
# Tonga injected mostly water vapour, with a small and debated net effect.
VOLCANOES = [
    ("1963-03-17", "Agung, Bali", 5, 0.4, None),
    ("1982-04-04", "El Chichon, Mexico", 5, 0.4, None),
    ("1991-06-15", "Pinatubo, Philippines", 6, 0.6, None),
    ("2022-01-15", "Hunga Tonga-Hunga Ha'apai", 5, 0.1,
     "mostly water vapour, not sulphate: the drone barely darkens"),
]


def get(name):
    p = RAW / name
    if not p.exists() or not p.stat().st_size:
        req = urllib.request.Request(SOURCES[name], headers=UA)
        p.write_bytes(urllib.request.urlopen(req, timeout=120).read())
        print("fetched", name)
    return p.read_text(errors="replace")


MONTHS = [(y, m) for y in range(Y0, Y1 + 1) for m in range(1, 13)]
IDX = {ym: i for i, ym in enumerate(MONTHS)}


def blank():
    return np.full(len(MONTHS), np.nan)


def put(arr, y, m, v, missing=None):
    if (y, m) in IDX and v is not None and np.isfinite(v) and (missing is None or abs(v - missing) > 1e-6):
        arr[IDX[(y, m)]] = v


def parse_co2():
    avg, des = blank(), blank()
    for ln in get("co2_mm_mlo.txt").splitlines():
        if ln.startswith("#") or not ln.strip():
            continue
        f = ln.split()
        y, m, a, d = int(f[0]), int(f[1]), float(f[3]), float(f[4])
        put(avg, y, m, a, -99.99)
        put(des, y, m, d, -99.99)
    return avg, des


def parse_oni():
    # rows: SEAS YR TOTAL ANOM; the 3-month season is assigned to its centre month
    centre = {"DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6, "JJA": 7, "JAS": 8,
              "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12}
    out = blank()
    for ln in get("oni.ascii.txt").splitlines()[1:]:
        f = ln.split()
        if len(f) == 4 and f[0] in centre:
            put(out, int(f[1]), centre[f[0]], float(f[3]))
    return out


def parse_year_by_12(text, missing):
    out = blank()
    for ln in text.splitlines():
        f = ln.split()
        if len(f) >= 13 and re.fullmatch(r"\d{4}", f[0]):
            for m in range(12):
                put(out, int(f[0]), m + 1, float(f[m + 1]), missing)
    return out


def parse_nao():
    out = blank()
    for ln in get("nao.monthly.ascii").splitlines():
        f = ln.split()
        if len(f) == 3 and f[0].isdigit():
            put(out, int(f[0]), int(f[1]), float(f[2]))
    return out


def parse_ncei_csv():
    out = blank()
    for ln in get("global_ocean_sst.csv").splitlines():
        f = ln.split(",")
        if len(f) >= 2 and re.fullmatch(r"\d{6}", f[0]):
            put(out, int(f[0][:4]), int(f[0][4:]), float(f[1]))
    return out


def parse_gistemp():
    out = blank()
    for ln in get("gistemp_glb.csv").splitlines():
        f = ln.split(",")
        if f and re.fullmatch(r"\d{4}", f[0]):
            for m in range(12):
                if f[m + 1].strip() not in ("***", ""):
                    put(out, int(f[0]), m + 1, float(f[m + 1]))
    return out


def parse_sunspots():
    out = blank()
    for ln in get("sunspots_silso.csv").splitlines():
        f = ln.split(";")
        if len(f) >= 4:
            put(out, int(f[0]), int(f[1]), float(f[3]), -1)
    return out


def saffir_simpson(kt):
    for cat, lo in ((5, 137), (4, 113), (3, 96), (2, 83), (1, 64)):
        if kt >= lo:
            return cat
    return 0


def parse_hurdat(name):
    """Per storm: name, peak wind (kt) and its date, min pressure, ACE, landfall, category."""
    storms, cur = [], None
    for ln in get(name).splitlines():
        f = [x.strip() for x in ln.split(",")]
        if re.fullmatch(r"(AL|EP|CP)\d{6}", f[0]):
            cur = {"id": f[0], "name": f[1].title(), "rows": []}
            storms.append(cur)
        elif cur is not None and re.fullmatch(r"\d{8}", f[0]):
            cur["rows"].append(f)
    out = []
    for s in storms:
        y = int(s["id"][-4:])
        if not (Y0 <= y <= Y1):
            continue
        best, ace, landfall, pmin = None, 0.0, False, None
        for f in s["rows"]:
            date, hhmm, rec, status = f[0], f[1], f[2], f[3]
            v = int(f[6]) if f[6] not in ("", "-99", "-999") else 0
            p = int(f[7]) if f[7] not in ("", "-999") else None
            if rec == "L":
                landfall = True
            if p is not None and p > 0:
                pmin = p if pmin is None else min(pmin, p)
            if hhmm in ("0000", "0600", "1200", "1800") and status in ("TS", "HU", "SS") and v >= 34:
                ace += v * v / 1e4
            if best is None or v > best[0]:
                best = (v, datetime.strptime(date + hhmm, "%Y%m%d%H%M"))
        if best is None:
            continue
        out.append({"id": s["id"], "name": s["name"], "peak_kt": best[0], "peak_time": best[1].isoformat(),
                    "category": saffir_simpson(best[0]), "ace": round(ace, 2), "landfall": landfall,
                    "min_pressure_mb": pmin})
    return out


def parse_ibtracs_wp():
    """West Pacific storms from IBTrACS, same record shape as parse_hurdat()."""
    import csv
    rows = csv.reader(get("ibtracs_wp.csv").splitlines())
    head = next(rows)
    next(rows)                                         # units row
    c = {k: i for i, k in enumerate(head)}
    storms = {}
    for r in rows:
        if r[c["BASIN"]] != "WP" or r[c["TRACK_TYPE"]] != "main":
            continue
        yr = int(r[c["SEASON"]])
        if not (Y0 <= yr <= Y1):
            continue
        s = storms.setdefault(r[c["SID"]], {"id": r[c["SID"]], "name": r[c["NAME"]].title(), "rows": []})
        w = r[c["USA_WIND"]].strip()
        s["rows"].append((r[c["ISO_TIME"]], int(w) if w else None, r[c["NATURE"]], r[c["LANDFALL"]].strip(),
                          r[c["USA_PRES"]].strip()))
    out = []
    for s in storms.values():
        winds = [(w, t) for t, w, *_ in s["rows"] if w is not None]
        if not winds:
            continue
        v, t = max(winds, key=lambda x: x[0])
        ace = sum(w * w / 1e4 for tt, w, nat, *_ in s["rows"]
                  if w is not None and w >= 34 and nat == "TS" and tt[11:16] in ("00:00", "06:00", "12:00", "18:00"))
        landfall = any(lf == "0" and w is not None and w >= 34 for _, w, _, lf, _ in s["rows"])
        pres = [int(p) for *_, p in s["rows"] if p]
        out.append({"id": s["id"], "name": s["name"], "peak_kt": v,
                    "peak_time": datetime.strptime(t, "%Y-%m-%d %H:%M:%S").isoformat(),
                    "category": saffir_simpson(v), "ace": round(ace, 2), "landfall": landfall,
                    "min_pressure_mb": min(pres) if pres else None})
    return sorted(out, key=lambda s: s["peak_time"])


def parse_seaice():
    """Arctic monthly sea-ice extent (million km2); -9999 = missing (Dec 1987-Jan 1988)."""
    out = blank()
    for m in range(1, 13):
        for ln in get(f"seaice_N_{m:02d}_extent_v4.0.csv").splitlines()[1:]:
            f = [x.strip() for x in ln.split(",")]
            if len(f) >= 5 and f[0].isdigit():
                put(out, int(f[0]), int(f[1]), float(f[4]), -9999)
    return out


def parse_ohc():
    """Global 0-2000 m ocean heat content anomaly (10^22 J, baseline 2006-15) and its
    95% half-width, monthly, from IAP v4.2 (columns 9 and 11)."""
    val, err = blank(), blank()
    for ln in get("iap_ohc_v4.2_monthly.txt").splitlines():
        f = ln.split()
        if len(f) >= 11 and f[0].isdigit():
            put(val, int(f[0]), int(f[1]), float(f[8]))
            put(err, int(f[0]), int(f[1]), float(f[10]))
    return val, err


def parse_kettle():
    """Kettle River near Laurier (USGS 12404500): each calendar year's peak daily flow and date."""
    d = json.loads((HERE / "data" / "kettle_laurier_12404500_lowflow.json").read_text())["daily"]
    out = {}
    for date, q in zip(d["date"], d["q"]):
        if q is None:
            continue
        y = int(date[:4])
        if y not in out or q > out[y]["max_daily_m3s"]:
            out[y] = {"max_daily_m3s": q, "date": date[:10]}
    return dict(sorted(out.items()))


def parse_granby():
    d = json.loads(get("granby_annual_stats.json"))
    out = {}
    for f in d["features"]:
        p = f["properties"]
        if p["DATA_TYPE_EN"] == "Discharge" and p["MAX_VALUE"] is not None:
            out[int(p["IDENTIFIER"].split(".")[1])] = {"max_daily_m3s": p["MAX_VALUE"], "date": p["MAX_DATE"],
                                                       "symbol": p["MAX_SYMBOL_EN"] or ""}
    return dict(sorted(out.items()))


def main():
    co2, co2_des = parse_co2()
    pdo = parse_year_by_12(get("ersst.v5.pdo.dat"), 99.99)
    amo = parse_year_by_12(get("amon.us.long.data"), -99.99)
    series = {
        "co2_ppm": co2, "co2_deseason_ppm": co2_des, "oni": parse_oni(), "pdo": pdo, "amo": amo,
        "nao": parse_nao(), "sst_global_anom": parse_ncei_csv(), "gistemp_anom": parse_gistemp(),
        "seaice_extent_mkm2": parse_seaice(),
    }
    ohc, ohc_err = parse_ohc()
    sunspots = parse_sunspots()
    months = [f"{y}-{m:02d}" for y, m in MONTHS]
    js = {"months": months,
          "series": {k: [None if not np.isfinite(v) else round(float(v), 4) for v in a] for k, a in series.items()},
          "volcanoes": [{"date": d, "name": n, "vei": v, "cooling": c, **({"note": t} if t else {})}
                        for d, n, v, c, t in VOLCANOES],
          "sources": {k: v for k, v in SOURCES.items()}}
    (OUT / "indices_monthly.json").write_text(json.dumps(js))
    rnd = lambda a, k: [None if not np.isfinite(v) else round(float(v), k) for v in a]
    (OUT / "fetched_only_monthly.json").write_text(json.dumps(
        {"months": months, "series": {"sunspots": rnd(sunspots, 1), "ohc_0_2000_1e22J": rnd(ohc, 2),
                                      "ohc_0_2000_err95": rnd(ohc_err, 2)},
         "terms": {"sunspots": "CC BY-NC 4.0, WDC-SILSO, Royal Observatory of Belgium, Brussels",
                   "ohc": "IAP v4.2 (Cheng et al. 2024); redistribution terms not yet confirmed"}}))
    series.update(sunspots=sunspots, ohc_0_2000_1e22J=ohc)
    for k, a in series.items():
        ok = np.isfinite(a)
        first = months[int(np.argmax(ok))] if ok.any() else None
        last = months[len(ok) - 1 - int(np.argmax(ok[::-1]))] if ok.any() else None
        print(f"{k:18s} {ok.sum():4d}/{len(a)} months  {first} .. {last}")
    for basin in ("atl", "nepac", "wpac"):
        st = parse_ibtracs_wp() if basin == "wpac" else parse_hurdat(f"hurdat2_{basin}.txt")
        (OUT / f"storms_{basin}.json").write_text(json.dumps(st, indent=0))
        cats = np.bincount([s["category"] for s in st], minlength=6)
        print(f"storms {basin}: {len(st)} systems, by category {cats.tolist()}, "
              f"max ACE {max(s['ace'] for s in st):.1f}")
    ke = parse_kettle()
    (OUT / "kettle_annual_max.json").write_text(json.dumps(ke, indent=0))
    print(f"kettle annual max: {len(ke)} years, {min(ke)}-{max(ke)}")
    gr = parse_granby()
    (OUT / "granby_annual_max.json").write_text(json.dumps(gr, indent=0))
    miss = [y for y in range(Y0, 2025) if y not in gr]
    print(f"granby annual max: {len(gr)} years, missing {Y0}-2024: {miss}")


if __name__ == "__main__":
    main()
