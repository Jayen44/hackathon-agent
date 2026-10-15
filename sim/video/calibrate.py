"""Image -> road-plane homography from user-clicked points with known road coordinates.

The user clicks >= 4 points on the road surface in the video frame and types their
road coordinates in metres. Two input modes:

  points     each click has its own (x, y) in metres (any planar layout, >= 4 points,
             no three collinear).
  rectangle  4 clicks on the corners of a rectangle painted on / implied by the road,
             e.g. two lane lines (lane width W) and a measured length L along them.
             Click order: A, B along one line (A near, B far), then C, D on the other
             line (C across from B, D across from A). World: A=(0,0), B=(L,0),
             C=(L,W), D=(0,W). W and L are ENTERED BY THE USER; nothing is assumed.

Uncertainty. With exactly 4 points the homography fits exactly, so reprojection
error is 0 and says nothing. We instead propagate the two real error sources:
  - click precision (pixels, sigma per coordinate), and
  - tape / map measurement error of the entered metres (sigma per coordinate),
through an ensemble of homographies fitted to perturbed inputs. Projecting a track
through every member gives the calibration (systematic) part of the speed error.
With > 4 points the RMS reprojection residual is also reported, and the click sigma
is raised to at least that residual (in pixels) so a bad click shows up as spread.

The default sigmas are DESIGN ASSUMPTIONS, shown in the UI and overridable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# DESIGN ASSUMPTION: a careful click on a sharp road-marking corner in a typical
# 720p-1080p CCTV frame is good to about 2 px (1 sigma per axis).
DEFAULT_CLICK_SIGMA_PX = 2.0
# DESIGN ASSUMPTION: a length taken from a tape, a site plan or a road-marking spec is
# good to about 5 cm (1 sigma per coordinate). The user can change this.
DEFAULT_WORLD_SIGMA_M = 0.05
ENSEMBLE_N = 64


class CalibrationError(ValueError):
    pass


def _normalise(p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Hartley normalisation: centroid to origin, mean distance sqrt(2)."""
    c = p.mean(axis=0)
    d = np.sqrt(((p - c) ** 2).sum(axis=1)).mean()
    s = np.sqrt(2) / d if d > 0 else 1.0
    T = np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1.0]])
    ph = np.c_[p, np.ones(len(p))] @ T.T
    return ph[:, :2], T


def fit_homography(img_pts, world_pts) -> np.ndarray:
    """Normalised DLT. Returns H (3x3) mapping image pixels -> road metres."""
    src = np.asarray(img_pts, float)
    dst = np.asarray(world_pts, float)
    if src.shape != dst.shape or src.ndim != 2 or src.shape[1] != 2:
        raise CalibrationError("need matching (N, 2) image and world point arrays")
    if len(src) < 4:
        raise CalibrationError("need at least 4 points")
    for pts, name in ((src, "image"), (dst, "world")):
        if np.linalg.matrix_rank(pts - pts.mean(axis=0)) < 2:
            raise CalibrationError(f"{name} points are collinear")
    s, Ts = _normalise(src)
    d, Td = _normalise(dst)
    rows = []
    for (x, y), (u, v) in zip(s, d):
        rows.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        rows.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, sv, vt = np.linalg.svd(np.asarray(rows))
    Hn = vt[-1].reshape(3, 3)
    H = np.linalg.inv(Td) @ Hn @ Ts
    if abs(H[2, 2]) < 1e-12:
        raise CalibrationError("degenerate homography")
    H = H / H[2, 2]
    # Every clicked point must be in front of the "horizon": same sign of w.
    w = np.c_[src, np.ones(len(src))] @ H[2]
    if not (np.all(w > 0) or np.all(w < 0)):
        raise CalibrationError("points straddle the horizon; check click order")
    return H


def project(H: np.ndarray, pts) -> np.ndarray:
    """Apply H to (N, 2) points."""
    p = np.asarray(pts, float).reshape(-1, 2)
    q = np.c_[p, np.ones(len(p))] @ np.asarray(H).T
    return q[:, :2] / q[:, 2:3]


def rectangle_world_points(length_m: float, width_m: float) -> np.ndarray:
    """A=(0,0), B=(L,0), C=(L,W), D=(0,W). L and W must come from the user."""
    if not (length_m > 0 and width_m > 0):
        raise CalibrationError("rectangle length and width must be positive metres entered by the user")
    return np.array([[0.0, 0.0], [length_m, 0.0], [length_m, width_m], [0.0, width_m]])


@dataclass
class Calibration:
    H: np.ndarray
    img_pts: np.ndarray
    world_pts: np.ndarray
    click_sigma_px: float
    world_sigma_m: float
    reproj_rms_m: float | None          # None with exactly 4 points (exact fit)
    reproj_rms_px: float | None
    ensemble: list[np.ndarray] = field(default_factory=list)
    mode: str = "points"
    assumptions: list[str] = field(default_factory=list)

    def project(self, pts) -> np.ndarray:
        return project(self.H, pts)

    def position_sigma_m(self, img_pt) -> float:
        """1-sigma position error (m, per axis, RMS) at one image point from the ensemble."""
        if not self.ensemble:
            return 0.0
        q = np.array([project(h, img_pt)[0] for h in self.ensemble])
        return float(np.sqrt(q.var(axis=0).mean()))

    def summary(self) -> dict:
        return {"mode": self.mode, "n_points": int(len(self.img_pts)), "H": self.H.tolist(),
                "click_sigma_px": self.click_sigma_px, "world_sigma_m": self.world_sigma_m,
                "reprojection_rms_m": self.reproj_rms_m, "reprojection_rms_px": self.reproj_rms_px,
                "ensemble_n": len(self.ensemble), "assumptions": self.assumptions}


def calibrate(img_pts, world_pts, click_sigma_px: float = DEFAULT_CLICK_SIGMA_PX,
              world_sigma_m: float = DEFAULT_WORLD_SIGMA_M, n_ensemble: int = ENSEMBLE_N,
              seed: int = 0, mode: str = "points") -> Calibration:
    src = np.asarray(img_pts, float)
    dst = np.asarray(world_pts, float)
    H = fit_homography(src, dst)
    rms_m = rms_px = None
    sig_px = float(click_sigma_px)
    if len(src) > 4:
        rms_m = float(np.sqrt(((project(H, src) - dst) ** 2).sum(axis=1).mean()))
        rms_px = float(np.sqrt(((project(np.linalg.inv(H), dst) - src) ** 2).sum(axis=1).mean()))
        sig_px = max(sig_px, rms_px)
    rng = np.random.default_rng(seed)
    ens = []
    for _ in range(n_ensemble):
        try:
            ens.append(fit_homography(src + rng.normal(0, sig_px, src.shape),
                                      dst + rng.normal(0, world_sigma_m, dst.shape)))
        except CalibrationError:
            continue
    assumptions = [f"click precision {sig_px:.1f} px (1 sigma)"
                   + (" (default design assumption)" if click_sigma_px == DEFAULT_CLICK_SIGMA_PX else " (user)"),
                   f"entered road coordinates good to {world_sigma_m:.2f} m (1 sigma)"
                   + (" (default design assumption)" if world_sigma_m == DEFAULT_WORLD_SIGMA_M else " (user)"),
                   "road surface treated as flat (one plane) across the scene"]
    return Calibration(H, src, dst, sig_px, float(world_sigma_m), rms_m, rms_px, ens, mode, assumptions)


def calibrate_from_request(c: dict) -> Calibration:
    """Parse the Sim Lab JSON: {"mode": "rectangle"|"points", "img_pts": [[u,v]..],
    "length_m", "width_m"} or {"world_pts": [[x,y]..]}, optional click_sigma_px, world_sigma_m.
    Inputs are untrusted: validated, never evaluated."""
    mode = c.get("mode", "rectangle")
    img = np.asarray(c["img_pts"], float)
    if not np.all(np.isfinite(img)) or img.ndim != 2 or img.shape[1] != 2 or not 4 <= len(img) <= 32:
        raise CalibrationError("img_pts must be 4-32 finite [u, v] pairs")
    if mode == "rectangle":
        if len(img) != 4:
            raise CalibrationError("rectangle mode needs exactly 4 clicks")
        world = rectangle_world_points(float(c["length_m"]), float(c["width_m"]))
    elif mode == "points":
        world = np.asarray(c["world_pts"], float)
        if world.shape != img.shape or not np.all(np.isfinite(world)):
            raise CalibrationError("world_pts must match img_pts")
    else:
        raise CalibrationError(f"unknown calibration mode {mode!r}")
    cs = float(c.get("click_sigma_px", DEFAULT_CLICK_SIGMA_PX))
    ws = float(c.get("world_sigma_m", DEFAULT_WORLD_SIGMA_M))
    if not (0 <= cs <= 50 and 0 <= ws <= 5):
        raise CalibrationError("sigmas out of range")
    return calibrate(img, world, cs, ws, mode=mode)
