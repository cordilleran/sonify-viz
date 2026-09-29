"""Prepare Lake Superior bathymetry + ice/SST fields for the Blender animation.

Run with the system python (rasterio lives there): /usr/bin/python3 scripts/blender_prep_superior.py

Inputs
  NOAA NCEI Great Lakes bathymetry, Lake Superior 3 arc-second grid (NOAA NGDC/GLERL/CHS), GeoTIFF
    -> fetched to BATHY_TIF (see BATHY_URL); values are metres relative to lake level (lake < 0).
  data/icecover/superior_{ice,sst}_atlas.png  (GLERL/CoastWatch ERDDAP grids, 16x15 atlas of 285x100 frames)
Outputs (heavy, runtime): rendered/icecover/blender/
  floor_1200.npy   float32 elevation (m), mesh grid, north-up
  mask_2048.png    lake mask (255 = lake) at texture resolution
  fields.npy       uint8 (days, 100, 285, 2)  [ice %, SST degC x 10], land filled from nearest lake cell
  days.json        dates + lake-mean ice % and SST per day (D: computed from the atlases)
  bathy_hillshade_4k.png   stand-alone still, 4096 px wide
"""
import json, os, sys, urllib.request, tarfile
from pathlib import Path
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parent.parent   # the repository root
# heavy outputs: $SONIFICATION_HEAVY/icecover/blender, else the repo's rendered/ (this runs under the system python,
# so set SONIFICATION_HEAVY yourself to keep them elsewhere)
OUT = Path(os.environ.get("SONIFICATION_HEAVY", ROOT / "rendered")) / "icecover" / "blender"
OUT.mkdir(parents=True, exist_ok=True)
SRC = OUT / "src"
SRC.mkdir(exist_ok=True)
BATHY_URL = "https://www.ngdc.noaa.gov/mgg/greatlakes/superior/data/geotiff/superior_lld.geotiff.tar.gz"
BATHY_TIF = SRC / "superior_lld/superior_lld.tif"

meta = json.load(open(ROOT / "data/icecover/superior_grid_meta.json"))
LAT0, LAT1 = meta["extent"]["lat"]
LON0, LON1 = meta["extent"]["lon"]
FW, FH, COLS = meta["fw"], meta["fh"], meta["cols"]
COSL = np.cos(np.radians((LAT0 + LAT1) / 2))
ASPECT = (LON1 - LON0) * COSL / (LAT1 - LAT0)


def fetch():
    if BATHY_TIF.exists():
        return
    tgz = SRC / "sup.tar.gz"
    print("downloading", BATHY_URL)
    urllib.request.urlretrieve(BATHY_URL, tgz)
    with tarfile.open(tgz) as t:
        t.extractall(SRC, filter="data")   # refuse absolute paths and ..: the archive comes from the network


def read_bathy(w):
    h = int(round(w / ASPECT))
    with rasterio.open(BATHY_TIF) as r:
        win = from_bounds(LON0, LAT0, LON1, LAT1, r.transform)
        a = r.read(1, window=win, out_shape=(h, w), resampling=Resampling.average, masked=True)
    return np.ma.filled(a, -0.0).astype("float32")


def atlas(name):
    im = np.array(Image.open(ROOT / f"data/icecover/{name}"))
    n = json.load(open(ROOT / "data/icecover/superior_daily.json"))["n"]
    fr = np.empty((n, FH, FW), np.uint8)
    for d in range(n):
        ox, oy = (d % COLS) * FW, (d // COLS) * FH
        fr[d] = im[oy:oy + FH, ox:ox + FW]
    return fr


def main():
    fetch()
    daily = json.load(open(ROOT / "data/icecover/superior_daily.json"))
    dates = daily["dates"]

    b4k = read_bathy(4096)
    b1200 = read_bathy(1200)
    b2048 = read_bathy(2048)
    np.save(OUT / "floor_1200.npy", b1200)
    lake = b2048 < 0
    lab, n = ndi.label(lake)
    big = np.argmax(ndi.sum(lake, lab, range(1, n + 1))) + 1
    lake = lab == big
    Image.fromarray((lake * 255).astype("uint8")).save(OUT / "mask_2048.png")
    print("lake area fraction of frame", lake.mean().round(3), "max depth m", float(b4k.min()))

    ice, sst = atlas("superior_ice_atlas.png"), atlas("superior_sst_atlas.png")
    land = ice[0] == 255
    small = np.array(Image.fromarray((lake * 255).astype("uint8")).resize((FW, FH), Image.BILINEAR)) < 128
    for name, cand in (("as-is", land), ("flipped", land[::-1])):
        print("atlas land vs shoreline mismatch", name, round(float((cand != small).mean()), 4))
    flip = float((land[::-1] != small).mean()) < float((land != small).mean())
    print("flip vertical:", flip)
    if flip:
        ice, sst = ice[:, ::-1], sst[:, ::-1]
    landm = ice[0] == 255
    idx = ndi.distance_transform_edt(landm, return_distances=False, return_indices=True)
    fields = np.zeros((len(dates), FH, FW, 2), np.uint8)
    lake_ice, lake_sst = [], []
    for d in range(len(dates)):
        i = ice[d].astype("float32")
        s = sst[d].astype("float32")
        i = np.where(landm, i[idx[0], idx[1]], i)
        s = np.where(landm, s[idx[0], idx[1]], s)
        i = np.where(i > 100, 0, i)
        s = np.where(s > 250, 0, s)
        fields[d, ..., 0] = i.astype("uint8")
        fields[d, ..., 1] = s.astype("uint8")
        lake_ice.append(float(i[~landm].mean()))
        lake_sst.append(float(s[~landm].mean() / 10))
    np.save(OUT / "fields.npy", fields)
    json.dump({"dates": dates, "lake_ice_pct": [round(x, 1) for x in lake_ice],
               "lake_sst_c": [round(x, 2) for x in lake_sst], "aspect": ASPECT,
               "extent": {"lat": [LAT0, LAT1], "lon": [LON0, LON1]}}, open(OUT / "days.json", "w"))
    print("peak lake-mean ice %", max(lake_ice), "on", dates[int(np.argmax(lake_ice))])

    still(b4k, "B", "key")   # the published figure: palette B, key light 315/45 (see superior_palette.py)


def multishade(b, kmx, z=12.0):
    """Multidirectional hillshade (gdaldem -multidirectional: several light azimuths, weighted by slope aspect),
    0..1. The grid is written as a metre-spaced GeoTIFF so gdaldem's slope maths is in metres."""
    import subprocess, tempfile
    from rasterio.transform import from_origin
    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td) / "z.tif", Path(td) / "hs.tif"
        with rasterio.open(src, "w", driver="GTiff", width=b.shape[1], height=b.shape[0], count=1, dtype="float32",
                           transform=from_origin(0, 0, kmx, kmx)) as w:
            w.write(b.astype("float32"), 1)
        subprocess.run(["gdaldem", "hillshade", "-q", "-multidirectional", "-alt", "45", "-z", str(z),
                        str(src), str(dst)], check=True)
        with rasterio.open(dst) as r:
            return r.read(1).astype("float32") / 255.0


def keyshade(b, kmx, az=315, alt=45, z=12.0):
    from matplotlib.colors import LightSource
    return LightSource(azdeg=az, altdeg=alt).hillshade(b, vert_exag=z, dx=kmx, dy=kmx)


def still(b, palette="A", light="key", tag=None, out=OUT):
    """The 4K hillshade still (the page's lake-floor figure is palette B, key light: superior_bathymetry_hillshade_4k.png
    is this function's bathy_hillshade_4k.png). palette A|B|C (superior_palette.py); light key (315 deg, 45 deg, the
    cartographic convention) | multi (gdaldem multidirectional). v0 was palette A, key light at 315/38."""
    import matplotlib
    matplotlib.use("Agg")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import superior_palette as SP
    kmx = (LON1 - LON0) * 111.32 * COSL * 1000 / b.shape[1]
    shade = multishade(b, kmx) if light == "multi" else keyshade(b, kmx)
    rgb = SP.shade_mix(SP.colours(b, palette), shade, palette)
    name = tag or "bathy_hillshade_4k"
    im = Image.fromarray((rgb * 255).astype("uint8"))
    im.save(out / f"{name}.png")
    print("still", name, rgb.shape)
    return im


def shades_1200():
    """Relief shading on the Blender mesh grid, for the lighting options baked into vertex colours."""
    b = np.load(OUT / "floor_1200.npy")
    kmx = (LON1 - LON0) * 111.32 * COSL * 1000 / b.shape[1]
    np.save(OUT / "shade_multi_1200.npy", multishade(b, kmx, z=20.0))
    np.save(OUT / "shade_key_1200.npy", keyshade(b, kmx, z=20.0).astype("float32"))


def ab_stills(out):
    """Palette and lighting comparison stills: 4096 px PNGs plus 2400 px JPEG copies."""
    out.mkdir(parents=True, exist_ok=True)
    fetch()
    b4k = read_bathy(4096)
    for pal, light in (("A", "key"), ("B", "key"), ("B", "multi"), ("C", "multi"), ("C", "key")):
        im = still(b4k, pal, light, tag=f"hillshade_{pal}_{light}", out=out)
        im.resize((2400, round(2400 * im.height / im.width)), Image.LANCZOS).save(out / f"hillshade_{pal}_{light}.jpg", quality=90)
    shades_1200()


if __name__ == "__main__":
    if "--ab" in sys.argv:
        ab_stills(Path(sys.argv[sys.argv.index("--ab") + 1]))
    else:
        main()
