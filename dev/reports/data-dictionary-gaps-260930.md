# Data dictionary gap review, 30 September 2026

Scope: the 10 `data-dict.yaml` files (26 tables, 236 columns) at commit `5ecf835`, read against the parquet tables they describe, plus a check of which data files have no dictionary at all. Findings only; no dictionary was edited.

Authorship: written by Claude (a cloud session). Every count below comes from `dev/dictionary/dd_audit.py` and two follow-up queries, described under "Method". The audit script over-reports on nulls (it looks for keywords), so I checked each flagged column by hand before listing it.

## Round 2 update (30 September 2026, later the same day)

Text fixes for the `climate_daily` findings were made in `data/parquet/data-dict.yaml` (wording only, validated). One correction to this review:

- **DD-01 was partly documented.** I wrote that the dictionary did not say Summerland lacks rain and snow. The table's `details` did say something ("flagged missing on 3,116 of 5,479 days"), which I missed because I read column descriptions and not the table note. It was misleading rather than absent: it read as if the other 2,363 days had values. By station, Summerland has **no** rain or snow value on any day (3,116 flagged M, 2,363 empty with no flag). The note now says so. DD-02, DD-03, DD-04 and DD-09 were confirmed and fixed for `climate_daily`. The other findings (DD-05 to DD-08, DD-10 to DD-14) are unchanged and not yet applied.

## Round 3 update (30 September 2026, later still)

Graham approved field additions, unified spellings and edits to the mapping dictionaries. Status of every finding:

| ID | Status |
|---|---|
| DD-01, 02, 03, 04, 09 | Fixed in round 2 (`climate_daily` wording) |
| DD-07 | Fixed: units on `pan`, `ice_frac`, `warmth_day`, `warmth_night` |
| DD-08 | Fixed: descriptions for the four tables |
| DD-10 | Fixed: descriptions for 20 more columns (the "19" above was a miscount; 20 were fixed, and the round 2 pass had already covered five in `climate_daily`) |
| DD-11 | Fixed: `percent` → `%` (14), `degrees C` → `°C` (7), bare `ppm` → `ppm (µmol per mol of dry air)` (2). Descriptive units and the `(WGS 84)` notes are unchanged. |
| DD-14 | Fixed: `range` on `modis_gpp.pixel` and the four Meridian `lat` columns (the validator accepts a range on an ID column and checks the data against it) |
| DD-12 | Left as it is. The two record sets carry a date and the mapping sets a semantic version; the difference looks deliberate. |
| DD-13 | Left as it is. Adding `relationships` and `glossary` blocks is content work, not a fix. |
| DD-05, DD-06 | Not done. Dictionaries for the Superior Ice, Meridian and storm source JSON need new parquet tables and a build step, which belongs in the kit spec. |

`dev/dictionary/dd_lint.py` now checks rules 1 to 5 in its docstring and passes on the edited dictionaries. Run against the originals on `main` it reports 56 problems, so it also detects a sync that restores an old copy. The ten `dictionary/*.html` pages were regenerated with `data-dict render`; the original YAML from `main` reproduced each committed page byte for byte first, so the page changes come only from the edits.

## TL;DR

- **The dictionaries are already strong.** All 10 validate against their data (`data-dict validate-data`), 179 of 236 columns state a range, 121 state units, and the Water Year and Climate Pair notes explain their own nulls in plain words ("Empty for lake-level-only days").
- **The biggest gap is one table.** `climate_daily` (ECCC weather stations) has 15 columns with no explanation for their many empty values (four of them have no description at all), and one fact that changes how a reader would use it: the Summerland station (979) never reports rain or snow separately. Its `total_rain` and `total_snow` are empty on all 5,479 days.
- **Second gap: whole data sets with no dictionary.** The Superior Ice and Meridian source data (`data/icecover/*.json`, `data/meridian/*.json`) and the three Climate Pair storm files have none. The mapping dictionaries describe what each piece did with the data, not the data itself.
- **Smaller, mechanical gaps:** 5 quantities without units, 4 tables without a description, 9 numeric columns without a range (mostly identifiers, but the four Meridian `lat` columns are real), mixed unit spellings, and two different version conventions.
- **False alarms I ruled out:** two "value outside stated range" hits (`hydrometric_daily.level` and `superior-ice-short events.t`) are float32 rounding at the third decimal, not errors.

## Findings

Priority: **A** = would mislead a reader or a re-user of the data; **B** = missing information a careful reader expects; **C** = consistency.

| ID | Pri | Gap | Where | Evidence |
|---|---|---|---|---|
| DD-01 | A | Station 979 never reports rain or snow; not stated | `climate_daily.total_rain`, `total_snow` | 5,479 of 5,479 rows empty for station 979; 718 of 5,479 (13%) for station 1100 |
| DD-02 | A | Station 1100 (Billings) has no humidity; station 979 has mostly none of `snow_on_ground` | `climate_daily.min_rel_humidity`, `snow_on_ground` | 100% empty for 1100; 90% empty for 979 on snow on ground; 30% empty for 979 on humidity |
| DD-03 | A | Empty-value meaning is unstated on 15 `climate_daily` columns | mean, min and max temperature, precipitation, rain, snow, snow on ground and humidity (8), and their 7 flag columns | 733–7,136 empties each; descriptions absent or silent about them |
| DD-04 | A | Five columns have no description at all | `climate_daily`: `mean_temperature`, `min_temperature`, `max_temperature`, `total_rain`; `stations.longitude` | dictionary read |
| DD-05 | B | No dictionary for the Superior Ice and Meridian source data | `data/icecover/superior_daily.json`, `superior_grid_meta.json`, `superior_regions.json`; `data/meridian/meridian_100w_ds2023.json` | file list; no parquet or YAML for them |
| DD-06 | B | No dictionary for the Climate Pair storm files or annual-max source JSON | `data/climate/storms_*.json`, `kettle_annual_max.json`, `indices_monthly.json` | The parquet copies are documented; the JSON originals are not. |
| DD-07 | B | Five quantities have no units | `superior-ice(-short).regions.pan`; `meridian-layer2-wide-long.voice_breaths`: `ice_frac`, `warmth_day`, `warmth_night` | dictionary read |
| DD-08 | B | Four tables have no description | `climate-pair-(atlantic, pacific).years`; `meridian-(daylight, layer2-wide-long).voices` | dictionary read |
| DD-09 | B | Flag columns explain "empty when there is none" for one flag but leave `total_rain_flag` with no description | `climate_daily.*_flag` | `total_rain_flag` has values (`M`, `T`) and no text |
| DD-10 | B | 19 more columns have no description | dates, `year`, `bar`, `name`, `place`, `day`, `volcanoes.name` | Most are self-explanatory; each should still say what it is (for example the date's time zone) |
| DD-11 | C | Units are spelled several ways | `%`, `percent`, `percentage points`; `°C`, `degrees C`; `degrees east`, `degrees east (WGS 84)` | 14 columns use `percent`, 2 use `%`; 11 use `°C`, 7 use `degrees C` |
| DD-12 | C | Two version conventions | `version: {date: …}` in the two record sets, `version: {number: …}` in the mapping sets | dictionary read |
| DD-13 | C | Optional blocks are used unevenly | `glossary` in 6 of 10, `relationships` in 7 of 10, `examples` on 24 of 236 columns | key count |
| DD-14 | B | The `lat` columns in both Meridian dictionaries (4 columns) and `modis_gpp.pixel` have no range | `meridian-*.voices.lat`, `voice_breaths.lat`, `modis_gpp.pixel` | dictionary read; `bar` is an identifier and needs none |

### Detail

**DD-01 to DD-03: `climate_daily`.** The table holds two stations, Billings (1100) and Summerland CS (979), 5,479 days each. Their empties are very different:

| Column | Billings (1100) empty | Summerland (979) empty |
|---|---|---|
| mean and max temperature | 715 (13%) | 34 (1%) |
| total precipitation | 718 (13%) | 470 (9%) |
| total rain, total snow | 718 (13%) | 5,479 (100%) |
| snow on ground | 710 (13%) | 4,944 (90%) |
| min relative humidity | 5,479 (100%) | 1,657 (30%) |

A reader of the dictionary currently learns none of this, and would reasonably assume a rain column holds rain. I do not know why 979 lacks rain and snow (probably the station's instrument or reporting scheme); the dictionary should say what the data show and cite ECCC only once someone has checked the station's metadata. `total_precipitation` and `total_rain` also disagree in coverage, which matters to the Water Year pieces if they use either.

Proposed text, one line per column, in the style the file already uses, for example: "Daily total rain. Empty on every day for station 979 (Summerland CS), which reports precipitation only as a total. About 13% empty for station 1100."

**DD-05 and DD-06: undocumented sources.** The Water Year and Climate Pair *records* have parquet tables and dictionaries, which the site's CI validates. Superior Ice and Meridian do not: their inputs sit in JSON with no schema, units or provenance beyond the fetch script's docstring. `superior_grid_meta.json` already names `ice_units` and `sst_units`, so part of a dictionary exists in the data itself. Recommendation: extend `scripts/build_parquet.py` (or a sibling) to produce parquet tables for them, so the same CI check covers them. That is a design decision, so it belongs in the kit discovery spec, not here.

**DD-07: units for dimensionless quantities.** The convention already used elsewhere is a description in the `units` field ("0 to 1 (percentile)", "0 to 1 (share of a high day)"). `pan` (−1 left to 1 right) and the Meridian fractions can follow it: `units: -1 to 1 (left to right)`, `units: 0 to 1 (fraction)`.

**DD-11: consistency.** Choose one spelling for each unit and keep it. Suggested: `°C`, `%` (for a share) and `percentage points` (for a difference), and `degrees east/north (WGS 84)` wherever the datum is known. Whether the pipeline or the site's generated `dictionary/*.html` pages depend on the exact strings is unchecked, so normalise only after `pytest tests` and the `data-dict` job pass.

## What the dictionaries already do well

- Every mapping table ties back to the locked render by SHA-256 (in `details`), so the dictionary cannot silently describe different data from the sound.
- R, D and S tags (retrieved, derived, simulated) appear in the descriptions, in the same words as the track cards.
- The withheld series (Wells Dam counts) are handled correctly: the dictionary says they are fetched, not stored, and does not reproduce their values.
- Enums list their values with a sentence each (for example the WSC data symbols).

## Method

- `dev/dictionary/dd_audit.py` parses each YAML and its parquet and reports: undocumented parquet columns (none), dictionary columns missing from the data (none), missing descriptions, quantities without units, numeric columns without a range, data outside stated ranges, and nulls without an explanation. Run it with the repo's venv: `python dev/dictionary/dd_audit.py`.
- **The null check is a keyword heuristic and over-reports.** It flagged 30 columns; after reading each description I kept the ones that give no explanation. Columns whose description says "empty", "blank", "missing" or gives a count are not listed as findings.
- Range checks use the stored floats; the float32 rounding hits are explained above.
- All 10 dictionaries validated with `data-dict-yaml==0.0.3`, the version CI pins.
- Not checked: whether descriptions are *accurate* against the agencies' own documentation (for example ECCC flag meanings, WSC symbol definitions). That needs the source documents, and a reviewer with the domain knowledge; Graham's read of the hydrometric entries would be more reliable than mine.

## Proposed order of work (for approval)

1. DD-01 to DD-04 and DD-09 in `data/parquet/data-dict.yaml`: text only, no schema change, validated by CI. Smallest change with the biggest effect.
2. DD-07, DD-08 and DD-10: one-line additions in the mapping dictionaries.
3. DD-11 to DD-13: agree the conventions once, in a short style note, and apply them.
4. DD-05 and DD-06: defer to the kit discovery spec.

**Port-back.** The parquet files are generated by `scripts/build_parquet.py` and `scripts/export_mapping.py`, but the YAML dictionaries look hand-written. I could not confirm from the repository where the YAML source of truth lives (the build script's docstring points to a vault path, `data/water-year.data-dict.yaml`). Edits to `data/parquet/data-dict.yaml`, `data/climate/parquet/data-dict.yaml` and `tracks/mapping/*/data-dict.yaml` need porting to whichever copy the vault treats as the source. `tracks/mapping/` is a synced folder, so an unported edit there would be overwritten.
