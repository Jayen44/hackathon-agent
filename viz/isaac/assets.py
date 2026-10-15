"""Asset catalogue + pure helpers for render_trace.py.

No Isaac / pxr imports here, so everything is unit-testable locally
(tests/test_viz_isaac_assets.py). Sources and licences: viz/isaac/ASSETS.md.

    python -m viz.isaac.assets --check    # HEAD-check every catalogued URL (no downloads)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

ISAAC_VERSION = "5.1"
# Default public asset root for Isaac Sim 5.1. At render time we prefer
# isaacsim.storage.native.get_assets_root_path(), which returns this unless the
# deployment overrides it (e.g. a local Nucleus mirror).
DEFAULT_ASSETS_ROOT = f"https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/{ISAAC_VERSION}"
POLYHAVEN = "https://dl.polyhaven.org/file/ph-assets"

_DS_VEH = "/NVIDIA/dsready_content/nv_content/common_assets/vehicles"


@dataclass(frozen=True)
class VehicleAsset:
    key: str
    rel_path: str  # relative to the Isaac assets root
    # Extra yaw (deg) so the model's nose points along +x after auto-fit.
    # TODO(Vakhtang): confirm on the first render; 0 assumes the model is authored nose-forward +x.
    yaw_offset_deg: float = 0.0


# Passenger cars served for Isaac Sim 5.1 (DRIVE Sim-ready content). Ego first.
VEHICLES: dict[str, VehicleAsset] = {
    "auto_01": VehicleAsset("auto_01", f"{_DS_VEH}/tri/auto_01/2023/main.usd"),
    "grand": VehicleAsset("grand", f"{_DS_VEH}/honey/grand/2024/main.usd"),
    "police_01": VehicleAsset("police_01", f"{_DS_VEH}/tri/police_01/2023/main.usd"),
    "security_01": VehicleAsset("security_01", f"{_DS_VEH}/tri/security_01/2023/main.usd"),
}
EGO_VEHICLE = "auto_01"
OTHER_VEHICLES = ["grand", "security_01"]  # police livery avoided on purpose (no implied blame)

MATERIALS = {
    "asphalt": "/NVIDIA/Materials/2023_1/Base/Natural/Asphalt.mdl",
    "asphalt_fine": "/NVIDIA/Materials/2023_1/vMaterials_2/Ground/Asphalt_Fine.mdl",
    "grass": "/NVIDIA/Materials/2023_1/Base/Natural/Grass_Countryside.mdl",
}

SKIES = {
    "kloofendal": "/NVIDIA/Assets/Skies/Cloudy/kloofendal_48d_partly_cloudy_4k.hdr",
    "noon_grass": "/NVIDIA/Assets/Skies/Clear/noon_grass_4k.hdr",
    "evening_road": "/NVIDIA/Assets/Skies/Evening/evening_road_01_4k.hdr",
}
DEFAULT_SKY = "kloofendal"

# Fallbacks fetched straight from Poly Haven (CC0) if the Isaac asset root is unreachable.
POLYHAVEN_SKY = f"{POLYHAVEN}/HDRIs/hdr/4k/kloofendal_48d_partly_cloudy_puresky_4k.hdr"
POLYHAVEN_ASPHALT = {
    "diffuse": f"{POLYHAVEN}/Textures/jpg/2k/asphalt_02/asphalt_02_diff_2k.jpg",
    "normal": f"{POLYHAVEN}/Textures/jpg/2k/asphalt_02/asphalt_02_nor_gl_2k.jpg",
    "roughness": f"{POLYHAVEN}/Textures/jpg/2k/asphalt_02/asphalt_02_rough_2k.jpg",
}
# Last-resort local cars: any *.usd/*.usdc/*.usdz the human drops here (e.g. Kenney Car Kit or
# Quaternius cars, CC0, converted from glTF with Isaac's asset converter). See ASSETS.md.
LOCAL_CAR_DIR = "/vol/assets/cars"


def url(root: str | None, rel: str) -> str:
    return (root or DEFAULT_ASSETS_ROOT).rstrip("/") + rel


def vehicle_candidates(actor_index: int, root: str | None, local_files: list[str] = ()) -> list[tuple[str, float]]:
    """Ordered (url, yaw_offset_deg) to try for actor #i (0 = ego). Empty list -> procedural car."""
    if actor_index == 0:
        keys = [EGO_VEHICLE]
    else:
        k = (actor_index - 1) % len(OTHER_VEHICLES)
        keys = OTHER_VEHICLES[k:] + OTHER_VEHICLES[:k]
    out = [(url(root, VEHICLES[k].rel_path), VEHICLES[k].yaw_offset_deg) for k in keys]
    local = sorted(local_files)
    if local:
        out.append((local[actor_index % len(local)], 0.0))
    return out


def sky_candidates(root: str | None, name: str = DEFAULT_SKY) -> list[str]:
    return [url(root, SKIES[name]), POLYHAVEN_SKY]


# --- geometry fitting ---------------------------------------------------------------

@dataclass(frozen=True)
class Fit:
    """xformOps for the 'fit' prim, applied to points as: scale, rotateX(up_fix), rotateZ(yaw), translate."""
    up_fix_deg: float
    yaw_deg: float
    scale: float
    translate: tuple[float, float, float]


def _rot_x(p, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (p[0], c * p[1] - s * p[2], s * p[1] + c * p[2])


def _rot_z(p, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (c * p[0] - s * p[1], s * p[0] + c * p[1], p[2])


def fit_vehicle(bbox_min, bbox_max, target_length: float, up_axis: str = "Z",
                yaw_offset_deg: float = 0.0) -> Fit:
    """Fit an arbitrary car model (bbox at identity, stage Z-up) to the sim footprint.

    Y-up models get +90 deg about X. The longest horizontal side is aligned with +x,
    uniformly scaled to target_length, centred on (0, 0) and put on the ground (z=0).
    """
    up_fix = 90.0 if up_axis.upper() == "Y" else 0.0
    corners = [(x, y, z) for x in (bbox_min[0], bbox_max[0]) for y in (bbox_min[1], bbox_max[1])
               for z in (bbox_min[2], bbox_max[2])]
    c1 = [_rot_x(p, up_fix) for p in corners]
    dx = max(p[0] for p in c1) - min(p[0] for p in c1)
    dy = max(p[1] for p in c1) - min(p[1] for p in c1)
    yaw = (90.0 if dy > dx else 0.0) + yaw_offset_deg
    long_side = max(dx, dy)
    if long_side <= 0:
        raise ValueError("degenerate bbox")
    s = target_length / long_side
    c2 = [_rot_z(tuple(v * s for v in p), yaw) for p in c1]
    xs, ys, zs = zip(*c2)
    tx = -(max(xs) + min(xs)) / 2
    ty = -(max(ys) + min(ys)) / 2
    tz = -min(zs)
    return Fit(up_fix, yaw, s, (tx, ty, tz))


def apply_fit(fit: Fit, p):
    q = _rot_z(_rot_x(tuple(v * fit.scale for v in p), fit.up_fix_deg), fit.yaw_deg)
    return (q[0] + fit.translate[0], q[1] + fit.translate[1], q[2] + fit.translate[2])


# --- brake lights ------------------------------------------------------------------

# Visual cue only (not a driver-model parameter): show brake lights when the
# trace's longitudinal deceleration exceeds this.
BRAKE_LIGHT_DECEL = 0.5  # m/s^2


def brake_flags(states: list, t: list, threshold: float = BRAKE_LIGHT_DECEL) -> list[bool]:
    """Per-sample brake-light state from the trace speeds (backward difference)."""
    out = [False] * len(states)
    for i in range(1, len(states)):
        dt = t[i] - t[i - 1]
        if dt > 0:
            out[i] = (states[i][3] - states[i - 1][3]) / dt < -threshold
    if len(out) > 1:
        out[0] = out[1]
    return out


# --- damped chase camera -------------------------------------------------------------

class DampedFollow:
    """Critically damped spring (per axis) towards a moving target; no overshoot."""

    def __init__(self, omega: float = 4.0):
        self.omega = omega
        self.pos: list[float] | None = None
        self.vel = [0.0, 0.0, 0.0]

    def update(self, target, dt: float) -> tuple[float, float, float]:
        if self.pos is None:
            self.pos = list(target)
            return tuple(self.pos)
        w = self.omega
        e = math.exp(-w * dt)
        for k in range(3):
            x = self.pos[k] - target[k]
            tmp = (self.vel[k] + w * x) * dt
            self.vel[k] = (self.vel[k] - w * tmp) * e
            self.pos[k] = target[k] + (x + tmp) * e
        return tuple(self.pos)


@dataclass
class ChaseCam:
    back: float = 13.0
    side: float = -4.0   # metres to the ego's right, so a cut-in from the left lane stays in view
    height: float = 5.5
    ahead: float = 14.0
    omega: float = 3.0

    def __post_init__(self):
        self._eye = DampedFollow(self.omega)
        self._look = DampedFollow(self.omega * 1.5)

    def update(self, x: float, y: float, heading: float, dt: float):
        c, s = math.cos(heading), math.sin(heading)
        eye = (x - self.back * c - self.side * s, y - self.back * s + self.side * c, self.height)
        look = (x + self.ahead * c, y + self.ahead * s, 0.8)
        return self._eye.update(eye, dt), self._look.update(look, dt)


# --- fixed CCTV camera (pure maths, shared by render_trace.py and the ground-truth export) ----

@dataclass(frozen=True)
class CctvCamera:
    """Fixed pole-mounted traffic camera. World frame = sim frame (x along road, y left, z up, m).

    yaw_deg: heading of the optical axis from +x towards +y. pitch_deg: tilt below horizontal.
    Pinhole, no distortion, square pixels, principal point at the image centre (USD camera
    with zero aperture offsets). fx = focal_mm / h_aperture_mm * width.
    """
    # Defaults frame the cctv_cut_in sample: pole 9 m high, 9 m right of the AV lane centre,
    # looking back down the road at oncoming traffic (yaw 160 deg), tilted 25 deg down.
    x: float = 112.0
    y: float = -9.0
    z: float = 9.0
    yaw_deg: float = 160.0
    pitch_deg: float = 25.0
    focal_mm: float = 24.0
    h_aperture_mm: float = 36.0
    width: int = 1920
    height: int = 1080

    @property
    def fx(self) -> float:
        return self.focal_mm / self.h_aperture_mm * self.width

    @property
    def v_aperture_mm(self) -> float:
        return self.h_aperture_mm * self.height / self.width

    def axes(self):
        """(right, up, forward) unit vectors in world coordinates."""
        cy, sy = math.cos(math.radians(self.yaw_deg)), math.sin(math.radians(self.yaw_deg))
        cp, sp = math.cos(math.radians(self.pitch_deg)), math.sin(math.radians(self.pitch_deg))
        fwd = (cp * cy, cp * sy, -sp)
        right = (sy, -cy, 0.0)
        up = (right[1] * fwd[2] - right[2] * fwd[1],
              right[2] * fwd[0] - right[0] * fwd[2],
              right[0] * fwd[1] - right[1] * fwd[0])
        return right, up, fwd

    def project(self, p) -> tuple[float, float, float]:
        """World point -> (u, v, depth). u right, v down, pixels; depth > 0 in front of the camera."""
        right, up, fwd = self.axes()
        d = (p[0] - self.x, p[1] - self.y, (p[2] if len(p) > 2 else 0.0) - self.z)
        xr = sum(a * b for a, b in zip(right, d))
        yu = sum(a * b for a, b in zip(up, d))
        zf = sum(a * b for a, b in zip(fwd, d))
        return self.width / 2 + self.fx * xr / zf, self.height / 2 - self.fx * yu / zf, zf

    def usd_matrix(self) -> list[list[float]]:
        """Camera-to-world 4x4 in USD row-vector convention (camera looks down -Z, +Y up)."""
        right, up, fwd = self.axes()
        back = tuple(-c for c in fwd)
        return [[*right, 0.0], [*up, 0.0], [*back, 0.0], [self.x, self.y, self.z, 1.0]]


CCTV = CctvCamera()


def cctv_timestamp_texts(seconds: float, start_hms: tuple[int, int, int] = (14, 22, 31),
                         date: str = "2026-10-15", cam: str = "CAM 04") -> list[str]:
    """One overlay string per whole second of clip (burned in by ffmpeg, one drawtext per second)."""
    h, m, s = start_hms
    out = []
    for k in range(int(math.ceil(seconds)) + 1):
        tot = h * 3600 + m * 60 + s + k
        out.append(f"{cam} \u00b7 {date} {tot // 3600 % 24:02d}:{tot // 60 % 60:02d}:{tot % 60:02d}")
    return out


def _check() -> int:
    import urllib.request
    urls = [url(None, a.rel_path) for a in VEHICLES.values()] + [url(None, m) for m in MATERIALS.values()] \
        + [url(None, s) for s in SKIES.values()] + [POLYHAVEN_SKY, *POLYHAVEN_ASPHALT.values()]
    bad = 0
    for u in urls:
        try:
            code = urllib.request.urlopen(urllib.request.Request(u, method="HEAD"), timeout=20).status
        except Exception as e:  # noqa: BLE001
            code, bad = repr(e), bad + 1
        print(code, u)
    return bad


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        sys.exit(1 if _check() else 0)
