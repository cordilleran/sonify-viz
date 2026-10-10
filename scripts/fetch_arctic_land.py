"""ARCTIC ROUND land layer, step 1 (fetch): ERA5 daily air temperature and snowfall at a coarse set of land points (picture, M2).

Source: Open-Meteo Historical Weather API (ERA5 reanalysis, Copernicus Climate Change Service; Open-Meteo data are CC BY 4.0, free for non-commercial use; attribute both).
Why a model and not a satellite product: NDVI starts in 1982 (GIMMS) or 2000 (MODIS) and needs a login; the ice record starts in 1978 and the
picture needs every day of it. The next script (arctic_land_model.py) turns these two series into a degree-day snowpack and a growing-degree
greenness. Label: M. Coarse by design: about 650 km between points, so it paints a wash over the land and does not claim local detail.
Points: land cells (GEBCO height > 0) on a lattice of 26 NSIDC cells inside the picture's 3000 km radius.
Quota: one 48-year, two-variable call weighs about 250 of Open-Meteo's 10,000 daily call units, so the script stops after 38 new points (`--max`). There are 29 points, so one run
is enough on a fresh quota; a rerun fetches only the points still missing.
Run: python scripts/fetch_arctic_land.py [--max 38]   Raw: $SONIFICATION_RAW/arctic/land/<col>_<row>.json
"""
import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("SONIFICATION_RAW", ROOT / "rendered" / "raw")) / "arctic" / "land"
RAW.mkdir(parents=True, exist_ok=True)
META = json.loads((ROOT / "data" / "arctic" / "terrain_meta.json").read_text())
R, K0 = 6378137.0, (1 + math.sin(math.radians(70))) / 2
STEP = 26


def lonlat(col, row):
    X, Y = META["x0"] + col * META["cell_m"], META["y0"] - row * META["cell_m"]
    rho = math.hypot(X, Y)
    return -45 + math.degrees(math.atan2(X, -Y)), 90 - math.degrees(2 * math.atan(rho / (2 * R * K0)))


def points():
    img = np.array(Image.open(ROOT / "data" / "arctic" / "terrain_3411.png"))
    k = META["oversample"]
    out = []
    for r in range(8, META["rows"], STEP):
        for c in range(8, META["cols"], STEP):
            if math.hypot(c - 154, r - 234) > 118:
                continue
            if img[int(r * k), int(c * k), 2] > 0:       # land (B channel > 0)
                lon, lat = lonlat(c, r)
                if lat > 52:
                    lon = (lon + 180) % 360 - 180          # the API wants -180..180
                out.append((c, r, round(lon, 3), round(lat, 3), int(img[int(r * k), int(c * k), 2])))
    return out


def main():
    mx = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 38
    pts = points()
    print(len(pts), "land points", flush=True)
    json.dump(pts, open(RAW.parent / "land_points.json", "w"))
    done = 0
    for c, r, lon, lat, _ in pts:
        f = RAW / f"{c}_{r}.json"
        if f.exists():
            continue
        if done >= mx:
            print("stopped at --max; run again for the rest (the next day if the quota is spent)"); break
        url = (f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date=1978-10-01&end_date=2026-10-06"
               "&daily=temperature_2m_mean,snowfall_sum&timezone=UTC")
        ok = False
        for attempt in range(3):
            try:
                f.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "sonification-workbench"}), timeout=200).read())
                ok = True
                break
            except Exception as e:
                print("retry", c, r, e, flush=True); time.sleep(20 * (attempt + 1))
        if not ok:
            print("FAILED", c, r, lon, lat, flush=True)
            continue
        done += 1
        print("got", c, r, lon, lat, flush=True)
        time.sleep(2)


if __name__ == "__main__":
    main()
