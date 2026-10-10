"""ARCTIC ROUND ice grids for the picture (M2): weekly NSIDC Sea Ice Index v4 concentration GeoTIFFs, cropped and packed.

Source: NSIDC G02135 v4.0 (10.7265/a98x-0f50), noaadata.apps.nsidc.org/NOAA/G02135/north/daily/geotiff/. Label R.
A frame for every 7th day of each ice year (1 Oct + 7k, k = 0..51), taking the nearest day on which a grid exists (every other day until Aug 1987,
and a gap 2 Dec 1987 to 13 Jan 1988; those frames repeat the nearest grid and are flagged in `observed`). Plus, for each ice year, the grids of the
day of its maximum and of its minimum total extent (the faint max/min lines), at full 25 km resolution.
Crop: columns 34..273, rows 114..353 of the 304 x 448 grid (the picture's 3000 km radius round the pole). Weekly frames are 2x block means (120 x 120).
Values: percent / 5 (0..20), 255 land or coast; the pole hole (flag 2510) is filled with 20 (ice) and is not measured.
Output (data/arctic/): ice_weekly.txt (base64 of gzip of frames, 120*120 bytes each, in order), ice_extremes.txt (full-res 240*240, order: year, max, min),
ice_meta.json (dates, observed flags, extreme dates). Raw tifs stay in $SONIFICATION_RAW/arctic/grids.
Run: python scripts/fetch_arctic_grids.py    (about 1.7 GB the first time; resumes) (needs the packages in arctic-bside/requirements-fetch.txt)
"""
import base64
import concurrent.futures as cf
import datetime as dt
import gzip
import json
import os
import urllib.request
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("SONIFICATION_RAW", ROOT / "rendered" / "raw")) / "arctic" / "grids"
OUT = ROOT / "data" / "arctic"
RAW.mkdir(parents=True, exist_ok=True)
C0, R0, SZ = 34, 114, 240
BASE = "https://noaadata.apps.nsidc.org/NOAA/G02135/north/daily/geotiff"


def url(d):
    return f"{BASE}/{d.year}/{d.month:02d}_{d.strftime('%b')}/N_{d:%Y%m%d}_concentration_v4.0.tif"


def get(d):
    f = RAW / f"{d:%Y%m%d}.tif"
    if not f.exists():
        for k in range(4):
            try:
                f.write_bytes(urllib.request.urlopen(urllib.request.Request(url(d), headers={"User-Agent": "sonification-workbench"}), timeout=120).read())
                break
            except Exception as e:
                if k == 3:
                    print("FAILED", d, e)
                    return None
    return f


def classes(f):
    a = rasterio.open(f).read(1).astype(float)[R0:R0 + SZ, C0:C0 + SZ]
    q = np.full(a.shape, 255, np.uint8)
    ok = a <= 1000
    q[ok] = np.clip(np.round(a[ok] / 10 / 5), 0, 20).astype(np.uint8)
    q[a == 2510] = 20
    return q


def half(q):
    """2x block reduction: land if two or more of four cells are land, else the mean class of the sea cells."""
    b = q.reshape(SZ // 2, 2, SZ // 2, 2).swapaxes(1, 2).reshape(SZ // 2, SZ // 2, 4).astype(float)
    land = (b == 255).sum(axis=2) >= 2
    sea = np.where(b == 255, np.nan, b)
    m = np.nanmean(np.where(np.isnan(sea).all(axis=2)[..., None], 0, sea), axis=2)
    m = np.round(np.nan_to_num(m))
    return np.where(land, 255, m).astype(np.uint8)


def main():
    d = json.loads((OUT / "arctic_daily.json").read_text())
    dates = [dt.date.fromisoformat(x) for x in d["dates"]]
    have = [x for x, o in zip(dates, d["observed"]) if o]
    obs_set = set(have)
    tot = np.array(d["total"])
    want, flags, ext = [], [], {}
    import bisect
    for y in range(1979, 2027):
        for k in range(52):
            t = dt.date(y - 1, 10, 1) + dt.timedelta(7 * k)
            i = bisect.bisect_left(have, t)
            cand = [have[j] for j in (i - 1, i) if 0 <= j < len(have)]
            n = min(cand, key=lambda x: abs((x - t).days))
            want.append(n)
            flags.append(int(t in obs_set))
        # the maximum is the highest day of Jan to Apr, the minimum the lowest day of Aug to Sep: the September minimum that closes the bar
        # (an Oct-Sep window would pick 1 Oct, which still carries the previous September's low)
        hi = [(x, tot[j]) for j, x in enumerate(dates) if dt.date(y, 1, 1) <= x <= dt.date(y, 4, 30) and d["observed"][j]]
        lo = [(x, tot[j]) for j, x in enumerate(dates) if dt.date(y, 8, 1) <= x <= dt.date(y, 9, 30) and d["observed"][j]]
        if hi and lo:
            ext[y] = (max(hi, key=lambda p: p[1])[0], min(lo, key=lambda p: p[1])[0])
    need = sorted(set(want) | {x for p in ext.values() for x in p})
    print(len(want), "weekly frames;", len(need), "distinct grids")
    with cf.ThreadPoolExecutor(6) as ex:
        files = dict(zip(need, ex.map(get, need)))
    bad = [x for x, f in files.items() if f is None]
    assert not bad, bad[:5]
    wk = bytearray()
    cache = {}
    for n in want:
        if n not in cache:
            cache[n] = half(classes(files[n])).tobytes()
        wk += cache[n]
    (OUT / "ice_weekly.txt").write_text(base64.b64encode(gzip.compress(bytes(wk), 9)).decode())
    ex_b = bytearray()
    for y in range(1979, 2027):
        for x in ext.get(y, (None, None)):
            ex_b += classes(files[x]).tobytes() if x else bytes(SZ * SZ)
    (OUT / "ice_extremes.txt").write_text(base64.b64encode(gzip.compress(bytes(ex_b), 9)).decode())
    (OUT / "ice_meta.json").write_text(json.dumps({
        "frame_w": SZ // 2, "frame_h": SZ // 2, "extreme_w": SZ, "crop": {"c0": C0, "r0": R0, "size": SZ}, "years": list(range(1979, 2027)), "per_year": 52,
        "frame_dates": [x.isoformat() for x in want], "observed": flags,
        "extremes": {str(y): [ext[y][0].isoformat(), ext[y][1].isoformat()] for y in ext},
        "classes": "percent/5 (0..20); 255 land or coast; pole hole drawn as 20 (not measured)",
        "source": "NSIDC Sea Ice Index v4.0 (G02135), doi 10.7265/a98x-0f50"}))
    print("wrote", [(p.name, p.stat().st_size // 1024) for p in OUT.glob("ice_*")])


if __name__ == "__main__":
    main()
