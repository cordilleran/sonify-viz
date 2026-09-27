# Remixes

A remix is a new track built from a published one: it names its parent track and version, what it keeps (usually the data and the mapping), what it changes, and who made it. It renders under its own id, gets its own track card, and `renders.lock.json` records its lineage. This is the path for B-sides, singles and outside contributors.

```yaml
remix: granby-wy2024-dusk            # the new track's id (lowercase, hyphens)
parent: {piece: granby, track: granby-wy2024, version: "1.0"}
keeps: [Granby and Burrell Creek flow, the ice record, the layer mapping]
changes: {bpm: 60, mode: Dorian, mute: [perc]}
credits:
  - {name: Your Name, role: remix}
notes: Why this remix exists, in a sentence or two.
```

Render it with `python scripts/pilot_granby_wy2024.py --remix remixes/granby-wy2024-dusk.yaml`. `changes` accepts the parameters the parent piece declares in its `DEFAULTS` (for Granby: `year`, `bpm`, `tonic`, `mode`, `mode_range`, `mute`, `gains`, `seed`); anything else is refused. Swapping instruments or timbres isn't a parameter yet.
