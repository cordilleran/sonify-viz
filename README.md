# sonify-viz

A learning workbench for turning environmental data into music and pictures. It is a starting scaffold, not a finished instrument: Graham brought the questions, the rivers and the domain knowledge, and Claude Code led the music theory and wrote the code. The site's [How this was made](https://cordilleran.github.io/sonify-viz/about.html) page sets out who did what.

- **Water Year Rings:** two pieces built from one hydrologic year (October 1, 2023 to September 30, 2024) in southern British Columbia, the Granby River at Grand Forks and Okanagan Lake and River. River gauges, weather stations, satellite plant productivity and Wells Dam sockeye counts drive recorded acoustic instruments. A synced "tree ring" page shows the year filling in as you listen.
- **Climate Pair:** two pieces on the global record from 1958 to 2025, one year per bar: CO₂, ocean heat, ENSO, the PDO or AMO, and storm tracks, heard from the Pacific and from the Atlantic. A year-ring spiral on the page draws each year as you hear it: ocean temperature as colour, ENSO as thickness, storms as sparks.
- **Meridian Chorus:** one meridian (100° W) from pole to pole, a voice every 15 degrees of latitude, through one year from solstice to solstice. Day length sets each note; layer 2 adds air, sea and ice.
- **Superior Ice Year:** Lake Superior's 2025-26 ice season, 1 November to 15 June, as eight regional voices on a map of the lake: ice, water temperature, air, sunlight, wind, snow, rain and birds, with the ghost of the lake's median year (v1.0). A 4K shaded-relief figure of the lake floor, with its method and code, is on the page.

**Site:** <https://cordilleran.github.io/sonify-viz/>

## What's here

| Path | Contents |
|---|---|
| `index.qmd`, `listen.qmd`, `methods.qmd`, `styles.scss`, `_quarto.yml` | Quarto website source; GitHub Actions renders and publishes it |
| `listen/` | the Water Year Rings listening companion (one HTML file, no framework), its data, audio and self-hosted fonts |
| `audio/`, `climate/` | the Climate Pair audio, its generated listening guides, and the spiral visualizer (`viz.js`, one canvas script, no framework, with its data `viz_*.json`) |
| `scripts/` | the Python pipeline: data pulls, harmony and instrument engine, the two scores, QA plots, export for the companion |
| `data/` | cached data used by the pieces; restricted series (Wells Dam counts, sunspots, ocean heat content) are fetched, not stored |
| `figs/` | QA plots: each data lane against each instrument's loudness |
| `samples_manifest.csv` | sources and licences for every instrument and bird recording |
| `tests/` | the engine's test suite (`pytest tests`, about a second, no data or samples needed); run on every push |
| `renders.lock.json` | each track's version, seed and content hashes; `python scripts/renders.py verify` re-renders and compares |
| `tracks/` | one card per published track (version, changelog, records, mapping, credits) and the album list; rendered into `tracks.qmd` by `scripts/export_cards.py` |
| `data/parquet/` | the records as tidy parquet tables, with their data dictionaries (`data-dict.yaml`, [data-dict](https://data-dict.tidyverse.org/) format); the site's build validates the data against them |
| `meridian/`, `superior-ice/` | the Meridian Chorus and Superior Ice Year pages (one HTML file each, no framework), their data and audio; `meridian.qmd` and `superior-ice.qmd` frame them in the site |
| `variants/`, `remixes/` | named variants of a track, and remixes of published tracks (see `CONTRIBUTING.md`) |

## Rebuild

Python 3.13, the packages in `requirements.txt`, `ffmpeg`, and [Quarto](https://quarto.org).

**Hear it first, in a minute, with no downloads:** `pip install -r requirements.txt`, then `python scripts/demo.py`. It plays the Granby River's 2024 water year on synthesizers through the same harmony engine, in about 45 seconds, and writes `rendered/demo_wy2024.wav`.

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
python fetch_climate.py            # climate records, storm tracks, sea ice, Kettle peaks
python climate_pair.py pacific     # and: atlantic
python climate_check_plot.py pacific
python export_climate_guide.py
python export_climate_viz.py      # data for the spiral visualizer
cd .. && quarto preview
```

Samples go to `samples/` and renders to `rendered/` (both git-ignored); set `SONIFICATION_SAMPLES` or `SONIFICATION_HEAVY` to put them elsewhere. Renders are seeded and, with the pinned packages, repeat byte for byte. Any water year the records cover renders with `python pilot_granby_wy2024.py wy2019`. To contribute a listening note, a remix or a fix, see `CONTRIBUTING.md`.

## Licences

- **Code:** Mozilla Public License 2.0 (`LICENSE`).
- **Rendered audio and figures:** Water Year Rings is CC BY-SA 4.0 (it incorporates CC BY-SA bird recordings, credited in `samples_manifest.csv`). Climate Pair is CC BY-NC-SA 4.0 (it derives in part from CC BY-NC sunspot data). See `LICENSE-media`.
- **Instrument samples:** VSCO 2 Community Edition, Versilian Studios, CC0. Not redistributed here; `fetch_samples.py` downloads them.
- **Fonts:** Gloock, Atkinson Hyperlegible and JetBrains Mono, SIL Open Font License 1.1.
- **Data:** Environment and Climate Change Canada / Water Survey of Canada: contains information licensed under the [Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada). NASA MODIS MOD17A2HGF v061 ([doi:10.5067/MODIS/MOD17A2HGF.061](https://doi.org/10.5067/MODIS/MOD17A2HGF.061)) via the ORNL DAAC. Columbia River DART, Columbia Basin Research, University of Washington (Wells Dam data courtesy of Douglas County PUD). Climate Pair sources are listed on its page.

To cite this work, see `CITATION.cff`. Built by Graham Watt with Claude Code.
