"""Point series from ECMWF's open AIFS forecast (CC BY 4.0), written in the shape the groove script reads.

Reads ECMWF's published .index for each step, downloads only the messages it needs by byte range
(about 20 MB a step), reads them with eccodes, bilinear-interpolates to the point, and deletes the
GRIB again. Sequential, one request at a time, honest user agent.

  uv run --no-project --with eccodes==2.48.0 --with eccodeslib==2.48.2.27 --with eckitlib==2.2.0.27 \\
      --with numpy python -I scripts/fetch_aifs_open.py 20261016 12 49.21042 -68.13721 OUT.json

Server: https://data.ecmwf.int/forecasts/<date>/<hh>z/aifs-single/0p25/oper/ (a few days of runs are kept).
Each stamp is the valid time on a fixed UTC-5 clock, written with a 'Z' (a label convention the song and page code read).
Precipitation, snowfall and shortwave are accumulations from the run start; the 6 h values are differences.
"""
import json
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import eccodes as ec
import numpy as np

UA = "Habitat-personal-research/1.0 (single-user, low rate)"
BASE = "https://data.ecmwf.int/forecasts/{d}/{h:02d}z/aifs-single/0p25/oper/{d}{h:02d}0000-{s}h-oper-fc"
WANT = [("sfc", None, p) for p in ("2t", "2d", "msl", "10u", "10v", "100u", "100v", "tp", "sf", "tcc", "ssrd")] + \
       [("pl", lv, p) for lv in ("850", "700") for p in ("u", "v")] + [("pl", "850", "t"), ("pl", "700", "t")]
LOCAL_OFFSET_H = -5  # fixed local clock for the stamps (no daylight-saving shifts across the run)
SNOW_CM_PER_MM_WE = 1.0  # 1 mm of water equivalent -> 1 cm of snow; the same rough 10:1 rule the earlier series implied (checked in the comparison)


def get(url, rng=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **({"Range": f"bytes={rng[0]}-{rng[0] + rng[1] - 1}"} if rng else {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def point_values(path, lat, lon):
    out = {}
    with open(path, "rb") as f:
        while (g := ec.codes_grib_new_from_file(f)) is not None:
            sn, lev = ec.codes_get(g, "shortName"), ec.codes_get(g, "level")
            ni, nj = ec.codes_get(g, "Ni"), ec.codes_get(g, "Nj")
            la0, lo0 = ec.codes_get(g, "latitudeOfFirstGridPointInDegrees"), ec.codes_get(g, "longitudeOfFirstGridPointInDegrees")
            dx, dy = ec.codes_get(g, "iDirectionIncrementInDegrees"), ec.codes_get(g, "jDirectionIncrementInDegrees")
            assert ec.codes_get(g, "jScansPositively") == 0 and abs(la0 - 90) < 1e-6 and ni == 1440 and nj == 721
            v = ec.codes_get_values(g).reshape(nj, ni)
            j, i = (la0 - lat) / dy, ((lon - lo0) % 360) / dx
            j0, i0 = int(j), int(i)
            fj, fi = j - j0, i - i0
            i1 = (i0 + 1) % ni
            val = (v[j0, i0] * (1 - fi) + v[j0, i1] * fi) * (1 - fj) + (v[j0 + 1, i0] * (1 - fi) + v[j0 + 1, i1] * fi) * fj
            out[(sn, lev if ec.codes_get(g, "typeOfLevel") == "isobaricInhPa" else 0)] = float(val)
            ec.codes_release(g)
    return out


def fetch_step(d, h, s, lat, lon, tmp):
    base = BASE.format(d=d, h=h, s=s)
    idx = [json.loads(l) for l in get(base + ".index").decode().splitlines()]
    sel = [m for m in idx for lt, lv, p in WANT if m["param"] == p and m["levtype"] == lt and (lv is None or m.get("levelist") == lv)]
    assert len(sel) == len(WANT), (s, len(sel))
    f = Path(tmp) / f"s{s}.grib2"
    with open(f, "wb") as fh:
        for m in sel:
            fh.write(get(base + ".grib2", (m["_offset"], m["_length"])))
            time.sleep(0.15)
    vals = point_values(f, lat, lon)
    f.unlink()
    return vals


def wind(u, v):
    return round(float(np.hypot(u, v)) * 3.6, 1), int(round((270 - np.degrees(np.arctan2(v, u))) % 360)) % 360


def main():
    d, h, lat, lon, out = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), Path(sys.argv[5])
    run = datetime.strptime(d, "%Y%m%d").replace(hour=h, tzinfo=timezone.utc)
    steps = list(range(0, 361, 6))
    cache = out.with_suffix(".steps.json")
    raw = {int(k): v for k, v in json.loads(cache.read_text()).items()} if cache.exists() else {}
    with tempfile.TemporaryDirectory() as tmp:
        for s in steps:
            if s not in raw:
                v = fetch_step(d, h, s, lat, lon, tmp)
                raw[s] = {f"{k[0]}:{k[1]}": x for k, x in v.items()}
                cache.write_text(json.dumps(raw))
                print("step", s, flush=True)
    S = {k: [] for k in ("Temp.", "Dew point", "RH", "850mb", "700mb", "Pressure", "Cloud Cover", "Ttl Rain", "Ttl Snow", "6hr Precip", "Downward Shortwave",
                         "10m Wind", "100m Wind", "850mb Wind", "700mb Wind")}
    prev = {"tp": 0.0, "sf": 0.0, "ssrd": 0.0}
    cum_rain = cum_snow = 0.0
    for s in steps:
        r = raw[s]
        stamp = (run + timedelta(hours=s + LOCAL_OFFSET_H)).strftime("%Y-%m-%dT%H:%MZ")
        t, td = r["2t:0"] - 273.15, r["2d:0"] - 273.15
        rh = 100 * np.exp(17.625 * td / (243.04 + td)) / np.exp(17.625 * t / (243.04 + t))
        tp, sf, ssrd = r["tp:0"], r["sf:0"], r["ssrd:0"]  # AIFS open data: tp and sf in mm water equivalent, ssrd in J/m2 (accumulated)
        dtp, dsf = max(tp - prev["tp"], 0), max(sf - prev["sf"], 0)
        rain_mm, snow_cm = max(dtp - dsf, 0), dsf * SNOW_CM_PER_MM_WE
        cum_rain, cum_snow = cum_rain + rain_mm, cum_snow + snow_cm
        sw = (ssrd - prev["ssrd"]) / 21600 if s else 0.0
        prev = {"tp": tp, "sf": sf, "ssrd": ssrd}
        S["Temp."].append([stamp, round(t, 1)])
        S["Dew point"].append([stamp, round(td, 1)])
        S["RH"].append([stamp, round(float(rh))])
        S["850mb"].append([stamp, round(r["t:850"] - 273.15, 1)])
        S["700mb"].append([stamp, round(r["t:700"] - 273.15, 1)])
        S["Pressure"].append([stamp, round(r["msl:0"] / 100, 1)])
        S["Cloud Cover"].append([stamp, round(r["tcc:0"])])
        S["Ttl Rain"].append([stamp, round(cum_rain, 1)])
        S["Ttl Snow"].append([stamp, round(cum_snow, 1)])
        kind = "none" if dtp < 0.05 else ("snow" if dsf > 0.5 * dtp else "rain")
        S["6hr Precip"].append([stamp, round(rain_mm + snow_cm, 1), "none" if kind == "none" else f"{round(rain_mm + snow_cm, 1)} {'mm rain' if kind == 'rain' else 'cm snow'}"])
        S["Downward Shortwave"].append([stamp, round(max(sw, 0), 1)])
        S["10m Wind"].append([stamp, *wind(r["10u:0"], r["10v:0"])])
        S["100m Wind"].append([stamp, *wind(r["100u:0"], r["100v:0"])])
        S["850mb Wind"].append([stamp, *wind(r["u:850"], r["v:850"])])
        S["700mb Wind"].append([stamp, *wind(r["u:700"], r["v:700"])])
    out.write_text(json.dumps({
        "model": "ecmwf_aifs_single",
        "source": f"ECMWF open data, AIFS single 0p25, run {d} {h:02d}z, https://data.ecmwf.int/forecasts/ (CC BY 4.0)",
        "tz": "UTC-5 fixed; labels are local clock time, written with a 'Z' for compatibility with the earlier series",
        "series": S,
        "point": {"lat": lat, "lon": lon, "method": "bilinear on the 0.25 degree grid"},
        "units": {"Temp.": "C", "Ttl Rain": "mm cumulative (tp - sf)", "Ttl Snow": f"cm cumulative ({SNOW_CM_PER_MM_WE} cm per mm water equivalent of sf)",
                  "6hr Precip": "mm/cm per 6 h", "wind": "km/h, direction in degrees (from)", "Downward Shortwave": "W/m2, mean over the 6 h ending at the stamp (ssrd difference / 21600)",
                  "Pressure": "hPa, mean sea level", "Cloud Cover": "% (tcc)"},
    }, indent=0))
    print("wrote", out)


if __name__ == "__main__":
    main()
