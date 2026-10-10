# The Wheel: a variant on Arctic Round, with its picture

The Wheel is a variant on Arctic Round and the first of the set to be published; the Round, the main piece, is in preparation. This folder is The Wheel's page: a map of Arctic sea ice, 1978 to 2026, on the same clock as the audio. (The folder and file names say `bside`, its working name.) One bar is one ice year (October to September), 16 seconds a bar, 48 bars and a short coda. Eight organ notes advance one note a week, so a full turn takes eight weeks, and the ice decides how many of the eight can sound. A cello's register follows ice volume; a bass pedal is present while the year's mean volume is high; the cello and bass swell with the year's extent; open water adds the organ's upper octave.

Open `index.html` from the site (it needs the site's `../listen/fonts/` folder and a web server; a `file://` open will not load the data). The audio (19 MB) loads when you press Play, not when the page opens; a slider move before that is remembered.

## How the picture follows the sound

The exporter does not recompute the music's rules. `scripts/export_bside_viz.py` calls the same functions as `scripts/arctic_bside.py` (`rubato_weights`, `active_slots`, `open_water`, `swell`, `cello_index`, `bass_gate`), and `tests/test_arctic_bside.py` fails if the exporter keeps its own copy of the rubato, open-water, swell, cello or bass rules. The page's drawing code repeats a few display constants (the halo curve, the volume meter's range, the bass label). The wheel follows the **total** ice extent, not particular seas: the highest and lowest notes fall silent first and the middle notes hold longest. It is not a map of regions.

## Where everything comes from

| What | Source | Label |
|---|---|---|
| Sea ice concentration (weekly frames at half resolution, each year's maximum and minimum grids at full 25 km, all in 5 % steps) and daily total extent | NSIDC Sea Ice Index v4 (G02135), Fetterer, Knowles, Meier, Savoie, Windnagel, Stafford, doi:10.7265/a98x-0f50 | R |
| Ice volume (the year's mean and the cello's register steps only; the series is not republished) | PIOMAS v2.1, Polar Science Center, University of Washington (Zhang and Rothrock 2003; Schweiger et al. 2011) | M (a model) |
| Terrain and sea floor | GEBCO_2025 Grid, GEBCO Bathymetric Compilation Group 2025, doi:10.5285/37c52e96-24ea-67ce-e063-7086abc05f29 (not for navigation; GEBCO does not endorse this page) | R |
| Land snow, green and melt | Degree-day model on ERA5 through Open-Meteo.com (CC BY 4.0; the free API is for non-commercial use). Generated using Copernicus Climate Change Service information 2026; contains modified Copernicus Climate Change Service information 2026 | M |
| Glaciated areas, coastlines | Natural Earth (public domain), pinned to a commit in `fetch_arctic_glaciers.py` | R |
| Organ and cello samples | VSCO 2 CE, Versilian Studios (CC0) | |
| d3 7.9.0 (`vendor/`) | Mike Bostock, ISC licence | |

Extent before mid-1987 is recorded every other day and 2 December 1987 to 13 January 1988 has no data; those days are filled by interpolation (flagged `observed = 0` in the engine's data). The disc at the pole is not measured: the satellites' orbits leave a round area unseen (radius about 600 km until August 1987, 305 km until the end of 2007, 95 km until the end of 2024, 140 km since, measured from the grids). The page draws it as full ice inside a dashed circle, and NSIDC's extent counts it as ice. The record starts on 26 October 1978, so the first weeks of the 1979 bar repeat that day's value. The land layer is coarse: 29 points about 650 km apart (the page reads the count from `arctic_land.json`).

**Per-file terms.** `assets/arctic_land.json` is derived from Open-Meteo's free API, which is for non-commercial use; if you reuse it commercially, regenerate it with a commercial Open-Meteo plan. The other assets follow the credits above.

## Reproduce

Needs: Python 3.13 with the pinned versions in the repo's `requirements.txt`, plus `pip install -r arctic-bside/requirements-fetch.txt` for steps 2 to 4 (`rasterio`, `Pillow` and `openpyxl`, which are not needed to listen), `ffmpeg`, about 2 GB of disk for the NSIDC grids and 500 MB for the sample library, and these environment variables when you want the large files elsewhere: `SONIFICATION_RAW` (downloads), `SONIFICATION_HEAVY` (WAVs), `SONIFICATION_LIGHT` (MP3 and score JSON), `SONIFICATION_SAMPLES` (instrument audio).

1. `python scripts/fetch_samples.py` (the VSCO sets, including the organ and cello).
2. `python scripts/fetch_arctic.py` (extent, PIOMAS, and the other series; the global SST file is optional and only the main piece uses it).
3. `python scripts/fetch_arctic_grids.py` (about 1.7 GB the first time; resumes), `python scripts/fetch_arctic_terrain.py` and `python scripts/fetch_arctic_glaciers.py`.
4. `python scripts/fetch_arctic_land.py` then `python scripts/arctic_land_model.py` (29 points; one run is enough on a fresh Open-Meteo daily quota, and a rerun fetches only the points still missing).
5. `python scripts/arctic_bside.py --set organ_gain=6.5 --set bass_gain=1.1 --set name=arctic_bside_v2` renders take 3, the published audio (seed 2026; `assets/arctic_bside_v2_score.json` holds the parameters that made it, and from this version on also the rule constants).
6. `python scripts/export_bside_viz.py --out arctic-bside/src` writes the picture's state, and `python scripts/build_arctic_bside_site.py .` (from the repo root) assembles `arctic-bside/`. `index.html` is a build product: edit `src/app.html`, not `index.html`.
7. `pytest tests/test_arctic_bside.py` checks the wheel's rule and that the picture follows the engine. It skips if step 2 has not been run.

## Design notes

The Wheel is an eight-note wheel in the process-music manner: the order and the pace never change, only which notes the ice can still hold. The decisions that matter: the number of notes sounding is piecewise in total extent (2, 6, 7 and 8 notes at 3.4, 7.2, 12 and 17.5 M km², so 1979 and 2020 are not one note apart); silenced notes are rests, not fades, so the notes that remain keep the pitch and touch they had in 1979; the weekly pulse presses 8 % in freeze-up and drags 10 % in melt while every bar stays exactly 16 s; the cello's register and the bass follow ice volume, and open water is told apart from thinning by the organ's upper octave and a brighter room. Warming is deliberately not in this piece (the Round will carry it).

## Licence

The audio (`assets/arctic_bside_v2.mp3` and its score) and the picture's derived files are CC BY-SA 4.0 (see the repo's `LICENSE-media`); the code in `scripts/` and `src/` is MPL-2.0. `assets/arctic_land.json` is derived from Open-Meteo's free API, which is for non-commercial use, so regenerate it under a commercial plan before reusing it commercially. Every dataset keeps its provider's terms (credits above).

Claude Code (Sonnet 5.5) built this; Graham Watt has reviewed it.
