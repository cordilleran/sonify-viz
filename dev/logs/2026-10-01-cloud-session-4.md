# Cloud session 4: workbench spec (2026-10-01)

**Scope.** Design discussion, then a draft spec. No code, no changes to existing files.

**Done**
- Discussed options for a beginner-friendly interface; Graham chose a local web interface with code in fold-downs, EDA per layer, A/B with a blind option, an experiments area, and Granby as the first test.
- Wrote `dev/specs/workbench-spec-v0.1.md` (stage model, decision record, blind A/B protocol, milestone-1 acceptance tests, risks, open questions).
- Ran `scripts/demo.py wy2024` in the cloud container (Python 3.11.15; numpy, scipy, soundfile, matplotlib, pyyaml, pyarrow installed from PyPI, versions unpinned). Output: 61 bars, 51.75 s, 44.1 kHz stereo, about 33 s to render. Two consecutive runs gave identical md5 hashes.

**Not done / not verified**
- marimo not installed or tested (spike U1 in the spec).
- `renders.py verify` baseline not recorded (U6).
- The determinism result holds for this container's Python and library versions only; the repo pins Python 3.13 and numpy 2.5.3.

**Waiting on Graham:** the five open questions in section 12 of the spec.

**Port-back:** none; only new files under `dev/` (new folder, not overwritten by the sync).
