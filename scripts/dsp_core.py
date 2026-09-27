"""Core helpers shared by the water-year pieces: where files go, the sample
rate, astronomical day length, and the ice-crackle grain. Design notes live on
the methods page (methods.qmd).

Paths default to folders inside the repo:
  rendered/  WAVs and stems (git-ignored)       override: SONIFICATION_HEAVY
  rendered/  MP3s and score JSON                override: SONIFICATION_LIGHT
  audio/     the site's copies of some tracks   override: SONIFICATION_SITE_AUDIO
  samples/   downloaded instrument audio        override: SONIFICATION_SAMPLES
Set the environment variables to keep large audio somewhere else; renders.py
sets the first three to a scratch folder to re-render without overwriting."""
import os
from pathlib import Path

import numpy as np
from scipy.signal import lfilter

SR = 44100

ROOT = Path(__file__).resolve().parent.parent
HEAVY_OUT = Path(os.environ.get("SONIFICATION_HEAVY", ROOT / "rendered"))
SAMPLES = Path(os.environ.get("SONIFICATION_SAMPLES", ROOT / "samples"))
LIGHT_OUT = Path(os.environ.get("SONIFICATION_LIGHT", ROOT / "rendered"))
SITE_AUDIO = Path(os.environ.get("SONIFICATION_SITE_AUDIO", ROOT / "audio"))


def ice_crinkle_grain(sr=SR, dur=0.035, intensity=0.5):
    """One grain of an ice-forming 'crinkle' texture - brittle, glassy,
    higher and more clicky than the shaker grain, built from several tiny
    sub-clicks rather than one smooth burst so it reads as crackling
    rather than hiss."""
    n = int(dur * sr)
    sig = np.zeros(n)
    n_clicks = 3 + int(4 * intensity)
    for _ in range(n_clicks):
        pos = np.random.randint(0, max(n - 20, 1))
        click_n = min(np.random.randint(6, 20), n - pos)
        noise = np.random.uniform(-1, 1, click_n)
        a = np.exp(-2 * np.pi * 6500 / sr)
        hp = lfilter([1, -1], [1, -a], noise)
        env = np.exp(-np.arange(click_n) / (click_n * 0.25))
        sig[pos:pos + click_n] += hp * env
    return sig / (np.abs(sig).max() + 1e-9)


def day_length_hours(day_of_year, latitude_deg=49.03):
    """Real astronomical day length (hours) from solar declination - a
    calendar-derived seasonal signal that needs no data fetch and, unlike
    snowpack, peaks at the summer solstice rather than lagging into
    early summer, so it moves out of phase with the flow-driven layers."""
    decl = np.radians(23.44) * np.sin(2 * np.pi * (284 + day_of_year) / 365.0)
    lat = np.radians(latitude_deg)
    cos_h = -np.tan(lat) * np.tan(decl)
    cos_h = np.clip(cos_h, -1, 1)
    hour_angle = np.arccos(cos_h)
    return (24.0 / np.pi) * hour_angle
