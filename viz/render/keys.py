"""Pure helpers for the Blender CCTV render (no bpy, no Modal). Shipped into the render container.

SYNTHETIC RENDER of a 2D sim trace. All motion comes from the trace (sim/ kinematics); this file only
resamples it to video frames, builds the fixed CCTV camera pose and the ffmpeg CCTV signal chain.

Camera convention matches viz/isaac/assets.CctvCamera exactly (pinhole, no distortion, principal point at
the image centre), so the calibration clicks in viz/isaac/samples/cctv_cut_in_truth.json stay exact.
"""
from __future__ import annotations

import math

WHEEL_RADIUS = 0.32  # m, 205/55 R16-ish tyre (illustrative)


# --- trace -> per-frame keys ------------------------------------------------------------------

def _interp(t_arr: list[float], states: list[list[float]], t: float) -> list[float]:
    if t <= t_arr[0]:
        return list(states[0])
    if t >= t_arr[-1]:
        return list(states[-1])
    lo, hi = 0, len(t_arr) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if t_arr[mid] <= t:
            lo = mid
        else:
            hi = mid
    a = (t - t_arr[lo]) / (t_arr[hi] - t_arr[lo])
    return [s0 + a * (s1 - s0) for s0, s1 in zip(states[lo], states[hi])]


def n_frames(trace: dict, fps: int) -> int:
    return int(math.floor(trace["t"][-1] * fps + 1e-6)) + 1


def frame_keys(trace: dict, fps: int = 25, wheel_radius: float = WHEEL_RADIUS) -> list[dict]:
    """One dict per video frame: {actor: (x, y, heading_rad, speed_mps, wheel_angle_rad)}.

    x, y = vehicle centre (sim frame), linearly interpolated at t = k / fps. Wheel angle is the
    cumulative distance travelled / wheel radius (rolling without slip), integrated on the trace grid.
    """
    t_arr = trace["t"]
    out: list[dict] = []
    # cumulative distance along the trace grid per actor
    dist: dict[str, list[float]] = {}
    for name, a in trace["actors"].items():
        st = a["states"]
        d = [0.0]
        for i in range(1, len(st)):
            d.append(d[-1] + math.hypot(st[i][0] - st[i - 1][0], st[i][1] - st[i - 1][1]))
        dist[name] = d
    for k in range(n_frames(trace, fps)):
        t = k / fps
        fr = {}
        for name, a in trace["actors"].items():
            x, y, h, v = _interp(t_arr, a["states"], t)[:4]
            s = _interp(t_arr, [[d] for d in dist[name]], t)[0]
            fr[name] = (x, y, h, v, s / wheel_radius)
        out.append(fr)
    return out


# --- camera ------------------------------------------------------------------------------------

def camera_axes(cam: dict):
    """(right, up, forward) unit vectors in world coordinates. Same maths as viz/isaac/assets.CctvCamera."""
    cy, sy = math.cos(math.radians(cam["yaw_deg"])), math.sin(math.radians(cam["yaw_deg"]))
    cp, sp = math.cos(math.radians(cam["pitch_deg"])), math.sin(math.radians(cam["pitch_deg"]))
    fwd = (cp * cy, cp * sy, -sp)
    right = (sy, -cy, 0.0)
    up = (right[1] * fwd[2] - right[2] * fwd[1],
          right[2] * fwd[0] - right[0] * fwd[2],
          right[0] * fwd[1] - right[1] * fwd[0])
    return right, up, fwd


def blender_camera_matrix(cam: dict) -> list[list[float]]:
    """4x4 camera-to-world (column-vector convention, Blender matrix_world). Blender cameras look down
    local -Z with +Y up, so the columns are (right, up, -forward, position)."""
    r, u, f = camera_axes(cam)
    b = tuple(-c for c in f)
    return [[r[0], u[0], b[0], cam["x"]],
            [r[1], u[1], b[1], cam["y"]],
            [r[2], u[2], b[2], cam["z"]],
            [0.0, 0.0, 0.0, 1.0]]


def project_blender(cam: dict, p) -> tuple[float, float]:
    """Project a world point through blender_camera_matrix + Blender's pinhole (sensor fit horizontal).
    Used by tests to prove the Blender camera reproduces the truth file's clicks."""
    M = blender_camera_matrix(cam)
    d = [p[0] - M[0][3], p[1] - M[1][3], (p[2] if len(p) > 2 else 0.0) - M[2][3]]
    # world -> camera = R^T d
    xc = sum(M[i][0] * d[i] for i in range(3))
    yc = sum(M[i][1] * d[i] for i in range(3))
    zc = sum(M[i][2] * d[i] for i in range(3))
    fx = cam["focal_mm"] / cam["h_aperture_mm"] * cam["width"]
    return cam["width"] / 2 + fx * xc / -zc, cam["height"] / 2 - fx * yc / -zc


# --- CCTV signal chain (ffmpeg) -----------------------------------------------------------------

CCTV_LABEL = "SYNTHETIC RENDER of a sim trace - not real footage"


def timestamp_texts(seconds: float, start_hms=(14, 22, 31), date: str = "2026-10-15", cam: str = "CAM 04") -> list[str]:
    """One burned-in timestamp per whole second of clip (same format as viz/isaac/assets.cctv_timestamp_texts)."""
    h, m, s = start_hms
    out = []
    for k in range(int(math.ceil(seconds)) + 1):
        tot = h * 3600 + m * 60 + s + k
        out.append(f"{cam} · {date} {tot // 3600 % 24:02d}:{tot // 60 % 60:02d}:{tot % 60:02d}")
    return out


def cctv_filtergraph(ts_files: list[str], label_file: str, font: str, width: int = 1920, height: int = 1080,
                     sub_w: int = 1280, sub_h: int = 720) -> str:
    """CCTV look. Geometry is preserved (no lens distortion, no crop): output stays width x height so
    calibration clicks hold. Chain: colour cast + desaturation -> downscale to a 720p sensor -> sensor noise
    -> upscale back -> in-camera sharpening -> vignette -> burned-in timestamp (one per second) -> label.
    Text is read from files with expansion=none, so nothing in it is interpreted."""
    vf = ["eq=saturation=0.74:contrast=1.07:brightness=-0.02:gamma=1.04",
          "colorbalance=rs=-0.03:gs=0.02:bs=0.04:rh=-0.02:bh=0.02",
          f"scale={sub_w}:{sub_h}:flags=area",
          "noise=c0s=9:c0f=t+u:c1s=4:c1f=t:c2s=4:c2f=t",
          f"scale={width}:{height}:flags=bicubic",
          "unsharp=5:5:0.7:5:5:0.0",
          "vignette=PI/5"]
    for k, f in enumerate(ts_files):
        vf.append(f"drawtext=fontfile={font}:expansion=none:textfile={f}:fontsize=h/30:fontcolor=white"
                  f":borderw=2:bordercolor=black@0.8:x=28:y=24:enable='gte(t,{k})*lt(t,{k + 1})'")
    vf.append(f"drawtext=fontfile={font}:expansion=none:textfile={label_file}:fontsize=h/60:fontcolor=white@0.8"
              ":box=1:boxcolor=black@0.4:boxborderw=6:x=w-tw-20:y=h-th-20")
    return ",".join(vf)


def x264_args(bitrate_kbps: int = 1800) -> list[str]:
    """Low-bitrate H.264 like a CCTV NVR export (compression artefacts on purpose)."""
    return ["-c:v", "libx264", "-preset", "medium", "-b:v", f"{bitrate_kbps}k",
            "-maxrate", f"{int(bitrate_kbps * 1.15)}k", "-bufsize", f"{bitrate_kbps}k",
            "-g", "50", "-bf", "0", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


def chunks(n: int, size: int) -> list[tuple[int, int]]:
    """Inclusive frame ranges covering 0..n-1."""
    return [(s, min(s + size, n) - 1) for s in range(0, n, size)]


# --- detection check helpers -------------------------------------------------------------------

def projected_box(cam: dict, x: float, y: float, h: float, length: float = 4.5, width: float = 1.8,
                  height: float = 1.45) -> tuple[float, float, float, float]:
    """Image bounding box (x1, y1, x2, y2) of a vehicle's 3D box (centre x, y on the ground, heading h)."""
    c, s = math.cos(h), math.sin(h)
    us, vs = [], []
    for dx in (-length / 2, length / 2):
        for dy in (-width / 2, width / 2):
            for z in (0.0, height):
                u, v = project_blender(cam, (x + c * dx - s * dy, y + s * dx + c * dy, z))
                us.append(u)
                vs.append(v)
    return min(us), min(vs), max(us), max(vs)


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def detection_rate(dets_per_frame: list[list[dict]], truth_boxes: list[dict], frame_wh=(1920, 1080),
                   min_iou: float = 0.3, min_score: float = 0.4, edge: float = 4.0) -> dict:
    """For each actor: share of frames (where its true box is fully inside the image) in which a detection
    labelled 'car' with score >= min_score overlaps it with IoU >= min_iou. Also counts non-car labels."""
    W, H = frame_wh
    out: dict[str, dict] = {}
    for dets, tb in zip(dets_per_frame, truth_boxes):
        for name, b in tb.items():
            r = out.setdefault(name, {"visible": 0, "car": 0, "other_label": 0, "scores": []})
            if b[0] < edge or b[1] < edge or b[2] > W - edge or b[3] > H - edge:
                continue
            r["visible"] += 1
            best = max(((iou(b, d["box"]), d) for d in dets), key=lambda t: t[0], default=(0.0, None))
            if best[1] is not None and best[0] >= min_iou and best[1]["score"] >= min_score:
                if best[1]["label"] == "car":
                    r["car"] += 1
                    r["scores"].append(best[1]["score"])
                else:
                    r["other_label"] += 1
    for r in out.values():
        r["car_rate"] = round(r["car"] / r["visible"], 3) if r["visible"] else None
        sc = sorted(r.pop("scores"))
        r["median_score"] = round(sc[len(sc) // 2], 3) if sc else None
    return out
