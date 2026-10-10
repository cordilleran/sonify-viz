"""
ARCTIC ROUND, shared data loader: the daily extent record and the monthly series built by fetch_arctic.py (data/arctic/arctic_daily.json),
the ice-year calendar, and the monthly-to-daily interpolation. Used by arctic_bside.py (The Wheel), export_bside_viz.py and the main piece's engine.
"""
import datetime as dt
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "arctic" / "arctic_daily.json"


def load():
    d = json.loads(DATA.read_text())
    first = dt.date.fromisoformat(d["dates"][0])
    n = len(d["dates"])
    D = {"first": first, "n": n, "total": np.array(d["total"]), "obs": np.array(d["observed"]),
         "reg": {k: np.array(v["extent"]) for k, v in d["regions"].items()}}
    # monthly series to month-index dicts with the end of the record extended by last year + trend (flagged)
    D["piomas"] = {k: v for k, v in d["piomas_1000km3"].items()}
    D["co2"] = dict(d["co2_brw_ppm"])
    D["sst"] = dict(d["sst_global_anom_c"])
    D["gis"] = {int(k): v for k, v in d["gistemp"].items()}
    return D


def month_curve(series, y0, y1, extend_per_year=0.0):
    """-> function(date) giving a monthly series interpolated linearly between month midpoints. Months after the last one
    repeat the same month of the year before plus `extend_per_year` (labelled extension, used only for 2026)."""
    keys = sorted(series)
    ly, lm = int(keys[-1][:4]), int(keys[-1][5:])
    ser = dict(series)
    for y in range(int(keys[0][:4]), y1 + 2):
        for m in range(1, 13):
            k = f"{y}-{m:02d}"
            if k not in ser and (y, m) > (ly, lm) and f"{y - 1}-{m:02d}" in ser:
                ser[k] = ser[f"{y - 1}-{m:02d}"] + extend_per_year
    pts = sorted((dt.date(int(k[:4]), int(k[5:]), 15).toordinal(), v) for k, v in ser.items())
    xs, ys = np.array([p[0] for p in pts], float), np.array([p[1] for p in pts], float)
    return lambda ords: np.interp(ords, xs, ys)


def bar_days(framing, label):
    if framing == "ice":
        a, b = dt.date(label - 1, 10, 1), dt.date(label, 9, 30)
    else:
        a, b = dt.date(label, 1, 1), dt.date(label, 12, 31)
    return [a + dt.timedelta(i) for i in range((b - a).days + 1)]
