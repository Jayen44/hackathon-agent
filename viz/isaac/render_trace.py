"""Render a sim/ trace JSON to PNG frames with Isaac Sim (headless, RTX).

Runs INSIDE Isaac Sim's interpreter:
    /isaac-sim/python.sh render_trace.py trace.json out_dir [--fps 25] [--camera chase|overhead]

Starting Isaac Sim requires the NVIDIA Isaac Sim EULA to have been accepted
by a human (modal_app.py sets ACCEPT_EULA only when --accept-eula is passed).

This is a drawing tool only. Every position comes from the 2D kinematic
trace produced by sim/world.py; nothing here simulates physics.
Frame: x along road, y lateral (left +), metres; ego lane centred y = 0.
Isaac stage is Z-up, metres, so sim (x, y) maps to stage (x, y, 0).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

ap = argparse.ArgumentParser()
ap.add_argument("trace")
ap.add_argument("out_dir")
ap.add_argument("--fps", type=int, default=25)
ap.add_argument("--width", type=int, default=1280)
ap.add_argument("--height", type=int, default=720)
ap.add_argument("--camera", choices=["chase", "overhead"], default="chase")
ap.add_argument("--hold", type=float, default=2.0, help="seconds to hold the last frame")
ap.add_argument("--subframes", type=int, default=4, help="RTX subframes per captured frame")
args = ap.parse_args()

from isaacsim import SimulationApp  # noqa: E402  (must be first Isaac import)

sim_app = SimulationApp({
    "headless": True,
    "renderer": "RayTracedLighting",
    "width": args.width,
    "height": args.height,
    "anti_aliasing": 3,
})

import numpy as np  # noqa: E402
import omni.replicator.core as rep  # noqa: E402
import omni.usd  # noqa: E402
from pxr import Gf, Sdf, UsdGeom, UsdLux, UsdShade  # noqa: E402

with open(args.trace) as f:
    TR = json.load(f)
os.makedirs(args.out_dir, exist_ok=True)

LANE_W = float(TR.get("lane_width", 3.5))
LANES = TR.get("lane_centres", [0.0, LANE_W])  # ego lane + left lane by default
EGO_COLOUR = (0.05, 0.45, 0.95)  # blue
OTHER_COLOURS = [(0.95, 0.55, 0.05), (0.85, 0.15, 0.15), (0.2, 0.75, 0.3), (0.7, 0.3, 0.8)]
HIT_COLOUR = (0.9, 0.05, 0.05)

omni.usd.get_context().new_stage()
for _ in range(5):
    sim_app.update()
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdGeom.Xform.Define(stage, "/World")


def material(path: str, rgb, rough: float = 0.5, metal: float = 0.0) -> UsdShade.Material:
    mat = UsdShade.Material.Define(stage, path)
    sh = UsdShade.Shader.Define(stage, path + "/Shader")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metal)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def box(path: str, centre, size, mat: UsdShade.Material) -> UsdGeom.Xformable:
    cube = UsdGeom.Cube.Define(stage, path)
    cube.CreateSizeAttr(1.0)
    xf = UsdGeom.Xformable(cube)
    xf.AddTranslateOp().Set(Gf.Vec3d(*centre))
    xf.AddScaleOp().Set(Gf.Vec3f(*size))
    UsdShade.MaterialBindingAPI.Apply(cube.GetPrim()).Bind(mat)
    return xf


# --- static scene: road, lane markings, lights ------------------------------------
actors = TR["actors"]
all_x = [s[0] for a in actors.values() for s in a["states"]]
x_min, x_max = min(all_x) - 60.0, max(all_x) + 120.0
road_len = x_max - x_min
y_lo = min(LANES) - LANE_W / 2
y_hi = max(LANES) + LANE_W / 2

m_grass = material("/World/Looks/Grass", (0.18, 0.28, 0.14), rough=0.95)
m_road = material("/World/Looks/Asphalt", (0.09, 0.09, 0.10), rough=0.9)
m_line = material("/World/Looks/Paint", (0.92, 0.92, 0.88), rough=0.6)

box("/World/Ground", ((x_min + x_max) / 2, (y_lo + y_hi) / 2, -0.06), (road_len + 400, 400, 0.1), m_grass)
box("/World/Road", ((x_min + x_max) / 2, (y_lo + y_hi) / 2, -0.005), (road_len, y_hi - y_lo + 1.0, 0.01), m_road)
# solid edge lines
for i, y in enumerate((y_lo, y_hi)):
    box(f"/World/Lines/edge_{i}", ((x_min + x_max) / 2, y, 0.002), (road_len, 0.15, 0.005), m_line)
# dashed lane dividers (UK: 3 m dash, 9 m gap on 30-40 mph roads, close enough for a picture)
dividers = [(a + b) / 2 for a, b in zip(sorted(LANES), sorted(LANES)[1:])]
for j, y in enumerate(dividers):
    x, k = x_min, 0
    while x < x_max:
        box(f"/World/Lines/div_{j}_{k}", (x + 1.5, y, 0.002), (3.0, 0.12, 0.005), m_line)
        x += 12.0
        k += 1

sun = UsdLux.DistantLight.Define(stage, "/World/Sun")
sun.CreateIntensityAttr(3000.0)
sun.CreateAngleAttr(0.5)
UsdGeom.Xformable(sun).AddRotateXYZOp().Set(Gf.Vec3f(-40.0, 25.0, 0.0))
dome = UsdLux.DomeLight.Define(stage, "/World/Sky")
dome.CreateIntensityAttr(600.0)
dome.CreateColorAttr(Gf.Vec3f(0.75, 0.85, 1.0))

# --- vehicles ----------------------------------------------------------------------
VEH = {}
hit_actor = (TR.get("meta") or {}).get("other_actor") if (TR.get("meta") or {}).get("collided") else None
for i, (name, a) in enumerate(actors.items()):
    colour = EGO_COLOUR if name == "ego" else OTHER_COLOURS[(i - 1) % len(OTHER_COLOURS)]
    L, W, H = float(a.get("length", 4.5)), float(a.get("width", 1.8)), float(a.get("height", 1.5))
    safe = "".join(c if c.isalnum() else "_" for c in name)
    root = UsdGeom.Xform.Define(stage, f"/World/Vehicles/{safe}")
    xf = UsdGeom.Xformable(root)
    t_op = xf.AddTranslateOp()
    r_op = xf.AddRotateZOp()
    m_body = material(f"/World/Looks/{safe}", colour, rough=0.35, metal=0.3)
    m_glass = material(f"/World/Looks/{safe}_glass", (0.05, 0.06, 0.08), rough=0.1)
    body = UsdGeom.Cube.Define(stage, f"/World/Vehicles/{safe}/body")
    body.CreateSizeAttr(1.0)
    UsdGeom.Xformable(body).AddTranslateOp().Set(Gf.Vec3d(0, 0, 0.35 + 0.35))
    UsdGeom.Xformable(body).AddScaleOp().Set(Gf.Vec3f(L, W, 0.7))
    UsdShade.MaterialBindingAPI.Apply(body.GetPrim()).Bind(m_body)
    cabin = UsdGeom.Cube.Define(stage, f"/World/Vehicles/{safe}/cabin")
    cabin.CreateSizeAttr(1.0)
    UsdGeom.Xformable(cabin).AddTranslateOp().Set(Gf.Vec3d(-0.1 * L, 0, 0.7 + (H - 0.7) / 2))
    UsdGeom.Xformable(cabin).AddScaleOp().Set(Gf.Vec3f(0.5 * L, 0.9 * W, H - 0.7))
    UsdShade.MaterialBindingAPI.Apply(cabin.GetPrim()).Bind(m_glass)
    VEH[name] = (t_op, r_op, body, safe)

cam = UsdGeom.Camera.Define(stage, "/World/Camera")
cam.CreateFocalLengthAttr(24.0)
cam.CreateClippingRangeAttr(Gf.Vec2f(0.1, 2000.0))
cam_op = UsdGeom.Xformable(cam).AddTransformOp()


def look_at(eye, target):
    view = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1))
    cam_op.Set(view.GetInverse())


# --- frame schedule: 50 Hz trace -> args.fps --------------------------------------
t = TR["t"]
n = len(t)
t_end = t[-1]
n_frames = int(math.floor(t_end * args.fps)) + 1
dt = (t[1] - t[0]) if n > 1 else 1.0
idx = [min(n - 1, int(round(k / args.fps / dt))) for k in range(n_frames)]
idx += [n - 1] * int(args.hold * args.fps)

rp = rep.create.render_product("/World/Camera", (args.width, args.height))
rgb = rep.AnnotatorRegistry.get_annotator("rgb")
rgb.attach([rp])
try:
    rep.orchestrator.set_capture_on_play(False)
except Exception:
    pass

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None
    print("[render_trace] PIL missing, writing .npy frames", file=sys.stderr)

# warm up the renderer (first frames are often black while shaders compile)
ego0 = actors["ego"]["states"][0]
look_at((ego0[0] - 16, ego0[1] - 6, 8), (ego0[0] + 12, ego0[1], 0))
for _ in range(20):
    sim_app.update()

for f_i, i in enumerate(idx):
    for name, (t_op, r_op, body, safe) in VEH.items():
        x, y, heading, _v = actors[name]["states"][min(i, len(actors[name]["states"]) - 1)]
        t_op.Set(Gf.Vec3d(x, y, 0.0))
        r_op.Set(math.degrees(heading))
        if hit_actor and f_i == n_frames and name in (hit_actor, "ego"):  # first held frame
            UsdShade.MaterialBindingAPI(body.GetPrim()).Bind(material(f"/World/Looks/{safe}_hit", HIT_COLOUR))

    ex, ey = actors["ego"]["states"][i][0], actors["ego"]["states"][i][1]
    if args.camera == "chase":
        look_at((ex - 16.0, ey - 7.0, 8.0), (ex + 14.0, LANE_W / 2 * 0.5, 0.0))
    else:
        look_at((ex + 8.0, LANE_W / 2, 55.0), (ex + 8.0, LANE_W / 2 + 0.01, 0.0))

    rep.orchestrator.step(rt_subframes=args.subframes, delta_time=0.0, pause_timeline=True)
    data = rgb.get_data()
    img = np.asarray(data)[..., :3]
    out = os.path.join(args.out_dir, f"frame_{f_i:05d}")
    if Image is not None:
        Image.fromarray(img.astype(np.uint8)).save(out + ".png")
    else:
        np.save(out + ".npy", img)
    if f_i % 25 == 0:
        print(f"[render_trace] frame {f_i}/{len(idx)}", flush=True)

rep.orchestrator.wait_until_complete()
sim_app.close()
