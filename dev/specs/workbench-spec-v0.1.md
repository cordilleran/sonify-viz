# Workbench spec, v0.1 (draft for review)

**Status:** draft. No code has been written for the workbench. Nothing here is decided until Graham reviews it.
**Date:** 2026-10-01 · **Author:** Claude Code (cloud session 4) · **Branch:** `claude/laughing-fermat-57fuql`

## 1. Purpose

A local, browser-based **workbench** for learning how data becomes music. You bring a table (from R or Python), step through each transformation, see and change the choices, and hear two versions side by side, including blind, before keeping either.

The aim is **understanding the steps and algorithms**, not learning to program. Code is shown in fold-downs so a choice can be traced to the line that makes it, but every choice can be changed with a control.

**Non-goals for v0.1**
- Not a replacement for the existing track scripts. Published tracks keep rendering exactly as now.
- Not a public, hosted tool. It runs on Graham's machine.
- No sample import or mixing UI yet (stage 8 is synth-only in milestone 1; see section 9).
- No LLM features.

## 2. Findings that shape the design

All from reading `scripts/demo.py`, `harmony.py`, `timegrid.py` and running the demo in the cloud container on 2026-10-01 (Python 3.11.15, numpy and scipy unpinned versions from PyPI; the repo pins Python 3.13 and numpy 2.5.3).

1. **`demo.py` is a complete data-to-WAV path in 100 lines** for the Granby River (flow plus Billings temperature, WY2024). It needs no samples. It is the base case.
2. **It renders deterministically.** Two consecutive runs produced byte-identical WAVs (md5 equal). The 51.75 s stereo file at 44.1 kHz took about 33 s to render for 61 bars, which is about 0.5 s of compute per bar. *Estimate, not measured:* a 10 s preview (about 13 bars) would take roughly 7 s.
3. **Many choices are hard-coded constants inside `main()`.** They are the content the workbench must expose. Inventory in section 4.
4. **The stages already exist as functions**, but they are interleaved in one script. `harmony.py` holds the music rules (mode, chord, voice leading); `timegrid.py` holds time and smoothing; `records.py` loads data from cached JSON. Refactoring is mostly *separating* stages, not inventing them.
5. **Input today is JSON from the Water Survey of Canada and ECCC.** A CSV or Parquet ingest path does not exist yet and is the new piece for the R hand-off.

## 3. Principles

1. **Every choice is visible.** Nothing that changes the sound is hidden in a default.
2. **Every choice is recorded** with its value, a reason in plain language, and the alternatives not taken.
3. **Nothing is final until promoted.** Experiments live in a ledger; the published site is untouched.
4. **A comparison changes one thing.** A/B forks differ in a single stage so the cause of any difference is known.
5. **Accessible from the first version** (section 10). A tool about hearing data must not need sight alone.

## 4. The stage model

Nine stages, each a card in the interface. "Code today" points at the lines of `scripts/demo.py` (or the module) where the Granby base case does that work.

| # | Stage | The question it answers | Code today | Layer-level EDA shown |
|---|---|---|---|---|
| 1 | **Ingest** | Which columns, which time axis, what units? | `R.wsc_series`, `R.climate_series` (l. 45-46) | Column types, range, row count, date span |
| 2 | **Audit** | What can be trusted? | `R.check_coverage` (l. 47), `R.in_year(fill="interp")` (l. 48-49) | Missingness strip, distribution, outliers |
| 3 | **Resample** | How much data per musical bar? | `per_bar`, `pairs` (l. 36-40, 50-52) | Before and after, bar boundaries |
| 4 | **Transform** | What shape should the signal take? | `smooth(...,15)`, `doy_percentile`, `norm01`, `np.log(q)` (l. 50-52) | Raw vs transformed overlay; for percentile, the seasonal normal |
| 5 | **Segment** | What phases does the data pass through? | `phase_day` thresholds, `H.phase_bars(min_run=6)` (l. 55-62) | Phase bands drawn on the series |
| 6 | **Map** | Which signal drives which musical dimension? | `bright`, `anom`, `level` into mode, cutoff, pluck count (l. 53, 77, 81) | A mapping table: signal, range, dimension, curve |
| 7 | **Compose** | What are the musical rules? | `H.mode_track`, `H.chord_track`, `H.voice_lead`, `PROG`, `TONIC` (l. 28-33, 53, 63, 73) | Mode ribbon, chord strip, density strip |
| 8 | **Sound** | Which instruments and processing? | `Y.pad_note`, `Y.sub_note`, `Y.pluck_note`, `Bus` (l. 68-85) | Per-layer spectrum and loudness |
| 9 | **Render** | Length, tempo, mix, output | `BAR_S`, `master`, `make_ir` (l. 32, 89) | Waveform, duration, loudness |

**Layers.** In the base case there are three layers (pad, sub, plucks). Stages 3 to 7 can be viewed per layer, so a user can add one layer at a time. This is the "build up a complex track" teaching path.

### Inventory of hidden choices in the Granby demo

Pattern Analysis of `scripts/demo.py` as of this commit (line numbers will drift). These are the first things the workbench turns into controls.

| Choice | Value in code | Stage | Line |
|---|---|---|---|
| Bar length in data | 6 days (3-day bars paired) | 3 | 36-40 |
| Smoothing window, anomaly signal | 15 days | 4 | 50 |
| Smoothing window, temperature | 15 days | 4 | 51 |
| Brightness blend | 0.7 day length + 0.3 temperature | 4 and 6 | 51 |
| Day-length normalisation range | 0 to 100 (units not stated in code) | 4 | 51 |
| Flow to level | `norm01(log(q))` | 4 | 52 |
| Mode range | `lo=1, hi=4`, phrase of 4 bars | 7 | 53 |
| Mode step limit and floor | `max_step=1`, `floor=1` (defaults in `harmony.py`) | 7 | `harmony.py` l. 68 |
| Anomaly weight on mode | `anomaly * 2.4`, clipped to ±1.2 | 6 and 7 | `harmony.py` l. 73 |
| Flow smoothing for phases | 9 days | 4 and 5 | 55 |
| Phase thresholds | level < 0.1, > 0.5; slope > 0.004, < -0.003; level > 0.15 | 5 | 58-61 |
| Day-of-year window for "dormant" | > 300 or < 60 | 5 | 58 |
| Minimum phase run | 6 | 5 | 62 |
| Chord loops per phase | `PROG` (5 loops of 4 degrees) | 7 | 28-31 |
| Bars per chord | 2 | 7 | 63 |
| Tonic | MIDI 50 (D3) | 7 | 33 |
| Voice-leading range | MIDI 57 to 76 | 7 | 73 |
| Pad brightness | cutoff = 700 + 1800 × level | 6 and 8 | 77 |
| Plucks per bar | round(level × 4) | 6 | 81 |
| Bar duration | 0.75 s | 9 | 32 |
| Reverb | `make_ir(2.8, bright=0.5)` | 9 | 89 |
| Random seed | 7 | 8 | 67 |

That is **22 hard-coded choices** in a 100-line script (some are explained in the file's docstring; most are not). Two of them (the 0.7/0.3 blend and the 0 to 100 day-length range) have no stated reason in the code. They are good candidates for the first A/B experiments.

## 5. Decision record

Each stage writes one record. A run is the ordered list of these records plus the audio.

```yaml
stage: transform
layer: pad
choice: smoothing_window_days
value: 15
reason: "Removes day-to-day noise so the mode drifts rather than flickers."
alternatives_not_taken:
  - {value: 3, why: "Follows storms; mode would change too often."}
  - {value: 30, why: "Hides the freshet's rise."}
source: scripts/demo.py:50
set_by: default        # default | user | fork
changed_from: null
```

- `reason` and `alternatives_not_taken` are written once per choice for the **default** by Claude (and editable by Graham). A user's change prompts for a one-line reason, which is optional.
- Records are plain YAML so they diff cleanly and can be pasted into a track card's `harmony` text.
- Records are **data about choices**, not a claim that a choice is right.

## 6. Experiments, forks and blind A/B

### 6.1 Run and ledger

A **run** is `{settings (all decision records), code version, seed, audio file, audio hash, created}`. The **ledger** is a folder of runs plus an index (`workbench/experiments/ledger.csv`). Rendered audio stays out of git (`rendered/` is already ignored).

### 6.2 Fork

A **fork** copies a run and changes **one choice** (for example `smoothing_window_days: 15 → 3`). The interface enforces one change per fork. A "multi-change" run is allowed but is labelled as a variant, not an A/B.

### 6.3 Blind A/B protocol

Goal: reduce my (the user's) bias when choosing between two renders. This protocol is a default, not the only mode.

1. **Same length and loudness.** Both clips are cut to the same duration and matched in integrated loudness (LUFS, or RMS if LUFS is unavailable), because the louder clip is usually preferred. Peak is limited to avoid clipping.
2. **Random assignment.** The labels "A" and "B" are assigned at random with a seed stored in the ledger but not shown.
3. **Hidden details.** File names, parameters and the decision diff are hidden until the verdict.
4. **Two questions, asked separately.** *Which do you prefer?* and *Which tells the river's story more clearly?* These are different questions and often get different answers; recording both is part of the learning.
5. **"Can't tell" is allowed**, and is a valid result.
6. **Catch trial (optional, on by default after the first few sessions).** Now and then the pair is A against A (identical). A confident preference between identical clips shows how much to trust the other verdicts.
7. **Replay is unlimited,** and each replay is logged.
8. **Reveal.** After the verdict, the tool shows which fork was which and which single choice differed, then asks for an optional one-line note.
9. **Log.** Verdict, both questions, replay count, catch-trial result and note go into the ledger.

**What this does not give.** One listener is a record of one person's taste on a given day, not evidence about what is better in general. The tool must say so on the results screen, and must not show percentages or a "winner" across fewer than about 10 comparisons.

## 7. Data in

**Contract (v0.1).** A table with:
- one **time column** (ISO date or datetime),
- one or more **numeric columns**,
- optional **flag columns** (such as WSC's `ice`),
- optional **units and range per column**, read from a data-dict YAML if one is next to the file, otherwise entered in the interface.

**Formats.** CSV and Parquet in the first version.

**From R.**
```r
readr::write_csv(df, "granby.csv")        # or:
arrow::write_parquet(df, "granby.parquet")
```
The interface shows an R snippet next to each exploratory stage (2 to 5) so the same check can be reproduced in R. These snippets are text for reading and copying; the workbench does not run R.

**Milestone-1 data.** A flat CSV derived from the cached Granby JSON (`data/granby_08NN002_2010_2024.json`) and Billings climate (`data/billings_1100_climate_2010_2024.json`), written by a small script, so the upload path is tested rather than bypassed.

## 8. Interface and architecture

**Leading option: marimo.** A Python notebook that runs as a local web app. Reactive cells, sliders and dropdowns, code collapsible. Chosen because it fits "fold-down code, mouse-driven" most directly.

**Status: unverified.** marimo was not installed in the cloud container as of this draft. Section 11 makes verification the first task.

**Alternatives if the spike fails:** Streamlit (simplest, but reruns the whole script on every interaction and has no native fold-down per stage), Gradio (good audio widgets, weak stage layout), or a static Pyodide/WebR page (no install, but the engine's weight is untested in the browser).

**Layering (so the interface can change without rewriting the engine):**
```
workbench/
  stages/       pure functions, one per stage, each returns (result, decision_records)
  runs/         build a run from settings; render; hash
  ab/           fork, loudness match, blind protocol, ledger
  ui/           the marimo notebook(s); no logic that the stages cannot do headless
  data/         ingest and the Granby CSV builder
  tests/
```
`workbench/` is a **new top-level folder**, so the vault sync described in earlier logs does not overwrite it. *Decision for Graham:* confirm the name and location, or choose another.

**Engine reuse.** Stages call the existing `harmony.py`, `timegrid.py`, `synth.py`, `sampler.py` and do not change them. Where `demo.py`'s logic is interleaved, the stage function copies the logic, and a test proves it reproduces `demo.py`'s output (section 9).

## 9. Milestone 1: Granby, one run, one fork, blind A/B

**Scope.** Granby WY2024 from the flat CSV; stages 1 to 9 as cards; three layers (pad, sub, plucks); synth sound only; a 10-12 s preview and a full render; one fork; blind A/B; ledger.

**Acceptance tests (all must be demonstrable without listening):**

| # | Test | How |
|---|---|---|
| T1 | The stage pipeline reproduces `demo.py` | With default settings, the workbench WAV is byte-identical to `python demo.py wy2024` (md5) |
| T2 | Determinism | Two runs of the same settings give the same audio hash |
| T3 | One fork changes one choice | Diff of the two decision-record sets lists exactly one `value` change |
| T4 | Loudness match | The two A/B clips are within 0.1 LU (or the stated RMS tolerance) |
| T5 | Equal length | Both clips have identical sample counts |
| T6 | Blind hides details | The A/B screen's DOM and accessibility tree contain no file name, parameter or fork label until the verdict |
| T7 | Randomisation is recorded | Ledger holds the seed and the A/B-to-fork mapping; re-deriving it from the seed matches |
| T8 | CSV ingest | The CSV upload path yields the same arrays as `R.wsc_series`/`R.climate_series` for the same year (within float tolerance) |
| T9 | Accessibility | axe-core: zero violations on each stage card and the A/B screen; keyboard-only completion of one A/B; checks as in `dev/a11y/` |
| T10 | Existing tracks unaffected | `python scripts/renders.py verify` result is unchanged from before the workbench was added |

**What stays out of milestone 1:** sample import, multi-dataset tracks, R execution, remix of published tracks, promotion to the site.

**Time estimate.** I won't give one. It depends on the marimo spike and on how cleanly `demo.py` separates (section 11).

## 10. Accessibility requirements

Carried from the audit of 30 September 2026, applied to the tool from the start:
- Every control reachable and operable by keyboard; visible focus.
- Plots have a text equivalent: a one-sentence description and a values table (as the Water Year rings page does).
- Each stage card announces its decision record as text, not only as a chart.
- The blind A/B screen works with a screen reader: players are labelled, the verdict is a pair of radio groups, replay count is announced politely, not per frame.
- Sound is never the only channel for a result: loudness-match values and fork differences are also in text after the reveal.
- Audio never starts on its own.

Not verified: screen reader testing (NVDA, VoiceOver) cannot be done in the cloud container. Graham's machine, or a tester who uses one, is needed for that.

## 11. Risks and unknowns

| # | Unknown | Why it matters | How to resolve |
|---|---|---|---|
| U1 | marimo behaves as expected with `<audio>` playback, file upload, and fold-down code | The whole interface choice rests on it | Spike: a one-card prototype with an uploaded CSV, a plot, a slider and two audio players; test headless with Playwright |
| U2 | How much of `demo.py` separates cleanly | Drives effort | Write stages 3 to 5 first; compare to `demo.py` arrays |
| U3 | Python version gap (3.11 here, 3.13 pinned) | Byte-identical claims (T1, T2) are version-specific | Run T1/T2 on Graham's machine; state the versions on every hash |
| U4 | Loudness matching dependency | LUFS needs a library (`pyloudnorm`) or RMS fallback | Check PyPI availability in the spike |
| U5 | Browser audio and large files | Preview length and format | Serve WAV or short MP3; measure |
| U6 | `renders.py verify` baseline | T10 needs it | Run it before and after, record both |
| U7 | I cannot listen | Judgement of how it sounds stays with Graham | Never claim a sound "works"; claim only what tests show |

## 12. Open questions for Graham

1. **Folder name and location** for the code: `workbench/` at repo root, or another name?
2. **Which scale of "reason"** do you want recorded: a sentence from me for every default (more reading, more learning), or only for the choices you change?
3. **Second question in blind A/B:** "tells the river's story more clearly" is my wording. Is there a better phrase for what you want to judge?
4. **Catch trials:** on by default, off by default, or ask at the start of each session?
5. **First fork to try:** the 0.7/0.3 brightness blend, the 15-day smoothing, or something else?

## 13. Proposed order of work (for approval)

1. **Spike (U1, U4, U6):** marimo prototype; baseline `renders.py verify`; no changes to existing files.
2. **Stages 1 to 5** with decision records and tests T8, then T1 up to stage 5 arrays.
3. **Stages 6 to 9** and T1, T2 end to end.
4. **Fork and blind A/B** with T3 to T7.
5. **Accessibility pass** (T9) and a log with port-back notes.

Each step ends with a commit on this branch and a log entry in `dev/logs/`. Nothing is pushed to any other branch, and no PR is opened unless asked.
