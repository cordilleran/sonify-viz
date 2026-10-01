"""
Write the Pieces menu of the site's navbar (site/_quarto.yml) from tracks/albums.yaml,
so a new album appears in the navigation without a hand edit (2026-10-01).

  python export_nav.py

Only the lines between the `nav:pieces` markers are replaced. tests/test_nav.py checks
that the file is current, so an album added without running this fails the tests.
"""
from pathlib import Path

import json

import yaml

ROOT = Path(__file__).resolve().parent.parent
QUARTO = (ROOT / "site" if (ROOT / "site").is_dir() else ROOT) / "_quarto.yml"   # vault layout, or the repo's
START, END = "# nav:pieces start", "# nav:pieces end"
INDENT = " " * 10
# not albums: the Water Year companion and the methods page, kept at the foot of the menu
EXTRAS = [("Water Year: listen with the visual", "listen.qmd"), ("Methods & code", "methods.qmd")]


def albums():
    return yaml.safe_load((ROOT / "tracks" / "albums.yaml").read_text())


def block():
    lines = [f"{INDENT}- href: {a['page']}\n{INDENT}  text: {json.dumps(a['title'])}" for a in albums()]
    lines.append(f"{INDENT}- text: \"---\"")
    lines += [f"{INDENT}- href: {href}\n{INDENT}  text: {json.dumps(text)}" for text, href in EXTRAS]
    return "\n".join(lines)


def render(text):
    """The _quarto.yml text with the generated menu between the markers."""
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    pad = head.rsplit("\n", 1)[1]   # the marker's own indentation
    return f"{head}{START}\n{block()}\n{pad}{END}{tail}"


if __name__ == "__main__":
    QUARTO.write_text(render(QUARTO.read_text()))
    print(f"{QUARTO.name}: {len(albums())} albums in the Pieces menu")
