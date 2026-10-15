"""Render a sim/ trace JSON to PNG frames with Isaac Sim (headless, RTX).

Runs INSIDE Isaac Sim's interpreter:
    /isaac-sim/python.sh render_trace.py trace.json out_dir [--fps 25] [--camera chase|overhead]
        [--renderer RayTracedLighting|PathTracing] [--assets isaac|procedural] [--sky kloofendal]

Starting Isaac Sim requires the NVIDIA Isaac Sim EULA to have been accepted
by a human (modal_app.py sets ACCEPT_EULA only when --accept-eula is passed).

Drawing tool only. Every position comes from the 2D kinematic trace produced
by sim/world.py; nothing here simulates physics. Frame: x along road, y lateral
(left +), metres; ego lane centred on y = 0. Stage is Z-up, metres.

Assets (see ASSETS.md): DRIVE Sim-ready cars, NVIDIA MDL asphalt/grass and an
HDRI sky served for Isaac Sim 5.1; Poly Haven CC0 sky/asphalt and local CC0 cars
as fallbacks; procedural box cars as the last resort. Asset lookup and the
fitting / brake-light / camera maths live in assets.py (unit-tested locally).
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assets as A  # noqa: E402  (pure python, no Isaac deps)

ap = argparse.ArgumentParser()
ap.add_argument("trace")
ap.add_argument("out_dir")
ap.add_argument("--fps", type=int, default=25)
ap.add_argument("--width", type=int, default=1920)
ap.add_argument("--height", type=int, default=1080)
ap.add_argument("--camera", choices=["chase", "overhead"], default="chase")
ap.add_argument("--renderer", choices=["RayTracedLighting", "PathTracing"], default="RayTracedLighting")
ap.add_argument("--subframes", type=int, default=0, help="RTX subframes per frame (0 = auto: 8 RT / 32 PT)")
ap.add_argument("--assets", choices=["isaac", "procedural"], default="isaac")
ap.add_argument("--sky", choices=sorted(A.SKIES), default=A.DEFAULT_SKY)
ap.add_argument("--hold", type=float, default=2.0, help="seconds to hold the last frame")
ap.add_argument("--lead_in", type=float, default=0.5, help="seconds to hold the first frame")
args = ap.parse_args()
SUBFRAMES = args.subframes or (32 if args.renderer == "PathTracing" else 8)

from isaacsim import SimulationApp  # noqa: E402  (must be the first Isaac import)

sim_app = SimulationApp({
    "headless": True,
    "renderer": args.renderer,
    "width": args.width,
    "height": args.height,
    "anti_aliasing": 3,
})

import carb  # noqa: E402
import numpy as np  # noqa: E402
import omni.kit.commands  # noqa: E402
import omni.replicator.core as rep  # noqa: E402
import omni.usd  # noqa: E402
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade  # noqa: E402


def log(*a):
    print("[render_trace]", *a, flush=True)


settings = carb.settings.get_settings()
settings.set("/rtx/post/motionblur/enabled", False)
settings.set("/rtx/directLighting/sampledLighting/enabled", True)
if args.renderer == "PathTracing":
    settings.set("/rtx/pathtracing/spp", 1)
    settings.set("/rtx/pathtracing/totalSpp", SUBFRAMES)
    settings.set("/rtx/pathtracing/optixDenoiser/enabled", True)

try:
    from isaacsim.storage.native import get_assets_root_path
    ROOT = get_assets_root_path() or A.DEFAULT_ASSETS_ROOT
except Exception:  # noqa: BLE001
    ROOT = A.DEFAULT_ASSETS_ROOT
log("assets root:", ROOT)

with open(args.trace) as f:
    TR = json.load(f)
os.makedirs(args.out_dir, exist_ok=True)
actors = TR["actors"]
t = TR["t"]
n = len(t)
LANE_W = float(TR.get("lane_width", 3.5))
LANES = sorted(TR.get("lane_centres", [0.0, LANE_W]))
META = TR.get("meta") or {}
HIT = META.get("other_actor") if META.get("collided") else None

omni.usd.get_context().new_stage()
for _ in range(5):
    sim_app.update()
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdGeom.Xform.Define(stage, "/World")


def wait_for_loading(max_updates: int = 3000):
    try:
        from isaacsim.core.utils.stage import is_stage_loading
    except Exception:  # noqa: BLE001
        is_stage_loading = None
    for i in range(max_updates):
        sim_app.update()
        if is_stage_loading is None and i > 60:
            return
        if is_stage_loading is not None and not is_stage_loading() and i > 10:
            return


# --- materials ---------------------------------------------------------------------

def preview_material(path: str, rgb, rough=0.5, metal=0.0, emissive=None, opacity=1.0) -> UsdShade.Material:
    mat = UsdShade.Material.Define(stage, path)
    sh = UsdShade.Shader.Define(stage, path + "/Shader")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metal)
    if emissive is not None:
        sh.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*emissive))
    if opacity < 1.0:
        sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def textured_material(path: str, tex: dict) -> UsdShade.Material:
    """UsdPreviewSurface with Poly Haven textures (fallback asphalt)."""
    mat = UsdShade.Material.Define(stage, path)
    sh = UsdShade.Shader.Define(stage, path + "/Shader")
    sh.CreateIdAttr("UsdPreviewSurface")
    st = UsdShade.Shader.Define(stage, path + "/st")
    st.CreateIdAttr("UsdPrimvarReader_float2")
    st.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    for key, inp, typ, out in [("diffuse", "diffuseColor", Sdf.ValueTypeNames.Color3f, "rgb"),
                               ("roughness", "roughness", Sdf.ValueTypeNames.Float, "r"),
                               ("normal", "normal", Sdf.ValueTypeNames.Normal3f, "rgb")]:
        tx = UsdShade.Shader.Define(stage, f"{path}/{key}")
        tx.CreateIdAttr("UsdUVTexture")
        tx.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(tex[key])
        tx.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st.ConnectableAPI(), "result")
        tx.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
        tx.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
        if key != "diffuse":
            tx.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("raw")
        if key == "normal":
            tx.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(2, 2, 2, 1))
            tx.CreateInput("bias", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(-1, -1, -1, 0))
        o = tx.CreateOutput(out, Sdf.ValueTypeNames.Float3 if out == "rgb" else Sdf.ValueTypeNames.Float)
        sh.CreateInput(inp, typ).ConnectToSource(o)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def mdl_material(path: str, rel_url: str) -> UsdShade.Material | None:
    if args.assets != "isaac":
        return None
    mdl_url = A.url(ROOT, rel_url)
    name = os.path.splitext(os.path.basename(rel_url))[0]
    try:
        omni.kit.commands.execute("CreateMdlMaterialPrim", mtl_url=mdl_url, mtl_name=name, mtl_path=path)
        prim = stage.GetPrimAtPath(path)
        if prim and prim.IsValid():
            return UsdShade.Material(prim)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    log("MDL failed, falling back:", mdl_url)
    return None


def bind(prim, mat):
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat, UsdShade.Tokens.strongerThanDescendants)


# --- static scene ------------------------------------------------------------------

def quad(path: str, x0, x1, y0, y1, z, uv_tile: float) -> UsdGeom.Mesh:
    m = UsdGeom.Mesh.Define(stage, path)
    m.CreatePointsAttr([Gf.Vec3f(x0, y0, z), Gf.Vec3f(x1, y0, z), Gf.Vec3f(x1, y1, z), Gf.Vec3f(x0, y1, z)])
    m.CreateFaceVertexCountsAttr([4])
    m.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    m.CreateNormalsAttr([Gf.Vec3f(0, 0, 1)] * 4)
    m.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    m.CreateExtentAttr([Gf.Vec3f(x0, y0, z), Gf.Vec3f(x1, y1, z)])
    st = UsdGeom.PrimvarsAPI(m).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
    u, v = (x1 - x0) / uv_tile, (y1 - y0) / uv_tile
    st.Set([Gf.Vec2f(0, 0), Gf.Vec2f(u, 0), Gf.Vec2f(u, v), Gf.Vec2f(0, v)])
    return m


def box(path: str, centre, size, mat) -> UsdGeom.Cube:
    cube = UsdGeom.Cube.Define(stage, path)
    cube.CreateSizeAttr(1.0)
    xf = UsdGeom.Xformable(cube)
    xf.AddTranslateOp().Set(Gf.Vec3d(*centre))
    xf.AddScaleOp().Set(Gf.Vec3f(*size))
    bind(cube.GetPrim(), mat)
    return cube


all_x = [s[0] for a in actors.values() for s in a["states"]]
x_min, x_max = min(all_x) - 150.0, max(all_x) + 250.0
y_lo, y_hi = LANES[0] - LANE_W / 2, LANES[-1] + LANE_W / 2

m_road = mdl_material("/World/Looks/Asphalt", A.MATERIALS["asphalt"]) or textured_material("/World/Looks/AsphaltPH", A.POLYHAVEN_ASPHALT)
m_grass = mdl_material("/World/Looks/Grass", A.MATERIALS["grass"]) or preview_material("/World/Looks/GrassPV", (0.16, 0.26, 0.12), rough=0.95)
m_line = preview_material("/World/Looks/Paint", (0.9, 0.9, 0.86), rough=0.55)
m_kerb = preview_material("/World/Looks/Kerb", (0.55, 0.55, 0.53), rough=0.8)

bind(quad("/World/Ground", x_min - 300, x_max + 300, -300, 300, -0.03, 6.0).GetPrim(), m_grass)
bind(quad("/World/Road", x_min, x_max, y_lo - 1.0, y_hi + 1.0, 0.0, 4.0).GetPrim(), m_road)
for i, y in enumerate((y_lo - 1.15, y_hi + 1.15)):  # kerbs
    box(f"/World/Kerb_{i}", ((x_min + x_max) / 2, y, 0.06), (x_max - x_min, 0.3, 0.15), m_kerb)
for i, y in enumerate((y_lo, y_hi)):  # solid edge lines
    box(f"/World/Lines/edge_{i}", ((x_min + x_max) / 2, y, 0.004), (x_max - x_min, 0.15, 0.006), m_line)
for j, y in enumerate((a + b) / 2 for a, b in zip(LANES, LANES[1:])):  # dashed lane lines
    x, k = x_min, 0
    while x < x_max:
        box(f"/World/Lines/div_{j}_{k}", (x + 1.5, y, 0.004), (3.0, 0.12, 0.006), m_line)
        x, k = x + 12.0, k + 1

# lighting: HDRI dome (Isaac-served, Poly Haven fallback) + sun
dome = UsdLux.DomeLight.Define(stage, "/World/Sky")
dome.CreateIntensityAttr(1000.0)
sky_urls = A.sky_candidates(ROOT if args.assets == "isaac" else None, args.sky)
dome.CreateTextureFileAttr(sky_urls[0] if args.assets == "isaac" else sky_urls[-1])
dome.CreateTextureFormatAttr(UsdLux.Tokens.latlong)
sun = UsdLux.DistantLight.Define(stage, "/World/Sun")
sun.CreateIntensityAttr(2500.0)
sun.CreateAngleAttr(0.53)
UsdGeom.Xformable(sun).AddRotateXYZOp().Set(Gf.Vec3f(-35.0, 20.0, 30.0))

# --- vehicles ----------------------------------------------------------------------
EGO_HALO = preview_material("/World/Looks/EgoHalo", (0.05, 0.4, 1.0), emissive=(0.1, 0.6, 2.5), opacity=0.55)
HIT_HALO = preview_material("/World/Looks/HitHalo", (1.0, 0.1, 0.05), emissive=(6.0, 0.4, 0.2), opacity=0.7)
BRAKE_ON = preview_material("/World/Looks/BrakeOn", (1.0, 0.05, 0.02), emissive=(40.0, 1.0, 0.5))
BRAKE_OFF = preview_material("/World/Looks/BrakeOff", (0.25, 0.02, 0.02), rough=0.3)
PROC_COLOURS = [(0.05, 0.35, 0.85), (0.85, 0.45, 0.05), (0.6, 0.6, 0.62), (0.15, 0.55, 0.25)]

local_cars = sorted(glob.glob(os.path.join(A.LOCAL_CAR_DIR, "*.usd*")))
VEH = {}


def procedural_car(root_path: str, L: float, W: float, colour):
    """Last-resort car: rounded-ish body + glasshouse + wheels from primitives."""
    body = preview_material(root_path + "/Looks/Paint", colour, rough=0.25, metal=0.6)
    glass = preview_material(root_path + "/Looks/Glass", (0.03, 0.04, 0.05), rough=0.05, metal=0.2)
    tyre = preview_material(root_path + "/Looks/Tyre", (0.02, 0.02, 0.02), rough=0.9)
    box(root_path + "/fit/body", (0, 0, 0.62), (L, W, 0.7), body)
    box(root_path + "/fit/cabin", (-0.08 * L, 0, 1.2), (0.52 * L, 0.88 * W, 0.5), glass)
    for i, (sx, sy) in enumerate([(1, 1), (1, -1), (-1, 1), (-1, -1)]):
        cyl = UsdGeom.Cylinder.Define(stage, f"{root_path}/fit/wheel_{i}")
        cyl.CreateRadiusAttr(0.33)
        cyl.CreateHeightAttr(0.24)
        cyl.CreateAxisAttr("Y")
        UsdGeom.Xformable(cyl).AddTranslateOp().Set(Gf.Vec3d(sx * 0.33 * L, sy * (W / 2 - 0.1), 0.33))
        bind(cyl.GetPrim(), tyre)


def load_asset_car(root_path: str, L: float, candidates) -> bool:
    fit_prim = UsdGeom.Xform.Define(stage, root_path + "/fit")
    for u, yaw_off in candidates:
        asset = stage.DefinePrim(root_path + "/fit/asset", "Xform")
        asset.GetReferences().ClearReferences()
        asset.GetReferences().AddReference(u)
        wait_for_loading(600)
        try:
            up = "Z"
            try:
                up = UsdGeom.GetStageUpAxis(Usd.Stage.Open(u, Usd.Stage.LoadNone))
            except Exception:  # noqa: BLE001
                pass
            cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
            rng = cache.ComputeWorldBound(asset).ComputeAlignedRange()
            if rng.IsEmpty():
                raise RuntimeError("empty bbox")
            lo, hi = rng.GetMin(), rng.GetMax()
            fit = A.fit_vehicle(tuple(lo), tuple(hi), L, up, yaw_off)
            xf = UsdGeom.Xformable(fit_prim)
            xf.ClearXformOpOrder()
            xf.AddTranslateOp().Set(Gf.Vec3d(*fit.translate))
            xf.AddRotateZOp().Set(fit.yaw_deg)
            xf.AddRotateXOp().Set(fit.up_fix_deg)
            xf.AddScaleOp().Set(Gf.Vec3f(fit.scale, fit.scale, fit.scale))
            log(f"{root_path}: {u} up={up} bbox={tuple(lo)}..{tuple(hi)} -> {fit}")
            return True
        except Exception as e:  # noqa: BLE001
            log(f"{root_path}: asset {u} unusable ({e}), trying next")
            stage.RemovePrim(root_path + "/fit/asset")
    return False


other_i = 0
for idx, (name, a) in enumerate(actors.items()):
    if name != "ego":
        other_i += 1
    L, W = float(a.get("length", 4.5)), float(a.get("width", 1.8))
    safe = "".join(c if c.isalnum() else "_" for c in name)
    rp = f"/World/Vehicles/{safe}"
    root = UsdGeom.Xform.Define(stage, rp)
    ok = False
    if args.assets == "isaac":
        ok = load_asset_car(rp, L, A.vehicle_candidates(0 if name == "ego" else other_i, ROOT, local_cars))
    if not ok:
        log(f"{name}: procedural car")
        procedural_car(rp, L, W, PROC_COLOURS[0] if name == "ego" else PROC_COLOURS[1 + (other_i - 1) % 3])
    # brake lights (our own emissive quads at the rear bumper; asset light rigs vary)
    lamps = []
    for k, sy in enumerate((1, -1)):
        lamps.append(box(f"{rp}/brake_{k}", (-L / 2 - 0.02, sy * (W / 2 - 0.25), 0.85), (0.04, 0.32, 0.12), BRAKE_OFF))
    # ground halo: ego marker (blue), turns red on impact for the vehicles involved
    halo = UsdGeom.Cylinder.Define(stage, f"{rp}/halo")
    halo.CreateRadiusAttr(max(L, W) * 0.62)
    halo.CreateHeightAttr(0.01)
    halo.CreateAxisAttr("Z")
    UsdGeom.Xformable(halo).AddTranslateOp().Set(Gf.Vec3d(0, 0, 0.012))
    UsdGeom.Xformable(halo).AddScaleOp().Set(Gf.Vec3f(1.0, W / L * 1.4, 1.0))
    if name == "ego":
        bind(halo.GetPrim(), EGO_HALO)
    else:
        UsdGeom.Imageable(halo).MakeInvisible()
    xf = UsdGeom.Xformable(root)
    VEH[name] = dict(t_op=xf.AddTranslateOp(), r_op=xf.AddRotateZOp(), lamps=lamps, halo=halo,
                     brakes=A.brake_flags(a["states"], t), lit=None)

cam = UsdGeom.Camera.Define(stage, "/World/Camera")
cam.CreateFocalLengthAttr(28.0)
cam.CreateHorizontalApertureAttr(36.0)
cam.CreateVerticalApertureAttr(36.0 * args.height / args.width)
cam.CreateClippingRangeAttr(Gf.Vec2f(0.1, 5000.0))
cam_op = UsdGeom.Xformable(cam).AddTransformOp()


def look_at(eye, target):
    view = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1))
    cam_op.Set(view.GetInverse())


# --- frame schedule: 50 Hz trace -> args.fps ---------------------------------------
dt_tr = (t[1] - t[0]) if n > 1 else 1.0
n_frames = int(math.floor(t[-1] * args.fps)) + 1
schedule = [0] * int(args.lead_in * args.fps) + \
    [min(n - 1, int(round(k / args.fps / dt_tr))) for k in range(n_frames)] + \
    [n - 1] * int(args.hold * args.fps)
first_hold = len(schedule) - int(args.hold * args.fps)

render_prod = rep.create.render_product("/World/Camera", (args.width, args.height))
rgb = rep.AnnotatorRegistry.get_annotator("rgb")
rgb.attach([render_prod])
try:
    rep.orchestrator.set_capture_on_play(False)
except Exception:  # noqa: BLE001
    pass

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None
    log("PIL missing, writing .npy frames")

chase = A.ChaseCam()
frame_dt = 1.0 / args.fps


def place(i: int, f_i: int):
    for name, v in VEH.items():
        st = actors[name]["states"]
        x, y, heading, _ = st[min(i, len(st) - 1)]
        v["t_op"].Set(Gf.Vec3d(x, y, 0.0))
        v["r_op"].Set(math.degrees(heading))
        lit = v["brakes"][min(i, len(st) - 1)]
        if lit != v["lit"]:
            for lamp in v["lamps"]:
                bind(lamp.GetPrim(), BRAKE_ON if lit else BRAKE_OFF)
            v["lit"] = lit
        if HIT and f_i == first_hold and name in (HIT, "ego"):
            UsdGeom.Imageable(v["halo"]).MakeVisible()
            bind(v["halo"].GetPrim(), HIT_HALO)
    ex, ey, eh, _ = actors["ego"]["states"][i]
    if args.camera == "chase":
        eye, look = chase.update(ex, ey, eh, frame_dt)
        look_at(eye, look)
    else:
        mid = (LANES[0] + LANES[-1]) / 2
        look_at((ex + 10.0, mid - 0.01, 45.0), (ex + 10.0, mid, 0.0))


place(0, 0)
wait_for_loading(3000)
for _ in range(30):  # warm-up: shader compile + texture streaming
    sim_app.update()
for _ in range(3):
    rep.orchestrator.step(rt_subframes=SUBFRAMES, delta_time=0.0, pause_timeline=True)

for f_i, i in enumerate(schedule):
    place(i, f_i)
    rep.orchestrator.step(rt_subframes=SUBFRAMES, delta_time=0.0, pause_timeline=True)
    img = np.asarray(rgb.get_data())[..., :3].astype(np.uint8)
    out = os.path.join(args.out_dir, f"frame_{f_i:05d}")
    if Image is not None:
        Image.fromarray(img).save(out + ".png")
    else:
        np.save(out + ".npy", img)
    if f_i % 25 == 0:
        log(f"frame {f_i}/{len(schedule)}")

rep.orchestrator.wait_until_complete()
sim_app.close()
