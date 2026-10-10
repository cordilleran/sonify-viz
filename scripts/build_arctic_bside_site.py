"""Builds the standalone B-side picture for the sonify-viz site: <out>/arctic-bside/ (index.html, assets/, vendor/d3).
    python build_arctic_bside_site.py <out-dir>      (does not commit or push)
Needs: the page source app.html (arctic/page/ in the workbench, arctic-bside/src/ in the published repo; this script copies it to <out>/arctic-bside/src/),
bside_state.json and arctic_page_min.json (from export_bside_viz.py), data/arctic/{terrain_3411.png,glacier_mask.png,ice_meta.json,ice_weekly.txt,ice_extremes.txt,
arctic_land.json} (from the fetch scripts) and the B-side mp3 and its score JSON ($SONIFICATION_LIGHT/arctic/arctic_bside_v2.*, from arctic_bside.py, take 3).
Fonts come from the site's own listen/fonts/. index.html is a build product: edit src/app.html, not index.html."""
import json
import os
import shutil
import sys
from pathlib import Path

WB = Path(__file__).resolve().parent.parent
PAGE = WB / "arctic" / "page" if (WB / "arctic" / "page" / "app.html").exists() else WB / "arctic-bside" / "src"
DATA = WB / "data" / "arctic"
out = Path(sys.argv[1]) / "arctic-bside"
(out / "assets").mkdir(parents=True, exist_ok=True)
(out / "vendor").mkdir(exist_ok=True)
(out / "src").mkdir(exist_ok=True)
audio = Path(os.environ.get("SONIFICATION_LIGHT", WB / "rendered")) / "arctic" / "arctic_bside_v2.mp3"
files = {"terrain": DATA / "terrain_3411.png", "glacier_mask": DATA / "glacier_mask.png", "ice_meta": DATA / "ice_meta.json", "ice_weekly": DATA / "ice_weekly.txt",
         "ice_extremes": DATA / "ice_extremes.txt", "arctic_land": DATA / "arctic_land.json", "arctic_daily": PAGE / "arctic_page_min.json",
         "bside_state": PAGE / "bside_state.json", "bside_v2": audio}
def put(src, dst):
    if not Path(src).exists() and Path(dst).exists():   # published layout: this file is already where it belongs
        print("kept the existing", dst)
        return
    if not Path(src).exists():
        raise SystemExit(f"missing {src}: run the earlier steps in arctic-bside/README.md first")
    if Path(src).resolve() != Path(dst).resolve():      # in the published repo the files are already in place
        shutil.copy(src, dst)


assets = {}
for k, src in files.items():
    put(src, out / "assets" / src.name)
    assets[k] = "assets/" + src.name
put(audio.with_name(audio.stem + "_score.json"), out / "assets" / (audio.stem + "_score.json"))   # the parameters and seed that made the mp3
put(PAGE / "app.html", out / "src" / "app.html")
put(PAGE / "README-arctic-bside.md", out / "README.md")
put(PAGE / "requirements-fetch.txt", out / "requirements-fetch.txt")
for f in ("d3.min.js", "d3-LICENSE.txt"):   # the page loads d3 from here, so a missing copy stops the build
    put(PAGE / "vendor" / f, out / "vendor" / f)
html = (PAGE / "app.html").read_text().replace("__ASSETS__", json.dumps(assets)).replace("__MODE__", "bside")
gfont = [ln for ln in html.splitlines() if "fonts.googleapis.com" in ln]
if len(gfont) != 1:
    raise SystemExit("expected exactly one Google Fonts link in app.html")
html = html.replace(gfont[0], '<link rel="stylesheet" href="../listen/fonts/fonts.css">')
cdn = "https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"
if cdn not in html:
    raise SystemExit("expected the d3 CDN script in app.html")
html = html.replace(cdn, "vendor/d3.min.js").replace("<title>Arctic Round</title>", "<title>The Wheel</title>", 1)
(out / "index.html").write_text('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n' + html.replace('<div class="wrap">', '</head>\n<body>\n<div class="wrap">', 1) + "\n</body>\n</html>\n")
print("wrote", out, sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) // 1024, "KB")
