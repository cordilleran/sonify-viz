"""Export the data behind the Climate Pair visualizer (climate/viz.js) to
climate/viz_{basin}.json: the spiral's monthly values, every storm at the time
its drum sounds, the listening-guide events, and each instrument's loudness.

Sunspots (CC BY-NC) and IAP ocean heat content (terms unconfirmed) are not
written as values: the page shows those two layers only through the loudness
of their instruments (shimmer, deep), which is derived from the audio.
usage: python export_climate_viz.py   (after climate_pair.py pacific|atlantic)"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dsp_core import ROOT, HEAVY_OUT, LIGHT_OUT
import records as R

J = R.climate_monthly()
J["volcanoes"] = R.volcanoes()
MONTHS = J["months"]
Y0 = int(MONTHS[0][:4])
ENV_HZ = 4                                     # loudness frames per second
STORMS = {"pacific": ["wpac", "nepac"], "atlantic": ["atl"]}


def r(a, nd):
    return [None if v is None else round(v, nd) for v in a]


def t_date(dt, bar):
    """Same placement as climate_pair.py: a year per bar, months evenly spaced."""
    frac = (dt.timetuple().tm_yday - 1) / (366 if dt.year % 4 == 0 else 365) * 12
    return (dt.year - Y0) * bar + frac * bar / 12


def envelope(path):
    """Loudness at ENV_HZ as 0-100 (-60 to 0 dBFS), from a stem of the render."""
    x, sr = sf.read(path)
    m = (x ** 2).mean(axis=1)
    w = sr // ENV_HZ
    db = 10 * np.log10(m[: len(m) // w * w].reshape(-1, w).mean(axis=1) + 1e-12)
    return np.clip(np.round((db + 60) / 60 * 100), 0, 100).astype(int).tolist()


for basin in ("pacific", "atlantic"):
    name = f"climate_{basin}_1958_2025"
    sc = json.loads((LIGHT_OUT / "climate" / f"{name}_score.json").read_text())
    bar = sc["bar_seconds"]
    ny = sc["years"][1] - sc["years"][0] + 1
    storms = []
    for b in STORMS[basin]:
        for s in R.storms(b):
            dt = datetime.fromisoformat(s["peak_time"])
            if Y0 <= dt.year < Y0 + ny:
                # [seconds, category 0-5, basin index, landfall, name, peak kt]
                storms.append([round(t_date(dt, bar), 2), s["category"], STORMS[basin].index(b),
                               int(bool(s["landfall"])), s["name"], s["peak_kt"]])
    storms.sort()
    ser = J["series"]
    mode_key = "pdo" if basin == "pacific" else "amo"
    out = {
        "basin": basin, "key": sc["key"], "y0": Y0, "years": ny, "bar": bar, "duration": sc["duration_s"],
        "storm_basins": STORMS[basin],
        "monthly": {"sst": r(ser["sst_global_anom"], 2), "oni": r(ser["oni"], 2),
                    "co2": r(ser["co2_deseason_ppm"], 1), "mode_index": r(ser[mode_key], 2),
                    "gistemp": r(ser["gistemp_anom"], 2)},  # public (NASA); sunspots and ocean heat stay out
        "yearly": [{k: y[k] for k in ("year", "mode", "co2_ppm", "sst_anom", "ace")} for y in sc["years_detail"]],
        "storms": storms,
        "events": sc["events"],
        "volcanoes": [{"t": round(t_date(datetime.fromisoformat(v["date"]), bar), 2), "name": v["name"]}
                      for v in J["volcanoes"]],
        "env_hz": ENV_HZ,
        "env": {p.stem: envelope(p) for p in sorted((HEAVY_OUT / "climate" / f"{name}_stems").glob("*.flac"))},
    }
    if basin == "atlantic":
        out["monthly"]["ice"] = r(ser["seaice_extent_mkm2"], 2)
        out["monthly"]["nao"] = r(ser["nao"], 2)
    else:
        kt = R.kettle_annual_peak()
        vals = [v["max_daily_m3s"] for k, v in kt.items() if Y0 <= int(k) < Y0 + ny]
        out["kettle"] = [{"t": round(t_date(datetime.fromisoformat(v["date"]), bar), 2),
                          "q": round(v["max_daily_m3s"]), "rank": round(float(np.mean(np.array(vals) < v["max_daily_m3s"])), 2)}
                         for k, v in sorted(kt.items()) if Y0 <= int(k) < Y0 + ny]
    dest = ROOT / "climate" / f"viz_{basin}.json"
    dest.write_text(json.dumps(out, separators=(",", ":")))
    print(dest.name, f"{dest.stat().st_size / 1024:.0f} KB", len(storms), "storms", list(out["env"]))
