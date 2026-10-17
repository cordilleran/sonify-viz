"""Every file a standalone page loads is listed in _quarto.yml's `resources`, and every listed file exists.

Quarto copies only what `resources` names. A page whose audio is missing from the list renders and passes
the other tests, then deploys with a player that 404s (Godbout, 17 Oct 2026: the list still named the v1.1 mp3).
"""
import fnmatch
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
QUARTO = ROOT / "_quarto.yml" if (ROOT / "_quarto.yml").exists() else ROOT / "site" / "_quarto.yml"
RESOURCES = yaml.safe_load(QUARTO.read_text())["project"]["resources"]
LOCAL_SRC = re.compile(r"""(?:src|href)=["']([^"'#?:]+\.(?:mp3|jpg|jpeg|png|webp|json|svg|wav))["']""")


def _listed(path):
    return any(fnmatch.fnmatch(path, r) for r in RESOURCES)


def test_listed_resources_exist():
    missing = [r for r in RESOURCES if "*" not in r and not (ROOT / r).exists() and not (ROOT / "site" / r).exists()]
    assert not missing, f"listed in _quarto.yml but not on disk: {missing}"


def test_files_a_standalone_page_loads_are_listed():
    unlisted = []
    for page in (r for r in RESOURCES if r.endswith("/index.html")):
        folder = Path(page).parent
        for ref in LOCAL_SRC.findall((ROOT / page).read_text()):
            target = (folder / ref).as_posix()
            if target.startswith(".."):  # shared assets such as ../shared/tokens.css are copied elsewhere
                continue
            if not _listed(target):
                unlisted.append(f"{page} loads {target}")
    assert not unlisted, "not in _quarto.yml resources, so the deployed page would 404: " + "; ".join(unlisted)
