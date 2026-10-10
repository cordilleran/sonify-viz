"""ARCTIC ROUND permanent-ice mask for the land layer (M2): Natural Earth 1:10m glaciated areas rasterised onto the terrain grid.

Source: Natural Earth, ne_10m_glaciated_areas (public domain; no attribution required, credited anyway). It outlines the Greenland ice sheet and the
large ice caps (Canadian Arctic, Svalbard, Novaya and Severnaya Zemlya, Franz Josef Land, Iceland, Alaska ranges). Small glaciers are not in it, so
the mask is generous to the greening in places, never to the ice. Label R (a cartographic compilation, not a survey).
Output: data/arctic/glacier_mask.png (grey, 255 where permanent ice, same grid as terrain_3411.png).
Run: python scripts/fetch_arctic_glaciers.py   (needs rasterio and Pillow: pip install -r arctic-bside/requirements-fetch.txt)
"""
import json
import os
import urllib.request
from pathlib import Path

from PIL import Image
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import transform_geom

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("SONIFICATION_RAW", ROOT / "rendered" / "raw")) / "arctic"
# pinned to a commit so two runs give the same mask
URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/693f11422f4e08d2da4566b854dda53eb7c39fb3/geojson/ne_10m_glaciated_areas.geojson"
META = json.loads((ROOT / "data" / "arctic" / "terrain_meta.json").read_text())


def main():
    f = RAW / "ne_10m_glaciated_areas.geojson"
    if not f.exists():
        f.write_bytes(urllib.request.urlopen(URL, timeout=120).read())
    feats = json.loads(f.read_text())["features"]
    shapes, failed = [], 0
    for ft in feats:
        b = ft.get("bbox") or [0, 0, 0, 0]
        if b[3] < 50:
            continue
        try:
            shapes.append((transform_geom("EPSG:4326", "EPSG:3411", ft["geometry"]), 1))
        except (ValueError, TypeError, KeyError) as e:   # a polygon that cannot be reprojected is left out, and counted
            failed += 1
            print("skipped one glaciated area:", e)
    w, h, px = META["width_px"], META["height_px"], META["cell_m"] / META["oversample"]
    m = rasterize(shapes, out_shape=(h, w), transform=from_origin(META["x0"], META["y0"], px, px), fill=0, dtype="uint8", all_touched=True)
    Image.fromarray(m * 255, "L").save(ROOT / "data" / "arctic" / "glacier_mask.png", optimize=True)
    print(len(shapes), "features;", failed, "skipped;", round(float(m.mean()) * 100, 1), "% of the picture grid is permanent ice")


if __name__ == "__main__":
    main()
