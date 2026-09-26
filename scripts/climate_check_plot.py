"""Visual QA for a climate-pair render: each year's data against each
instrument's loudness, on one time axis. Lets a reader SEE whether each layer
speaks when its data says it should.
usage: python climate_check_plot.py pacific|atlantic"""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dsp_core import ROOT, HEAVY_OUT

basin = sys.argv[1] if len(sys.argv) > 1 else "pacific"
name = f"climate_{basin}_1958_2025"
with open(ROOT / "rendered" / "climate" / f"{name}_score.json") as fh:
    sc = json.load(fh)
yrs = sc["years_detail"]
t = np.array([(y["year"] - yrs[0]["year"] + 0.5) * sc["bar_seconds"] for y in yrs])
lanes = [("co2_ppm", "CO2 (ppm)"), ("sst_anom", "SST anomaly"), ("ohc_1e22J", "ocean heat 0-2000 m"),
         ("ace", "storm energy (ACE)")]
if basin == "atlantic":
    lanes.append(("seaice_sep_mkm2", "Sept. sea ice"))
stems = sorted((HEAVY_OUT / "climate" / f"{name}_stems").glob("*.flac"))
fig, ax = plt.subplots(len(lanes) + len(stems), 1, figsize=(13, 0.62 * (len(lanes) + len(stems))), sharex=True)
for a, (k, label) in zip(ax, lanes):
    v = np.array([np.nan if y[k] is None else float(y[k]) for y in yrs])
    a.bar(t, v - np.nanmin(v), width=sc["bar_seconds"] * 0.9, color="#4a7a96")
    a.set_ylabel(label, rotation=0, ha="right", fontsize=7)
    a.set_yticks([])
for a, f in zip(ax[len(lanes):], stems):
    x, sr = sf.read(f)
    m = x.mean(1)
    blk = sr // 4
    r = np.sqrt(np.array([(m[i:i + blk] ** 2).mean() for i in range(0, len(m) - blk, blk)]) + 1e-12)
    db = np.clip(20 * np.log10(r * 4) + 70, 0, None)
    a.fill_between(np.arange(len(db)) * 0.25, db, color="#b0603a", lw=0)
    a.set_ylabel("♪ " + f.stem, rotation=0, ha="right", fontsize=7)
    a.set_yticks([])
ticks = [y for y in range(1960, 2030, 10) if y <= yrs[-1]["year"]]
ax[-1].set_xticks([(y - yrs[0]["year"]) * sc["bar_seconds"] for y in ticks], [str(y) for y in ticks])
ax[-1].set_xlabel("year (7 s each)")
plt.tight_layout(h_pad=0.1)
(ROOT / "figs").mkdir(exist_ok=True)
plt.savefig(ROOT / "figs" / f"{name}_check.png", dpi=80)
