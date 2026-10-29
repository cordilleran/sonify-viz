# Sound Channel Brewer

A page for choosing two auditory channels for two variables, heard together on seeded
random data before a real data lane is bound to them. Live at
https://cordilleran.github.io/sonify-viz/sound-channel-brewer.html.

Everything runs in the browser: `channels.js` (the channels and their levels), `pool.js`
(seeded draws, data models, layouts, the explanations), `map.js` (events to notes),
`dsp.js` (synthesis into a looping buffer), `drum.js` (the drum lane, V4), `viz.js` (the strips)
and `main.js` (the page).
The panel "How the data are made" shows the same rules in plain words, as formulas and as
the source of the functions that run.

To run it locally, serve this folder (ES modules do not load from a `file://` page), for
example `python3 -m http.server` here, then open http://localhost:8000/. The Node and
headless-browser tests live with the source in the authoring workbench, not in this
repository. `scripts/build_picker_site.py` builds this folder from that source. The site page
embeds it in an iframe on the same origin, which the height message relies on.

Design logic from Channel Brewer by Enrico Bertini (https://github.com/ebertini/channel-brewer),
taken as an idea only; this is new code under the repository's licence (MPL-2.0).
`vendor/katex.min.js` is KaTeX 0.16.9 (MIT, licence beside it).
