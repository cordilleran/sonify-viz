"""Superior Ice Year, Blender version: the 2025-26 ice season over the real lake floor.

Run (after scripts/blender_prep_superior.py):
  /snap/bin/blender -b -P scripts/blender_superior_ice.py -- --days 0:227 --res 1280x720 --engine CYCLES --samples 24
  --days A:B   day indices to render (227 days, 0 = 2025-11-01); --fpd N frames per day (fields interpolate in time)
  --day N      one still (day N) to stdout path <out>/still_dNNN.png
  --ve 20      vertical exaggeration of relief (bathymetry and land)

What is what (R observed / D derived / S symbolic):
  R  lake floor and land relief: NOAA NCEI Great Lakes bathymetry (NOAA/GLERL/CHS 3 arc-second grid)
  R  ice concentration and SST fields: GLERL/CoastWatch ERDDAP grids, the same atlases as the audio page
  D  sun elevation = solar noon elevation at 47.7 N for each date; camera path chosen by hand
  S  ice floe pattern: a noise threshold that puts ice on a fraction of the surface equal to the observed
     concentration. Where the floes sit inside a cell is not observed. Vertical exaggeration is a stated factor.
Outputs go to runtime rendered/icecover/blender/frames_<tag>/.
"""
import sys, os, json, math, argparse, time
from pathlib import Path
import numpy as np
import bpy, mathutils

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--days", default="0:227")
ap.add_argument("--day", type=float, default=None)
ap.add_argument("--fpd", type=int, default=1)
ap.add_argument("--res", default="1280x720")
ap.add_argument("--engine", default="CYCLES")
ap.add_argument("--samples", type=int, default=24)
ap.add_argument("--ve", type=float, default=20.0)
ap.add_argument("--tag", default="v0")
ap.add_argument("--cam", default="nadir")  # nadir (straight down, perspective) | ortho (straight down, orthographic: a map) | path (v0 tilt path)
ap.add_argument("--light", default="sun205")  # key (315/45 fixed + seasonal exposure lift, D) | multi (baked multidirectional relief + soft fill) | noon (true noon sun, 180) | sun205 (v0)
ap.add_argument("--palette", default="v0")    # A | B | C (superior_palette.py, shared with the 4K still) | v0
ap.add_argument("--device", default="CPU")    # CPU | GPU | BOTH (Cycles; GPU compute type from $CYCLES_DEVICE_TYPE, default HIP)
ap.add_argument("--layer", default="full")    # full | plate (terrain only, no water/ice) | ice (water/ice sheet over a holdout terrain, transparent)
ap.add_argument("--eevee_tune", action="store_true")  # EEVEE with ray-traced shadows, finer sun shadow maps, fast GI for contact shading
ap.add_argument("--sat", type=float, default=1.0)     # compositor saturation after render (1 = none)
ap.add_argument("--world", type=float, default=0.5)    # sky (ambient) strength; lower = deeper relief shading
ap.add_argument("--sun_gain", type=float, default=1.0) # multiplies the key light's energy
ap.add_argument("--look", default="AgX - Medium High Contrast")
ap.add_argument("--exr", action="store_true")  # write linear, premultiplied OpenEXR (for compositing layers before the view transform)
ap.add_argument("--hud", action="store_true")  # burn a date/stat HUD into frames (off: GW's frame is HTML/JS, 09-28)
a = ap.parse_args(argv)

RT = Path(os.environ.get("SONIFICATION_HEAVY", Path(__file__).resolve().parent.parent / "rendered")) / "icecover" / "blender"   # as blender_prep_superior.py
days = json.load(open(RT / "days.json"))
fields = np.load(RT / "fields.npy")
floor = np.load(RT / "floor_1200.npy")
N = len(days["dates"])
FH, FW = fields.shape[1:3]
H, W = floor.shape
ASPECT = days["aspect"]
LAT0, LAT1 = days["extent"]["lat"]
LON0, LON1 = days["extent"]["lon"]
BU_KM = 10.0
SX = (LON1 - LON0) * 111.32 * math.cos(math.radians((LAT0 + LAT1) / 2)) / BU_KM
SY = (LAT1 - LAT0) * 111.19 / BU_KM

bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene


def ramp(vals, stops):
    xs = np.array([s[0] for s in stops], "float32")
    cols = np.array([[int(s[1][i:i + 2], 16) / 255 for i in (1, 3, 5)] for s in stops], "float32")
    return np.stack([np.interp(vals, xs, cols[:, k]) for k in range(3)], -1)


def lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


# ---- terrain mesh: land and lake floor in one displaced grid -----------------------------------
xs = (np.arange(W) / (W - 1) - 0.5) * SX
ys = (0.5 - np.arange(H) / (H - 1)) * SY
X, Y = np.meshgrid(xs, ys)
Z = floor / 1000.0 * (1000.0 / (BU_KM * 1000.0)) * a.ve  # metres -> BU (10 km) with exaggeration
verts = np.stack([X, Y, Z], -1).reshape(-1, 3).astype("float32")
ii, jj = np.meshgrid(np.arange(W - 1), np.arange(H - 1))
v00 = (jj * W + ii).ravel()
quads = np.stack([v00, v00 + 1, v00 + W + 1, v00 + W], -1).astype("int32")
mesh = bpy.data.meshes.new("Terrain")
mesh.vertices.add(len(verts))
mesh.vertices.foreach_set("co", verts.ravel())
nq = len(quads)
mesh.loops.add(nq * 4)
mesh.loops.foreach_set("vertex_index", quads.ravel())
mesh.polygons.add(nq)
mesh.polygons.foreach_set("loop_start", (np.arange(nq) * 4).astype("int32"))
mesh.polygons.foreach_set("use_smooth", np.ones(nq, bool))
mesh.update(calc_edges=True)
mesh.validate()

if a.palette == "v0":   # the v0 ramps; A/B/C come from superior_palette.py, shared with the 4K still
    depth = np.clip(-floor, 0, 406) / 406.0
    dcol = ramp(depth, [(0, "#9fd0d2"), (0.08, "#3e8fa8"), (0.3, "#1d5a86"), (0.6, "#122f5c"), (1, "#070c22")])
    lcol = ramp(np.clip(floor, 0, 520) / 520.0, [(0, "#4b5a45"), (0.25, "#6f7358"), (0.6, "#948e73"), (1, "#c9c4b0")])
    rgb = lin(np.where((floor < 0)[..., None], dcol, lcol * 0.62))
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import superior_palette as SP
    base = SP.colours(floor, a.palette)
    if a.light == "multi":   # multidirectional: the relief is baked from gdaldem's multidirectional hillshade; the sun is only a fill
        base = SP.shade_mix(base, np.load(RT / "shade_multi_1200.npy"), a.palette)
    base = np.where((floor < 0)[..., None], base, base * 0.7)   # land darker than in the still, so ice reads against it (v0 did x0.62)
    rgb = lin(base)
rgba = np.concatenate([rgb, np.ones((H, W, 1), "float32")], -1).reshape(-1, 4).astype("float32")
ca = mesh.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
ca.data.foreach_set("color", rgba.ravel())
uv = mesh.uv_layers.new(name="UV")
u = (X / SX + 0.5).reshape(-1)
v = (Y / SY + 0.5).reshape(-1)
uv.data.foreach_set("uv", np.stack([u[quads.ravel()], v[quads.ravel()]], -1).ravel().astype("float32"))
terrain = bpy.data.objects.new("Terrain", mesh)
scn.collection.objects.link(terrain)

BASE = -1.4
edges = [(Z[0, :], X[0, :], Y[0, :]), (Z[-1, ::-1], X[-1, ::-1], Y[-1, ::-1]),
         (Z[::-1, 0], X[::-1, 0], Y[::-1, 0]), (Z[:, -1], X[:, -1], Y[:, -1])]
sv, sf = [], []
for z_, x_, y_ in edges:
    k0 = len(sv)
    n = len(z_)
    for i in range(n):
        sv.append((float(x_[i]), float(y_[i]), float(z_[i])))
        sv.append((float(x_[i]), float(y_[i]), BASE))
    for i in range(n - 1):
        sf.append((k0 + 2 * i, k0 + 2 * i + 1, k0 + 2 * i + 3, k0 + 2 * i + 2))
skm = bpy.data.meshes.new("Skirt")
skm.from_pydata(sv, [], sf)
sk = bpy.data.objects.new("Skirt", skm)
scn.collection.objects.link(sk)
kmat = bpy.data.materials.new("SkirtMat")
kmat.use_nodes = True
kb = kmat.node_tree.nodes["Principled BSDF"]
kb.inputs["Base Color"].default_value = (0.012, 0.014, 0.016, 1)
kb.inputs["Roughness"].default_value = 0.9
skm.materials.append(kmat)

tm = bpy.data.materials.new("TerrainMat")
tm.use_nodes = True
nt = tm.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial")
pb = nt.nodes.new("ShaderNodeBsdfPrincipled")
at = nt.nodes.new("ShaderNodeAttribute")
at.attribute_name = "Col"
pb.inputs["Roughness"].default_value = 0.9
nt.links.new(at.outputs["Color"], pb.inputs["Base Color"])
nt.links.new(pb.outputs["BSDF"], out.inputs["Surface"])
mesh.materials.append(tm)

# ---- water / ice surface ------------------------------------------------------------------------
surf_mesh = bpy.data.meshes.new("Surface")
surf_mesh.from_pydata([(-SX / 2, -SY / 2, 0), (SX / 2, -SY / 2, 0), (SX / 2, SY / 2, 0), (-SX / 2, SY / 2, 0)], [], [(0, 1, 2, 3)])
suv = surf_mesh.uv_layers.new(name="UV")
for li, uvv in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
    suv.data[li].uv = uvv
surf = bpy.data.objects.new("Surface", surf_mesh)
scn.collection.objects.link(surf)

fimg = bpy.data.images.new("fields", FW, FH, alpha=True, float_buffer=True)
fimg.colorspace_settings.name = "Non-Color"
mimg = bpy.data.images.load(str(RT / "mask_2048.png"))
mimg.colorspace_settings.name = "Non-Color"

sm = bpy.data.materials.new("SurfaceMat")
sm.use_nodes = True
try:
    sm.surface_render_method = "BLENDED"
except Exception:
    pass
nt = sm.node_tree
N_ = nt.nodes
L_ = nt.links
N_.clear()
out = N_.new("ShaderNodeOutputMaterial")
pb = N_.new("ShaderNodeBsdfPrincipled")
tc = N_.new("ShaderNodeTexCoord")
ft = N_.new("ShaderNodeTexImage")
ft.image = fimg
ft.interpolation = "Cubic"
ft.extension = "EXTEND"
sep = N_.new("ShaderNodeSeparateColor")
mt = N_.new("ShaderNodeTexImage")
mt.image = mimg
mt.interpolation = "Linear"
mt.extension = "EXTEND"
noise = N_.new("ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 0.9
noise.inputs["Detail"].default_value = 12
noise.inputs["Roughness"].default_value = 0.62
noise.inputs["Distortion"].default_value = 0.5
L_.new(tc.outputs["UV"], ft.inputs["Vector"])
L_.new(tc.outputs["UV"], mt.inputs["Vector"])
L_.new(tc.outputs["Object"], noise.inputs["Vector"])
L_.new(ft.outputs["Color"], sep.inputs["Color"])


def node_math(op, x, y=None, clamp=False):
    n = N_.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    if isinstance(x, (int, float)):
        n.inputs[0].default_value = x
    else:
        L_.new(x, n.inputs[0])
    if y is not None:
        if isinstance(y, (int, float)):
            n.inputs[1].default_value = y
        else:
            L_.new(y, n.inputs[1])
    return n.outputs[0]


def maprange(x, a0, a1, b0, b1):
    n = N_.new("ShaderNodeMapRange")
    n.clamp = True
    L_.new(x, n.inputs["Value"])
    n.inputs["From Min"].default_value = a0
    n.inputs["From Max"].default_value = a1
    n.inputs["To Min"].default_value = b0
    n.inputs["To Max"].default_value = b1
    return n.outputs["Result"]


f = sep.outputs["Red"]
nprime = maprange(noise.outputs["Fac"], 0.25, 0.75, 0.05, 0.95)
diff = node_math("SUBTRACT", f, nprime)
cover = maprange(diff, -0.04, 0.04, 0.0, 1.0)

sst_col = N_.new("ShaderNodeValToRGB")
L_.new(sep.outputs["Green"], sst_col.inputs["Fac"])
cr = sst_col.color_ramp
cr.elements[0].position = 0.0
cr.elements[0].color = (0.010, 0.045, 0.085, 1)
cr.elements[1].position = 1.0
cr.elements[1].color = (0.03, 0.30, 0.34, 1)
e = cr.elements.new(0.16)
e.color = (0.012, 0.075, 0.13, 1)

ice_var = maprange(noise.outputs["Fac"], 0.3, 0.7, 0.55, 0.85)
vor = N_.new("ShaderNodeTexVoronoi")
vor.feature = "DISTANCE_TO_EDGE"
vor.inputs["Scale"].default_value = 2.4
vor.inputs["Randomness"].default_value = 1.0
L_.new(tc.outputs["Object"], vor.inputs["Vector"])
crack = maprange(vor.outputs["Distance"], 0.0, 0.07, 1.0, 0.0)
crack_dim = node_math("SUBTRACT", 1.0, node_math("MULTIPLY", crack, 0.42))
ice_lum = node_math("MULTIPLY", ice_var, crack_dim)
ice_col = N_.new("ShaderNodeCombineColor")
L_.new(ice_lum, ice_col.inputs["Red"])
L_.new(ice_lum, ice_col.inputs["Green"])
L_.new(node_math("MULTIPLY", ice_lum, 1.12, clamp=True), ice_col.inputs["Blue"])

mix = N_.new("ShaderNodeMix")
mix.data_type = "RGBA"
L_.new(cover, mix.inputs[0])
L_.new(sst_col.outputs["Color"], mix.inputs[6])
L_.new(ice_col.outputs["Color"], mix.inputs[7])
L_.new(mix.outputs[2], pb.inputs["Base Color"])

rough = maprange(cover, 0.0, 1.0, 0.05, 0.5)
L_.new(rough, pb.inputs["Roughness"])
al = maprange(cover, 0.0, 1.0, 0.62, 1.0)
sepm = N_.new("ShaderNodeSeparateColor")
L_.new(mt.outputs["Color"], sepm.inputs["Color"])
lake_a = maprange(sepm.outputs["Red"], 0.45, 0.55, 0.0, 1.0)
alpha = node_math("MULTIPLY", al, lake_a)
L_.new(alpha, pb.inputs["Alpha"])
bump = N_.new("ShaderNodeBump")
L_.new(node_math("MULTIPLY", cover, 0.3), bump.inputs["Strength"])
L_.new(node_math("ADD", noise.outputs["Fac"], node_math("MULTIPLY", crack, -0.6)), bump.inputs["Height"])
L_.new(bump.outputs["Normal"], pb.inputs["Normal"])
pb.inputs["Specular IOR Level"].default_value = 0.6
L_.new(pb.outputs["BSDF"], out.inputs["Surface"])
surf_mesh.materials.append(sm)

# ---- world, sun, camera, HUD --------------------------------------------------------------------
world = bpy.data.worlds.new("W")
world.use_nodes = True
scn.world = world
wnt = world.node_tree
wn = wnt.nodes
sky = wn.new("ShaderNodeTexSky")
sky.sky_type = "SINGLE_SCATTERING"
try:
    sky.sun_disc = False
except Exception:
    pass
bg = wn["Background"]
lp = wn.new("ShaderNodeLightPath")
win = wn.new("ShaderNodeTexCoord")
gsep = wn.new("ShaderNodeSeparateXYZ")
gr = wn.new("ShaderNodeValToRGB")
gr.color_ramp.elements[0].color = (0.006, 0.010, 0.022, 1)
gr.color_ramp.elements[1].color = (0.030, 0.052, 0.085, 1)
wnt.links.new(win.outputs["Window"], gsep.inputs[0])
wnt.links.new(gsep.outputs["Y"], gr.inputs["Fac"])
wmix = wn.new("ShaderNodeMix")
wmix.data_type = "RGBA"
wnt.links.new(lp.outputs["Is Camera Ray"], wmix.inputs[0])
wnt.links.new(sky.outputs["Color"], wmix.inputs[6])
wnt.links.new(gr.outputs["Color"], wmix.inputs[7])
wnt.links.new(wmix.outputs[2], bg.inputs["Color"])
bg.inputs["Strength"].default_value = a.world

sun_data = bpy.data.lights.new("Sun", "SUN")
sun_data.angle = math.radians(1.5)
sun = bpy.data.objects.new("Sun", sun_data)
scn.collection.objects.link(sun)

cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 35
cam_data.clip_end = 1000
cam = bpy.data.objects.new("Cam", cam_data)
scn.collection.objects.link(cam)
scn.camera = cam

hud_mat = bpy.data.materials.new("HUD")
hud_mat.use_nodes = True
hn = hud_mat.node_tree.nodes
hn.clear()
he = hn.new("ShaderNodeEmission")
ho = hn.new("ShaderNodeOutputMaterial")
he.inputs["Strength"].default_value = 3.0
hud_mat.node_tree.links.new(he.outputs[0], ho.inputs["Surface"])


def hud(name, size, x, y):
    c = bpy.data.curves.new(name, "FONT")
    c.size = size
    c.body = name
    o = bpy.data.objects.new(name, c)
    o.parent = cam
    o.location = (x, y, -6.0)
    c.materials.append(hud_mat)
    scn.collection.objects.link(o)
    return c


res_x, res_y = map(int, a.res.split("x"))
half_w = 6.0 * 18.0 / 35.0
half_h = half_w * res_y / res_x
hud_date = hud("date", 0.34, -half_w + 0.25, half_h - 0.62) if a.hud else None
hud_stat = hud("stat", 0.17, -half_w + 0.25, half_h - 0.95) if a.hud else None
if a.cam == "ortho":
    cam_data.type = "ORTHO"
    exact = abs(res_x / res_y - SX / SY) < 0.02   # a frame of the data's own shape is exactly the extent, no margin
    cam_data.ortho_scale = max(SX, SY * res_x / res_y) * (1.0 if exact else 1.03)

scn.render.resolution_x, scn.render.resolution_y = res_x, res_y
scn.render.resolution_percentage = 100
scn.render.image_settings.file_format = "PNG"
scn.view_settings.view_transform = "AgX"
scn.view_settings.look = a.look
scn.render.engine = "BLENDER_EEVEE" if a.engine.upper().startswith("EEVEE") else "CYCLES"
if scn.render.engine == "CYCLES":
    scn.cycles.samples = a.samples
    scn.cycles.use_denoising = True
    scn.cycles.device = "CPU" if a.device == "CPU" else "GPU"
    if a.device != "CPU":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = os.environ.get("CYCLES_DEVICE_TYPE", "HIP")
        prefs.get_devices()
        for dv in prefs.devices:
            dv.use = dv.type == prefs.compute_device_type or (a.device == "BOTH" and dv.type == "CPU")
        print("DEVICES", [(dv.name, dv.type, dv.use) for dv in prefs.devices])
    scn.render.threads_mode = "AUTO"
    scn.cycles.max_bounces = 4
    scn.cycles.transparent_max_bounces = 8

WAY = [  # day, camera azimuth deg from N (180 = south of the target, looking north), elevation deg (90 = straight down), distance BU, target x, y
    (0, 180, 89, 68, 0, 0),
    (82, 180, 83, 64, 3, -1),
    (121, 180, 76, 63, 0, -1.5),
    (175, 180, 83, 64, -2, -0.5),
    (227, 180, 89, 68, 0, 0),
]


def catmull(p0, p1, p2, p3, t):
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)


def cam_state(d):
    ws = np.array(WAY, float)
    k = int(np.clip(np.searchsorted(ws[:, 0], d, side="right") - 1, 0, len(ws) - 2))
    t = (d - ws[k, 0]) / (ws[k + 1, 0] - ws[k, 0])
    P = lambda i: ws[int(np.clip(i, 0, len(ws) - 1)), 1:]
    return catmull(P(k - 1), P(k), P(k + 1), P(k + 2), float(np.clip(t, 0, 1)))


def solar_elev(date):
    import datetime
    y, m, dd = map(int, date.split("-"))
    doy = datetime.date(y, m, dd).timetuple().tm_yday
    decl = 23.44 * math.sin(math.radians(360 / 365 * (doy - 80)))
    return 90 - abs(47.7 - decl)


def set_day(d):
    d = float(np.clip(d, 0, N - 1))
    d0 = int(math.floor(d))
    d1 = min(d0 + 1, N - 1)
    w = d - d0
    fr = fields[d0].astype("float32") * (1 - w) + fields[d1].astype("float32") * w
    buf = np.zeros((FH, FW, 4), "float32")
    buf[..., 0] = fr[..., 0] / 100.0
    buf[..., 1] = np.clip(fr[..., 1] / 10.0 / 25.0, 0, 1)
    buf[..., 3] = 1
    fimg.pixels.foreach_set(buf[::-1].ravel())
    fimg.update()
    date = days["dates"][int(round(d))]
    el = solar_elev(date)
    az = math.radians(205)
    dvec = mathutils.Vector((math.sin(az) * math.cos(math.radians(el)), math.cos(az) * math.cos(math.radians(el)), math.sin(math.radians(el))))
    if a.light in ("key", "multi"):   # cartographic key light from the NW, fixed; exposure lifts with the real noon sun (D)
        kaz, kel = math.radians(315), math.radians(45 if a.light == "key" else 70)
        dvec = mathutils.Vector((math.sin(kaz) * math.cos(kel), math.cos(kaz) * math.cos(kel), math.sin(kel)))
    elif a.light == "noon":
        az = math.radians(180)
        dvec = mathutils.Vector((math.sin(az) * math.cos(math.radians(el)), math.cos(az) * math.cos(math.radians(el)), math.sin(math.radians(el))))
    sun.rotation_euler = (-dvec).to_track_quat("-Z", "Y").to_euler()
    sun_data.energy = 0.9 + 2.2 * math.sin(math.radians(el))
    if a.light == "key":
        sun_data.energy = 2.2 + 1.0 * math.sin(math.radians(el))
    elif a.light == "multi":
        sun_data.energy = 1.2 + 0.6 * math.sin(math.radians(el))
    sun_data.energy *= a.sun_gain
    sky.sun_elevation = math.radians(el)
    if a.cam in ("nadir", "ortho", "top"):   # straight down, north up, fixed: no tilt, no motion
        cam.location = (0, 0, 62)
        cam.rotation_euler = (0, 0, 0)
    else:
        s = cam_state(d)
        az_c, el_c, dist, tx, ty = math.radians(s[0]), math.radians(s[1]), s[2], s[3], s[4]
        tgt = mathutils.Vector((tx, ty, 0))
        eye = tgt + mathutils.Vector((math.sin(az_c) * math.cos(el_c), math.cos(az_c) * math.cos(el_c), math.sin(el_c))) * dist
        cam.location = eye
        cam.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
    if not a.hud:
        return
    mo = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(date[5:7]) - 1]
    hud_date.body = f"{int(date[8:10])} {mo} {date[:4]}"
    i = int(round(d))
    hud_stat.body = f"lake-mean ice {days['lake_ice_pct'][i]:.0f} %\nsurface temperature {days['lake_sst_c'][i]:.1f} C"


if scn.render.engine == "BLENDER_EEVEE" and a.eevee_tune:
    ee = scn.eevee
    ee.use_shadows = True
    ee.shadow_ray_count = 4
    ee.shadow_step_count = 16
    ee.shadow_resolution_scale = 1.0
    ee.use_raytracing = True
    ee.use_fast_gi = True
    ee.fast_gi_distance = 3.0
    ee.fast_gi_ray_count = 4
    ee.fast_gi_step_count = 12
    sun_data.shadow_maximum_resolution = 0.001
    sun_data.shadow_filter_radius = 0.5
    sun_data.use_shadow_jitter = True
if abs(a.sat - 1.0) > 1e-6:   # compositor: saturation only, after the view transform's input
    ng = bpy.data.node_groups.new("Comp", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    hs = ng.nodes.new("CompositorNodeHueSat")
    go = ng.nodes.new("NodeGroupOutput")
    ng.links.new(rl.outputs["Image"], hs.inputs["Image"])
    ng.links.new(hs.outputs["Image"], go.inputs[0])
    hs.inputs["Saturation"].default_value = a.sat
    scn.compositing_node_group = ng
    scn.render.use_compositing = True

if a.layer == "plate":   # the sheet stays in the scene for light and shadow, but the camera does not see it
    surf.visible_camera = False
elif a.layer == "ice":   # the terrain is still there for light and shadow, but cut out of the image
    scn.render.film_transparent = True
    terrain.is_holdout = True
    sk.is_holdout = True
    scn.render.image_settings.color_mode = "RGBA"

if a.exr:
    scn.render.image_settings.file_format = "OPEN_EXR"
    scn.render.image_settings.color_mode = "RGBA"
    scn.render.image_settings.color_depth = "32"

out_dir = RT / f"frames_{a.tag}"
out_dir.mkdir(exist_ok=True)
T0 = time.time()
if a.day is not None:
    set_day(a.day)
    T0 = time.time()
    scn.render.filepath = str(out_dir / f"still_d{int(a.day):03d}.{'exr' if a.exr else 'png'}")
    bpy.ops.render.render(write_still=True)
    print("WROTE", scn.render.filepath)
    print("RENDER_SECONDS", round(time.time() - T0, 1))
else:
    d_a, d_b = map(int, a.days.split(":"))
    t0 = time.time()
    fr = 0
    for k in range(d_a * a.fpd, d_b * a.fpd):
        p = out_dir / f"frame_{k:05d}.png"
        if p.exists():
            continue
        set_day(k / a.fpd)
        scn.render.filepath = str(p)
        bpy.ops.render.render(write_still=True)
        fr += 1
        print(f"FRAME {k} done, {(time.time() - t0) / fr:.1f}s/frame", flush=True)
