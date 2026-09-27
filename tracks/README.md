# Tracks: versions and cards

One YAML card per published track (`<track-id>.yaml`), and `albums.yaml` to group them. `scripts/export_cards.py` renders them into the site's Tracks page, adding each track's reproduce block (version, seed, content hashes) from `renders.lock.json`, and, for the Water Year tracks, the layer mapping from `scripts/export_companion.py`, so the mapping is written in one place. `tests/test_cards.py` fails if a card's version and the lock disagree.

**Versions.** A track's version changes when its music changes: `1.0 → 1.1` for a revision, `2.0` for a rework. `renders.py verify` shows whether a change altered the audio. Every version gets a changelog line with its date.

**Card fields:**
- `id`, `title`, `album`, `script`, `args`: which track, and what renders it.
- `question`: what the track asks of its data.
- `place`, `territory`: where the records come from, and whose land that is. `territory` is written by Graham; until then it's empty and not shown.
- `year`: the span and its framing.
- `records`: the data, with sources.
- `mapping`: layer, data, what you hear, and the R/D/S tag (retrieved, derived, simulated). Water Year cards say `mapping: companion` and take it from the companion's table.
- `harmony`, `simulated`, `limitations`: how the music is organized, which layers are modelled rather than observed, and what to be careful about.
- `credits`, including AI assistance; `lineage`: parent, variants and remixes.
- `changelog`: one line per version.
- `todo`: open questions, kept out of the public page.
