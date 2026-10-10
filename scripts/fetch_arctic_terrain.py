"""ARCTIC ROUND terrain for the picture (M2): GEBCO_2025 land and sea-floor elevation on the NSIDC polar stereographic grid.

Source: GEBCO_2025 Grid (public domain; acknowledge the source; not for navigation; DOI 10.5285/37c52e96-24ea-67ce-e063-7086abc05f29),
served as an ImageServer by UNH CCOM (gis.ccom.unh.edu/server/rest/services/GEBCO2025/GEBCO_2025_IS). Label: R (a compiled terrain model, not a survey).
The grid is fetched in EPSG:3411 over the extent of the NSIDC Sea Ice Index GeoTIFFs (304 x 448 cells of 25 km), at 4x the cell count each way.

Output (data/arctic/): terrain_3411.png, 3 channels (no alpha, so browsers keep the values exactly):
  R  hillshade of the whole surface, 0..255 (sun from the north-west, 40 degrees; the sea floor is exaggerated more than land)
  G  sea depth, 0 on land, 1..255 for 0..6000 m
  B  land height, 0 at sea, 1..255 for 0..3500 m (the ice sheet is land here)
  terrain_meta.json  the grid, scales, source and licence line.
Run: python scripts/fetch_arctic_terrain.py   (needs the packages in arctic-bside/requirements-fetch.txt); raw tif kept in $SONIFICATION_RAW/arctic
"""
import json
import os
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("SONIFICATION_RAW", ROOT / "rendered" / "raw")) / "arctic"
OUT = ROOT / "data" / "arctic"
RAW.mkdir(parents=True, exist_ok=True)
X0, Y0, W, H, CELL = -3850000, 5850000, 304, 448, 25000
K = 4
URL = ("https://gis.ccom.unh.edu/server/rest/services/GEBCO2025/GEBCO_2025_IS/ImageServer/exportImage?"
       f"bbox={X0},{Y0 - H * CELL},{X0 + W * CELL},{Y0}&bboxSR=3411&imageSR=3411&size={W * K},{H * K}&format=tiff&pixelType=F32"
       "&interpolation=RSP_BilinearInterpolation&f=image")


def main():
    tif = RAW / "gebco2025_3411.tif"
    if not tif.exists():
        print("fetching", W * K, "x", H * K)
        tif.write_bytes(urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "sonification-workbench"}), timeout=300).read())
    z = rasterio.open(tif).read(1).astype(float)
    cell = CELL / K
    ex = np.where(z < 0, z * 3.0, z * 1.5)                    # exaggerated surface
    gy, gx = np.gradient(ex, cell)                              # rows run south, so gy is d/d(row)
    az, alt = np.radians(315), np.radians(40)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(gy, -gx)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    hs = np.clip((hs - hs.min()) / (np.ptp(hs) + 1e-9), 0, 1)
    land = z > 0
    r = (hs * 255).astype(np.uint8)
    g = np.where(land, 0, np.clip(1 + (-z) / 6000 * 254, 1, 255)).astype(np.uint8)
    b = np.where(land, np.clip(1 + z / 3500 * 254, 1, 255), 0).astype(np.uint8)
    Image.fromarray(np.dstack([r, g, b]), "RGB").save(OUT / "terrain_3411.png", optimize=True)
    (OUT / "terrain_meta.json").write_text(json.dumps({
        "crs": "EPSG:3411", "x0": X0, "y0": Y0, "cell_m": CELL, "cols": W, "rows": H, "oversample": K, "width_px": W * K, "height_px": H * K,
        "depth_max_m": 6000, "height_max_m": 3500, "land_is": "elevation above 0 m, including the ice sheet surface",
        "source": "GEBCO_2025 Grid, GEBCO Compilation Group, doi 10.5285/37c52e96-24ea-67ce-e063-7086abc05f29",
        "licence": "public domain; acknowledge the source; not for navigation; no endorsement implied",
        "served_by": "UNH CCOM GEBCO_2025 ImageServer", "label": "R (compiled terrain model)"}, indent=1))
    print("wrote terrain_3411.png", (OUT / "terrain_3411.png").stat().st_size // 1024, "KB; land share", round(float(land.mean()), 3))


if __name__ == "__main__":
    main()
