"""
Lake Superior ice cover, winter 2025/26: fetch + process (icecover project).

Inputs (all public, NOAA GLERL / CoastWatch Great Lakes Node ERDDAP; free to reuse and redistribute):
  ice_concentration  GL_Ice_Concentration_GCS  daily, percent (GLSEA + NIC analysis)   -> raw/icecover/sup_ice_wy2526.nc
  sst                GLSEA_ACSPO_GCS           daily, deg C (ACSPO GLSEA satellite)    -> raw/icecover/sup_sst_wy2526.nc
  lake-wide ice      g<year>_<year+1>_ice.dat  GLERL daily lake averages, 2008/09-2025/26 -> raw/icecover/
  weather            Open-Meteo ERA5 archive   daily, one point per region              -> raw/icecover/era5_<region>.json
Large raw files stay in runtime (raw/icecover/); the compact products land in data/icecover/.

Outputs (data/icecover/):
  superior_daily.json       per-region daily ice/SST/weather + lake-wide series + historical envelope
  superior_regions.json     region definitions (anchor, centroid, cell count, area share)
  superior_ice_atlas.png    ice concentration map frames (uint8 percent, 255 = land), 2x block mean
  superior_sst_atlas.png    SST map frames (uint8 = deg C x 10, 255 = land/no data)
  superior_grid_meta.json   frame layout, extent, dates

Regions: every lake cell goes to the nearest of eight anchor points (equal-area-ish metric). Anchors are
named for the places listeners will know; the map (data/icecover/check_regions.png) shows the result.

Run: .venv/bin/python scripts/fetch_icecover.py [--refetch]   (raw downloads: $SONIFICATION_RAW/icecover, default rendered/raw/icecover)
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.io import netcdf_file

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("SONIFICATION_RAW", Path(__file__).resolve().parent.parent / "rendered" / "raw")) / "icecover"
OUT = ROOT / "data" / "icecover"
OUT.mkdir(parents=True, exist_ok=True)
START, END = dt.date(2025, 11, 1), dt.date(2026, 6, 15)

# name, short id, (lon, lat) anchor; ordering here is the voice order everywhere (south-west to north-east)
REGIONS = [
    ("Western Arm", "west", (-91.3, 46.95)),
    ("North Shore", "nshore", (-90.0, 47.6)),
    ("Keweenaw and south shore", "keweenaw", (-88.3, 47.05)),
    ("Isle Royale", "royale", (-88.6, 47.95)),
    ("Thunder Bay and Nipigon", "thunder", (-88.9, 48.6)),
    ("Central basin", "central", (-87.3, 47.6)),
    ("Northeast (Pukaskwa)", "northeast", (-86.5, 48.6)),
    ("Whitefish Bay and Sault", "whitefish", (-85.2, 46.8)),
]


def read_nc(path, var):
    f = netcdf_file(str(path), mmap=False)
    a = np.array(f.variables[var][:], dtype="f4")
    a[a < -1000] = np.nan
    t = np.array(f.variables["time"][:])
    lat = np.array(f.variables["latitude"][:])
    lon = np.array(f.variables["longitude"][:])
    f.close()
    days = [dt.date(1970, 1, 1) + dt.timedelta(seconds=float(x)) for x in t]
    return a, days, lat, lon


def assign_regions(lat, lon, water):
    kx = np.cos(np.radians(47.5))
    LON, LAT = np.meshgrid(lon, lat)
    d = np.stack([((LON - a[0]) * kx) ** 2 + (LAT - a[1]) ** 2 for _, _, a in REGIONS])
    lab = d.argmin(0)
    lab[~water] = -1
    return lab


def block2(a, fn):
    """2x2 block reduction over the last two axes, NaN-aware; north up (lat descending)."""
    h, w = a.shape[-2] // 2 * 2, a.shape[-1] // 2 * 2
    a = a[..., :h, :w]
    b = a.reshape(*a.shape[:-2], h // 2, 2, w // 2, 2)
    with np.errstate(all="ignore"):
        r = fn(b, axis=(-3, -1))
    return r[..., ::-1, :]


def atlas(frames, path, cols=16):
    n, h, w = frames.shape
    rows = -(-n // cols)
    img = np.full((rows * h, cols * w), 255, np.uint8)
    for i in range(n):
        r, c = divmod(i, cols)
        img[r * h:(r + 1) * h, c * w:(c + 1) * w] = frames[i]
    Image.fromarray(img, "L").save(path, optimize=True)
    return {"cols": cols, "rows": rows, "fw": w, "fh": h}


def hist_envelope(season_days):
    """Lake-wide Superior ice (%) from GLERL .dat files, aligned to day-of-season (day 0 = 1 Nov)."""
    seasons = {}
    for p in sorted(RAW.glob("hist/g*_ice.dat")) + [RAW / "g2025_2026_ice.dat"]:
        y0 = int(p.name[1:5])
        ser = {}
        for ln in open(p):
            q = ln.split()
            if len(q) >= 3 and q[0].isdigit() and q[1].isdigit():
                d = dt.date(int(q[0]), 1, 1) + dt.timedelta(days=int(q[1]) - 1)
                k = (d - dt.date(y0, 11, 1)).days
                if 0 <= k < season_days:
                    ser[k] = float(q[2])
        seasons[y0] = ser
    cur = seasons.pop(2025)
    prior = sorted(seasons)
    M = np.full((len(prior), season_days), np.nan)
    for i, y in enumerate(prior):
        for k, v in seasons[y].items():
            M[i, k] = v
    # ice-free days before the record starts (late Nov) are missing in some files; treat as 0 before first row
    for i in range(len(prior)):
        first = np.where(np.isfinite(M[i]))[0]
        if len(first) and first[0] > 0:
            M[i, :first[0]] = 0.0
    with np.errstate(all="ignore"):
        env = {q: np.nanpercentile(M, p, axis=0) for q, p in [("min", 0), ("p25", 25), ("med", 50), ("p75", 75), ("max", 100)]}
    peaks = {f"{y}/{str(y + 1)[2:]}": round(float(np.nanmax(M[i])), 1) for i, y in enumerate(prior)}
    return env, cur, peaks


def era5(anchor, key, refetch):
    p = RAW / f"era5_{key}.json"
    if p.exists() and not refetch:
        return json.loads(p.read_text())
    q = dict(latitude=anchor[1], longitude=anchor[0], start_date=START.isoformat(), end_date=END.isoformat(),
             models="era5", wind_speed_unit="ms", timezone="America/Toronto",
             daily="temperature_2m_mean,temperature_2m_min,temperature_2m_max,wind_speed_10m_max,wind_direction_10m_dominant,"
                   "precipitation_sum,snowfall_sum,shortwave_radiation_sum,cloud_cover_mean")
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(q)
    with urllib.request.urlopen(url, timeout=60) as r:
        js = json.load(r)
    p.write_text(json.dumps(js))
    return js


def main():
    refetch = "--refetch" in sys.argv
    ice, days, lat, lon = read_nc(RAW / "sup_ice_wy2526.nc", "ice_concentration")
    sst, sdays, slat, slon = read_nc(RAW / "sup_sst_wy2526.nc", "sst")
    assert days == sdays and np.allclose(lat, slat) and np.allclose(lon, slon), "ice and SST grids differ"
    assert days[0] == START and days[-1] == END and len(days) == (END - START).days + 1
    nd = len(days)
    water = np.isfinite(ice).any(0)
    lab = assign_regions(lat, lon, water)
    # lake-wide mean: area-weight is uniform in lat/lon degrees to first order; GLERL uses cell means, so does this
    lake = np.nanmean(ice.reshape(nd, -1), axis=1)

    regs, per = [], {}
    LON, LAT = np.meshgrid(lon, lat)
    for i, (name, key, anchor) in enumerate(REGIONS):
        m = lab == i
        n = int(m.sum())
        ri = np.nanmean(ice[:, m], axis=1)
        rs = np.nanmean(sst[:, m], axis=1)
        wx = era5(anchor, key, refetch)["daily"]
        assert len(wx["time"]) == nd, (key, len(wx["time"]), nd)
        cx, cy = float(LON[m].mean()), float(LAT[m].mean())
        regs.append({"id": key, "name": name, "anchor": list(anchor), "centroid": [round(cx, 3), round(cy, 3)],
                     "cells": n, "share": round(n / int(water.sum()), 4)})
        f = lambda v, r=2: [None if x is None else round(float(x), r) for x in v]
        per[key] = {"ice": f(ri, 1), "sst": f(rs, 2),
                    "tmean": f(wx["temperature_2m_mean"], 1), "tmin": f(wx["temperature_2m_min"], 1), "tmax": f(wx["temperature_2m_max"], 1),
                    "wind": f(wx["wind_speed_10m_max"], 1), "wdir": f(wx["wind_direction_10m_dominant"], 0),
                    "precip": f(wx["precipitation_sum"], 1), "snow": f(wx["snowfall_sum"], 1),
                    "sw": f(wx["shortwave_radiation_sum"], 2), "cloud": f(wx["cloud_cover_mean"], 0)}

    env, cur, peaks = hist_envelope(nd)
    val = [(lake[k], cur[k]) for k in range(nd) if k in cur]
    d = np.array([a - b for a, b in val])
    print(f"lake-wide mean vs GLERL .dat: n={len(val)} RMSE={np.sqrt((d ** 2).mean()):.3f} max|diff|={np.abs(d).max():.3f}")

    daily = {
        "start": START.isoformat(), "end": END.isoformat(), "n": nd,
        "dates": [x.isoformat() for x in days],
        "lake_ice": [round(float(x), 2) for x in lake],
        "lake_sst": [round(float(x), 2) for x in np.nanmean(sst.reshape(nd, -1), axis=1)],
        "hist": {k: [None if not np.isfinite(x) else round(float(x), 2) for x in v] for k, v in env.items()},
        "hist_seasons": "2008/09 to 2024/25 (17 winters)",
        "hist_peaks": peaks,
        "cur_peak": round(float(np.nanmax(lake)), 1), "cur_peak_day": days[int(np.nanargmax(lake))].isoformat(),
        "regions": per,
        "source": {
            "ice": "NOAA GLERL / CoastWatch Great Lakes Node ERDDAP GL_Ice_Concentration_GCS (GLSEA + NIC analysis), daily, percent",
            "sst": "NOAA GLERL / CoastWatch Great Lakes Node ERDDAP GLSEA_ACSPO_GCS (ACSPO GLSEA), daily, degC",
            "lakewide": "NOAA GLERL lake-average ice concentration, g<year>_<year+1>_ice.dat",
            "weather": "ERA5 reanalysis (Copernicus / ECMWF) via Open-Meteo archive API, one point per region",
        },
    }
    (OUT / "superior_daily.json").write_text(json.dumps(daily, separators=(",", ":")))
    (OUT / "superior_regions.json").write_text(json.dumps(regs, indent=1))

    ice2 = block2(ice, np.nanmean)
    sst2 = block2(sst, np.nanmean)
    fr_ice = np.where(np.isfinite(ice2), np.clip(np.rint(ice2), 0, 100), 255).astype(np.uint8)
    fr_sst = np.where(np.isfinite(sst2), np.clip(np.rint(sst2 * 10), 0, 250), 255).astype(np.uint8)
    lay = atlas(fr_ice, OUT / "superior_ice_atlas.png")
    atlas(fr_sst, OUT / "superior_sst_atlas.png")
    h, w = fr_ice.shape[1:]
    la, lo = lat[:h * 2].reshape(h, 2).mean(1)[::-1], lon[:w * 2].reshape(w, 2).mean(1)
    lab2 = assign_regions(la, lo, np.isfinite(ice2).any(0))
    meta = {**lay, "extent": {"lat": [float(la.min()), float(la.max())], "lon": [float(lo.min()), float(lo.max())]},
            "ice_units": "percent; 255 = land", "sst_units": "degC x 10; 255 = land",
            "region_mask": lab2.tolist()}
    (OUT / "superior_grid_meta.json").write_text(json.dumps(meta, separators=(",", ":")))

    for r in regs:
        s = per[r["id"]]["ice"]
        on = next((days[k] for k in range(nd) if s[k] >= 10), None)
        off = next((days[k] for k in range(nd - 1, -1, -1) if s[k] >= 10), None)
        print(f"{r['name']:28s} cells={r['cells']:5d} peak={max(s):5.1f}% first>=10%: {on}  last>=10%: {off}")
    print(f"lake peak {daily['cur_peak']}% on {daily['cur_peak_day']}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(14, 4.5))
        show = np.where(lab >= 0, lab, np.nan)
        ax[0].imshow(show[::-1], cmap="tab10", extent=[lon.min(), lon.max(), lat.min(), lat.max()], aspect=1 / np.cos(np.radians(47.5)))
        for r in regs:
            ax[0].text(*r["centroid"], r["id"], ha="center", fontsize=8)
        pk = int(np.nanargmax(lake))
        ax[1].imshow(ice[pk][::-1], cmap="Blues", vmin=0, vmax=100, extent=[lon.min(), lon.max(), lat.min(), lat.max()], aspect=1 / np.cos(np.radians(47.5)))
        ax[1].set_title(f"ice {days[pk]}")
        fig.savefig(OUT / "check_regions.png", dpi=90, bbox_inches="tight")
    except Exception as e:  # plotting is a check, not a product
        print("check plot skipped:", e)


if __name__ == "__main__":
    main()
