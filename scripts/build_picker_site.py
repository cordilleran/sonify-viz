"""Build the Sound Channel Brewer folder for the site from the picker's source folder.

The source index.html is a page fragment (no doctype, Google Fonts, follows the viewer's
light or dark theme). For the site this wraps it in a full document, swaps Google Fonts for
the site's own fonts (listen/fonts), starts it dark like the rest of the site, and copies
only what the page loads: the seven modules, vendored KaTeX with its licence, and a README
written for this repository. The tests and the local server stay with the source.

Usage: python3 -I build_picker_site.py <picker source dir> <output dir named sound-channel-brewer>
"""
import re
import shutil
import sys
from pathlib import Path

MODULES = ["main.js", "channels.js", "pool.js", "map.js", "dsp.js", "viz.js", "drum.js"]
VENDOR = ["katex.min.js", "katex-LICENSE.txt"]
SITE_FONTS = """--font-body: "Atkinson Hyperlegible", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-label: "Atkinson Hyperlegible", system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;"""

README = """# Sound Channel Brewer

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
"""


def build(src: Path, out: Path) -> None:
    page = (src / "index.html").read_text(encoding="utf-8")
    # The site serves its own fonts: drop the Google Fonts links and point the tokens at the site's faces.
    page = re.sub(r'<link rel="preconnect" href="https://fonts\.googleapis\.com">\n', "", page)
    page, n = re.subn(r'<link rel="stylesheet" href="https://fonts\.googleapis\.com/[^"]+">', '<link rel="stylesheet" href="../listen/fonts/fonts.css">', page)
    if n != 1:
        raise SystemExit("Google Fonts link not found: the page would still load Google Fonts")
    page, n = re.subn(r"--font-body:.*?\n\s*--font-label:.*?\n\s*--font-mono:[^;]*;", SITE_FONTS, page, flags=re.S)
    if n != 1:
        raise SystemExit("font tokens not found")
    page = page.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', "")
    # Title, font link and style go in the head; the markup and scripts in the body.
    head, sep, body = page.partition('<div class="wrap">')
    if not sep:
        raise SystemExit("page markup not found")
    doc = ('<!doctype html>\n<html lang="en" data-theme="dark">\n<head>\n<meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
           '<style>body{margin:0}[hidden]{display:none!important}</style>\n'
           f"{head.strip()}\n</head>\n<body>\n{sep}{body.strip()}\n</body>\n</html>\n")
    # The output folder is deleted and rebuilt, so refuse anything but the page's own folder.
    if out.name != "sound-channel-brewer":
        raise SystemExit(f"refusing to replace {out}: the output folder must be named sound-channel-brewer")
    if out.exists():
        shutil.rmtree(out)
    (out / "vendor").mkdir(parents=True)
    (out / "index.html").write_text(doc, encoding="utf-8")
    for m in MODULES:
        shutil.copy2(src / m, out / m)
    for v in VENDOR:
        shutil.copy2(src / "vendor" / v, out / "vendor" / v)
    (out / "README.md").write_text(README, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    build(Path(sys.argv[1]), Path(sys.argv[2]))
    print("built", sys.argv[2])
