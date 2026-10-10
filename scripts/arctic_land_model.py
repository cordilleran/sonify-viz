"""ARCTIC ROUND land layer, step 2 (model): a degree-day snowpack and a growing-degree greenness from ERA5 daily air temperature and snowfall.
Label M (modelled, coarse, about 650 km between points). Not a satellite product and not a measurement of vegetation.

Per land point, one day at a time:
  snow   S += snowfall (cm of snow = mm of water equivalent, a 100 kg/m3 pack); melt = min(S, DDF * max(T, 0)); S -= melt        DDF = 3 mm per degree-day
  green  with snow on the ground (S > 2 mm) greenness falls 10 % a day and growing degrees reset; with bare ground it follows
         min(1, growing degrees / 250) where growing degrees add max(T - 3, 0) a day; below 0 C it falls 5 % a day
  glint  melt over snow, clipped at 12 mm a day, is the meltwater shine; it is zero when there is no melt
The constants are textbook round numbers (degree-day factor 2 to 5 mm; tundra reaches full canopy near 250 degree-days above 3 C), not fitted, and the seasons they give are not validated against observations. Output stores every 4th day: snow (0..255 for 0..300 mm), greenness (0..255), glint (the maximum in the 4-day window, 0..255).
Run: python scripts/arctic_land_model.py
"""
import base64
import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("SONIFICATION_RAW", ROOT / "rendered" / "raw")) / "arctic" / "land"
PARAMS = {"ddf_mm_per_degC_day": 3.0, "snow_cover_mm": 2.0, "gdd_base_c": 3.0, "gdd_full": 250.0, "green_decay_snow": 0.90, "green_decay_cold": 0.95,
          "glint_cap_mm": 12.0, "snow_cm_to_mm_we": 1.0, "step_days": 4}


def model(T, snow_cm, P=PARAMS):
    n = len(T)
    S = G = gdd = 0.0
    swe, green, melt_o = np.zeros(n), np.zeros(n), np.zeros(n)
    for i in range(n):
        t = T[i] if np.isfinite(T[i]) else 0.0
        S += (snow_cm[i] if np.isfinite(snow_cm[i]) else 0.0) * P["snow_cm_to_mm_we"]
        melt = min(S, P["ddf_mm_per_degC_day"] * max(t, 0.0))
        S -= melt
        if S > P["snow_cover_mm"]:
            G *= P["green_decay_snow"]
            gdd = 0.0
        else:
            gdd += max(t - P["gdd_base_c"], 0.0)
            G = min(1.0, gdd / P["gdd_full"]) if t >= 0 else G * P["green_decay_cold"]
        swe[i], green[i], melt_o[i] = S, G, melt if S > 0 or melt > 0 else 0.0
    return swe, green, melt_o


def q(a, hi):
    return base64.b64encode(np.clip(a / hi * 255, 0, 255).astype(np.uint8).tobytes()).decode()


def main():
    pts = json.loads((RAW.parent / "land_points.json").read_text())
    step = PARAMS["step_days"]
    out, time_axis = [], None
    for c, r, lon, lat, _elev in pts:
        f = RAW / f"{c}_{r}.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text())["daily"]
        if time_axis is not None and len(d["time"]) != len(time_axis):
            print("skipped", f.name, "(a different length: the fetch may have stopped part-way)")
            continue
        time_axis = d["time"]
        T, sn = np.array(d["temperature_2m_mean"], float), np.array(d["snowfall_sum"], float)
        swe, green, melt = model(T, sn)
        m = len(T) // step * step
        out.append({"col": c, "row": r, "lon": lon, "lat": lat, "snow": q(swe[:m:step], 300), "green": q(green[:m:step], 1.0),
                    "glint": q(melt[:m].reshape(-1, step).max(axis=1) if m else melt, PARAMS["glint_cap_mm"])})
    if not out:
        raise SystemExit("no point files found: run fetch_arctic_land.py first")
    n = len(time_axis)   # days; every point file covers the same dates
    (ROOT / "data" / "arctic" / "arctic_land.json").write_text(json.dumps({
        "start": "1978-10-01", "end": time_axis[-1], "step_days": step, "n_steps": n // step, "params": PARAMS, "points": out,
        "label": "M: degree-day snowpack and growing-degree greenness from ERA5 2 m air temperature and snowfall; coarse, about 650 km between points",
        "source": "ERA5 (Copernicus Climate Change Service, Hersbach et al. 2020) through the Open-Meteo Historical Weather API (CC BY 4.0, non-commercial)"},
        separators=(",", ":")))
    print(len(out), "points of", len(pts), "modelled;", n, "days")


if __name__ == "__main__":
    main()
