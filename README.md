# sonify-viz

A workbench for turning environmental data into music and pictures. The first worked example is **Water Year Rings**: two pieces built from one hydrologic year (October 1, 2023 to September 30, 2024) in southern British Columbia, the Granby River at Grand Forks and Okanagan Lake and River. River gauges, weather stations, satellite plant productivity and Wells Dam sockeye counts drive recorded acoustic instruments. A synced "tree ring" page shows the year filling in as you listen.

**Site:** <https://cordilleran.github.io/sonify-viz/>

## What's here

| Path | Contents |
|---|---|
| `index.qmd`, `listen.qmd`, `methods.qmd`, `styles.scss`, `_quarto.yml` | Quarto website source; GitHub Actions renders and publishes it |
| `listen/` | the listening companion (one HTML file, no framework), its data, audio and self-hosted fonts |
| `scripts/` | the Python pipeline: data pulls, harmony and instrument engine, the two scores, QA plots, export for the companion |
| `data/` | cached daily data used by the two pieces (the Wells Dam counts are fetched, not stored) |
| `figs/` | QA plots: each data lane against each instrument's loudness |
| `samples_manifest.csv` | sources and licences for every instrument and bird recording |

## Rebuild

Python 3.13, the packages in `requirements.txt`, `ffmpeg`, and [Quarto](https://quarto.org).

```bash
pip install -r requirements.txt
cd scripts
python fetch_granby.py             # Granby, Burrell Creek, Billings (cached in data/)
python fetch_okanagan.py           # Okanagan gauges, Summerland, MODIS GPP, Wells Dam (DART)
python fetch_samples.py            # ~500 MB VSCO 2 CE subset + bird recordings -> samples/
python pilot_granby_wy2024.py      # ~30 s to render ~7 min of audio -> rendered/
python pilot_okanagan_wy2024.py
python pilot_check_plot.py granby_wy2024
python export_companion.py         # -> listen/
cd .. && quarto preview
```

Samples go to `samples/` and renders to `rendered/` (both git-ignored); set `SONIFICATION_SAMPLES` or `SONIFICATION_HEAVY` to put them elsewhere. Renders are seeded and, with the pinned packages, repeat byte for byte.

## Licences

- **Code:** Mozilla Public License 2.0 (`LICENSE`).
- **Rendered audio and figures:** CC BY-SA 4.0 (`LICENSE-media`), because the audio incorporates CC BY-SA bird recordings, credited in `samples_manifest.csv` and on the Methods page.
- **Instrument samples:** VSCO 2 Community Edition, Versilian Studios, CC0. Not redistributed here; `fetch_samples.py` downloads them.
- **Fonts:** Gloock, Atkinson Hyperlegible and JetBrains Mono, SIL Open Font License 1.1.
- **Data:** Environment and Climate Change Canada / Water Survey of Canada: contains information licensed under the [Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada). NASA MODIS MOD17A2HGF v061 ([doi:10.5067/MODIS/MOD17A2HGF.061](https://doi.org/10.5067/MODIS/MOD17A2HGF.061)) via the ORNL DAAC. Columbia River DART, Columbia Basin Research, University of Washington (Wells Dam data courtesy of Douglas County PUD).

To cite this work, see `CITATION.cff`. Built by Graham Watt with Claude Code.
