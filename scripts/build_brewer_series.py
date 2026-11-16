#!/usr/bin/env python3
"""Build the Sound Channel Brewer's series pack (deck/app/picker/series.json) from data already public on sonify-viz.

Spec: deck/261116-brewer-data-feed-spec.md (Slice A, M2). Every value comes from a file in the public repo's data/
folder; nothing is typed by hand. Each series keeps its source and licence line, one canonical period, its kind
(which picks the page's default transform), named bookmarks for Slice mode, and the synthetic model nearest to it
(the "twin"). Series are grouped by timescale (GW 11-16: packs for days to weeks, a year, decades, a century; a
"future" pack waits for a source whose licence allows it).

M1 (11-16): Wells Dam sockeye is dropped (the site plays it but does not republish it, methods.qmd); its alternative, a
zero-heavy pulse, is Northeast Pacific hurricane energy by month (HURDAT2, already public). Kelowna climate (ECCC 48369) is
not in the public repo, so the climate pair uses Summerland CS (ECCC 979), which is.

Usage: python3 -I scripts/build_brewer_series.py [--repo <folder holding data/>] [--check]
The data files read are the ones already published in the repository's data/ folder.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent  # the workbench or the public repository: both keep the data in data/


def out_for(root: pathlib.Path) -> pathlib.Path:
    """The workbench writes into the picker's source; the public repository into the built tool folder."""
    src = root / "deck" / "app" / "picker"
    return src / "series.json" if src.is_dir() else root / "sound-channel-brewer" / "series.json"
MAX_BYTES = 80_000
WY = ("2023-10-01", "2024-09-30")  # water year 2024, the Water Year Rings period

OGL = "Contains information licensed under the Open Government Licence – Canada"
SCALES = [
    {"id": "days", "label": "Days to weeks"},
    {"id": "season", "label": "A season, daily"},
    {"id": "year", "label": "A year, daily"},
    {"id": "decades", "label": "Decades, monthly"},
    {"id": "century", "label": "A century, yearly"},
]
KINDS = {"skewed", "slow", "signed", "spiky", "bounded", "trend", "seasonal", "peaks"}


def rnd(x, dec):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), dec)


def days(a: str, b: str):
    d0, d1 = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    return [(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def runs(flags):
    """Index ranges [i0, i1] (inclusive) where flags are true."""
    out, i0 = [], None
    for i, f in enumerate(flags + [False]):
        if f and i0 is None:
            i0 = i
        if not f and i0 is not None:
            out.append([i0, i - 1]); i0 = None
    return out


def mark(values, rule, half=8):
    """A Slice start for a named bookmark: the window of 16 steps centred on the rule's day."""
    idx = [i for i, v in enumerate(values) if v is not None]
    if rule == "max":
        c = max(idx, key=lambda i: values[i])
    elif rule == "min":
        c = min(idx, key=lambda i: values[i])
    elif rule.startswith("first_above:"):
        t = float(rule.split(":")[1]); c = next(i for i in idx if values[i] > t); half = 2
    elif rule.startswith("at:"):
        c = int(rule.split(":")[1]); half = 0
    else:
        raise ValueError(rule)
    return max(0, min(len(values) - 16, c - half))


def series(**k):
    if k["kind"] not in KINDS:
        raise ValueError(f"unknown kind {k['kind']} for {k['id']}")
    k["n"] = len(k["values"])
    k["bookmarks"] = [{"label": lab, "start": mark(k["values"], rule)} for lab, rule in k.pop("marks", [])]
    return k


def hydro(repo, fname, field, dec):
    rows = json.loads((repo / "data" / fname).read_text(encoding="utf-8"))
    by = {r["properties"]["DATE"][:10]: r["properties"] for r in rows}
    ds = days(*WY)
    vals = [rnd(by.get(d, {}).get(field), dec) for d in ds]
    ice = [(by.get(d, {}).get(f"{field}_SYMBOL_EN") or "") == "Ice Conditions" for d in ds]
    return vals, ice


def climate_daily(repo, fname, field, dec):
    rows = json.loads((repo / "data" / fname).read_text(encoding="utf-8"))
    by = {r["properties"]["LOCAL_DATE"][:10]: r["properties"] for r in rows}
    return [rnd(by.get(d, {}).get(field), dec) for d in days(*WY)]


def build(repo: pathlib.Path) -> dict:
    out = []
    # --- A year, daily (water year 2024) ---
    q, ice = hydro(repo, "granby_08NN002_2010_2024.json", "DISCHARGE", 2)
    out.append(series(id="granby", title="Granby River discharge", short="Granby flow", place="Granby River at Grand Forks (08NN002)",
                      units="m³/s", kind="skewed", scale="year", step="day", start=WY[0], values=q, flags={"ice": runs(ice)},
                      twin="skewed", polarity="more flow sounds higher",
                      source="Water Survey of Canada, HYDAT daily discharge", licence=OGL,
                      marks=[("Freshet", "max"), ("Low flow", "min")]))
    lv, _ = hydro(repo, "okanagan_lake_kelowna_08NM083_2010_2024.json", "LEVEL", 3)
    out.append(series(id="okanagan-lake", title="Okanagan Lake level", short="Lake level", place="Okanagan Lake at Kelowna (08NM083)",
                      units="m", kind="slow", scale="year", step="day", start=WY[0], values=lv, twin="walk", polarity="higher lake sounds higher",
                      source="Water Survey of Canada, HYDAT daily level (gauge datum)", licence=OGL,
                      marks=[("Lake peak", "max"), ("Lake low", "min")]))
    t = climate_daily(repo, "summerland_cs_979_climate_2010_2024.json", "MEAN_TEMPERATURE", 1)
    out.append(series(id="summerland-temp", title="Summerland daily mean temperature", short="Summerland temp", place="Summerland CS (ECCC climate 979)",
                      units="°C", kind="signed", scale="year", step="day", start=WY[0], values=t, twin="seasonal", polarity="warmer sounds higher",
                      source="Environment and Climate Change Canada, daily climate data", licence=OGL,
                      marks=[("Cold snap", "min"), ("Heat", "max")]))
    p = climate_daily(repo, "summerland_cs_979_climate_2010_2024.json", "TOTAL_PRECIPITATION", 1)
    out.append(series(id="summerland-precip", title="Summerland daily precipitation", short="Summerland precip", place="Summerland CS (ECCC climate 979)",
                      units="mm", kind="spiky", scale="year", step="day", start=WY[0], values=p, twin="spikes", polarity="wetter sounds higher",
                      source="Environment and Climate Change Canada, daily climate data", licence=OGL,
                      marks=[("Wettest day", "max")]))
    # --- A season, daily: Lake Superior ice, winter 2025-26 (percent to fraction) ---
    si = json.loads((repo / "data/icecover/superior_daily.json").read_text(encoding="utf-8"))
    ice_f = [rnd(None if x is None else x / 100, 3) for x in si["lake_ice"]]
    out.append(series(id="superior-ice", title="Lake Superior ice cover", short="Superior ice", place="Lake Superior, whole lake",
                      units="fraction", kind="bounded", scale="season", step="day", start=si["start"], values=ice_f, twin="bimodal",
                      polarity="more ice sounds higher", source="NOAA GLERL / CoastWatch Great Lakes Node, GLSEA and NIC ice analysis",
                      licence="U.S. Government work (public domain)",
                      marks=[("Ice-on", "first_above:0.01"), ("Ice peak", "max")]))
    # --- Days to weeks: an AIFS forecast, 6-hourly ---
    mg = json.loads((repo / "data/meteogram/aifs_godbout_village_ecmwf_20261016.json").read_text(encoding="utf-8"))
    tt = mg["series"]["Temp."]
    out.append(series(id="godbout-temp", title="Godbout forecast temperature", short="Godbout forecast", place="Godbout, Quebec (forecast point)",
                      units="°C", kind="signed", scale="days", step="6h", start=tt[0][0][:13], values=[rnd(v, 1) for _, v in tt], twin="walk",
                      polarity="warmer sounds higher", source="© 2026 European Centre for Medium-Range Weather Forecasts (ECMWF), AIFS Single open data, run 2026-10-16 12z; 2 m temperature interpolated to the point and rounded to 0.1 °C",
                      licence="CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)",
                      marks=[("Coldest", "min"), ("Warmest", "max")]))
    # --- Decades, monthly: the climate indices on the Climate Pair page ---
    ci = json.loads((repo / "data/climate/indices_monthly.json").read_text(encoding="utf-8"))
    months = ci["months"]

    def monthly(key, dec):
        v = ci["series"][key]
        i0 = next(i for i, x in enumerate(v) if x is not None)
        i1 = max(i for i, x in enumerate(v) if x is not None)
        return months[i0], [rnd(x, dec) for x in v[i0:i1 + 1]]

    for sid, key, dec, title, short, units, kind, twin, pol, src, lic, marks in [
        ("oni", "oni", 2, "Oceanic Niño Index (ENSO)", "ONI", "°C anomaly", "signed", "walk", "El Niño sounds higher",
         "NOAA Climate Prediction Center, ONI", "U.S. Government work (public domain)", [("Biggest El Niño", "max"), ("Deepest La Niña", "min")]),
        ("pdo", "pdo", 2, "Pacific Decadal Oscillation", "PDO", "index", "signed", "walk", "warm phase sounds higher",
         "NOAA NCEI, ERSSTv5 PDO index", "U.S. Government work (public domain)", [("Warmest phase", "max"), ("Coolest phase", "min")]),
        ("nao", "nao", 2, "North Atlantic Oscillation", "NAO", "index", "signed", "normal", "positive phase sounds higher",
         "NOAA Climate Prediction Center, NAO", "U.S. Government work (public domain)", [("Highest", "max"), ("Lowest", "min")]),
        ("gistemp", "gistemp_anom", 2, "Global temperature anomaly", "Global temp", "°C vs 1951–80", "trend", "trend", "warmer sounds higher",
         "NASA GISS Surface Temperature Analysis (GISTEMP v4)", "U.S. Government work (public domain)", [("Warmest month", "max")]),
        ("co2", "co2_ppm", 1, "CO₂ at Mauna Loa", "CO₂", "ppm", "trend", "trend", "more CO₂ sounds higher",
         "NOAA Global Monitoring Laboratory, Mauna Loa monthly mean", "U.S. Government work (public domain)", [("First year", "at:0")]),
        ("seaice", "seaice_extent_mkm2", 2, "Arctic sea-ice extent", "Arctic sea ice", "million km²", "seasonal", "seasonal", "more ice sounds higher",
         "National Snow and Ice Data Center, Sea Ice Index, version 4 (G02135), doi 10.7265/a98x-0f50", "NSIDC data, free to use; cited here as the source asks", [("Record low", "min")]),
    ]:
        start, vals = monthly(key, dec)
        out.append(series(id=sid, title=title, short=short, place="global" if sid in ("gistemp", "co2", "seaice") else "ocean basin index",
                          units=units, kind=kind, scale="decades", step="month", start=start, values=vals, twin=twin, polarity=pol,
                          source=src, licence=lic, marks=marks))
    # --- Decades, monthly: a zero-heavy pulse, in place of the dropped sockeye counts (GW 11-16: "add an alternative") ---
    storms = json.loads((repo / "data/climate/storms_nepac.json").read_text(encoding="utf-8"))
    ace = {m: 0.0 for m in months}
    for s in storms:
        m = s["peak_time"][:7]
        if m in ace and s.get("ace") is not None:
            ace[m] += s["ace"]
    out.append(series(id="nepac-ace", title="Northeast Pacific hurricane energy (ACE by month of peak)", short="NE Pacific storms", place="Northeast and Central Pacific basin",
                      units="10⁴ kt²", kind="spiky", scale="decades", step="month", start=months[0], values=[rnd(ace[m], 1) for m in months], twin="spikes",
                      polarity="more storm energy sounds higher", source="NOAA National Hurricane Center HURDAT2 (Northeast and Central Pacific); each storm's accumulated cyclone energy counted in the month of its peak",
                      licence="U.S. Government work (public domain)", marks=[("Busiest month", "max")]))
    # --- A century, yearly: Kettle River annual peak ---
    kt = json.loads((repo / "data/climate/kettle_annual_max.json").read_text(encoding="utf-8"))
    yrs = sorted(kt, key=int)
    out.append(series(id="kettle-peaks", title="Kettle River annual peak flow", short="Kettle peaks", place="Kettle River near Laurier, WA (USGS 12404500)",
                      units="m³/s", kind="peaks", scale="century", step="year", start=yrs[0], values=[rnd(kt[y]["max_daily_m3s"], 0) for y in yrs],
                      twin="normal", polarity="bigger peak sounds higher", source="U.S. Geological Survey, gauge 12404500",
                      licence="U.S. Government work (public domain)", marks=[("Biggest peak", "max"), ("Smallest peak", "min")]))
    return {
        "schema": "sound-channel-brewer/series@1",
        "built_by": "scripts/build_brewer_series.py",
        "note": "Values read from the public sonify-viz data folder; one canonical period per series.",
        "scales": SCALES,
        "series": out,
    }


def check(pack: dict, repo: pathlib.Path) -> list[str]:
    errs = []
    for s in pack["series"]:
        for k in ("id", "title", "units", "kind", "scale", "step", "start", "values", "source", "licence", "twin"):
            if not s.get(k) and s.get(k) != 0:
                errs.append(f"{s.get('id')}: missing {k}")
        good = [v for v in s["values"] if v is not None]
        if len(good) < 0.8 * len(s["values"]):
            errs.append(f"{s['id']}: only {len(good)} of {len(s['values'])} values")
        if len(set(good)) < 3:
            errs.append(f"{s['id']}: fewer than three distinct values")
    n = {s["id"]: s["n"] for s in pack["series"]}
    expect = {"granby": 366, "okanagan-lake": 366, "summerland-temp": 366, "summerland-precip": 366,
              "superior-ice": len(json.loads((repo / "data/icecover/superior_daily.json").read_text(encoding="utf-8"))["dates"])}
    for k, v in expect.items():
        if n.get(k) != v:
            errs.append(f"{k}: {n.get(k)} values, expected {v}")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=pathlib.Path, default=ROOT)
    ap.add_argument("--out", type=pathlib.Path, default=None, help="where to write series.json (default: under --repo)")
    ap.add_argument("--check", action="store_true", help="build in memory, check, do not write")
    a = ap.parse_args()
    out = a.out or out_for(a.repo.expanduser())
    pack = build(a.repo.expanduser())
    text = json.dumps(pack, ensure_ascii=False, separators=(",", ":"))
    errs = check(pack, a.repo.expanduser())
    if len(text.encode()) > MAX_BYTES:
        errs.append(f"pack is {len(text.encode())} bytes, over {MAX_BYTES}")
    for s in pack["series"]:
        print(f"{s['id']:18} {s['scale']:8} {s['kind']:9} n={s['n']:4} start={s['start']} marks={[b['label'] for b in s['bookmarks']]}")
    print(f"{len(pack['series'])} series, {len(text.encode())} bytes")
    if errs:
        print("\n".join(errs), file=sys.stderr)
        return 1
    if not a.check:
        out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
