"""
Copy a Meridian Chorus render's MP3 and visual data beside its page,
meridian/ (2026-09-27). The page reads <name>.json and plays <name>.mp3.

    python export_meridian.py [meridian_ds2023 ...]

Published from 2026-09-28 (GW's go, with a visible note that the territory
acknowledgements are still being prepared): publish_site.sh copies the page
and the renders named in PUBLISHED. The MP3 is encoded here at 128 kbps from
the WAV, so a 16-minute render stays under the repo's 20 MB file limit.
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dsp_core as W

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "meridian"
PUBLISHED = ["meridian_ds2023__layer2-wide-long", "meridian_ds2023"]  # the page's menu; publish_site.sh copies these


def main(names):
    DEST.mkdir(exist_ok=True)
    for name in names or PUBLISHED:
        src = W.LIGHT_OUT / "meridian"
        shutil.copyfile(src / f"{name}_viz.json", DEST / f"{name}.json")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(W.HEAVY_OUT / "meridian" / f"{name}.wav"),
                        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-b:a", "128k", str(DEST / f"{name}.mp3")],
                       check=True)
        print(f"meridian/{name}: {(DEST / f'{name}.json').stat().st_size // 1024} KB json, "
              f"{(DEST / f'{name}.mp3').stat().st_size // 2**20} MB mp3")


if __name__ == "__main__":
    main(sys.argv[1:])
