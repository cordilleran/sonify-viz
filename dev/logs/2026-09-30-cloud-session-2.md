# 2026-09-30: cloud session 2 (round 2 brief)

## TL;DR

- Nine accessibility findings fixed, one commit each, plus one follow-up; the `climate_daily` dictionary wording fixed and validated; `accessibility.qmd` written (not rendered). Everything is on `claude/laughing-fermat-57fuql`. Nothing was pushed to `main`, and no pull request was opened.
- **Nothing changed how the pages look.** Full-page screenshots of all three pieces, standalone and `?embed`, at 1280 and 390 px, are pixel-identical before and after (0 px differ in every image).
- **Failing axe nodes fell from 475 to 211.** What remains is the small-text contrast (A11Y-07, for Graham) and `page-has-heading-one` in the two embedded modes, which is expected because the site's wrapper page supplies the heading.
- **Two of my round-1 statements were wrong** (A11Y-02 overstated; DD-01 partly documented already). Both are corrected in the reports.
- **Held, as briefed:** A11Y-07, A11Y-11, the kit spec and the flood-track spec.

## Commits (oldest first)

| Commit | What | Files |
|---|---|---|
| `015a797` | A11Y-06 `lang="en"` | `superior-ice/index.html`, `meridian/index.html`, `listen/index.html` |
| `37dab9b` | A11Y-09 `<main>` (with `main{display:contents}` so the grid is unchanged) | the same three |
| `88378ed` | A11Y-10 empty header cell hidden with `aria-hidden` (deleting it changed the layout) | `superior-ice/index.html`, `dev/a11y/shots.js` |
| `c54b0a0` | A11Y-08 map canvas `role=img`, out of the tab order | `superior-ice/index.html` |
| `5dc945c` | A11Y-03 score label; both scroll boxes reachable | `listen/index.html` |
| `0835b2b` | A11Y-04 seek bars speak the date and time | the three pages, `dev/a11y/compare_shots.py` |
| `9d29bd7` | A11Y-05 one polite announcement on pin or release; adds `.sr-only` | `shared/tokens.css`, `superior-ice/index.html`, `meridian/index.html` |
| `dc068b5` | A11Y-01 spoken values per region row | `superior-ice/index.html`, `meridian/index.html` |
| `edb9963` | A11Y-02 ring label | `listen/index.html` |
| `81f85ae` | Dictionary wording | `data/parquet/data-dict.yaml` |
| `1a23895` | Accessibility page | `accessibility.qmd` |
| `8380aaa` | Follow-up: hidden region text moved inside `<main>` | `superior-ice/index.html`, `meridian/index.html` |

Also on the branch: the merge of `main` (the brief), `dev/a11y/check.js`, `dev/a11y/wrapper.html`, and the corrected reports in `dev/reports/`.

## What I tested, and how

- **Before and after counts** (`dev/a11y/check.js`, axe-core 4.13.0 in Chromium 141 via Playwright 1.63; raw files in `dev/reports/a11y-audit-260930/check-before.json` and `check-after.json`). Each piece is tested standalone, with `?embed`, and inside an iframe wrapper (`dev/a11y/wrapper.html`, which mimics the site's wrapper pages), at 1280 and 390 px:

| Page, mode, width | Tab stops before → after | Failing rules before (nodes) | Failing rules after (nodes) |
|---|---|---|---|
| superior-ice standalone 1280 | 28 → 27 | color-contrast 21, empty-table-header 1, html-has-lang 1, landmark-one-main 1, region 14 | color-contrast 21 |
| superior-ice standalone 390 | 28 → 27 | color-contrast 21, empty-table-header 1, html-has-lang 1, landmark-one-main 1, region 14 | color-contrast 21 |
| superior-ice embed 1280 | 25 → 24 | color-contrast 20, empty-table-header 1, html-has-lang 1, landmark-one-main 1, page-has-heading-one 1, region 14 | color-contrast 20, page-has-heading-one 1 |
| superior-ice embed 390 | 25 → 24 | color-contrast 20, empty-table-header 1, html-has-lang 1, landmark-one-main 1, page-has-heading-one 1, region 14 | color-contrast 20, page-has-heading-one 1 |
| superior-ice iframe 1280 | 25 → 24 | color-contrast 20, empty-table-header 1, html-has-lang 1, landmark-one-main 1, page-has-heading-one 1, region 14 | color-contrast 20, page-has-heading-one 1 |
| superior-ice iframe 390 | 25 → 24 | color-contrast 20, empty-table-header 1, html-has-lang 1, landmark-one-main 1, page-has-heading-one 1, region 14 | color-contrast 20, page-has-heading-one 1 |
| meridian standalone 1280 | 23 → 23 | color-contrast 16, html-has-lang 1, landmark-one-main 1, region 7 | color-contrast 16 |
| meridian standalone 390 | 23 → 23 | color-contrast 3, html-has-lang 1, landmark-one-main 1, region 7 | color-contrast 3 |
| meridian embed 1280 | 20 → 20 | color-contrast 15, html-has-lang 1, landmark-one-main 1, page-has-heading-one 1, region 7 | color-contrast 15, page-has-heading-one 1 |
| meridian embed 390 | 20 → 20 | color-contrast 2, html-has-lang 1, landmark-one-main 1, page-has-heading-one 1, region 7 | color-contrast 2, page-has-heading-one 1 |
| meridian iframe 1280 | 20 → 20 | color-contrast 15, html-has-lang 1, landmark-one-main 1, page-has-heading-one 1, region 7 | color-contrast 15, page-has-heading-one 1 |
| meridian iframe 390 | 20 → 20 | color-contrast 2, html-has-lang 1, landmark-one-main 1, page-has-heading-one 1, region 7 | color-contrast 2, page-has-heading-one 1 |
| listen standalone 1280 | 33 → 34 | color-contrast 4, html-has-lang 1, landmark-one-main 1, region 15 | color-contrast 4 |
| listen standalone 390 | 34 → 34 | color-contrast 4, html-has-lang 1, landmark-one-main 1, region 15, scrollable-region-focusable 2 | color-contrast 4 |
| listen embed 1280 | 33 → 34 | color-contrast 4, html-has-lang 1, landmark-one-main 1, page-has-heading-one 1, region 15 | color-contrast 4, page-has-heading-one 1 |
| listen embed 390 | 34 → 34 | color-contrast 4, html-has-lang 1, landmark-one-main 1, page-has-heading-one 1, region 15, scrollable-region-focusable 2 | color-contrast 4, page-has-heading-one 1 |
| listen iframe 1280 | 33 → 34 | color-contrast 4, html-has-lang 1, landmark-one-main 1, page-has-heading-one 1, region 15 | color-contrast 4, page-has-heading-one 1 |
| listen iframe 390 | 34 → 34 | color-contrast 4, html-has-lang 1, landmark-one-main 1, page-has-heading-one 1, region 15, scrollable-region-focusable 2 | color-contrast 4, page-has-heading-one 1 |

  The tab-stop counts come from a script that stops at the first repeat. Superior falls by one, which is the map canvas leaving the tab order (A11Y-08). Water Year Rings gains two focusable scroll boxes, but the measured count moved by at most one, and I did not reconcile the two figures, so treat its count as approximate. `page-has-heading-one` in the two embedded modes appeared before as well; axe runs inside the frame, and the wrapper page supplies the heading.
- **Behaviour checks** (standalone and `?embed`, keyboard only):
  - Seek bars: on focus and after eight PageUp presses the spoken value is correct on all three pages (Superior day 1 → 189, Meridian breath 1 → 99, Water Year Oct 1 → Jul 26).
  - Announcements: a MutationObserver on the live region recorded 0 changes during 6 s of playback and 4 after keyboard pin, unpin, pin and Escape, on both Superior Ice and Meridian.
  - Region descriptions: read from Chromium's accessibility tree (computed `description`) on both pages.
  - Score box: ArrowRight scrolls it from the keyboard (scrollLeft 0 → 80) and it shows a 2 px focus outline.
- **No visual change:** `dev/a11y/shots.js` and `compare_shots.py` (full-page screenshots, reduced motion on, deterministic: two runs of the unchanged page gave 0 differing pixels). After the fixes to all three pages: 0 px differ in all 12 images. After the last commit (`8380aaa`): 0 px differ in the 8 Superior Ice and Meridian images. The Water Year ring label (`edb9963`) was made after the 12-image run; it is an attribute-only change.
- **Tests:** `pytest tests -q` before every commit: 155 passed, 1 skipped, 1 xfailed. No file under `tests/`, `scripts/`, `tracks/`, `audio/` or `renders.lock.json` was touched.
- **Dictionary:** `data-dict validate-data` (data-dict-yaml 0.0.3) on `data/parquet/data-dict.yaml`: ok. It prints two "unresolved todo" notes, which it printed before my edit too.

## What I could not test

- No screen reader (NVDA, JAWS, VoiceOver, TalkBack), no Safari, no Firefox, no phone. "Announced" and "spoken" mean the text is in Chromium's accessibility tree or a live region, not that I heard it.
- The Quarto site was not built, so `accessibility.qmd` was not rendered and its links were not clicked.
- While the seek bar is focused and the piece is playing, its spoken value refreshes only on seek or pause, by design (the brief bars per-frame updates), so it can be a few seconds stale.
- The Climate Pair page (`climate.qmd` and `climate/viz.js`) was not touched or tested.

## Found and not fixed (outside the brief)

- `listen/index.html` has no `<!doctype html>`, so it renders in quirks mode. I added only `lang`. A doctype could change its layout, so it needs a look by a person.
- `superior-ice/index.html` intermittently throws "Cannot set properties of null (setting 'textContent')" at load, in `frame()` where it writes to the region list before the list is built. It happens on the last commit of `main` too. My changes guard against it and do not cause it.
- A11Y-07 (six small-text colour pairs) and A11Y-11 (a prose account of the season) remain for Graham.

## Port-back

| Repo path | Vault path | Kind |
|---|---|---|
| `superior-ice/index.html` | `superior-ice/index.html` | fix (overwritten by the sync unless ported) |
| `meridian/index.html` | `meridian/index.html` | fix |
| `listen/index.html` | `listen/index.html` | fix |
| `shared/tokens.css` | `shared/tokens.css` | fix (adds `.sr-only`) |
| `data/parquet/data-dict.yaml` | the vault's copy of this dictionary. `scripts/build_parquet.py` names `data/water-year.data-dict.yaml`, so check that path | fix (wording) |
| `accessibility.qmd` | `site/accessibility.qmd` | new file (survives the sync) |
| `dev/**` | not required; new folder, survives the sync | new tooling and reports |

## Lines for `_quarto.yml` (not applied)

In `project: render:`, after `- about.qmd`:

```yaml
    - accessibility.qmd
```

In `website: page-footer: left:`, replace the text with:

```yaml
    left: "Graham Watt & Claude Code · [how this was made](about.qmd) · [accessibility](accessibility.qmd) · [source on GitHub](https://github.com/cordilleran/sonify-viz)"
```

Two notes. The page links to the audit report at `dev/reports/a11y-audit-260930.md` on `main`, which resolves only once this branch is merged. And the page's "What we are fixing" wording assumes the fixes publish with the page; adjust it if they do not.

## What I would change in the brief

- **Say `/docs/` is git-ignored** (it is, in `.gitignore`); the round-1 handoff named it.
- **Add a "no visual change" test to the definition of done.** The obvious fix for A11Y-10 (delete the empty cell) changed the layout, and only a pixel comparison caught it. `dev/a11y/shots.js` and `compare_shots.py` do this in about two minutes per page set and are worth keeping.
- **"Safe" is a claim to test, not assume.** Two of the fixes needed a different approach once tested (A11Y-10, and moving `#srRegions` inside `<main>`).
- **Re-grade findings when the fix is written.** A11Y-02 was wrong in round 1, and only reading the code again showed it.
- **Say who owns the `data-dict` YAML.** The brief says it is hand-written in the vault, but the build script's docstring points at a different file name.

## Questions

1. Is "Voice released." (Meridian) and "Region released." (Superior Ice) the wording you want spoken, or should both say the same thing?
2. Should the `listen/index.html` doctype be added? It is probably right, and it needs your eye on the layout.
3. Do you want the remaining dictionary findings (DD-05 to DD-08, DD-10 to DD-14) in a third round?
