"""Write each climate piece's listening guide (every timed event in its score)
as a Markdown table in climate/, for the site's Climate Pair page.
usage: python export_climate_guide.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dsp_core import ROOT

OUT = ROOT / "climate"
OUT.mkdir(exist_ok=True)
for basin in ("pacific", "atlantic"):
    with open(ROOT / "rendered" / "climate" / f"climate_{basin}_1958_2025_score.json") as fh:
        sc = json.load(fh)
    rows = ["| Time | What you hear |", "|---:|---|"]
    for t, e in sc["events"]:
        e = e.replace("CO2", "CO₂").replace("Nino", "Niño").replace("Nina", "Niña").replace("|", "/")
        rows.append(f"| {int(t // 60)}:{int(t % 60):02d} | {e} |")
    (OUT / f"guide_{basin}.md").write_text("\n".join(rows) + "\n")
    print(basin, len(sc["events"]), "events")
