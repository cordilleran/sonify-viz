"""Assemble the Superior Ice Year page's folder (superior-ice/) from a render's light outputs.

    python export_icecover.py               # the default render and the variants the page's menu offers

Copies the MP3 and writes one JSON per render: the viz JSON from icecover.py plus the grid geometry and the
region mask (one string per row, a digit for the region, '.' for land) so the page needs nothing else but the
two atlas PNGs, which are copied alongside. Nothing is pushed or published from here."""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dsp_core as W

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "icecover"
SRC = W.LIGHT_OUT / "icecover"
OUT = ROOT / "superior-ice"
PUBLISHED = ["icecover_sup2526", "icecover_sup2526__long", "icecover_sup2526__ghost"]


def build_mask(meta):
    regs = json.loads((DATA / "superior_regions.json").read_text())
    file_ids = [r["id"] for r in regs]
    viz_ids = [r["id"] for r in sorted(regs, key=lambda r: r["centroid"][0])]   # icecover.load()'s west-to-east order
    remap = {i: viz_ids.index(rid) for i, rid in enumerate(file_ids)}    # the mask uses the regions file's order, the viz is west to east
    return ["".join("." if v < 0 else str(remap[int(v)]) for v in row) for row in meta["region_mask"]]


def main():
    OUT.mkdir(exist_ok=True)
    meta = json.loads((DATA / "superior_grid_meta.json").read_text())
    mask = build_mask(meta)
    geo = {k: meta[k] for k in ("cols", "rows", "fw", "fh", "extent")}
    for name in PUBLISHED:
        viz = json.loads((SRC / f"{name}_viz.json").read_text())
        viz["grid"] = dict(geo, mask=mask, ice_atlas="superior_ice_atlas.png", sst_atlas="superior_sst_atlas.png")
        (OUT / f"{name}.json").write_text(json.dumps(viz, separators=(",", ":")))
        shutil.copy2(SRC / f"{name}.mp3", OUT / f"{name}.mp3")
        print(f"{name}: {(OUT / f'{name}.json').stat().st_size // 1024} KB json, {(OUT / f'{name}.mp3').stat().st_size // 1024} KB mp3")
    for a in ("superior_ice_atlas.png", "superior_sst_atlas.png"):
        shutil.copy2(DATA / a, OUT / a)


if __name__ == "__main__":
    main()
