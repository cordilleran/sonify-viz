"""Superior Ice Year (2026-09-28): does a terrain plate plus a daily ice layer equal one full render?
Run: blender -b -P blender_composite_check.py -- DIR   (DIR holds full.exr, plate.exr, ice.exr from blender_superior_ice.py --exr)
"""
# Blender python: composite plate + ice EXRs in linear light (premultiplied alpha over), compare with the full EXR,
# then write all three through the scene's AgX view transform as PNGs.
import bpy, numpy as np, sys
from pathlib import Path
d = Path(sys.argv[sys.argv.index("--") + 1])
def load(n):
    im = bpy.data.images.load(str(d / n)); w, h = im.size
    a = np.empty(w * h * 4, "float32"); im.pixels.foreach_get(a); return a.reshape(h, w, 4), (w, h)
full, (w, h) = load("full.exr"); plate, _ = load("plate.exr"); ice, _ = load("ice.exr")
comp = ice[..., :3] + (1 - ice[..., 3:4]) * plate[..., :3]
enc = lambda x: np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.clip(x, 0, None) ** (1 / 2.4) - 0.055)
diff = np.abs(enc(np.clip(full[..., :3], 0, 1)) - enc(np.clip(comp, 0, 1))) * 255
print("LINEAR_COMP mean", round(float(diff.mean()), 2), "p99", round(float(np.percentile(diff, 99)), 1), "max", round(float(diff.max()), 1), "frac>8", round(float((diff.max(-1) > 8).mean()), 4))
scn = bpy.context.scene
scn.view_settings.view_transform = "AgX"; scn.view_settings.look = "AgX - Medium High Contrast"
for name, rgb in (("comp_linear", comp), ("full_linear", full[..., :3])):
    im = bpy.data.images.new(name, w, h, float_buffer=True)
    im.pixels.foreach_set(np.concatenate([rgb, np.ones((h, w, 1), "float32")], -1).ravel())
    im.save_render(str(d / f"{name}.png"), scene=scn)
dd = np.clip(diff * 8, 0, 255).astype("uint8")
im = bpy.data.images.new("diff", w, h); im.colorspace_settings.name = "Non-Color"
im.pixels.foreach_set(np.concatenate([dd / 255.0, np.ones((h, w, 1))], -1).astype("float32").ravel())
im.filepath_raw = str(d / "diff_linear.png"); im.file_format = "PNG"; im.save()
