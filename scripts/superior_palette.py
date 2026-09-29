"""Superior Ice Year terrain palettes (2026-09-28). One definition for the 4K hillshade still
(blender_prep_superior.py) and the Blender terrain's vertex colours (blender_superior_ice.py). Pure numpy, so
Blender's own python can import it.

  A  as the v0 still: saturated depth ramp, olive land
  B  winter: saturation about 60 %, 20 % blend toward a cool white, land in cool stone greys
  C  paler winter: saturation about 45 %, 30 % lift, meant for the multidirectional relief

Depth runs 0..406 m (Superior's deepest sounding), land 0..500 m above lake level.
"""
import numpy as np

DEPTH_MAX, LAND_MAX = 406.0, 500.0
DEEP = ["#a8d4d8", "#3e8fa8", "#1d5a86", "#122f5c", "#0a1233"]
LAND_OLIVE = ["#54604a", "#7d7a5c", "#a29b80", "#d9d4c4"]
LAND_STONE = ["#5d6468", "#7f868a", "#a3a9ab", "#d6dadb"]
WINTER_WHITE = "#eef3f6"
PALETTES = {
    "A": dict(land=LAND_OLIVE, sat=1.0, lift=0.0),
    "B": dict(land=LAND_STONE, sat=0.6, lift=0.2),
    "C": dict(land=LAND_STONE, sat=0.45, lift=0.3),
}


def hex_rgb(h):
    return np.array([int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)], "float32")


def ramp(v, stops):
    """v in 0..1 -> rgb, stops evenly spaced."""
    cols = np.stack([hex_rgb(s) for s in stops])
    xs = np.linspace(0, 1, len(stops))
    return np.stack([np.interp(v, xs, cols[:, k]) for k in range(3)], -1).astype("float32")


def winterize(rgb, sat, lift):
    lum = (rgb * np.array([0.2126, 0.7152, 0.0722], "float32")).sum(-1, keepdims=True)
    rgb = lum + sat * (rgb - lum)
    return rgb + lift * (hex_rgb(WINTER_WHITE) - rgb)


def colours(elev, name="A"):
    """elev: metres relative to lake level (lake < 0) -> sRGB 0..1, shape elev.shape + (3,)."""
    p = PALETTES[name]
    lake = (elev < 0)[..., None]
    deep = ramp(np.clip(-elev, 0, DEPTH_MAX) / DEPTH_MAX, DEEP)
    land = ramp(np.clip(elev, 0, LAND_MAX) / LAND_MAX, p["land"])
    return np.clip(winterize(np.where(lake, deep, land), p["sat"], p["lift"]), 0, 1)


def shade_mix(rgb, shade, name="A"):
    """Apply a 0..1 hillshade. The winter palettes keep more of the base colour in shadow, so relief reads softer."""
    lo = {"A": 0.55, "B": 0.62, "C": 0.7}[name]
    return np.clip(rgb * (lo + (1.15 - lo) * shade[..., None]), 0, 1)
