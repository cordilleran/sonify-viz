"""
Fetch the Meridian Chorus covariates, layer 2: air temperature, sea surface
temperature and sea ice, at each of the 13 voices on one meridian, daily
through one solstice year (2026-09-27; spec 260927-meridian-chorus-spec.md §7).

    python fetch_meridian.py                 # 100 W, DS2023 (2023-12-22 .. 2024-12-21)
    python fetch_meridian.py -120 ds2023

Sources (checked 2026-09-27):
  Air temp  ERA5 0.25 deg reanalysis via the Open-Meteo historical API,       D (modelled)
            models=era5, daily mean/min/max of temperature_2m (UTC days).
            cell_selection follows each voice's surface (land or sea).
            ERA5: CC BY 4.0 (Copernicus); Open-Meteo: CC BY 4.0, non-commercial API.
  SST       NOAA OISST v2.1, 0.25 deg daily (CoastWatch ERDDAP                R (blended obs)
            ncdcOisst21Agg_LonPM180), nearest ocean cell. Under sea ice
            OISST reports a freezing-point value derived from the ice, so it
            is kept but flagged `under_ice` where ice > 15%.
  Sea ice   NOAA/NSIDC Climate Data Record v6, 25 km daily, polar            R (satellite)
            stereographic (CoastWatch ERDDAP nsidcG02202v6[nh|sh]1day),
            cdr_seaice_conc, nearest winter-ocean cell not touched by the
            land-spillover filter; days that filter touched are dropped and
            interpolated by the loader (it zeroes coastal cells). The 90 N
            "pole hole" is filled by the CDR's own spatial interpolation (its
            flag is kept). Licence: "No constraints on data access or use".
Each series records the cell it actually used and that cell's distance from the
nominal point (spec §7, point-extraction rules). The South Pole's AMRC station
record (the spec's primary source there) is still to do; ERA5 stands in, flagged.

Raw downloads are cached in data/meridian/raw/ (skipped if present).
Output: data/meridian/meridian_<lon>_<year>.json
"""
import csv
import io
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import timegrid as T

HERE = Path(__file__).resolve().parent.parent
RAW = HERE / "data" / "meridian" / "raw"
OUT = HERE / "data" / "meridian"
RAW.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "curl/8 (sonification-workbench; personal research)"}
LATS = [90, 75, 60, 45, 30, 15, 0, -15, -30, -45, -60, -75, -90]
# which surface each voice asks ERA5 for, and which sea layers it has (spec §2; 75 N and 75 S take the
# nearest sea for SST and ice: Barrow Strait / Viscount Melville Sound, and Pine Island Bay)
SURFACE = {90: "sea", 75: "land", 60: "land", 45: "land", 30: "land", 15: "sea", 0: "sea", -15: "sea",
           -30: "sea", -45: "sea", -60: "sea", -75: "land", -90: "land"}
SST_VOICES = [90, 75, 15, 0, -15, -30, -45, -60, -75]
ICE_VOICES = [90, 75, -60, -75]
ERDDAP = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"
POLARWATCH = "https://polarwatch.noaa.gov/erddap/griddap"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def get(url, cache):
    p = RAW / cache
    if not p.exists():
        for attempt in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                    p.write_bytes(r.read())
                break
            except Exception as e:  # ERDDAP and Open-Meteo both rate-limit; back off and retry
                log(f"  retry {attempt + 1} for {cache}: {e}")
                time.sleep(10 * (attempt + 1))
        else:
            raise RuntimeError(f"failed: {url}")
        time.sleep(1.0)
    return p.read_text()


def km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))


def erddap_csv(text):
    rows = list(csv.reader(io.StringIO(text)))
    return rows[0], rows[2:]  # header, (units row skipped), data


# ------------------------------------------------------------------ air --
def air(lat, lon, Y):
    url = ("https://archive-api.open-meteo.com/v1/archive?"
           f"latitude={lat}&longitude={lon}&start_date={Y.start}&end_date={Y.end}"
           "&daily=temperature_2m_mean,temperature_2m_min,temperature_2m_max"
           f"&timezone=GMT&models=era5&cell_selection={SURFACE[lat]}")
    j = json.loads(get(url, f"era5_{lat:+d}_{lon:+.0f}_{Y.label}.json"))
    d = j["daily"]
    return {"source": "ERA5 via Open-Meteo (models=era5)", "tag": "D",
            "cell": [j["latitude"], j["longitude"]], "cell_elevation_m": j["elevation"],
            "cell_selection": SURFACE[lat], "distance_km": round(km(lat, lon, j["latitude"], j["longitude"]), 1),
            "note": ("stands in for the AMRC Amundsen-Scott station record (to do): a 2,835 m plateau grid cell"
                     if lat == -90 else None),
            "date": d["time"], "mean": d["temperature_2m_mean"], "min": d["temperature_2m_min"],
            "max": d["temperature_2m_max"]}


# ------------------------------------------------------------------ sst --
def sst(lat, lon, Y):
    """Nearest OISST cell with data: search outward in 0.25-degree rings (a coast or an island
    can put the nominal point on land)."""
    q = max(-89.875, min(89.875, lat))
    for r in range(0, 9):
        box = f"[({Y.start}T12:00:00Z)][(0.0)][({q - 0.25 * r}):1:({q + 0.25 * r})][({lon - 0.25 * r}):1:({lon + 0.25 * r})]"
        head, rows = erddap_csv(get(f"{ERDDAP}/ncdcOisst21Agg_LonPM180.csv?sst{box}",
                                    f"oisst_probe_{lat:+d}_{lon:+.0f}_{Y.start}_r{r}.csv"))
        wet = [(km(lat, lon, float(rw[2]), float(rw[3])), float(rw[2]), float(rw[3])) for rw in rows
               if rw[4] not in ("", "NaN")]
        if wet:
            break
    else:
        return None
    dist, clat, clon = min(wet)
    box = f"[({Y.start}T12:00:00Z):1:({Y.end}T12:00:00Z)][(0.0)][({clat})][({clon})]"
    head, rows = erddap_csv(get(f"{ERDDAP}/ncdcOisst21Agg_LonPM180.csv?sst{box}",
                                f"oisst_{lat:+d}_{lon:+.0f}_{Y.label}.csv"))
    return {"source": "NOAA OISST v2.1 (ERDDAP ncdcOisst21Agg_LonPM180)", "tag": "R",
            "cell": [clat, clon], "distance_km": round(dist, 1),
            "date": [rw[0][:10] for rw in rows], "sst": [None if rw[4] in ("", "NaN") else float(rw[4]) for rw in rows]}


# ------------------------------------------------------------------ ice --
def ice(lat, lon, Y):
    hemi = "nh" if lat > 0 else "sh"
    grid = get(f"{POLARWATCH}/nsidcCDRice_{hemi}_grid.csv?latitude,longitude", f"nsidc_{hemi}_latlon.csv")
    head, rows = erddap_csv(grid)
    cells = sorted((km(lat, lon, float(rw[2]), float(rw[3])), float(rw[0]), float(rw[1]), float(rw[2]), float(rw[3]))
                   for rw in rows if rw[2] not in ("", "NaN"))[:40]
    ds = f"nsidcG02202v6{hemi}1day"
    winter = f"{Y.start.year + (1 if hemi == 'sh' else 0)}-{'08' if hemi == 'sh' else '03'}-15"
    # the nearest cell that is open ocean in winter: land, coast and lakes carry flag values > 1, and a
    # coastal cell whose winter value was zeroed by the CDR's land-spillover filter (QA bit 4) is skipped
    # (at 75 S the nearest sea cell reads 0.0 all winter for that reason, beside cells at 0.6-0.7)
    for dist, y, x, clat, clon in cells:
        q = f"[({winter}T00:00:00Z)][({y})][({x})]"
        h, r = erddap_csv(get(f"{ERDDAP}/{ds}.csv?cdr_seaice_conc{q},cdr_seaice_conc_qa_flag{q}",
                              f"nsidc_probe_qa_{hemi}_{y:.0f}_{x:.0f}_{winter}.csv"))
        v, qa = (r[0][3], r[0][4]) if r else ("NaN", "0")
        if v not in ("", "NaN") and 0 <= float(v) <= 1 and not int(float(qa or 0)) & 4:
            break
    else:
        return None
    box = f"[({Y.start}T00:00:00Z):1:({Y.end}T00:00:00Z)][({y})][({x})]"
    h, r = erddap_csv(get(f"{ERDDAP}/{ds}.csv?cdr_seaice_conc{box},cdr_seaice_conc_interp_spatial_flag{box},"
                          f"cdr_seaice_conc_qa_flag{box}", f"nsidc_qa_{lat:+d}_{lon:+.0f}_{Y.label}.csv"))
    # a day the land-spillover filter touched is dropped (the loader interpolates across it): at 75 S it
    # zeroes the cell for 12 days in mid-winter July between days at 0.6-0.7
    spill = lambda rw: rw[5] not in ("", "NaN") and int(float(rw[5])) & 4
    conc = [None if rw[3] in ("", "NaN") or not 0 <= float(rw[3]) <= 1 or spill(rw) else float(rw[3]) for rw in r]
    return {"source": f"NOAA/NSIDC sea ice CDR v6 (ERDDAP {ds}), cdr_seaice_conc", "tag": "R",
            "cell": [round(clat, 3), round(clon, 3)], "cell_xy_m": [x, y], "distance_km": round(dist, 1),
            "date": [rw[0][:10] for rw in r], "conc": conc,
            "spatially_interpolated_days": sum(1 for rw in r if rw[4] not in ("", "NaN", "0")),
            "land_spillover_days_dropped": sum(1 for rw in r if spill(rw))}


def main():
    lon = float(sys.argv[1]) if len(sys.argv) > 1 else -100.0
    Y = T.Year.parse(sys.argv[2] if len(sys.argv) > 2 else "ds2023")
    out = {"meridian": lon, "year": Y.label, "start": str(Y.start), "end": str(Y.end), "n_days": Y.n_days,
           "fetched": time.strftime("%Y-%m-%d"), "voices": {}}
    for lat in LATS:
        v = {"lat": lat, "air": air(lat, lon, Y)}
        a = v["air"]
        log(f"{lat:+3d} air  cell {a['cell']} ({a['distance_km']} km, {a['cell_elevation_m']} m) "
            f"mean {min(a['mean']):.1f}..{max(a['mean']):.1f} C")
        if lat in SST_VOICES:
            v["sst"] = sst(lat, lon, Y)
            s = v["sst"]
            ok = [x for x in s["sst"] if x is not None]
            log(f"    sst  cell {s['cell']} ({s['distance_km']} km) {min(ok):.2f}..{max(ok):.2f} C, {len(ok)} days")
        if lat in ICE_VOICES:
            v["ice"] = ice(lat, lon, Y)
            c = v["ice"]
            ok = [x for x in c["conc"] if x is not None]
            log(f"    ice  cell {c['cell']} ({c['distance_km']} km) {min(ok):.2f}..{max(ok):.2f}, {len(ok)} days, "
                f"{c['spatially_interpolated_days']} interpolated, {c['land_spillover_days_dropped']} spillover days dropped")
        out["voices"][str(lat)] = v
    dest = OUT / f"meridian_{abs(lon):.0f}{'w' if lon < 0 else 'e'}_{Y.label.lower()}.json"
    dest.write_text(json.dumps(out, indent=1))
    log(f"-> {dest.relative_to(HERE)} ({dest.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
