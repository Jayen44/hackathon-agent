"""Build the CCTV street scene procedurally in Blender (bpy) and render a frame range with Cycles.

    python blender_scene.py --trace trace.json --assets /assets --out /vol/renders/x/frames \
        --start 0 --end 24 [--samples 64] [--device GPU|CPU] [--res 100]

SYNTHETIC RENDER of a 2D sim trace. Vehicle motion is the sim trace (viz/isaac/samples/*_trace.json);
nothing here simulates anything. Camera = viz/isaac/assets.CctvCamera (exact pose + intrinsics), so the
calibration clicks in the truth file stay exact. Assets: Poly Haven CC0 (asphalt_02 textures, kloofendal
HDRI). Everything else (cars, kerbs, buildings, lamp posts, markings) is procedural.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

import bpy  # noqa: I001  (bpy must be imported before bmesh)
import bmesh
from mathutils import Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from keys import WHEEL_RADIUS, blender_camera_matrix, frame_keys  # noqa: E402

LANE_W = 3.5
CARRIAGEWAY_HALF = 5.75       # 3 x 3.5 m lanes + 0.5 m strips
KERB_W, KERB_H = 0.15, 0.12
PAVE_W = 2.8
ROAD_X0, ROAD_X1 = -420.0, 260.0


# --- materials ---------------------------------------------------------------------------------

def principled(name, color, rough=0.5, metal=0.0, coat=0.0, emit=None, emit_strength=0.0, spec=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = 0.03
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = spec
    if emit is not None:
        b.inputs["Emission Color"].default_value = (*emit, 1.0)
        b.inputs["Emission Strength"].default_value = emit_strength
    return m


def _noise_mix(m, scale, c_lo, c_hi, detail=6.0, rough_lo=None, rough_hi=None, coord="Object"):
    """Base colour = noise-driven ramp between c_lo and c_hi (breaks up flat procedural surfaces)."""
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    nt.links.new(geo.outputs["Position"], n.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (*c_lo, 1)
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = (*c_hi, 1)
    nt.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    if rough_lo is not None:
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = rough_lo
        mr.inputs["To Max"].default_value = rough_hi
        nt.links.new(n.outputs["Fac"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    return m


def asphalt_material(assets):
    m = principled("asphalt", (0.08, 0.08, 0.08), rough=0.9)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / 4.2, 1 / 4.2, 1 / 4.2)   # ~4 m tile, rotated so repeats don't line up
    mp.inputs["Rotation"].default_value = (0, 0, 0.37)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])

    def tex(fn, noncolor):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(os.path.join(assets, fn))
        if noncolor:
            t.image.colorspace_settings.name = "Non-Color"
        nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
        return t

    diff = tex("asphalt_02_diff_2k.jpg", False)
    rough = tex("asphalt_02_rough_2k.jpg", True)
    nor = tex("asphalt_02_nor_gl_2k.jpg", True)
    # Large-scale variation (patching, wear, tyre polish in the wheel paths) to hide tiling.
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 0.08
    n.inputs["Detail"].default_value = 4
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.55, 0.55, 0.56, 1)
    ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1)
    nt.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(diff.outputs["Color"], mul.inputs[6])
    nt.links.new(ramp.outputs["Color"], mul.inputs[7])
    nt.links.new(mul.outputs[2], b.inputs["Base Color"])
    nt.links.new(rough.outputs["Color"], b.inputs["Roughness"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 0.8
    nt.links.new(nor.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


def paint_material(name):
    """Worn thermoplastic road paint: white with noise-driven wear patches."""
    m = principled(name, (0.8, 0.8, 0.78), rough=0.55)
    return _noise_mix(m, 9.0, (0.32, 0.32, 0.31), (0.86, 0.86, 0.84), detail=8, rough_lo=0.8, rough_hi=0.5)


# --- mesh helpers ------------------------------------------------------------------------------

def link(obj, coll=None):
    (coll or bpy.context.scene.collection).objects.link(obj)
    return obj


def box(name, x0, x1, y0, y1, z0, z1, mat, parent=None, bevel=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(me)
    bm.free()
    ob = link(bpy.data.objects.new(name, me))
    ob.scale = (x1 - x0, y1 - y0, z1 - z0)
    ob.location = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    me.materials.append(mat)
    if bevel > 0:
        bv = ob.modifiers.new("bevel", "BEVEL")
        bv.width = bevel
        bv.segments = 2
    if parent is not None:
        ob.parent = parent
    return ob


def plane(name, x0, x1, y0, y1, z, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [], [(0, 1, 2, 3)])
    me.materials.append(mat)
    return link(bpy.data.objects.new(name, me))


def cylinder(name, r, depth, mat, verts=32):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=r, depth=depth)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    return link(bpy.data.objects.new(name, me))


def loft(name, profile_xz, half_w, mats, face_mat_fn, parent):
    """Extrude a side profile (x along car, z up) across the car with a z-dependent half width.
    face_mat_fn(kind, i) -> material index; kind in {'side', 'quad'}; i = profile edge index."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    L = [bm.verts.new((x, -half_w(z), z)) for x, z in profile_xz]
    R = [bm.verts.new((x, half_w(z), z)) for x, z in profile_xz]
    n = len(profile_xz)
    f = bm.faces.new(L)
    f.material_index = face_mat_fn("side", -1)
    f = bm.faces.new(list(reversed(R)))
    f.material_index = face_mat_fn("side", -1)
    for i in range(n):
        j = (i + 1) % n
        f = bm.faces.new((L[i], R[i], R[j], L[j]))
        f.material_index = face_mat_fn("quad", i)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    for m in mats:
        me.materials.append(m)
    ob = link(bpy.data.objects.new(name, me))
    ob.parent = parent
    return ob


# --- car ---------------------------------------------------------------------------------------

_SHARED = {}


def shared_mats():
    if not _SHARED:
        _SHARED["glass"] = principled("glass", (0.015, 0.017, 0.02), rough=0.04, spec=0.9)
        _SHARED["tyre"] = principled("tyre", (0.025, 0.025, 0.025), rough=0.85)
        _SHARED["rim"] = principled("rim", (0.75, 0.75, 0.76), rough=0.25, metal=1.0)
        _SHARED["trim"] = principled("trim", (0.02, 0.02, 0.02), rough=0.5)
        _SHARED["chrome"] = principled("chrome", (0.9, 0.9, 0.9), rough=0.08, metal=1.0)
        _SHARED["head"] = principled("headlamp", (0.9, 0.9, 0.95), rough=0.05, emit=(1.0, 0.97, 0.9), emit_strength=2.0)
        _SHARED["tail"] = principled("taillamp", (0.5, 0.02, 0.02), rough=0.1, emit=(1.0, 0.05, 0.03), emit_strength=0.6)
        _SHARED["brake"] = principled("brakelamp", (0.6, 0.02, 0.02), rough=0.1, emit=(1.0, 0.05, 0.03), emit_strength=6.0)
        _SHARED["plate_r"] = principled("plate_rear", (0.85, 0.7, 0.05), rough=0.3)
        _SHARED["plate_f"] = principled("plate_front", (0.85, 0.85, 0.85), rough=0.3)
        _SHARED["well"] = principled("wheelwell", (0.01, 0.01, 0.01), rough=0.9)
    return _SHARED


# Side profile of a mid-size saloon (x forward from the centre, m): roof / bonnet / boot height.
_TOP = [(-2.25, 0.62), (-2.2, 0.86), (-2.1, 0.97), (-1.85, 1.01), (-1.55, 1.03), (-1.4, 1.06), (-1.0, 1.33),
        (-0.75, 1.42), (-0.45, 1.45), (0.05, 1.45), (0.3, 1.42), (0.55, 1.3), (0.95, 1.01), (1.4, 0.93),
        (1.85, 0.86), (2.12, 0.78), (2.22, 0.68), (2.25, 0.55)]
_WHEEL_X = (-1.36, 1.36)
_ARCH_R = 0.40


def _lerp_table(tab, x):
    for (x0, y0), (x1, y1) in zip(tab, tab[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return tab[0][1] if x < tab[0][0] else tab[-1][1]


def _station(x):
    """Cross-section ring at x: 10 (y, z) points, left (-y) bottom to right bottom, plus flags."""
    hl = 2.25
    end = max(0.0, (abs(x) - 1.95) / 0.3)                     # 0 mid-car, 1 at the bumper face
    hw = 0.895 - 0.09 * end ** 2
    zb = 0.19 + 0.13 * end
    for wx in _WHEEL_X:                                       # wheel-arch cut-out
        d = abs(x - wx)
        if d < _ARCH_R:
            zb = max(zb, 0.34 + math.sqrt(_ARCH_R ** 2 - d ** 2) * 0.95)
    zt = _lerp_table(_TOP, x)
    belt = min(0.96, zt - 0.03) if abs(x) < hl - 0.05 else zt - 0.02
    shoulder = max(zb + 0.05, belt - 0.1)
    lower = min(shoulder - 0.02, zb + 0.16)
    hw_top = 0.85 * hw + (0.665 - 0.85 * hw) * min(1.0, max(0.0, (zt - 1.02) / 0.43))
    ring = [(-hw * 0.94, zb), (-hw, lower), (-hw, shoulder), (-hw * 0.975, belt), (-hw_top, zt),
            (hw_top, zt), (hw * 0.975, belt), (hw, shoulder), (hw, lower), (hw * 0.94, zb)]
    return ring


def car_body_mesh(name):
    """Lofted saloon body: (verts, faces, face material index) with 0 = paint, 1 = glass, 2 = black trim."""
    xs = [-2.25 + 0.075 * i for i in range(61)]
    rings = [_station(x) for x in xs]
    verts = [(x, y, z) for x, r in zip(xs, rings) for (y, z) in r]
    n = 10
    faces, mats = [], []
    for i in range(len(xs) - 1):
        xm = (xs[i] + xs[i + 1]) / 2
        zt = _lerp_table(_TOP, xm)
        for j in range(n):
            k = (j + 1) % n
            faces.append((i * n + j, (i + 1) * n + j, (i + 1) * n + k, i * n + k))
            if j in (3, 5) and -1.32 < xm < 0.88 and zt > 1.12:
                mats.append(1)                                 # side windows
            elif j == 4 and (-1.38 < xm < -0.78 or 0.32 < xm < 0.93):
                mats.append(1)                                 # rear screen / windscreen
            elif j in (0, 9) or j == 9:
                mats.append(2)                                 # sills
            else:
                mats.append(0)
    faces.append(tuple(reversed(range(n))))
    mats.append(0)
    last = (len(xs) - 1) * n
    faces.append(tuple(last + j for j in range(n)))
    mats.append(0)
    return verts, faces, mats


def make_car(name, paint_rgb, metallic):
    """Procedural 4-door saloon, 4.5 x 1.79 x 1.45 m (trace geometry: length 4.5, width 1.8), lofted from
    cross-sections with wheel-arch cut-outs, flush glass, lamps, plates, mirrors. Origin = centre on the
    ground, +x forward. Plates are blank (no characters)."""
    S = shared_mats()
    paint = principled(f"paint_{name}", paint_rgb, rough=0.22, metal=metallic, coat=1.0)
    root = link(bpy.data.objects.new(name, None))
    verts, faces, mats = car_body_mesh(name)
    me = bpy.data.meshes.new(f"{name}_body")
    me.from_pydata(verts, [], faces)
    for m in (paint, S["glass"], S["trim"]):
        me.materials.append(m)
    for p, mi in zip(me.polygons, mats):
        p.material_index = mi
        p.use_smooth = True
    me.validate()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    body = link(bpy.data.objects.new(f"{name}_body", me))
    body.parent = root
    hl = 2.25
    # B-pillar (black) splits the side glass into two windows.
    for sgn in (-1, 1):
        y = sgn * 0.735
        box(f"{name}_bpillar{sgn}", -0.38, -0.28, y - 0.015, y + 0.015, 1.0, 1.38, S["trim"], parent=root)
        box(f"{name}_head{sgn}", hl - 0.22, hl - 0.03, sgn * 0.52 - 0.15, sgn * 0.52 + 0.15, 0.62, 0.72,
            S["head"], parent=root, bevel=0.02)
        box(f"{name}_tail{sgn}", -hl + 0.0, -hl + 0.16, sgn * 0.62 - 0.17, sgn * 0.62 + 0.17, 0.78, 0.9,
            S["tail"], parent=root, bevel=0.02)
        box(f"{name}_mirror{sgn}", 0.68, 0.86, sgn * 0.93 - 0.08, sgn * 0.93 + 0.08, 0.98, 1.09, S["trim"],
            parent=root, bevel=0.02)
        box(f"{name}_handle{sgn}{0}", 0.25, 0.4, sgn * 0.9 - 0.01, sgn * 0.9 + 0.01, 0.86, 0.89, S["chrome"], parent=root)
        box(f"{name}_handle{sgn}{1}", -0.85, -0.7, sgn * 0.9 - 0.01, sgn * 0.9 + 0.01, 0.86, 0.89, S["chrome"], parent=root)
    box(f"{name}_grille", hl - 0.06, hl + 0.005, -0.42, 0.42, 0.34, 0.52, S["trim"], parent=root, bevel=0.02)
    box(f"{name}_plate_f", hl - 0.01, hl + 0.02, -0.26, 0.26, 0.37, 0.48, S["plate_f"], parent=root)
    box(f"{name}_plate_r", -hl - 0.02, -hl + 0.01, -0.26, 0.26, 0.55, 0.66, S["plate_r"], parent=root)
    box(f"{name}_rbumper", -hl - 0.01, -hl + 0.12, -0.8, 0.8, 0.27, 0.36, S["trim"], parent=root)
    box(f"{name}_fbumper", hl - 0.1, hl + 0.01, -0.78, 0.78, 0.24, 0.32, S["trim"], parent=root)
    box(f"{name}_under", -1.9, 1.9, -0.8, 0.8, 0.17, 0.3, S["well"], parent=root)
    # Wheels on pivots (rotate about local y): tyre + alloy rim with 5 dark spoke gaps.
    pivots = []
    for wx in _WHEEL_X:
        for sgn in (-1, 1):
            pv = link(bpy.data.objects.new(f"{name}_wpivot{wx}{sgn}", None))
            pv.parent = root
            pv.location = (wx, sgn * 0.765, WHEEL_RADIUS)
            t = cylinder(f"{name}_tyre{wx}{sgn}", WHEEL_RADIUS, 0.205, S["tyre"])
            t.parent = pv
            t.rotation_euler = (math.pi / 2, 0, 0)
            bv = t.modifiers.new("bevel", "BEVEL")
            bv.width, bv.segments = 0.04, 3
            r = cylinder(f"{name}_rim{wx}{sgn}", 0.2, 0.212, S["rim"], verts=24)
            r.parent = pv
            r.rotation_euler = (math.pi / 2, 0, 0)
            for k in range(5):
                a = 2 * math.pi * k / 5
                g = box(f"{name}_gap{wx}{sgn}{k}", -0.035, 0.035, -0.109, 0.109, 0.055, 0.175, S["well"])
                g.parent = pv
                g.location = (0.115 * math.sin(a), 0.0, 0.115 * math.cos(a))
                g.rotation_euler = (0, a, 0)
            pivots.append(pv)
    return root, pivots


# --- environment -------------------------------------------------------------------------------

def build_world(assets):
    sc = bpy.context.scene
    w = bpy.data.worlds.new("world")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(os.path.join(assets, "sky_2k.hdr"))
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, math.radians(110))
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
    bg = nt.nodes["Background"]
    bg.inputs["Strength"].default_value = 0.75
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 2.6
    sun.angle = math.radians(1.5)
    sun.color = (1.0, 0.96, 0.9)
    so = link(bpy.data.objects.new("sun", sun))
    so.rotation_euler = (math.radians(50), 0, math.radians(-30))   # afternoon sun, shadows across the road


def build_road(assets):
    asphalt = asphalt_material(assets)
    paint = paint_material("paint")
    kerb = _noise_mix(principled("kerb", (0.45, 0.45, 0.43), rough=0.8), 4.0, (0.24, 0.24, 0.23), (0.36, 0.36, 0.35))
    pave = principled("pavement", (0.3, 0.3, 0.29), rough=0.85)
    nt = pave.node_tree
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Color1"].default_value = (0.21, 0.205, 0.2, 1)
    br.inputs["Color2"].default_value = (0.18, 0.175, 0.17, 1)
    br.inputs["Mortar"].default_value = (0.11, 0.11, 0.105, 1)
    br.inputs["Mortar Size"].default_value = 0.012
    br.inputs["Brick Width"].default_value = 0.6
    br.inputs["Row Height"].default_value = 0.6
    tc = nt.nodes.new("ShaderNodeNewGeometry")
    nt.links.new(tc.outputs["Position"], br.inputs["Vector"])
    nt.links.new(br.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
    grass = _noise_mix(principled("grass", (0.12, 0.15, 0.07), rough=0.95), 2.5, (0.06, 0.08, 0.035),
                       (0.15, 0.17, 0.09), detail=12)
    ground = _noise_mix(principled("ground", (0.2, 0.2, 0.18), rough=0.95), 0.3, (0.13, 0.15, 0.10),
                        (0.22, 0.22, 0.2))

    plane("carriageway", ROAD_X0, ROAD_X1, -CARRIAGEWAY_HALF, CARRIAGEWAY_HALF, 0.0, asphalt)
    plane("ground", -900, 700, -400, 400, -0.05, ground)
    for sgn in (-1, 1):
        y0 = sgn * CARRIAGEWAY_HALF
        y1 = sgn * (CARRIAGEWAY_HALF + KERB_W)
        box(f"kerb{sgn}", ROAD_X0, ROAD_X1, min(y0, y1), max(y0, y1), -0.05, KERB_H, kerb)
        p0, p1 = y1, sgn * (CARRIAGEWAY_HALF + KERB_W + PAVE_W)
        box(f"pave{sgn}", ROAD_X0, ROAD_X1, min(p0, p1), max(p0, p1), -0.05, KERB_H - 0.01, pave)
        g0, g1 = p1, sgn * (CARRIAGEWAY_HALF + KERB_W + PAVE_W + 6.0)
        plane(f"verge{sgn}", ROAD_X0, ROAD_X1, min(g0, g1), max(g0, g1), 0.02, grass)
        # Solid edge line 0.15 m, 0.3 m in from the kerb.
        ye = sgn * (CARRIAGEWAY_HALF - 0.3)
        plane(f"edge{sgn}", ROAD_X0, ROAD_X1, ye - 0.075, ye + 0.075, 0.004, paint)
    # Lane-line dashes: 3 m long, 0.12 m wide, starting at x = 12 k (same as the truth file).
    k0, k1 = int(ROAD_X0 // 12), int(ROAD_X1 // 12)
    verts, faces = [], []
    for y in (-LANE_W / 2, LANE_W / 2):
        for k in range(k0, k1 + 1):
            x0 = 12.0 * k
            i = len(verts)
            verts += [(x0, y - 0.06, 0.004), (x0 + 3.0, y - 0.06, 0.004), (x0 + 3.0, y + 0.06, 0.004), (x0, y + 0.06, 0.004)]
            faces.append((i, i + 1, i + 2, i + 3))
    me = bpy.data.meshes.new("dashes")
    me.from_pydata(verts, [], faces)
    me.materials.append(paint)
    link(bpy.data.objects.new("dashes", me))


def build_streetscape():
    pole = principled("pole", (0.35, 0.36, 0.37), rough=0.5, metal=0.6)
    lamp = principled("lamp", (0.9, 0.9, 0.85), rough=0.2)
    for x in range(-300, 240, 32):
        for sgn in (-1, 1):
            if sgn < 0 and 100 < x < 125:
                continue  # leave room for the camera pole
            yp = sgn * (CARRIAGEWAY_HALF + KERB_W + 0.5)
            p = cylinder(f"pole{x}{sgn}", 0.08, 8.0, pole, verts=12)
            p.location = (x, yp, 4.0)
            box(f"arm{x}{sgn}", x - 0.05, x + 0.05, min(yp, yp - sgn * 1.6), max(yp, yp - sgn * 1.6), 7.85, 7.95, pole)
            box(f"head{x}{sgn}", x - 0.18, x + 0.18, yp - sgn * 1.9, yp - sgn * 1.4, 7.75, 7.85, lamp)
    # Building frontages beyond the verge (simple massing, brick + window bands).
    import random
    rnd = random.Random(7)
    bricks = []
    for i, c in enumerate([(0.36, 0.18, 0.12), (0.45, 0.32, 0.22), (0.55, 0.52, 0.48), (0.30, 0.27, 0.25)]):
        m = principled(f"facade{i}", c, rough=0.85)
        nt = m.node_tree
        br = nt.nodes.new("ShaderNodeTexBrick")
        # "bricks" = window panes, "mortar" = wall: a window grid in world metres on (x, z)
        br.offset = 0.0
        br.inputs["Scale"].default_value = 0.3
        br.inputs["Color1"].default_value = (0.05, 0.06, 0.075, 1)
        br.inputs["Color2"].default_value = (0.09, 0.1, 0.12, 1)
        br.inputs["Mortar"].default_value = (*c, 1)
        br.inputs["Mortar Size"].default_value = 0.3
        br.inputs["Brick Width"].default_value = 1.2
        br.inputs["Row Height"].default_value = 1.0
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Rotation"].default_value = (math.pi / 2, 0, 0)
        nt.links.new(geo.outputs["Position"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], br.inputs["Vector"])
        nt.links.new(br.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
        bricks.append(m)
    roof = principled("roof", (0.12, 0.12, 0.13), rough=0.8)
    for sgn in (-1, 1):
        x = -420.0
        while x < 260:
            w = rnd.uniform(10, 26)
            d = rnd.uniform(10, 16)
            h = rnd.uniform(7, 16)
            y0 = sgn * (CARRIAGEWAY_HALF + KERB_W + PAVE_W + 6.5 + rnd.uniform(0, 3))
            y1 = y0 + sgn * d
            if not (sgn < 0 and 80 < x < 140):
                box(f"bld{sgn}{int(x)}", x, x + w - 1.5, min(y0, y1), max(y0, y1), 0, h, rnd.choice(bricks))
                box(f"roof{sgn}{int(x)}", x - 0.2, x + w - 1.3, min(y0, y1) - 0.2, max(y0, y1) + 0.2, h, h + 0.4, roof)
            x += w
    # A few trees on the verges.
    bark = principled("bark", (0.12, 0.09, 0.06), rough=0.9)
    leaf = _noise_mix(principled("leaf", (0.08, 0.12, 0.05), rough=0.9), 3.0, (0.03, 0.05, 0.02), (0.11, 0.15, 0.06))
    for x in (-180, -120, -64, -10, 40, 76):
        for sgn in (-1, 1):
            yt = sgn * (CARRIAGEWAY_HALF + KERB_W + PAVE_W + 2.5)
            t = cylinder(f"trunk{x}{sgn}", 0.18, 3.0, bark, verts=10)
            t.location = (x + 6 * (sgn > 0), yt, 1.5)
            me = bpy.data.meshes.new(f"crown{x}{sgn}")
            bm = bmesh.new()
            bmesh.ops.create_icosphere(bm, subdivisions=3, radius=2.4)
            bm.to_mesh(me)
            bm.free()
            for p in me.polygons:
                p.use_smooth = True
            me.materials.append(leaf)
            c = link(bpy.data.objects.new(f"crown{x}{sgn}", me))
            c.location = (x + 6 * (sgn > 0), yt, 4.6)
            c.scale = (1.0, 1.0, 1.15)
            dp = c.modifiers.new("disp", "DISPLACE")
            tx = bpy.data.textures.new(f"cl{x}{sgn}", "CLOUDS")
            tx.noise_scale = 0.8
            dp.texture = tx
            dp.strength = 0.9


# --- animation + render ------------------------------------------------------------------------

def animate(trace, fps, cars):
    keys = frame_keys(trace, fps)
    for f, fr in enumerate(keys):
        for name, (root, pivots) in cars.items():
            x, y, h, v, wa = fr[name]
            root.location = (x, y, 0.0)
            root.rotation_euler = (0.0, 0.0, h)
            root.keyframe_insert("location", frame=f)
            root.keyframe_insert("rotation_euler", frame=f)
            for pv in pivots:
                pv.rotation_euler = (0.0, wa, 0.0)
                pv.keyframe_insert("rotation_euler", frame=f)
    for ob in bpy.data.objects:
        if ob.animation_data and ob.animation_data.action:
            for fc in ob.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
    return len(keys)


def setup_camera(cam):
    c = bpy.data.cameras.new("cctv")
    c.sensor_fit = "HORIZONTAL"
    c.sensor_width = cam["h_aperture_mm"]
    c.lens = cam["focal_mm"]
    c.clip_start, c.clip_end = 0.5, 2000
    ob = link(bpy.data.objects.new("cctv", c))
    ob.matrix_world = Matrix(blender_camera_matrix(cam))
    bpy.context.scene.camera = ob
    return ob


def setup_render(cam, samples, device, res_pct):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.render.resolution_x, sc.render.resolution_y = cam["width"], cam["height"]
    sc.render.resolution_percentage = res_pct
    sc.render.fps = 25
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.5     # 1/50 s exposure at 25 fps
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except TypeError:
        pass
    sc.cycles.max_bounces = 4
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 2
    sc.cycles.transmission_bounces = 2
    sc.cycles.use_adaptive_sampling = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.image_settings.compression = 15
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        sc.view_settings.view_transform = "Filmic"
    used = "CPU"
    if device == "GPU":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for backend in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = backend
                prefs.get_devices()
                devs = [d for d in prefs.devices if d.type == backend]
                if devs:
                    for d in prefs.devices:
                        d.use = d.type == backend
                    sc.cycles.device = "GPU"
                    used = backend
                    break
            except Exception as e:  # noqa: BLE001
                print("GPU backend", backend, "unavailable:", e, flush=True)
    if used == "CPU":
        sc.cycles.device = "CPU"
        sc.render.threads_mode = "AUTO"
    print("cycles device:", used, flush=True)
    return used


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=-1)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--device", default="GPU")
    ap.add_argument("--res", type=int, default=100)
    ap.add_argument("--fps", type=int, default=25)
    a = ap.parse_args(argv)
    t0 = time.time()
    trace = json.load(open(a.trace))
    cam = trace["cctv_camera"]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _SHARED.clear()   # containers are reused between calls; the factory reset frees these materials
    build_world(a.assets)
    build_road(a.assets)
    build_streetscape()
    colours = {"ego": ((0.78, 0.78, 0.77), 0.15), "cutter": ((0.02, 0.045, 0.13), 0.6),
               "traffic": ((0.35, 0.03, 0.03), 0.4)}
    cars = {}
    for name in trace["actors"]:
        rgb, metal = colours.get(name, ((0.4, 0.4, 0.42), 0.6))
        cars[name] = make_car(name, rgb, metal)
    n = animate(trace, a.fps, cars)
    setup_camera(cam)
    used = setup_render(cam, a.samples, a.device, a.res)
    sc = bpy.context.scene
    end = n - 1 if a.end < 0 else min(a.end, n - 1)
    os.makedirs(a.out, exist_ok=True)
    print(f"scene built in {time.time() - t0:.1f}s; rendering {a.start}..{end} of {n}", flush=True)
    for f in range(a.start, end + 1):
        t1 = time.time()
        sc.frame_set(f)
        sc.render.filepath = os.path.join(a.out, f"{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print(f"frame {f} {time.time() - t1:.1f}s ({used})", flush=True)
    return used


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
