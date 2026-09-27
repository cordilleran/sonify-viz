# Contributing

This is an art practice that uses real environmental records to build an understanding of climate signals by ear. Contributions are welcome in four ways.

## Listen and tell us what you heard

Open an issue with the **Listening note** template. Say which track and version you heard (both are on the track's page), and what you heard: what worked, what confused you, what you'd expect a river or a year to sound like. No musical or scientific background needed.

## Remix a track

A remix is a new track built from a published one. It keeps the data and changes the treatment: tempo, mood, which layers play, another year of the same records. Copy the example in `remixes/README.md`, name the parent track and version, list what you changed, and credit yourself. Render it with, for example:

```bash
python scripts/pilot_granby_wy2024.py --remix remixes/your-remix.yaml
```

Then open a pull request with the YAML file (not the audio; renders are reproducible from the spec) and an issue with the **Remix** template describing it. The parameters a piece accepts are its `DEFAULTS`, near the top of its script. Swapping instruments isn't a parameter yet; say so in the issue if that's what you want.

## Report a bug

Use the **Bug** template. The most useful reports include the command you ran, the output, and your Python and package versions. If a render doesn't reproduce, run `python scripts/renders.py verify TRACK` and paste its output.

## Change the code

- Run the tests before a pull request: `pip install -r requirements.txt pytest`, then `pytest tests`. They take about a second and need no data or samples.
- A change that alters a published track's audio is a new version of that track, not a fix. Say so in the pull request, and expect a listening comparison before it's merged. `python scripts/renders.py verify` shows whether a change alters any render.
- Keep a new parameter named, bounded and documented in the piece's `DEFAULTS`, so a variant or remix can set it.
- Data: add a new record's source, licence and quirks alongside it. Records whose terms don't allow redistribution are fetched by a script, never committed.

By contributing you agree that your code is licensed under the Mozilla Public License 2.0 and your media under the licence of the track it belongs to (see `LICENSE-media`). Remix credits are kept in the remix spec and on the track's card.
