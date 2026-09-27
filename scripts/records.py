"""
Record loaders: cached pulls (data/*.json) -> date->value dicts -> daily
arrays for one Year. Split out of seasonal.py on 2026-09-27.

Every function that returns a daily array takes `year` (a timegrid.Year) and
defaults to WY2024, the year every piece before 2026-09-27 was built on.

Since 2026-09-27 the loaders read the tidy parquet tables in data/parquet/
(built by build_parquet.py and described by data/parquet/data-dict.yaml).
A station that isn't in the tables yet (fetched since the last build) is
read from its raw JSON pull instead, so fetch_records.py keeps working.
"""
import csv, io, json, re, datetime as dt
from functools import lru_cache
from pathlib import Path

import numpy as np

from timegrid import WY2024

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
PARQUET = DATA / "parquet"


@lru_cache(maxsize=None)
def _rows(table, station):
    """One station's rows from a parquet table, in stored order, as dicts (None if absent)."""
    p = PARQUET / f"{table}.parquet"
    if not p.exists():
        return None
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    t = pq.read_table(p)
    t = t.filter(pc.equal(t["station_id"], station))
    return t.to_pylist() if t.num_rows else None


@lru_cache(maxsize=None)
def _load(fname):
    """Parse a cached pull once per run (the climate file is read for four variables)."""
    with open(DATA / fname) as fh:
        return json.load(fh)


def wsc_series(fname, key="DISCHARGE"):
    """dict date->value (and date->symbol) for a WSC station, named by its pull's
    file name (e.g. granby_08NN002_2010_2024.json)."""
    out, sym = {}, {}
    m = re.search(r"_(\d\d[A-Z]{2}\d{3})_", fname)
    rows = _rows("hydrometric_daily", m.group(1)) if m else None
    if rows is not None:
        col = key.lower()
        for r in rows:
            d = str(r["date"])
            if r[col] is not None:
                out[d] = float(r[col])
            sym[d] = r[col + "_symbol"]
        return out, sym
    for f in _load(fname):
        p = f["properties"]
        if p.get(key) is not None:
            out[p["DATE"][:10]] = float(p[key])
        sym[p["DATE"][:10]] = p.get(key + "_SYMBOL_EN")
    return out, sym


def climate_series(fname, key):
    """dict date->value of one daily climate variable (e.g. "MEAN_TEMPERATURE"),
    for a station named by its pull's file name (billings_1100_climate_2010_2024.json)."""
    out = {}
    m = re.search(r"_(\d+)_climate_", fname)
    rows = _rows("climate_daily", m.group(1)) if m else None
    if rows is not None and key.lower() in rows[0]:
        for r in rows:
            if r[key.lower()] is not None:
                out[str(r["date"])] = float(r[key.lower()])
        return out
    for f in _load(fname):
        p = f["properties"]
        if p.get(key) is not None:
            out[p["LOCAL_DATE"][:10]] = float(p[key])
    return out


def in_year(series, fill="interp", year=WY2024):
    """Pull `year`'s days out of a date->value dict as an array. Gaps are
    interpolated (or zero-filled with fill='zero'; left NaN with fill=None)."""
    x = np.array([series.get(str(d), np.nan) for d in year.days], dtype=float)
    if fill == "interp" and np.isnan(x).any():
        ok = ~np.isnan(x)
        if ok.sum() == 0:
            return np.zeros(year.n_days)
        x = np.interp(np.arange(year.n_days), np.flatnonzero(ok), x[ok])
    elif fill == "zero":
        x = np.nan_to_num(x)
    return x


def coverage(series, year=WY2024):
    """Fraction of `year`'s days with a value: check before rendering a new year."""
    return float(np.mean([str(d) in series for d in year.days]))


def doy_percentile(series, halfwin=7, year=WY2024):
    """For each day of `year`: where does its value sit among ALL years'
    values within +-halfwin days of the same calendar day? 0..1. This is the
    'is it normal for the time of year' signal - the anomaly, not the level."""
    by_doy = {}
    for k, v in series.items():
        d = dt.date.fromisoformat(k)
        by_doy.setdefault(d.timetuple().tm_yday, []).append(v)
    out = np.full(year.n_days, 0.5)
    for i, d in enumerate(year.days):
        v = series.get(str(d))
        if v is None:
            continue
        doy = d.timetuple().tm_yday
        pool = []
        for o in range(-halfwin, halfwin + 1):
            pool += by_doy.get((doy - 1 + o) % 366 + 1, [])
        pool = np.array(pool)
        out[i] = (pool < v).mean() + 0.5 * (pool == v).mean()
    return out


def modis_gpp_daily(name, year=WY2024):
    """MODIS MOD17A2HGF 8-day GPP at a point -> daily array for `year`, plus a
    0..1 version scaled by the 2015-2024 95th percentile.
    Returns (None, None) if the pull isn't cached (caller falls back to a
    growing-degree-day model and says so)."""
    rows = None
    tbl = _rows("modis_gpp", name)
    if tbl is not None:  # regroup the tidy rows into composites, pixels in stored order
        by = {}
        for r in tbl:
            by.setdefault(str(r["date"]), []).append(r["gpp_raw"])
        rows = [{"date": d, "data": v} for d, v in by.items()]
    else:
        p = DATA / f"modis_gpp_{name}_2015_2024.json"
        if not p.exists():
            return None, None
        with open(p) as fh:
            rows = json.load(fh)["rows"]
    dates, vals = [], []
    for r in rows:
        v = [x for x in r["data"] if x < 32761]
        if v:
            dates.append(dt.date.fromisoformat(r["date"]) + dt.timedelta(4))  # composite centre
            vals.append(np.mean(v) * 0.0001 / 8 * 1000)  # g C m-2 day-1
    if dates[0] > year.start + dt.timedelta(8) or dates[-1] < year.days[-1] - dt.timedelta(8):
        return None, None  # the cache doesn't cover this year: don't extrapolate a flat season
    t = np.array([(d - year.start).days for d in dates])
    v = np.array(vals)
    daily = np.interp(np.arange(year.n_days), t, v)
    return daily, np.clip(daily / np.percentile(v, 95), 0, 1)


def growing_degree_days(tmean, base=5.0):
    return np.cumsum(np.maximum(0, tmean - base))


def dart_sockeye(year=WY2024):
    """Wells Dam daily adult sockeye + Wells water temperature (C) for `year`.
    Counting season is May-Nov; off-season days = 0 / NaN."""
    raw = _load("wells_dam_sockeye_2015_2024.json")
    cnt, temp = {}, {}
    for y in range(year.start.year, year.days[-1].year + 1):
        if str(y) not in raw:  # a silent zero would play as "no fish came"
            raise ValueError(f"no Wells Dam counts cached for {y} ({year.label})")
        for r in csv.DictReader(io.StringIO(raw[str(y)])):
            d = r.get("Date") or ""
            if not d.startswith(str(y)):
                continue
            cnt[d] = max(0.0, float(r["Sock"] or 0))
            if r["TempC"] and float(r["TempC"]) != 0.0:  # 0.0 is a missing code (2015-07-23): no 0 °C Columbia in season
                temp[d] = float(r["TempC"])
    return in_year(cnt, fill="zero", year=year), np.array([temp.get(str(d), np.nan) for d in year.days])


def dart_run_totals(year=WY2024):
    """Adult sockeye counted at Wells Dam in each calendar year `year` touches."""
    raw = _load("wells_dam_sockeye_2015_2024.json")
    out = {}
    for y in range(year.start.year, year.days[-1].year + 1):
        if str(y) not in raw:
            raise ValueError(f"no Wells Dam counts cached for {y} ({year.label})")
        out[y] = sum(max(0.0, float(r["Sock"] or 0)) for r in csv.DictReader(io.StringIO(raw[str(y)]))
                     if (r.get("Date") or "").startswith(str(y)))
    return out


def check_coverage(named_series, year, need=0.9):
    """Refuse to render a year the records don't cover: {name: series} -> ValueError
    listing every series below `need`, so a gap is never heard as a quiet year."""
    short = {k: coverage(v, year) for k, v in named_series.items()}
    short = {k: c for k, c in short.items() if c < need}
    if short:
        raise ValueError(f"{year.label}: records too thin to render: "
                         + ", ".join(f"{k} {c:.0%}" for k, c in short.items()))


# ---------------------------------------------------------- Climate Pair ---
CLIMATE = DATA / "climate"


def _climate_table(name):
    """A Climate Pair parquet table as {column: list}, or None if it hasn't been built."""
    p = CLIMATE / "parquet" / f"{name}.parquet"
    if not p.exists():
        return None
    import pyarrow.parquet as pq
    return pq.read_table(p).to_pydict()


def climate_monthly(name="indices_monthly"):
    """{'months': ['1958-01', ...], 'series': {name: [value or None]}} from the parquet table
    (or the parsed JSON it was built from). 'fetched_only_monthly' is the local-only file."""
    t = _climate_table(name)
    if t is None:
        return json.loads((CLIMATE / f"{name}.json").read_text())
    months = [f"{d:%Y-%m}" for d in t.pop("month")]
    return {"months": months, "series": t}


def volcanoes():
    t = _climate_table("volcanoes")
    if t is None:
        return json.loads((CLIMATE / "indices_monthly.json").read_text())["volcanoes"]
    return [{"date": str(d), "name": n, "vei": v, "cooling": c, **({"note": x} if x else {})}
            for d, n, v, c, x in zip(t["date"], t["name"], t["vei"], t["cooling"], t["note"])]


def storms(basin):
    """One basin's tropical cyclones (atl, nepac, wpac), in stored order."""
    t = _climate_table("storms")
    if t is None:
        return json.loads((CLIMATE / f"storms_{basin}.json").read_text())
    keys = [k for k in t if k != "basin"]
    return [{k: (t[k][i].isoformat() if k == "peak_time" else t[k][i]) for k in keys}
            for i, b in enumerate(t["basin"]) if b == basin]


def kettle_annual_peak():
    """{'1929': {'max_daily_m3s': ..., 'date': 'YYYY-MM-DD'}, ...}"""
    t = _climate_table("kettle_annual_peak")
    if t is None:
        return json.loads((CLIMATE / "kettle_annual_max.json").read_text())
    return {str(y): {"max_daily_m3s": q, "date": str(d)} for y, q, d in zip(t["year"], t["max_daily_m3s"], t["date"])}
