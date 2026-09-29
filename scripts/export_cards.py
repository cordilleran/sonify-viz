"""
Render the track catalogue (tracks/*.yaml + tracks/albums.yaml) into the
site's Tracks page, site/tracks.qmd (2026-09-27). Each card gets its
reproduce block (version, seeds, lock date, MP3 hash) from renders.lock.json,
and Water Year cards get their layer mapping from export_companion.LANES, so
the mapping is written in one place.

  python export_cards.py

A card whose version disagrees with the lock stops the export
(tests/test_cards.py checks the same thing). Card `todo` lists stay in the
YAML and never reach the page.
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_companion as EC

ROOT = Path(__file__).resolve().parent.parent
TRACKS = ROOT / "tracks"
LOCK = ROOT / "renders.lock.json"
OUT = (ROOT / "site" if (ROOT / "site").is_dir() else ROOT) / "tracks.qmd"  # vault layout, or the repo's
LISTEN = {"water-year": "listen.qmd?piece={name}", "climate-pair": "climate.qmd?piece={basin}",
          "meridian": "meridian.qmd", "superior-ice": "superior-ice.qmd"}


def load_cards():
    albums = yaml.safe_load((TRACKS / "albums.yaml").read_text())
    cards = {p.stem: yaml.safe_load(p.read_text()) for p in sorted(TRACKS.glob("*.yaml")) if p.name != "albums.yaml"}
    return albums, cards


def check(cards, lock):
    """-> list of problems: a card without a lock entry, or versions that disagree."""
    bad = []
    for tid, c in cards.items():
        if tid != c["id"]:
            bad.append(f"{tid}.yaml has id {c['id']}")
        e = lock["tracks"].get(c.get("lock", c["id"]))   # `lock`: a variant's lock id (ids with ':' can't be file names everywhere)
        if e is None:
            bad.append(f"{c['id']}: no entry in renders.lock.json")
        elif str(c["changelog"][-1]["version"]) != str(e["version"]):
            bad.append(f"{c['id']}: card says v{c['changelog'][-1]['version']}, lock says v{e['version']}")
    return bad


def card_mp3(c):
    """The site path of the MP3 a card describes."""
    if c.get("site_mp3"):
        return c["site_mp3"]
    if c["album"] == "water-year":
        return f"listen/{c['script'].replace('pilot_', '').replace('.py', '')}.mp3"
    if c["album"] == "climate-pair":
        return f"audio/climate_{c['args'][0]}_1958_2025.mp3"
    return None


def uncarded(root):
    """-> MP3s the site plays that no track card describes (a publish check: every published track has a card)."""
    root = Path(root)
    claimed = {card_mp3(c) for c in load_cards()[1].values()}
    played = [str(f.relative_to(root)) for d in ("listen", "audio", "meridian", "superior-ice") for f in sorted((root / d).glob("*.mp3"))
              if not f.name.endswith("_rollcall.mp3")]   # orientation files (a legend in sound), not tracks
    return [f for f in played if f not in claimed]


def mapping_table(c):
    """Markdown table. Water Year cards read the companion's lanes (record -> what you hear);
    the lane-to-stem pairing there drives the page's glow, so it isn't shown as the 'layer'."""
    tag = lambda t: f'<span class="src {t}">{t}</span>'
    if c["mapping"] != "companion":
        return ["| Layer | Data | What you hear | |", "|---|---|---|---|"] + \
               [f"| {m['layer']} | {m['data']} | {m['sound']} | {tag(m['tag'])} |" for m in c["mapping"]]
    name = c["script"].replace("pilot_", "").replace(".py", "")
    return ["| Record | What you hear | |", "|---|---|---|"] + \
           [f"| {label} | {does} | {tag(src)} |" for key, label, col, how, src, stem, does in EC.LANES[name]]


def card_md(c, e, album):
    name = c["script"].replace("pilot_", "").replace(".py", "")
    listen = LISTEN[album].format(name=name, basin=(c["args"] or [""])[0])
    if c.get("site_mp3") and "?" not in listen:   # a piece page with several renders: open this card's render
        listen += "?piece=" + Path(c["site_mp3"]).stem
    y = c["year"]
    # hash the MP3 this site actually plays: the site copy the render wrote (Climate Pair), or the
    # companion's encode of the locked WAV (Water Year, written by export_companion.py)
    mp3 = next((h for k, h in e["outputs"].items() if k.startswith("site_audio/") and k.endswith(".mp3")), None)
    if mp3 is None and c.get("site_mp3") and (ROOT / c["site_mp3"]).exists():   # a piece with its own page folder
        import hashlib
        mp3 = hashlib.sha256((ROOT / c["site_mp3"]).read_bytes()).hexdigest()
    if mp3 is None and (ROOT / "listen" / f"{name}.mp3").exists():
        import hashlib
        mp3 = hashlib.sha256((ROOT / "listen" / f"{name}.mp3").read_bytes()).hexdigest()
    L = [f"## {c['title']} {{#{c['id']}}}", "",
         f"**v{e['version']}** · {y['label']} ({y['framing']}, {y['from']} to {y['to']}) · [listen]({listen})", "",
         f"*{c['question'].strip()}*", "",
         f"**Place.** {c['place'].strip()}", ""]
    if c.get("territory"):
        L += [f"**Territory.** {c['territory'].strip()}", ""]
    L += ["**Records.**", ""] + [f"- {r}" for r in c["records"]] + [""]
    L += mapping_table(c) + [""]
    if (ROOT / "tracks" / "mapping" / c["id"] / "data-dict.yaml").exists():
        L += [f"Every step from record to sound, with its bounds: [the mapping dictionary](dictionary/{c['id']}-mapping.html) "
              f"(tables in `tracks/mapping/{c['id']}/`).", ""]
    L += [f"**Harmony.** {c['harmony'].strip()}", ""]
    if c.get("simulated"):
        L += ["**Simulated, not observed.**", ""] + [f"- {s}" for s in c["simulated"]] + [""]
    L += ["**Be careful about.**", ""] + [f"- {s}" for s in c["limitations"]] + [""]
    args = " ".join(c["args"])
    L += ["**Reproduce.** " + f"`python scripts/{c['script']}{(' ' + args) if args else ''}` · seed{'s' if len(e['seeds']) > 1 else ''} "
          + ", ".join(str(s) for s in e["seeds"]) + f" · locked {e['locked']}"
          + (f" · SHA-256 of the MP3 on this site `{mp3[:16]}…`" if mp3 else "")
          + f" · check it with `python scripts/renders.py verify {c.get('lock', c['id'])}`", ""]
    L += ["**Credits.** " + "; ".join(c["credits"]) + ".", ""]
    lin = c.get("lineage") or {}
    bits = []
    if lin.get("parent"):
        bits.append(f"remix of {lin['parent']}")
    if lin.get("variants"):
        bits.append("variants: " + ", ".join(f"`{v}`" for v in lin["variants"]))
    if lin.get("remixes"):
        bits.append("remixes: " + ", ".join(lin["remixes"]))
    if bits:
        L += ["**Lineage.** " + "; ".join(bits) + ".", ""]
    L += ["**Changelog.**", ""] + [f"- v{x['version']} ({x['date']}): {x['change']}" for x in reversed(c["changelog"])] + [""]
    return "\n".join(L)


def render():
    albums, cards = load_cards()
    lock = json.loads(LOCK.read_text())
    bad = check(cards, lock)
    if bad:
        raise SystemExit("cards and lock disagree:\n  " + "\n  ".join(bad))
    L = ["---", 'title: "Tracks"',
         'subtitle: "Every published track, its version, and how to check it"', "toc: true", "---", "",
         "<!-- generated by scripts/export_cards.py from tracks/*.yaml and renders.lock.json; edit those, not this -->", "",
         "Each track has a card: the question it asks, where its records come from, what drives each sound, what "
         "is simulated rather than observed, what to be careful about, and how to reproduce it byte for byte. "
         "A track's version changes when its music changes; the changelog says when and why. Tracks are grouped "
         "into albums. See [Methods](methods.qmd#versions-variants-and-remixes) for how versions, variants and "
         "remixes work, and `CONTRIBUTING.md` to propose a remix.", ""]
    for a in albums:
        L += [f"# {a['title']}", "", f"{a['about']} [The album's page]({a['page']}).", ""]
        for tid in a["tracks"]:
            L.append(card_md(cards[tid], lock["tracks"][cards[tid].get("lock", tid)], a["id"]))
    return "\n".join(L) + "\n", sum(len(a["tracks"]) for a in albums)


def main():
    ap = argparse.ArgumentParser(description="Write the Tracks page from tracks/*.yaml, or check a published tree.")
    ap.add_argument("--check-published", metavar="REPO", help="fail if any MP3 under REPO has no track card (publish_site.sh)")
    a = ap.parse_args()
    if a.check_published:
        bad = uncarded(a.check_published)
        if bad:
            raise SystemExit("published audio with no track card (add one in tracks/):\n  " + "\n  ".join(bad))
        print("every published MP3 has a track card")
        return
    text, n = render()
    OUT.write_text(text)
    print(f"{OUT.relative_to(ROOT)}: {n} cards")


if __name__ == "__main__":
    main()
