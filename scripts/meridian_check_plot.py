"""
Check figure for a Meridian Chorus render (2026-09-27): does the sound follow
the light? Four panels on one time axis:
  1. day length at each voice, per breath (the data);
  2. each voice's note envelope, as rendered (what shapes its sound);
  3. loudness of the mix, and of the in-breath stem, 4 frames a second;
  4. a spectrogram of the mix, with each voice's pitch marked.

    python meridian_check_plot.py meridian_ds2023
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf
from scipy.signal import spectrogram

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dsp_core as W

name = sys.argv[1] if len(sys.argv) > 1 else "meridian_ds2023"
out_dir = W.LIGHT_OUT / "meridian"
sc = json.loads((out_dir / f"{name}_score.json").read_text())
viz = json.loads((out_dir / f"{name}_viz.json").read_text())
mix, sr = sf.read(W.HEAVY_OUT / "meridian" / f"{name}.wav")
breath_stem, _ = sf.read(W.HEAVY_OUT / "meridian" / f"{name}_stems" / "breath.flac")
lats = [v["lat"] for v in sc["voices"]]
B = sc["breath_s"]
T = sc["n_breaths"] * B

fig, ax = plt.subplots(4, 1, figsize=(14, 13), sharex=True, gridspec_kw={"height_ratios": [1.2, 1.2, 0.7, 1.5]})
dl = np.array([[b["voices"][i][0] for b in sc["breaths"]] for i in range(len(lats))])
ax[0].imshow(dl, aspect="auto", cmap="cividis", extent=[0, T, len(lats) - 0.5, -0.5], vmin=0, vmax=24)
ax[0].set_yticks(range(len(lats)), [f"{la:+d}°" for la in lats])
ax[0].set_title(f"{name}: day length per voice (h), one column per breath of {sc['days_per_breath']} days")

env = np.array(viz["env"]) / 100
ax[1].imshow(env, aspect="auto", cmap="magma", extent=[0, len(env[0]) / viz["env_hz"], len(lats) - 0.5, -0.5],
             interpolation="nearest")
ax[1].set_yticks(range(len(lats)), [f"{la:+d}°" for la in lats])
ax[1].set_title("note envelope as rendered (8 Hz): each breath is one day, midnight to midnight")

hop = sr // 4
rms = lambda x: 20 * np.log10(np.sqrt(np.mean(x[: len(x) // hop * hop].reshape(-1, hop, 2) ** 2, axis=(1, 2))) + 1e-9)
tt = np.arange(len(mix) // hop) / 4
ax[2].plot(tt, rms(mix), lw=0.6, label="mix")
ax[2].plot(tt, rms(breath_stem * 4), lw=0.6, label="in-breath stem")
ax[2].set_ylabel("dBFS"), ax[2].legend(loc="lower right"), ax[2].set_ylim(-70, 0)

f, ts, Sxx = spectrogram(mix.mean(axis=1)[:: 2], fs=sr / 2, nperseg=4096, noverlap=2048)
keep = (f > 50) & (f < 2500)
ax[3].pcolormesh(ts, f[keep], 10 * np.log10(Sxx[keep] + 1e-12), shading="auto", cmap="viridis", vmin=-110, vmax=-40)
ax[3].set_yscale("log"), ax[3].set_ylabel("Hz")
for v in sc["voices"]:
    ax[3].axhline(440 * 2 ** ((v["midi"] - 69) / 12), color="w", lw=0.3, alpha=0.5)
for c in sc["movement_cuts_breath"]:
    for a in ax:
        a.axvline(c * B, color="c", lw=0.8, ls="--")
ax[3].set_xlabel("seconds (dashed: equinoxes and the June solstice)")
fig.tight_layout()
dest = Path(__file__).resolve().parent.parent / "figs" / f"{name}_check.png"
dest.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(dest, dpi=90)
print(dest)

if "covariates" in sc:
    # layer 2: each covariate per voice and breath, beside the loudness of the stem it drives
    stems = {k: sf.read(W.HEAVY_OUT / "meridian" / f"{name}_stems" / f"{k}.flac")[0] for k in ("organ", "sea", "ice")}
    fig, ax = plt.subplots(5, 1, figsize=(14, 15), sharex=True, gridspec_kw={"height_ratios": [1, 1, 1, 1, 0.9]})
    C = sc["covariates"]
    ext = [0, T, len(lats) - 0.5, -0.5]
    for a, (col, title, cmap, lo, hi) in zip(ax, [
            ("air_max_c", "air, daily max (C, ERA5): the organ's registration", "RdYlBu_r", -40, 35),
            ("air_min_c", "air, daily min (C, ERA5): the in-breath's body", "RdYlBu_r", -40, 35),
            ("sst_c", "sea surface (C, OISST): the sea voice", "RdYlBu_r", -2, 30),
            ("ice_frac", "sea-ice concentration (NSIDC CDR): the lid on the sea, and the glass", "Blues", 0, 1)]):
        m = np.array([[np.nan if C[str(la)][col] is None else C[str(la)][col][k] for k in range(sc["n_breaths"])]
                      for la in lats], dtype=float)
        im = a.imshow(m, aspect="auto", cmap=cmap, extent=ext, vmin=lo, vmax=hi, interpolation="nearest")
        a.set_yticks(range(len(lats)), [f"{la:+d}°" for la in lats])
        a.set_title(title)
        fig.colorbar(im, ax=a, pad=0.01)
    for k, x in stems.items():
        ax[4].plot(np.arange(len(x) // hop) / 4, rms(x), lw=0.6, label=k)
    ax[4].set_ylim(-80, -10), ax[4].legend(loc="lower right"), ax[4].set_ylabel("stem dBFS")
    ax[4].set_xlabel("seconds")
    fig.tight_layout()
    dest2 = dest.with_name(f"{name}_layer2.png")
    fig.savefig(dest2, dpi=80)
    print(dest2)
