"""Pixel tracks -> road-frame trajectories in metres with speed error bars -> crash bundle.

Pipeline
  1. Contact point of each box = bottom-centre (where the vehicle meets the road).
  2. Project through the calibration homography H (and every member of its ensemble).
  3. Smooth with a local quadratic fit (Savitzky-Golay style, handles dropped frames):
     position, velocity and acceleration at every sample.
  4. Uncertainty per sample, 1 sigma:
       jitter  random detector/box noise, from the fit residuals via the least-squares
               covariance (assumes frame-to-frame errors are independent; real box jitter
               is partly correlated, so this part can be optimistic),
       calib   systematic calibration error, from the spread across the H ensemble.
     total = sqrt(jitter^2 + calib^2).
  5. Rotate into the sim frame: x along the road (ego moves +x), y lateral (left +),
     origin = ego contact point at conflict start.
  6. Conflict extraction -> bundle `conflict` + `conflict_ranges` (source "reported").

Known biases (all reported in `assumptions`):
  - Contact point is the bottom-centre of the 2D box, not the true vehicle centre. Its
    offset to the centre depends on viewing angle and vehicle size; for two vehicles seen
    from the same side it largely cancels in the gap. CONTACT_POINT_SIGMA_M covers the rest.
  - Vehicle lengths are not measured: DEFAULT_GEOMETRY from montecarlo.evidence.
  - Flat road; no lens-distortion correction (straight lines must look straight).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from sim.video.calibrate import Calibration, project

# DESIGN ASSUMPTIONS (named, reported with every result).
SMOOTH_WINDOW_S = 1.0          # local quadratic fit window for position/speed
ACCEL_WINDOW_S = 1.5           # wider window for acceleration
CONTACT_POINT_SIGMA_M = 0.5    # residual contact-point vs centre offset between two vehicles
# The box bottom is not a fixed point on the vehicle: it drifts as the viewing angle changes,
# which biases speed by a few percent. 3 % (1 sigma) matches the 2-4 % bias we measured on our
# synthetic rendered clips (sim/video/synthetic_clip.py). DESIGN ASSUMPTION, not a real-footage figure.
CONTACT_DRIFT_REL = 0.03
RANGE_K_SIGMA = 2.0            # conflict_ranges = measured value +/- 2 sigma
CLOSING_MIN_MPS = 0.5          # "closing" if ego approaches the other faster than this
BRAKE_THRESHOLD_MPS2 = 1.0     # other vehicle "brakes" if decel exceeds this
AV_BRAKE_THRESHOLD_MPS2 = 1.5  # AV "brakes" if decel exceeds this
COLLISION_GAP_M = 0.5          # min bumper gap below this = contact (boxes meet)
DEFAULT_LENGTH_M = 4.6         # = montecarlo.evidence.DEFAULT_GEOMETRY.length
MIN_TRACK_FRAMES = 8
SAME_VEHICLE_M = 2.5           # two tracks this close (median) are the same vehicle
LOST_TTC_S = 2.0               # other lost from view this close to contact (time-to-contact) = suspected impact


class TrajectoryError(ValueError):
    pass


@dataclass
class Track:
    id: int
    cls: str
    frames: np.ndarray            # (N,) int
    boxes: np.ndarray             # (N, 4) x1 y1 x2 y2 pixels
    conf: np.ndarray | None = None

    def contact_px(self) -> np.ndarray:
        b = self.boxes
        return np.c_[(b[:, 0] + b[:, 2]) / 2, b[:, 3]]


def merge_tracks(tracks: dict[int, Track], ids: list[int]) -> Track:
    """Stitch fragments of ONE vehicle (tracker ID switches, occlusion). Earlier-listed ids win
    on frames they share. The merged track gets the first id."""
    missing = [i for i in ids if i not in tracks]
    if missing:
        raise TrajectoryError(f"unknown track(s) {missing}")
    seen: dict[int, np.ndarray] = {}
    for i in ids:
        for f, b in zip(tracks[i].frames, tracks[i].boxes):
            seen.setdefault(int(f), b)
    fr = np.array(sorted(seen))
    return Track(ids[0], tracks[ids[0]].cls, fr, np.array([seen[f] for f in fr]))


def tracks_from_json(d: dict) -> dict[int, Track]:
    """Parse detect.py output: {"tracks": {"<id>": {"cls", "frames", "boxes", "conf"}}}."""
    out = {}
    for k, t in (d.get("tracks") or {}).items():
        fr = np.asarray(t["frames"], int)
        bx = np.asarray(t["boxes"], float).reshape(-1, 4)
        if len(fr) != len(bx) or len(fr) == 0 or not np.all(np.isfinite(bx)):
            continue
        order = np.argsort(fr)
        out[int(k)] = Track(int(k), str(t.get("cls", "vehicle")), fr[order], bx[order],
                            None if t.get("conf") is None else np.asarray(t["conf"], float)[order])
    return out


# ---------------------------------------------------------------- local polynomial smoother

def _local_weights(t: np.ndarray, window_s: float, order: int = 2):
    """Per-sample local polynomial fit weights. Linear in the data, so computed once per
    time base and reused for every ensemble member. Returns idx (N,K), W (N,K,order+1),
    G (N, order+1, order+1) = (A^T A)^-1, counts (N,)."""
    n = len(t)
    half = window_s / 2
    lo = np.searchsorted(t, t - half, side="left")
    hi = np.searchsorted(t, t + half, side="right")
    # Ensure at least order+3 samples per window (widen at the ends / sparse tracks).
    need = order + 3
    for i in range(n):
        while hi[i] - lo[i] < need and (lo[i] > 0 or hi[i] < n):
            if lo[i] > 0:
                lo[i] -= 1
            if hi[i] - lo[i] < need and hi[i] < n:
                hi[i] += 1
    K = int((hi - lo).max())
    idx = np.zeros((n, K), int)
    W = np.zeros((n, K, order + 1))
    G = np.zeros((n, order + 1, order + 1))
    cnt = hi - lo
    for i in range(n):
        j = np.arange(lo[i], hi[i])
        tau = t[j] - t[i]
        A = np.vander(tau, order + 1, increasing=True)
        g = np.linalg.pinv(A.T @ A)
        idx[i, :len(j)] = j
        W[i, :len(j)] = (g @ A.T).T
        G[i] = g
    return idx, W, G, cnt


def _apply(idx, W, z: np.ndarray) -> np.ndarray:
    """z (N,) or (M, N) -> coefficients (N, order+1) or (M, N, order+1)."""
    return np.einsum("...nk,nkc->...nc", z[..., idx], W)


@dataclass
class Kinematics:
    """One track in road-plane metres (calibration world frame until to_road_frame)."""
    id: int
    cls: str
    t: np.ndarray
    pos: np.ndarray        # (N, 2) smoothed
    vel: np.ndarray        # (N, 2)
    acc: np.ndarray        # (N, 2)
    pos_sd: np.ndarray     # (N,) per-axis RMS 1 sigma
    vel_sd: np.ndarray     # (N, 2) per-axis 1 sigma (jitter + calib)
    acc_sd: np.ndarray     # (N, 2)
    speed_sd_jitter: np.ndarray
    speed_sd_calib: np.ndarray
    raw: np.ndarray        # (N, 2) projected unsmoothed points
    vel_ens: np.ndarray = field(default=None, repr=False)   # (M, N, 2) for re-projection

    @property
    def speed(self) -> np.ndarray:
        return np.hypot(self.vel[:, 0], self.vel[:, 1])

    @property
    def speed_sd(self) -> np.ndarray:
        return np.sqrt(self.speed_sd_jitter ** 2 + self.speed_sd_calib ** 2 + (CONTACT_DRIFT_REL * self.speed) ** 2)


def _speed_sd(v: np.ndarray, v_sd: np.ndarray) -> np.ndarray:
    s = np.maximum(np.hypot(v[:, 0], v[:, 1]), 1e-6)
    return np.sqrt((v[:, 0] * v_sd[:, 0]) ** 2 + (v[:, 1] * v_sd[:, 1]) ** 2) / s


def kinematics(track: Track, calib: Calibration, fps: float, window_s: float = SMOOTH_WINDOW_S,
               accel_window_s: float = ACCEL_WINDOW_S) -> Kinematics:
    if len(track.frames) < MIN_TRACK_FRAMES:
        raise TrajectoryError(f"track {track.id} has only {len(track.frames)} frames")
    if not fps > 0:
        raise TrajectoryError("fps must be positive")
    t = track.frames / float(fps)
    px = track.contact_px()
    world = project(calib.H, px)
    idx, W, G, cnt = _local_weights(t, window_s)
    idx2, W2, G2, cnt2 = _local_weights(t, accel_window_s)

    c = _apply(idx, W, world.T)            # (2, N, 3)
    c2 = _apply(idx2, W2, world.T)
    pos = c[:, :, 0].T
    vel = c[:, :, 1].T
    acc = 2 * c2[:, :, 2].T

    # Jitter sigma per axis from residuals of each local fit (dof-corrected, median over windows).
    sig = np.zeros(2)
    for a in range(2):
        z = world[:, a]
        zz = z[idx]                                           # (N, K)
        tau = t[idx] - t[:, None]
        fit = c[a, :, 0:1] + c[a, :, 1:2] * tau + c[a, :, 2:3] * tau ** 2
        mask = np.arange(idx.shape[1])[None, :] < cnt[:, None]
        rss = (((zz - fit) ** 2) * mask).sum(axis=1)
        dof = np.maximum(cnt - 3, 1)
        sig[a] = math.sqrt(float(np.median(rss / dof)))
    vel_sd_j = np.sqrt(G[:, 1, 1])[:, None] * sig[None, :]
    acc_sd_j = 2 * np.sqrt(G2[:, 2, 2])[:, None] * sig[None, :]

    # Calibration ensemble.
    if calib.ensemble:
        ens_world = np.stack([project(h, px) for h in calib.ensemble])      # (M, N, 2)
        ce = _apply(idx, W, np.moveaxis(ens_world, 2, 1))                    # (M, 2, N, 3)
        ce2 = _apply(idx2, W2, np.moveaxis(ens_world, 2, 1))
        vel_ens = np.moveaxis(ce[:, :, :, 1], 1, 2)                          # (M, N, 2)
        pos_ens = np.moveaxis(ce[:, :, :, 0], 1, 2)
        acc_ens = 2 * np.moveaxis(ce2[:, :, :, 2], 1, 2)
        vel_sd_c = vel_ens.std(axis=0)
        acc_sd_c = acc_ens.std(axis=0)
        pos_sd_c = np.sqrt(pos_ens.var(axis=0).mean(axis=1))
        sp_ens = np.hypot(vel_ens[..., 0], vel_ens[..., 1])
        speed_sd_c = sp_ens.std(axis=0)
    else:
        vel_ens = None
        vel_sd_c = acc_sd_c = np.zeros_like(vel)
        pos_sd_c = np.zeros(len(t))
        speed_sd_c = np.zeros(len(t))
    speed_sd_j = _speed_sd(vel, vel_sd_j)
    pos_sd = np.sqrt(pos_sd_c ** 2 + sig.mean() ** 2 / np.maximum(cnt, 1))
    return Kinematics(track.id, track.cls, t, pos, vel, acc, pos_sd,
                      np.sqrt(vel_sd_j ** 2 + vel_sd_c ** 2 + (CONTACT_DRIFT_REL * vel) ** 2),
                      np.hypot(acc_sd_j, acc_sd_c),
                      speed_sd_j, speed_sd_c, world, vel_ens)


# ---------------------------------------------------------------- road frame

@dataclass
class RoadFrame:
    """Rotation world -> road. The lateral sign follows the user's coordinates: which side is
    'left' cannot be known from a CCTV frame alone, and the sim is mirror-symmetric."""
    theta: float          # road x = world direction theta (rad)
    origin: np.ndarray    # world point that maps to road (0, 0)
    basis: str            # how the axis was chosen

    def R(self) -> np.ndarray:
        c, s = math.cos(self.theta), math.sin(self.theta)
        return np.array([[c, s], [-s, c]])

    def apply_pts(self, p: np.ndarray) -> np.ndarray:
        return (p - self.origin) @ self.R().T

    def apply_vec(self, v: np.ndarray) -> np.ndarray:
        return v @ self.R().T


def road_frame(ego: Kinematics, other: Kinematics | None, calib: Calibration) -> RoadFrame:
    """x along the road in the ego's direction of travel.

    rectangle calibration: the rectangle's A->B side lies along the lane line, so world x is the
    road direction (only its sign is chosen from the motion). points mode: principal direction of
    the ego path (or the other vehicle's path if the ego barely moves).
    """
    def disp(k: Kinematics) -> np.ndarray:
        return k.pos[-1] - k.pos[0]

    mover = ego if np.linalg.norm(disp(ego)) > 3.0 or other is None else other
    if calib.mode == "rectangle":
        theta = 0.0 if disp(mover)[0] >= 0 else math.pi
        basis = "rectangle A->B side (lane line)"
    else:
        p = mover.pos - mover.pos.mean(axis=0)
        _, _, vt = np.linalg.svd(p, full_matrices=False)
        d = vt[0] if np.dot(vt[0], disp(mover)) >= 0 else -vt[0]
        theta = math.atan2(d[1], d[0])
        basis = f"principal direction of track {mover.id}"
    return RoadFrame(theta, ego.pos[0].copy(), basis)


@dataclass
class RoadTrack:
    id: int
    t: np.ndarray
    x: np.ndarray
    y: np.ndarray
    vx: np.ndarray
    vy: np.ndarray
    ax: np.ndarray
    speed: np.ndarray
    speed_sd: np.ndarray
    vx_sd: np.ndarray
    vy_sd: np.ndarray
    ax_sd: np.ndarray
    pos_sd: np.ndarray
    speed_sd_jitter: np.ndarray
    speed_sd_calib: np.ndarray

    def at(self, t: float, attr: str) -> float:
        return float(np.interp(t, self.t, getattr(self, attr)))


def to_road(k: Kinematics, rf: RoadFrame) -> RoadTrack:
    p = rf.apply_pts(k.pos)
    v = rf.apply_vec(k.vel)
    a = rf.apply_vec(k.acc)
    R = np.abs(rf.R())
    v_sd = np.sqrt((k.vel_sd ** 2) @ (R ** 2).T)
    a_sd = np.sqrt((k.acc_sd ** 2) @ (R ** 2).T)
    return RoadTrack(k.id, k.t, p[:, 0], p[:, 1], v[:, 0], v[:, 1], a[:, 0], k.speed, k.speed_sd,
                     v_sd[:, 0], v_sd[:, 1], a_sd[:, 0], k.pos_sd, k.speed_sd_jitter, k.speed_sd_calib)


# ---------------------------------------------------------------- conflict extraction

def _rng(v: float, sd: float, floor: float | None = None) -> dict:
    lo, hi = v - RANGE_K_SIGMA * sd, v + RANGE_K_SIGMA * sd
    if floor is not None:
        lo, hi = max(floor, lo), max(floor, hi)
    return {"lo": round(lo, 3), "hi": round(hi, 3), "source": "reported"}


def _s(f: float) -> float:
    """Normalised time at which a cosine lane change has covered fraction f."""
    return math.acos(1 - 2 * f) / math.pi


def _cross_time(t: np.ndarray, f: np.ndarray, level: float) -> float | None:
    i = np.nonzero(f >= level)[0]
    if not len(i):
        return None
    i = int(i[0])
    if i == 0:
        return float(t[0])
    f0, f1 = f[i - 1], f[i]
    return float(t[i - 1] + (level - f0) / (f1 - f0) * (t[i] - t[i - 1])) if f1 != f0 else float(t[i])


def _onset(t: np.ndarray, a: np.ndarray, j_peak: int) -> float:
    """Braking onset = last time before the peak where decel crosses half the peak. The
    smoother spreads a brake step symmetrically, so the 50% crossing sits at the true step."""
    half = a[j_peak] / 2
    above = np.nonzero(a[:j_peak + 1] > half)[0]
    if not len(above):
        return float(t[0])
    i = int(above[-1])
    if i + 1 > j_peak:
        return float(t[i])
    a0, a1 = a[i], a[i + 1]
    return float(t[i] + (half - a0) / (a1 - a0) * (t[i + 1] - t[i])) if a1 != a0 else float(t[i])


def pick_other(ego: RoadTrack, candidates: list[RoadTrack]) -> RoadTrack:
    """The vehicle the ego gets closest to while it is ahead (largest threat)."""
    best, best_d = None, math.inf
    for c in candidates:
        common = np.intersect1d(np.round(ego.t, 6), np.round(c.t, 6))
        if len(common) < MIN_TRACK_FRAMES:
            continue
        dx = np.interp(common, c.t, c.x) - np.interp(common, ego.t, ego.x)
        dy = np.interp(common, c.t, c.y) - np.interp(common, ego.t, ego.y)
        if np.median(np.hypot(dx, dy)) < SAME_VEHICLE_M:
            continue   # duplicate box / fragment of the AV itself
        ahead = dx > 0
        if not ahead.any() or not ((np.interp(common, ego.t, ego.vx) - np.interp(common, c.t, c.vx))[ahead]
                                   > CLOSING_MIN_MPS).any():
            continue
        d = float(np.hypot(dx[ahead], dy[ahead]).min())
        if d < best_d:
            best, best_d = c, d
    if best is None:
        raise TrajectoryError("no other vehicle is ahead of the selected AV track while both are tracked")
    return best


def extract_conflict(ego: RoadTrack, other: RoadTrack, lane_width_m: float,
                     ego_length_m: float = DEFAULT_LENGTH_M, other_length_m: float = DEFAULT_LENGTH_M,
                     crash_type: str | None = None, collided: bool | None = None) -> dict:
    """Conflict facts + ranges from two road-frame tracks (times in video seconds).

    lane_width_m is ENTERED BY THE USER (used only to classify cut-in vs lead vehicle).
    crash_type / collided override the automatic guesses.
    """
    if not lane_width_m or lane_width_m <= 0:
        raise TrajectoryError("lane width must be entered by the user (metres)")
    t = np.intersect1d(np.round(ego.t, 6), np.round(other.t, 6))
    if len(t) < MIN_TRACK_FRAMES:
        raise TrajectoryError("AV and other vehicle are tracked together for too few frames")
    ex, ox = np.interp(t, ego.t, ego.x), np.interp(t, other.t, other.x)
    ey, oy = np.interp(t, ego.t, ego.y), np.interp(t, other.t, other.y)
    evx, ovx = np.interp(t, ego.t, ego.vx), np.interp(t, other.t, other.vx)
    rel = ox - ex
    half_len = (ego_length_m + other_length_m) / 2
    gap = rel - half_len
    closing = evx - ovx
    if not (rel > 0).any():
        raise TrajectoryError("the other vehicle is never ahead of the AV: rear impact into the AV, "
                              "outside cut-in / lead-vehicle scope")
    # Skip the first half smoothing window of the joint track: one-sided fits at track ends
    # are much noisier than in the middle.
    settled = t >= max(ego.t[0], other.t[0]) + SMOOTH_WINDOW_S / 2
    start_ok = (rel > 0) & (closing > CLOSING_MIN_MPS) & settled
    if not start_ok.any():
        raise TrajectoryError("the AV never closes on the other vehicle while it is ahead")
    i0 = int(np.nonzero(start_ok)[0][0])
    t0 = float(t[i0])
    # Crash / closest approach: minimum bumper gap after t0 while the other is still ahead.
    ahead = np.arange(len(t)) >= i0
    lat = np.abs(oy - ey)
    gap_eff = np.where(ahead & (rel > 0), gap, np.inf)
    ic = int(np.argmin(gap_eff))
    min_gap = float(gap[ic])
    touching = np.nonzero(ahead & (rel > 0) & (gap <= COLLISION_GAP_M) & (lat < lane_width_m * 0.75))[0]
    auto_collided = bool(len(touching))
    if auto_collided:
        ic = int(touching[0])          # first contact, not the deepest overlap
    t_c = float(t[ic])
    collided = auto_collided if collided is None else bool(collided)
    # Impact time: seen contact, or (contact asserted but not seen) extrapolated from the last frame.
    if auto_collided:
        t_imp = t_c
    elif collided and closing[ic] > CLOSING_MIN_MPS:
        t_imp = t_c + max(min_gap, 0.0) / closing[ic]
    else:
        t_imp = math.inf

    sd = lambda tr, attr, tt: float(np.interp(tt, tr.t, getattr(tr, attr)))
    v_e, v_o = sd(ego, "vx", t0), sd(other, "vx", t0)
    v_e_sd, v_o_sd = sd(ego, "vx_sd", t0), sd(other, "vx_sd", t0)
    gap0 = float(gap[i0])
    gap_sd = math.sqrt(sd(ego, "pos_sd", t0) ** 2 + sd(other, "pos_sd", t0) ** 2 + CONTACT_POINT_SIGMA_M ** 2)

    # Lateral: other relative to the ego lane centre (ego lateral position at t0).
    y_ego0 = float(ey[i0])
    yrel = oy - y_ego0
    y0 = float(yrel[i0])
    in_lane_later = (np.abs(yrel[i0:ic + 1]) < lane_width_m / 2).any()
    auto_type = "cut_in" if abs(y0) > lane_width_m / 2 and in_lane_later else "lead_vehicle_decel"
    ctype = crash_type or auto_type
    if ctype not in ("cut_in", "lead_vehicle_decel"):
        raise TrajectoryError(f"crash type {ctype!r} not supported from video (cut_in, lead_vehicle_decel)")

    ranges: dict[str, dict] = {
        "ego_speed": _rng(v_e, v_e_sd, floor=0.0),
        "other_speed": _rng(v_o, v_o_sd, floor=0.0),
        "gap": _rng(gap0, gap_sd, floor=0.5),
    }
    notes: list[str] = []
    tt = t[i0:ic + 1]

    if ctype == "cut_in":
        if abs(y0) < 0.3:
            raise TrajectoryError("cut-in selected but the other vehicle starts in the AV lane")
        frac = 1 - yrel[i0:ic + 1] / y0
        t10 = _cross_time(tt, frac, 0.1)
        hi_lvl = 0.9 if _cross_time(tt, frac, 0.9) is not None else 0.5
        t_hi = _cross_time(tt, frac, hi_lvl)
        if t10 is None or t_hi is None or t_hi <= t10:
            raise TrajectoryError("could not measure the lane change (other vehicle never moves halfway in)")
        dur = (t_hi - t10) / (_s(hi_lvl) - _s(0.1))
        start = t10 - _s(0.1) * dur - t0
        vy_mid = abs(float(np.interp((t10 + t_hi) / 2, other.t, other.vy))) or 0.1
        y_sd = math.hypot(sd(other, "pos_sd", t0), sd(ego, "pos_sd", t0))
        t_sd = max(0.1, y_sd / vy_mid)
        ranges["lateral_offset"] = _rng(abs(y0), y_sd, floor=0.0)
        ranges["cut_in_start"] = _rng(max(0.0, start), t_sd, floor=0.0)
        ranges["cut_in_duration"] = _rng(dur, t_sd * 1.4, floor=0.2)
        if hi_lvl < 0.9:
            notes.append("lane change not complete before impact; duration extrapolated from the 10%-50% part")
        notes.append("lateral side mirrored to +y (the sim is left/right symmetric)")

    # Contact not seen: the other vehicle drops out of view while still closing at a short gap
    # (typically hidden behind the AV just before impact).
    lost_closing = bool(ic == len(t) - 1 and other.t[-1] < ego.t[-1] - 0.2
                        and closing[ic] > CLOSING_MIN_MPS and min_gap / closing[ic] < LOST_TTC_S)
    if lost_closing:
        if not math.isfinite(t_imp):
            t_imp = t_c + max(min_gap, 0.0) / closing[ic]   # suspected impact, for braking exclusion only
        notes.append(f"other vehicle lost from view {min_gap:.1f} m ahead while still closing: contact not "
                     "observed in the video; set 'contact' manually if the crash is known")

    # Braking is measured only on motion BEFORE the impact: the smoother would otherwise smear
    # the crash deceleration back into the pre-crash phase (only if the track runs past impact).
    margin = ACCEL_WINDOW_S / 2 if auto_collided else ACCEL_WINDOW_S   # extrapolated impact time is less certain

    def lim(tr: RoadTrack) -> float:
        return t_imp - margin if tr.t[-1] > t_imp else math.inf
    tt_o, tt_e = tt[tt <= lim(other)], tt[tt <= lim(ego)]
    if math.isfinite(t_imp):
        notes.append(f"braking measured only up to {margin} s before the (suspected) impact at "
                     f"t={t_imp:.2f} s")

    # Other vehicle braking after t0 (until impact).
    oax = np.interp(tt_o, other.t, other.ax) if len(tt_o) else np.zeros(1)
    oax_sd = np.interp(tt_o, other.t, other.ax_sd) if len(tt_o) else np.zeros(1)
    j = int(np.argmin(oax))
    if len(tt_o) and -oax[j] > BRAKE_THRESHOLD_MPS2:
        tb = _onset(tt_o, oax, j) - t0
        ranges["other_decel"] = _rng(-float(oax[j]), float(oax_sd[j]), floor=0.0)
        ranges["other_brake_time"] = _rng(tb, 0.2, floor=0.0)
    elif ctype == "lead_vehicle_decel":
        ranges["other_decel"] = {"lo": 0.0, "hi": round(RANGE_K_SIGMA * float(oax_sd.max()), 3), "source": "reported"}
        ranges["other_brake_time"] = {"lo": 0.0, "hi": 0.0, "source": "reported"}
        notes.append("no braking of the other vehicle measured above "
                     f"{BRAKE_THRESHOLD_MPS2} m/s^2; decel range is measurement noise only")

    # What the AV did: braking measured from video.
    eax = np.interp(tt_e, ego.t, ego.ax) if len(tt_e) else np.zeros(1)
    eax_sd = np.interp(tt_e, ego.t, ego.ax_sd) if len(tt_e) else np.zeros(1)
    k = int(np.argmin(eax))
    av = None
    if len(tt_e) and -eax[k] > AV_BRAKE_THRESHOLD_MPS2:
        tb = _onset(tt_e, eax, k) - t0
        ranges["av_brake_start"] = _rng(tb, 0.2, floor=0.0)
        ranges["av_decel"] = _rng(-float(eax[k]), float(eax_sd[k]), floor=0.0)
        av = {"t_after_conflict_s": round(tb, 3), "decel_mps2": round(-float(eax[k]), 3)}

    conflict = {"t_start": round(t0, 4), "ego_speed_mps": round(v_e, 4), "gap_m": round(max(gap0, 0.5), 4),
                "hazard_speed_mps": round(v_o, 4), "crash_type": ctype, "hazard_id": f"track-{other.id}"}
    # Speed just before impact: evaluated half a smoothing window earlier so the crash stop does not leak in.
    t_pre = max(t0, min(t_c, t_imp) - SMOOTH_WINDOW_S / 2) if math.isfinite(t_imp) else t_c
    ego_speed_c = sd(ego, "speed", t_pre)
    measured = {
        "t_start": t0, "t_closest": t_c, "min_gap_m": round(min_gap, 3),
        "ego_speed_mps": {"value": round(v_e, 3), "sd": round(v_e_sd, 3)},
        "other_speed_mps": {"value": round(v_o, 3), "sd": round(v_o_sd, 3)},
        "gap_m": {"value": round(gap0, 3), "sd": round(gap_sd, 3)},
        "lateral_offset_m": round(y0, 3), "auto_crash_type": auto_type, "auto_collided": auto_collided,
        "ego_speed_before_impact_mps": {"value": round(ego_speed_c, 3), "sd": round(sd(ego, "speed_sd", t_pre), 3),
                                        "t": round(t_pre, 3)},
        "av_braking": av, "notes": notes,
    }
    outcome = {"collided": collided}
    if collided:
        outcome["impact_speed_mps"] = round(ego_speed_c, 3)
    t_crash = round(t_imp if math.isfinite(t_imp) else t_c, 4) if collided else None
    return {"conflict": conflict, "conflict_ranges": ranges, "outcome": outcome, "t_crash": t_crash,
            "measured": measured}


ASSUMPTIONS = [
    f"contact point = bottom-centre of the vehicle box; residual offset +/-{CONTACT_POINT_SIGMA_M} m and "
    f"{CONTACT_DRIFT_REL:.0%} speed drift as the viewing angle changes (design assumptions)",
    f"vehicle lengths not measured: {DEFAULT_LENGTH_M} m each for the bumper gap (design assumption)",
    f"local quadratic smoothing, {SMOOTH_WINDOW_S} s window for speed, {ACCEL_WINDOW_S} s for acceleration",
    f"conflict ranges = measured value +/- {RANGE_K_SIGMA} sigma (jitter and calibration combined)",
    f"contact assumed if bumper gap < {COLLISION_GAP_M} m (user can override)",
    "jitter error assumes independent frame-to-frame box noise; correlated jitter would make it optimistic",
    "flat road, no lens-distortion correction",
]


def series(tr: RoadTrack, t0: float, step: int = 1) -> dict:
    r = lambda a: [round(float(x), 3) for x in a[::step]]
    return {"id": tr.id, "t": r(tr.t - t0), "x": r(tr.x), "y": r(tr.y), "speed": r(tr.speed),
            "speed_sd": r(tr.speed_sd), "speed_sd_jitter": r(tr.speed_sd_jitter),
            "speed_sd_calib": r(tr.speed_sd_calib), "vx": r(tr.vx), "ax": r(tr.ax)}


def _ids(x) -> list[int]:
    if x is None:
        return []
    return [int(i) for i in (x if isinstance(x, (list, tuple)) else [x])]


def analyse(tracks: dict[int, Track], calib: Calibration, fps: float, ego_id, lane_width_m: float,
            other_id=None, crash_type: str | None = None, collided: bool | None = None,
            case_id: str = "cctv", video_sha256: str | None = None, synthetic: bool = False) -> dict:
    """Tracks + calibration -> {bundle, ego/other series, calibration summary, assumptions}.

    ego_id / other_id: one track id, or a list of ids that are fragments of the same vehicle
    (stitched with merge_tracks). other_id None = pick automatically.
    """
    ego_ids, other_ids = _ids(ego_id), _ids(other_id)
    if not ego_ids:
        raise TrajectoryError("select the AV track")
    if set(ego_ids) & set(other_ids):
        raise TrajectoryError("a track cannot be both the AV and the other vehicle")
    tracks = dict(tracks)
    used = set(ego_ids) | set(other_ids)
    ego_key = ego_ids[0]
    tracks[ego_key] = merge_tracks(tracks, ego_ids)
    other_key = None
    if other_ids:
        other_key = other_ids[0]
        tracks[other_key] = merge_tracks(tracks, other_ids)
    for i in used - {ego_key, other_key}:
        tracks.pop(i, None)
    kin = {}
    for tid, tr in tracks.items():
        if len(tr.frames) >= MIN_TRACK_FRAMES:
            try:
                kin[tid] = kinematics(tr, calib, fps)
            except TrajectoryError:
                pass
    if ego_key not in kin:
        raise TrajectoryError(f"AV track {ego_key} is too short to measure")
    if other_key is not None and other_key not in kin:
        raise TrajectoryError(f"other track {other_key} is too short to measure")
    rf = road_frame(kin[ego_key], kin.get(other_key), calib)
    road = {tid: to_road(k, rf) for tid, k in kin.items()}
    ego = road[ego_key]
    other = road[other_key] if other_key is not None else pick_other(
        ego, [r for tid, r in road.items() if tid != ego_key])
    c = extract_conflict(ego, other, lane_width_m, crash_type=crash_type, collided=collided)
    t0 = c["conflict"]["t_start"]
    # Re-origin the road frame at the ego position at t0 so measured paths overlay the sim
    # (sim: ego centre starts at (0, 0) at conflict start).
    ex0, ey0 = ego.at(t0, "x"), ego.at(t0, "y")
    for r in (ego, other):
        r.x = r.x - ex0
        r.y = r.y - ey0
    if c["conflict"]["crash_type"] == "cut_in" and c["measured"]["lateral_offset_m"] < 0:
        other.y = -other.y   # sim cut-ins come from +y; mirror (sim is symmetric)
        ego.y = -ego.y
    bundle = {
        "schema": "0.1", "case_id": case_id, "synthetic": synthetic,
        "source": "video (CCTV / dashcam), measured by sim/video",
        "external": {"cctv": [case_id]},
        "integrity": {"hashes_present": video_sha256 is not None, "video_sha256": video_sha256,
                      "chain_of_custody": False},
        "conflict": c["conflict"], "conflict_ranges": c["conflict_ranges"], "outcome": c["outcome"],
    }
    if c["t_crash"] is not None:
        bundle["t_crash"] = c["t_crash"]
    return {"bundle": bundle, "measured": c["measured"], "calibration": calib.summary(),
            "road_frame": {"basis": rf.basis, "theta_rad": rf.theta},
            "ego": series(ego, t0), "other": series(other, t0),
            "ego_id": ego_key, "ego_ids": ego_ids, "other_id": other.id, "other_ids": other_ids or [other.id],
            "fps": fps,
            "assumptions": ASSUMPTIONS + calib.assumptions + c["measured"]["notes"]}
