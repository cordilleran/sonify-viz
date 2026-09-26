"""
Build/refresh the sample library and its license manifest.

Audio goes to samples/ in the repo (git-ignored; about 500 MB), or to
$SONIFICATION_SAMPLES if set. The manifest is committed so provenance is
browsable:
  samples_manifest.csv  (one row per source SET, not per file)

Sources:
  - VSCO 2 Community Edition (CC0, github.com/sgossner/VSCO-2-CE) - pulled by
    the scratch download list in the 2026-09-24 session; the instrument
    subset is recorded below.
  - Wikimedia Commons bird recordings (mostly xeno-canto mirrors, CC BY-SA),
    fetched by exact title. Attribution is kept per file.
"""
import csv, json, time, urllib.request, urllib.parse
from pathlib import Path

from dsp_core import SAMPLES as ROOT
MANIFEST = Path(__file__).resolve().parent.parent / "samples_manifest.csv"
UA = {"User-Agent": "sonify-viz/0.1 (https://github.com/cordilleran/sonify-viz; personal research)"}

VSCO_SETS = [
    ("Keys/Upright Piano", "Upright piano (Ivy Audio / Simon Dalzell), 3 dynamics, sampled every major 3rd"),
    ("Strings/Harp", "Harp, mf"),
    ("Strings/Cello Section/susvib", "Cello section sustain w/ vibrato"),
    ("Strings/Cello Section/pizzT", "Cello section pizzicato"),
    ("Strings/Violin Section/susVib", "Violin section sustain w/ vibrato"),
    ("Strings/Violin Section/Pizz", "Violin section pizzicato"),
    ("Strings/Violin Section/Trem", "Violin section tremolo"),
    ("Strings/Solo Contrabass/SusNV", "Solo contrabass sustain, no vibrato"),
    ("Strings/Solo Contrabass/Pizz", "Solo contrabass pizzicato"),
    ("Woodwinds/Flute/susNV", "Flute sustain, no vibrato"),
    ("Percussion/Marimba", "Marimba"),
    ("Percussion/Glock", "Glockenspiel"),
    ("Percussion/Timpani", "Timpani hits and rolls (added 2026-09-25 for the climate pair's storm layer)"),
    ("Percussion/BDrumNewhit_*", "Concert bass drum, 7 dynamics (added 2026-09-25)"),
    ("Percussion/gongHit_*", "Tam-tam / gong hits p..fff (added 2026-09-25)"),
    ("Percussion/cymbal-crash1_* + susCymb1-hit_*", "Crash and suspended-cymbal hits (added 2026-09-25)"),
    ("Keys/Organ/Quiet", "Pipe organ, quiet manual, for drones (added 2026-09-25)"),
    ("Percussion/*", "Hand percussion + cymbal/gong/triangle one-shots (conga, tumba, quinto, log drum, tambourine shake, bowed/crescendo cymbal, gong scrape, bass-drum rub, bell tree)"),
]

BIRDS = [
    # (commons title, local name, species, why it's here)
    ("File:Catharus ustulatus - Swainson's Thrush XC250599.mp3", "swainsons_thrush_a.mp3",
     "Swainson's Thrush", "Granby riparian; late-May arrival, spiralling evening song"),
    ("File:Catharus ustulatus - Swainson's Thrush XC250601.mp3", "swainsons_thrush_b.mp3",
     "Swainson's Thrush", "second take for variety"),
    ("File:Yellowstone sound library - American Dipper & Canada Geese - 001.mp3", "american_dipper.mp3",
     "American Dipper", "the river's winter singer; sings through ice season"),
    ("File:Sturnella neglecta - Western Meadowlark - XC104522.ogg", "western_meadowlark_a.ogg",
     "Western Meadowlark", "Okanagan grassland benches; March arrival"),
    ("File:Sturnella neglecta - Western Meadowlark XC254454.mp3", "western_meadowlark_b.mp3",
     "Western Meadowlark", "second take"),
    ("File:Grus canadensis - Sandhill Crane - XC111491.ogg", "sandhill_crane.ogg",
     "Sandhill Crane", "Okanagan flyway passage, April and September"),
    ("File:Riparia riparia - Sand Martin XC487832.mp3", "bank_swallow.mp3",
     "Bank Swallow (Sand Martin, European recording, same species)", "Grand Forks cutbank colonies, May-Aug"),
]


def commons(title):
    q = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "imageinfo",
                                "iiprop": "url|extmetadata", "format": "json"})
    req = urllib.request.Request("https://commons.wikimedia.org/w/api.php?" + q, headers=UA)
    page = next(iter(json.load(urllib.request.urlopen(req, timeout=60))["query"]["pages"].values()))
    ii = page["imageinfo"][0]
    m = ii["extmetadata"]
    strip = lambda s: __import__("re").sub("<[^>]+>", "", s or "").strip()
    return ii["url"], strip(m.get("LicenseShortName", {}).get("value")), strip(m.get("Artist", {}).get("value")), ii["descriptionurl"]


def fetch_vsco():
    """Download the VSCO 2 CE subset listed in vsco_files.txt (skips files present)."""
    lst = Path(__file__).resolve().parent / "vsco_files.txt"
    base = "https://raw.githubusercontent.com/sgossner/VSCO-2-CE/master/"
    for rel in lst.read_text().split("\n"):
        if not rel:
            continue
        dest = ROOT / "vsco2ce" / rel
        if dest.exists() and dest.stat().st_size:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(base + urllib.parse.quote(rel), headers=UA)
        dest.write_bytes(urllib.request.urlopen(req, timeout=300).read())
        print("vsco", rel)


def main():
    fetch_vsco()
    rows = [["set_or_file", "local_path", "license", "author", "source_url", "notes"]]
    for sub, note in VSCO_SETS:
        rows.append([sub, f"samples/vsco2ce/{sub}", "CC0-1.0", "Versilian Studios (VSCO 2 CE)",
                     "https://github.com/sgossner/VSCO-2-CE", note])
    bird_dir = ROOT / "birds"
    bird_dir.mkdir(parents=True, exist_ok=True)
    for title, local, species, why in BIRDS:
        url, lic, author, page = commons(title)
        dest = bird_dir / local
        if not dest.exists():
            time.sleep(8)  # Commons 429s back-to-back media downloads
            req = urllib.request.Request(url, headers=UA)
            dest.write_bytes(urllib.request.urlopen(req, timeout=120).read())
        rows.append([f"{species}", f"samples/birds/{local}", lic, author, page, why])
        print(local, lic, author)
    with open(MANIFEST, "w", newline="") as f:
        csv.writer(f).writerows(rows)


if __name__ == "__main__":
    main()
