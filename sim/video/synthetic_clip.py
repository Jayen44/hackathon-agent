"""Render a SYNTHETIC CCTV clip with known ground truth (for smoke tests and accuracy checks).

A pinhole camera on a pole looks along a straight two-lane road. Low-poly cars (shaded boxes:
body, cabin, wheels, tail lights) drive scripted trajectories, so every speed in the clip is
known exactly. Nothing here is real footage; results on it are labelled synthetic.

    python -m sim.video.synthetic_clip out.mp4 [lead_brake|cut_in]

writes out.mp4 and out.truth.json (world trajectories, calibration clicks in pixels + metres).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

W_IMG, H_IMG = 1280, 720
LANE_W = 3.5
DASH_L, GAP_L = 3.0, 6.0          # synthetic marking pattern (not a UK standard claim)
X0 = 16.5                         # AV centre at t=0: fully in view (box clear of the frame edge)


def camera(height=8.0, pitch_deg=12.0, back=4.0, f=1500.0, y_cam=-2.0):
    p = math.radians(pitch_deg)
    right = np.array([0.0, -1.0, 0.0])
    fwd = np.array([math.cos(p), 0.0, -math.sin(p)])
    down = np.cross(fwd, right)
    R = np.vstack([right, down, fwd])
    C = np.array([-back, y_cam, height])
    K = np.array([[f, 0, W_IMG / 2], [0, f, H_IMG / 2], [0, 0, 1.0]])
    return K, R, C


def project3(K, R, C, P):
    P = np.atleast_2d(P)
    pc = (P - C) @ R.T
    z = pc[:, 2:3]
    uv = (pc @ K.T)[:, :2] / z
    return uv, z[:, 0]


def ground_H(K, R, C):
    """World ground plane -> image."""
    H = K @ np.c_[R[:, 0], R[:, 1], -R @ C]
    return H / H[2, 2]


def _box(cx, cy, z0, L, Wd, Hh, yaw=0.0):
    c, s = math.cos(yaw), math.sin(yaw)
    pts = []
    for dz in (z0, z0 + Hh):
        for dx, dy in ((-L / 2, -Wd / 2), (L / 2, -Wd / 2), (L / 2, Wd / 2), (-L / 2, Wd / 2)):
            pts.append([cx + c * dx - s * dy, cy + s * dx + c * dy, dz])
    return np.array(pts)


FACES = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def _draw_box(img, cam, pts, color, shade=(0.55, 1.0, 0.75, 0.85, 0.75, 0.6)):
    import cv2
    K, R, C = cam
    uv, z = project3(K, R, C, pts)
    if (z <= 0.5).any():
        return
    faces = []
    for fi, f in enumerate(FACES):
        centre = pts[list(f)].mean(axis=0)
        faces.append((np.linalg.norm(centre - C), fi, f))
    for _, fi, f in sorted(faces, reverse=True):
        k = shade[fi]
        col = tuple(int(min(255, c * k)) for c in color)
        cv2.fillConvexPoly(img, uv[list(f)].round().astype(np.int32), col, lineType=cv2.LINE_AA)


def draw_car(img, cam, x, y, yaw, color, braking=False):
    import cv2
    L, Wd = 4.5, 1.8
    K, R, C = cam
    # wheels
    for dx in (-1.4, 1.4):
        for dy in (-0.82, 0.82):
            c, s = math.cos(yaw), math.sin(yaw)
            _draw_box(img, cam, _box(x + c * dx - s * dy, y + s * dx + c * dy, 0.0, 0.65, 0.25, 0.65, yaw), (20, 20, 20))
    _draw_box(img, cam, _box(x, y, 0.3, L, Wd, 0.65, yaw), color)
    _draw_box(img, cam, _box(x - 0.3, y, 0.95, 2.4, Wd * 0.86, 0.5, yaw), tuple(int(c * 0.35 + 40) for c in color))
    # tail lights + rear window on the back face (x - L/2)
    c, s = math.cos(yaw), math.sin(yaw)
    for dy in (-0.65, 0.65):
        px = x - c * (L / 2 + 0.02) - s * dy
        py = y - s * (L / 2 + 0.02) + c * dy
        uv, z = project3(K, R, C, np.array([[px, py, 0.75]]))
        if z[0] > 0.5:
            r = max(2, int(220 / z[0]))
            cv2.circle(img, tuple(uv[0].round().astype(int)), r, (40, 40, 255) if braking else (30, 30, 150), -1, cv2.LINE_AA)


def draw_road(img, cam):
    import cv2
    K, R, C = cam
    near = C[0] + 1.0                                       # nearest visible road x
    img[:] = (90, 140, 95)                                  # verge
    pitch = math.asin(-R[2, 2])
    img[:max(0, int(K[1, 2] - K[1, 1] * math.tan(pitch)))] = (225, 200, 170)   # sky above the horizon
    road = np.array([[near, -LANE_W / 2 - LANE_W], [400, -LANE_W / 2 - LANE_W], [400, LANE_W / 2 + LANE_W * 0.2], [near, LANE_W / 2 + LANE_W * 0.2]])
    uv, _ = project3(K, R, C, np.c_[road, np.zeros(4)])
    cv2.fillConvexPoly(img, uv.round().astype(np.int32), (75, 75, 78), lineType=cv2.LINE_AA)
    def stripe(y, x0, x1, w=0.15):
        q = np.array([[x0, y - w / 2, 0], [x1, y - w / 2, 0], [x1, y + w / 2, 0], [x0, y + w / 2, 0]])
        uv, z = project3(K, R, C, q)
        if (z > 0.5).all():
            cv2.fillConvexPoly(img, uv.round().astype(np.int32), (235, 235, 235), lineType=cv2.LINE_AA)
    stripe(-LANE_W / 2 - LANE_W, near, 400)            # edge lines
    stripe(LANE_W / 2, near, 400)
    x = 0.0
    while x < 300:                                     # dashed lane divider
        stripe(-LANE_W / 2, x, x + DASH_L)
        x += DASH_L + GAP_L


def scenario(kind: str, fps: float, seconds: float):
    t = np.arange(0, seconds, 1 / fps)
    n = len(t)
    ego = np.zeros((n, 3))     # x, y, yaw
    oth = np.zeros((n, 3))
    pas = np.zeros((n, 3))
    if kind == "lead_brake":
        ve, vo, a, tb = 14.0, 9.0, 6.0, 1.5
        ego[:, 0] = X0 + ve * t
        tt = np.clip(t - tb, 0, vo / a)
        oth[:, 0] = X0 + 4.5 + 20.0 + vo * np.minimum(t, tb) + vo * tt - 0.5 * a * tt ** 2
        truth = {"ego_speed_mps": ve, "other_speed_mps": vo, "gap_m": 20.0, "other_decel_mps2": a, "other_brake_t_s": tb}
    else:
        ve, vo, ts, dur = 14.0, 9.0, 1.2, 1.8
        ego[:, 0] = X0 + ve * t
        oth[:, 0] = X0 + 4.5 + 14.0 + vo * t
        u = np.clip((t - ts) / dur, 0, 1)
        oth[:, 1] = -LANE_W * (1 + np.cos(np.pi * u)) / 2
        oth[:, 2] = np.where((u > 0) & (u < 1), np.arctan2(np.gradient(oth[:, 1], t), vo), 0.0)
        truth = {"ego_speed_mps": ve, "other_speed_mps": vo, "gap_m": 14.0, "lateral_offset_m": LANE_W,
                 "cut_in_start_s": ts, "cut_in_duration_s": dur}
    pas[:, 0] = -10 + 19.0 * t
    pas[:, 1] = -LANE_W
    # Contact: freeze both once bumpers meet in the same lane.
    contact = None
    for i in range(n):
        if oth[i, 0] - ego[i, 0] <= 4.5 and abs(oth[i, 1] - ego[i, 1]) < 1.8:
            contact = i
            break
    if contact is not None:
        ego[contact:] = ego[contact]
        oth[contact:] = oth[contact]
        truth["contact_t_s"] = float(t[contact])
    return t, ego, oth, pas, truth


def render_clip(path: str, kind: str = "lead_brake", fps: float = 25.0, seconds: float = 5.0) -> dict:
    import cv2
    cam = camera()
    t, ego, oth, pas, truth = scenario(kind, fps, seconds)
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W_IMG, H_IMG))
    base = np.zeros((H_IMG, W_IMG, 3), np.uint8)
    draw_road(base, cam)
    for i in range(len(t)):
        img = base.copy()
        cars = [(pas[i], (160, 160, 165), False), (oth[i], (40, 60, 170), i > 0 and oth[i, 0] - oth[i - 1, 0] < oth[max(0, i - 1), 0] - oth[max(0, i - 2), 0] - 1e-3),
                (ego[i], (230, 230, 235), False)]
        for (x, y, yaw), col, brk in sorted(cars, key=lambda c: -c[0][0]):   # far first
            draw_car(img, cam, x, y, yaw, col, brk)
        vw.write(img)
    vw.release()
    K, R, C = cam
    Hg = ground_H(K, R, C)
    # Calibration rectangle: a lane-divider dash (A, B) and the facing stretch of the right edge line.
    x0 = 2 * (DASH_L + GAP_L)    # third dash, near end (in view)
    Lc = 3 * (DASH_L + GAP_L)    # three dash periods
    world = np.array([[x0, -LANE_W / 2], [x0 + Lc, -LANE_W / 2], [x0 + Lc, LANE_W / 2], [x0, LANE_W / 2]])
    q = np.c_[world, np.ones(4)] @ Hg.T
    px = q[:, :2] / q[:, 2:3]
    out = {"kind": kind, "fps": fps, "synthetic": True, "truth": truth,
           "calibration": {"mode": "rectangle", "img_pts": px.round(2).tolist(), "length_m": Lc, "width_m": LANE_W,
                           "note": "rectangle = divider line to edge line across the AV lane (synthetic geometry)"},
           "lane_width_m": LANE_W,
           "world": {"t": t.round(4).tolist(), "ego": ego[:, :2].round(4).tolist(), "other": oth[:, :2].round(4).tolist()}}
    Path(str(path) + ".truth.json").write_text(json.dumps(out))
    return out


if __name__ == "__main__":
    o = render_clip(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "lead_brake")
    print(json.dumps({k: v for k, v in o.items() if k != "world"}, indent=1))
