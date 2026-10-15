"""CitySim (UCF SST) drone trajectories -> road-frame events -> SimScenario.

Purpose: an automatic eval with no hand labels. A real near-miss / cut-in from
drone video is reconstructed in our 2D sim; we check the sim reproduces the
measured trajectories, then the careful-driver Monte Carlo runs on it.

Dataset facts used here (all from the official format wiki,
https://github.com/ozheng1993/UCF-SST-CitySim-Dataset/wiki/Home, and the paper,
arXiv:2208.11036, Table 2):
- One CSV row per vehicle per video frame; videos at 30 frames per second.
- Columns used: frameNum, carId (one tool script spells it carID), carCenterXft,
  carCenterYft, headXft/headYft, tailXft/tailYft (front/rear centre),
  boundingBox{1..4}{X,Y}ft (1 front-right, 2 rear-right, 3 rear-left,
  4 front-left), speed (miles per hour), laneId (lane map id, optional).
- Positions are given in pixels, feet and (US sites only) GPS. We use feet.

LICENCE: CitySim is non-commercial only, by signed request form; no
redistribution of the data or modified versions. Never commit CitySim files.

Unverified (TODO, check on the first real file):
- Whether the *ft frame has y pointing down like the image frame. If it does,
  pass mirror_y=True so "left" is +y. The collision outcome is mirror-symmetric
  so event detection does not depend on it.
- Expressway / freeway segments are assumed straight over the event window
  (one road axis per recording). Weaving / merge sites may curve; check the
  lateral residual before trusting a reconstruction.

Frames: global metric frame = feet columns x FT_TO_M (optionally y mirrored).
Road frame per travel direction: x along the direction of travel, y lateral,
left positive. Event frame: road frame shifted so the ego starts at x = 0 and
the ego lane centre (median ego y over the window) is y = 0, t = 0 at window
start. Units SI throughout.
"""
from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from sim.scenario import LateralManoeuvre, ScriptedActor, SimScenario
from sim.vehicle import Geometry, VehicleState

# Exact unit definitions (international foot and mile), not tuning values.
FT_TO_M = 0.3048
MPH_TO_MPS = 0.44704
# Documented recording rate (wiki "Trajectory" section; paper Table 2).
CITYSIM_FPS = 30.0

# Lane keys encode (direction, lane) as one int; lane ids are far below this.
LANE_KEY_STRIDE = 100000

EventKind = Literal["cut_in", "lead_brake"]
Sample = tuple[float, float, float, float, float]  # (t, x, y, heading, v)


# ---------------------------------------------------------------- loading

@dataclass
class Recording:
    """One CitySim trajectory CSV in a global metric frame.

    df columns: frame, t, id, X, Y (m), hx, hy (unit heading vector, NaN if the
    head/tail columns are missing), v (m/s, NaN if no speed column), lane
    (int, -1 if unknown), length, width (m, NaN if unknown).
    """
    location: str
    frame_rate: float
    df: pd.DataFrame
    source: str = ""


def _col(raw: pd.DataFrame, *names: str) -> str | None:
    for n in names:
        if n in raw.columns:
            return n
    return None


# Where CitySim files live inside Modal: volume `accel-data` mounted at /data
# (see sim/data/modal_fetch.py). Override with env CITYSIM_ROOT.
MODAL_CITYSIM_ROOT = "/data/citysim"


def resolve_path(path: str | Path) -> Path:
    """Absolute/existing local paths are used as is; otherwise the path is taken
    relative to $CITYSIM_ROOT, falling back to the Modal volume mount."""
    p = Path(path)
    if p.is_absolute() or p.exists():
        return p
    return Path(os.environ.get("CITYSIM_ROOT", MODAL_CITYSIM_ROOT)) / p


def load_recording(path: str | Path, location: str, *, frame_rate: float = CITYSIM_FPS,
                   mirror_y: bool = False) -> Recording:
    """Read a CitySim trajectory CSV (as data only) into a Recording.

    path: a local file, or a path relative to the CitySim root (see resolve_path),
    so the same call works on a laptop and inside a Modal function.
    """
    path = resolve_path(path)
    raw = pd.read_csv(path)
    return recording_from_frame(raw, location, frame_rate=frame_rate, mirror_y=mirror_y,
                                source=str(path))


def recording_from_frame(raw: pd.DataFrame, location: str, *, frame_rate: float = CITYSIM_FPS,
                         mirror_y: bool = False, source: str = "") -> Recording:
    id_col = _col(raw, "carId", "carID")
    for need in ("frameNum", "carCenterXft", "carCenterYft"):
        if need not in raw.columns:
            raise ValueError(f"CitySim CSV missing column {need!r}")
    if id_col is None:
        raise ValueError("CitySim CSV missing column 'carId'")
    sy = -1.0 if mirror_y else 1.0

    def ft(c: str) -> np.ndarray:
        return raw[c].to_numpy(dtype=float) * FT_TO_M

    df = pd.DataFrame({
        "frame": raw["frameNum"].to_numpy(dtype=int),
        "id": raw[id_col].to_numpy(dtype=int),
        "X": ft("carCenterXft"),
        "Y": sy * ft("carCenterYft"),
    })
    df["t"] = df["frame"] / frame_rate

    if all(c in raw.columns for c in ("headXft", "headYft", "tailXft", "tailYft")):
        dx = ft("headXft") - ft("tailXft")
        dy = sy * (ft("headYft") - ft("tailYft"))
        n = np.hypot(dx, dy)
        with np.errstate(invalid="ignore", divide="ignore"):
            df["hx"], df["hy"] = dx / n, dy / n
        df["length"] = n
    else:
        df["hx"] = df["hy"] = df["length"] = np.nan

    if all(f"boundingBox{k}{a}ft" in raw.columns for k in (1, 4) for a in "XY"):
        df["width"] = np.hypot(ft("boundingBox1Xft") - ft("boundingBox4Xft"),
                               ft("boundingBox1Yft") - ft("boundingBox4Yft"))
    else:
        df["width"] = np.nan

    df["v"] = raw["speed"].to_numpy(dtype=float) * MPH_TO_MPS if "speed" in raw.columns else np.nan
    df["lane"] = raw["laneId"].fillna(-1).to_numpy(dtype=int) if "laneId" in raw.columns else -1

    # One length/width per vehicle (median over its track) so geometry is rigid.
    for c in ("length", "width"):
        df[c] = df.groupby("id")[c].transform("median")
    df = df.sort_values(["id", "frame"]).reset_index(drop=True)
    return Recording(location=location, frame_rate=frame_rate, df=df, source=source)


# ---------------------------------------------------------------- road frame

def estimate_road_axis(rec: Recording, *, min_track_displacement_m: float) -> float:
    """Angle (rad, in [0, pi)) of the dominant travel axis, direction-agnostic.

    Principal eigenvector of the summed outer products of each vehicle's
    first-to-last displacement. Assumes a straight road segment.
    """
    g = rec.df.groupby("id")
    d = np.stack([g["X"].last() - g["X"].first(), g["Y"].last() - g["Y"].first()], axis=1)
    d = d[np.hypot(d[:, 0], d[:, 1]) >= min_track_displacement_m]
    if len(d) == 0:
        raise ValueError("no track moved at least min_track_displacement_m")
    w, vecs = np.linalg.eigh(d.T @ d)
    ux, uy = vecs[:, np.argmax(w)]
    first = math.atan2(uy, ux)
    # Refine with the median per-track deviation so lane-changers do not tilt the axis.
    dev = (np.arctan2(d[:, 1], d[:, 0]) - first + math.pi / 2) % math.pi - math.pi / 2
    return (first + float(np.median(dev))) % math.pi


def road_frame(rec: Recording, road_angle: float, *, speed_smoothing_s: float) -> pd.DataFrame:
    """Project into road frames. Adds direction (+1/-1), x, y, heading, v_road.

    Each vehicle's direction is the sign of its net displacement along the axis;
    the frame for direction -1 is rotated 180 deg, so x always points along that
    vehicle's travel and y stays left-positive. If the CSV has no speed column,
    v comes from smoothed position differences over speed_smoothing_s.
    """
    df = rec.df.copy()
    ux, uy = math.cos(road_angle), math.sin(road_angle)
    s = df["X"] * ux + df["Y"] * uy
    n = -df["X"] * uy + df["Y"] * ux
    net = df.groupby("id")["X"].transform(lambda c: c.iloc[-1] - c.iloc[0]) * ux \
        + df.groupby("id")["Y"].transform(lambda c: c.iloc[-1] - c.iloc[0]) * uy
    df["direction"] = np.where(net >= 0, 1, -1)
    df["x"] = df["direction"] * s
    df["y"] = df["direction"] * n

    if df["hx"].notna().any():
        hs = df["hx"] * ux + df["hy"] * uy
        hn = -df["hx"] * uy + df["hy"] * ux
        df["heading"] = np.arctan2(df["direction"] * hn, df["direction"] * hs)
    else:
        df["heading"] = np.nan

    if df["v"].isna().all():
        win = max(1, int(round(speed_smoothing_s * rec.frame_rate)))
        g = df.groupby("id")
        sp = pd.Series(np.hypot(g["x"].diff(), g["y"].diff()) / g["t"].diff(), index=df.index)
        sp = sp.groupby(df["id"]).transform(lambda s: s.rolling(win, center=True, min_periods=1).mean().bfill())
        df["v"] = sp
    # Fill heading gaps from the direction of motion.
    if df["heading"].isna().any():
        vy = df.groupby("id")["y"].diff()
        vx = df.groupby("id")["x"].diff()
        df["heading"] = df["heading"].fillna(pd.Series(np.arctan2(vy, vx), index=df.index)).fillna(0.0)
    return df


def assign_lanes(df: pd.DataFrame, *, use_lane_id: bool, lane_width_m: float | None) -> pd.DataFrame:
    """Lane key per row: (direction, lane). Uses the dataset laneId when present
    and use_lane_id, else bins y by lane_width_m (must be given then)."""
    df = df.copy()
    if use_lane_id and (df["lane"] >= 0).any():
        valid = df["lane"] >= 0
        lane = df["lane"]
    else:
        if lane_width_m is None:
            raise ValueError("no laneId in data: pass lane_width_m to bin lateral position")
        lane = np.floor(df["y"] / lane_width_m + 0.5).astype(int)
        lane = lane - lane.min()  # keep keys non-negative
        df["lane"] = lane
        valid = pd.Series(True, index=df.index)
    df["lane_key"] = np.where(valid, (df["direction"] + 1) * LANE_KEY_STRIDE + lane, -1)
    return df


def leader_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per (frame, vehicle): the nearest vehicle ahead in the same lane, gap and TTC.

    gap = bumper-to-bumper longitudinal gap (m); ttc = gap / closing speed (s),
    inf when not closing.
    """
    d = df[df["lane_key"] >= 0].sort_values(["frame", "lane_key", "x"])
    g = d.groupby(["frame", "lane_key"])
    d = d.assign(lead_id=g["id"].shift(-1), lead_x=g["x"].shift(-1),
                 lead_v=g["v"].shift(-1), lead_len=g["length"].shift(-1))
    d = d[d["lead_id"].notna()].copy()
    d["lead_id"] = d["lead_id"].astype(int)
    d["gap"] = d["lead_x"] - d["x"] - (d["length"].fillna(0) + d["lead_len"].fillna(0)) / 2
    closing = d["v"] - d["lead_v"]
    d["ttc"] = np.where(closing > 0, np.maximum(d["gap"], 0.0) / closing.where(closing > 0, 1.0), np.inf)
    return d


# ---------------------------------------------------------------- events

@dataclass(frozen=True)
class EventThresholds:
    """All event-selection knobs. These are tuning parameters, not data;
    the defaults are starting points to tune on real files."""
    ttc_max_s: float = 3.0                # keep events with min TTC at or below this
    max_gap_at_cut_in_m: float = 30.0     # follower-to-cutter bumper gap when the lane changes
    min_lane_hold_s: float = 1.0          # lane must be held this long on both sides of a change
    min_lead_decel_mps2: float = 2.0      # lead_brake: leader decel at least this (positive number)
    accel_smoothing_s: float = 0.5        # window for smoothing v before differentiating
    min_follow_s: float = 2.0             # lead_brake: follower behind same leader at least this
    lane_change_exclusion_s: float = 2.0  # lead_brake: skip if leader entered the lane this recently
    pre_s: float = 3.0                    # window before the key moment
    post_s: float = 4.0                   # window after the key moment
    require_ego_lane_keep: bool = True    # ego (follower) must not change lane in the window
    min_track_displacement_m: float = 20.0  # tracks used to estimate the road axis
    use_lane_id: bool = True
    lane_width_m: float | None = None     # only needed when the CSV has no laneId


@dataclass
class VehicleTrack:
    id: int
    length: float
    width: float
    samples: list[Sample]  # (t, x, y, heading, v) in the event frame


@dataclass
class Event:
    kind: EventKind
    location: str
    ego: VehicleTrack     # the follower: the seat a careful driver / AV would occupy
    other: VehicleTrack   # cutter or braking leader
    t_key: float          # lane-change or min-TTC moment, event-frame seconds
    min_ttc_s: float
    min_gap_m: float
    meta: dict = field(default_factory=dict)


def _runs(lanes: np.ndarray) -> list[tuple[int, int, int]]:
    """Run-length encode: [(start_idx, end_idx_exclusive, lane)]."""
    out, start = [], 0
    for i in range(1, len(lanes) + 1):
        if i == len(lanes) or lanes[i] != lanes[start]:
            out.append((start, i, int(lanes[start])))
            start = i
    return out


def _pair_window(df: pd.DataFrame, ego: int, other: int, f0: int, f1: int) -> pd.DataFrame:
    a = df[(df["id"] == ego) & df["frame"].between(f0, f1)]
    b = df[(df["id"] == other) & df["frame"].between(f0, f1)]
    return a.merge(b, on="frame", suffixes=("_e", "_o"))


def _pair_ttc(w: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    gap = (w["x_o"] - w["x_e"] - (w["length_e"].fillna(0) + w["length_o"].fillna(0)) / 2).to_numpy()
    closing = (w["v_e"] - w["v_o"]).to_numpy()
    ttc = np.full(len(w), np.inf)
    m = closing > 0
    ttc[m] = np.maximum(gap[m], 0.0) / closing[m]
    return gap, ttc


def _make_event(kind: EventKind, rec: Recording, w: pd.DataFrame, ego: int, other: int,
                frame_key: int, ttc_from_frame: int, meta: dict) -> Event:
    t0 = float(w["t_e"].iloc[0])
    x0 = float(w["x_e"].iloc[0])
    y0 = float(w["y_e"].median())

    def track(sfx: str, vid: int) -> VehicleTrack:
        s = [(float(t - t0), float(x - x0), float(y - y0), float(h), float(v))
             for t, x, y, h, v in zip(w[f"t{sfx}"], w[f"x{sfx}"], w[f"y{sfx}"],
                                      w[f"heading{sfx}"], w[f"v{sfx}"])]
        return VehicleTrack(vid, float(w[f"length{sfx}"].iloc[0]), float(w[f"width{sfx}"].iloc[0]), s)

    after = w[w["frame"] >= ttc_from_frame]
    gap, ttc = _pair_ttc(after)
    return Event(kind=kind, location=rec.location, ego=track("_e", ego), other=track("_o", other),
                 t_key=frame_key / rec.frame_rate - t0,
                 min_ttc_s=float(ttc.min()) if len(ttc) else math.inf,
                 min_gap_m=float(gap.min()) if len(gap) else math.nan,
                 meta={"source": rec.source, "direction": int(w["direction_e"].iloc[0]),
                       "frame_start": int(w["frame"].iloc[0]), "frame_end": int(w["frame"].iloc[-1]),
                       **meta})


def prepare(rec: Recording, th: EventThresholds, road_angle: float | None = None) -> pd.DataFrame:
    if road_angle is None:
        road_angle = estimate_road_axis(rec, min_track_displacement_m=th.min_track_displacement_m)
    df = road_frame(rec, road_angle, speed_smoothing_s=th.accel_smoothing_s)
    df = assign_lanes(df, use_lane_id=th.use_lane_id, lane_width_m=th.lane_width_m)
    df.attrs["road_angle"] = road_angle
    return df


def find_events(rec: Recording, kind: EventKind, thresholds: EventThresholds | None = None, *,
                road_angle: float | None = None) -> list[Event]:
    """Extract candidate safety-critical interactions, sorted by min TTC (worst first).

    cut_in: vehicle C changes lane (both lanes held >= min_lane_hold_s); F is the
      vehicle directly behind C in C's new lane at the change frame; keep if the
      bumper gap then is <= max_gap_at_cut_in_m and min TTC(F->C) from the change
      to post_s after is <= ttc_max_s. Ego = F, other = C.
    lead_brake: F follows the same leader L in one lane for >= min_follow_s; keep
      if L decelerates by >= min_lead_decel_mps2 and min TTC <= ttc_max_s, and L
      did not enter the lane within lane_change_exclusion_s (that is a cut-in).
    """
    th = thresholds or EventThresholds()
    df = prepare(rec, th, road_angle)
    lead = leader_table(df)
    fps = rec.frame_rate
    hold = int(round(th.min_lane_hold_s * fps))
    pre, post = int(round(th.pre_s * fps)), int(round(th.post_s * fps))
    events: list[Event] = []
    lane_by_id = {vid: g[["frame", "lane_key"]].to_numpy() for vid, g in df.groupby("id")}

    def lane_kept(vid: int, f0: int, f1: int) -> bool:
        a = lane_by_id[vid]
        lanes = a[(a[:, 0] >= f0) & (a[:, 0] <= f1), 1]
        return len(set(lanes.tolist())) == 1

    if kind == "cut_in":
        for vid, a in lane_by_id.items():
            runs = _runs(a[:, 1])
            for (s0, e0, l0), (s1, e1, l1) in zip(runs, runs[1:]):
                if l0 < 0 or l1 < 0 or e0 - s0 < hold or e1 - s1 < hold:
                    continue
                fc = int(a[s1, 0])
                behind = lead[(lead["frame"] == fc) & (lead["lead_id"] == vid) & (lead["lane_key"] == l1)]
                if behind.empty or float(behind["gap"].iloc[0]) > th.max_gap_at_cut_in_m:
                    continue
                ego = int(behind["id"].iloc[0])
                if th.require_ego_lane_keep and not lane_kept(ego, fc - pre, fc + post):
                    continue
                w = _pair_window(df, ego, vid, fc - pre, fc + post)
                if w.empty:
                    continue
                ev = _make_event("cut_in", rec, w, ego, vid, fc, fc,
                                 {"from_lane": l0 % LANE_KEY_STRIDE, "to_lane": l1 % LANE_KEY_STRIDE,
                                  "gap_at_cut_in_m": float(behind["gap"].iloc[0])})
                if ev.min_ttc_s <= th.ttc_max_s:
                    events.append(ev)

    elif kind == "lead_brake":
        smooth = max(1, int(round(th.accel_smoothing_s * fps)))
        df = df.sort_values(["id", "frame"])
        vs = df.groupby("id")["v"].transform(lambda s: s.rolling(smooth, center=True, min_periods=1).mean())
        df["accel"] = vs.groupby(df["id"]).diff() / df.groupby("id")["t"].diff()
        acc = df.set_index(["id", "frame"])["accel"]
        lead = lead.sort_values(["id", "frame"])
        # Contiguous follow episodes: same follower, same leader, consecutive frames.
        brk = (lead["id"].ne(lead["id"].shift()) | lead["lead_id"].ne(lead["lead_id"].shift())
               | lead["frame"].diff().ne(1))
        lead["episode"] = brk.cumsum()
        lc = int(round(th.lane_change_exclusion_s * fps))
        for _, ep in lead.groupby("episode"):
            if len(ep) < int(round(th.min_follow_s * fps)):
                continue
            ego, lid = int(ep["id"].iloc[0]), int(ep["lead_id"].iloc[0])
            fs, fe = int(ep["frame"].iloc[0]), int(ep["frame"].iloc[-1])
            if not lane_kept(lid, fs - lc, fe):
                continue
            la = acc.reindex(list(zip([lid] * len(ep), ep["frame"]))).to_numpy()
            if not np.nanmin(la, initial=np.inf) <= -th.min_lead_decel_mps2:
                continue
            fk = int(ep["frame"].iloc[int(np.argmin(ep["ttc"].to_numpy()))])
            f0, f1 = max(fs, fk - pre), min(fe, fk + post)
            if th.require_ego_lane_keep and not lane_kept(ego, f0, f1):
                continue
            w = _pair_window(df, ego, lid, f0, f1)
            if w.empty:
                continue
            ev = _make_event("lead_brake", rec, w, ego, lid, fk, f0,
                             {"lane": int(ep["lane_key"].iloc[0]) % LANE_KEY_STRIDE,
                              "min_lead_accel_mps2": float(np.nanmin(la))})
            if ev.min_ttc_s <= th.ttc_max_s:
                events.append(ev)
    else:
        raise ValueError(f"unknown event kind {kind!r}")

    events.sort(key=lambda e: e.min_ttc_s)
    return events


# ---------------------------------------------------------------- to sim

@dataclass(frozen=True)
class ReplayCase:
    scenario: SimScenario
    ego_accel_profile: list[tuple[float, float]]  # feed to AVReplayPolicy to replay the measured ego
    actor_name: str


def accel_profile(samples: list[Sample], segment_s: float) -> list[tuple[float, float]]:
    """Piecewise-constant accel that hits the measured speed at every segment boundary."""
    t = np.array([s[0] for s in samples])
    v = np.array([s[4] for s in samples])
    out = []
    k = t[0]
    while k < t[-1] - 1e-9:
        k1 = min(k + segment_s, t[-1])
        out.append((float(k - t[0]), float((np.interp(k1, t, v) - np.interp(k, t, v)) / (k1 - k))))
        k = k1
    return out


def lateral_manoeuvre(samples: list[Sample], *, settle_s: float, min_shift_m: float,
                      fractions: tuple[float, float]) -> LateralManoeuvre | None:
    """Fit the sim's cosine lane change to a measured lateral track.

    y_from / y_to: median y over the first / last settle_s. Start and duration
    are solved so the cosine profile passes the measured times at which the
    shift reaches fractions[0] and fractions[1] of its total. None if the total
    shift is below min_shift_m.
    """
    t = np.array([s[0] for s in samples])
    y = np.array([s[2] for s in samples])
    y_from = float(np.median(y[t <= t[0] + settle_s]))
    y_to = float(np.median(y[t >= t[-1] - settle_s]))
    if abs(y_to - y_from) < min_shift_m:
        return None
    f = (y - y_from) / (y_to - y_from)
    lo, hi = fractions
    i_lo, i_hi = int(np.argmax(f >= lo)), int(np.argmax(f >= hi))
    u_lo, u_hi = math.acos(1 - 2 * lo) / math.pi, math.acos(1 - 2 * hi) / math.pi
    duration = max((t[i_hi] - t[i_lo]) / (u_hi - u_lo), 1e-3)
    return LateralManoeuvre(t_start=float(t[i_lo] - u_lo * duration - t[0]), duration=float(duration),
                            y_from=y_from, y_to=y_to)


def to_sim_scenario(ev: Event, *, wheelbase_m: float, accel_segment_s: float,
                    lateral_settle_s: float, min_lateral_shift_m: float,
                    lateral_fractions: tuple[float, float] = (0.1, 0.9),
                    dt: float = 0.02) -> ReplayCase:
    """Initial conditions + scripted profiles for the other vehicle; ego profile for AV replay.

    wheelbase_m is NOT in CitySim; the caller must supply it as a labelled assumption.
    """
    def geom(tr: VehicleTrack) -> Geometry:
        return Geometry(length=tr.length, width=tr.width, wheelbase=wheelbase_m)

    def initial(tr: VehicleTrack, lat: LateralManoeuvre | None) -> VehicleState:
        _, x, y, _, v = tr.samples[0]
        # Scripted actors keep heading 0 unless a lateral manoeuvre sets it (world.py).
        return VehicleState(x, lat.y_from if lat else y, 0.0, v)

    name = "cutter" if ev.kind == "cut_in" else "lead"
    lat = (lateral_manoeuvre(ev.other.samples, settle_s=lateral_settle_s,
                             min_shift_m=min_lateral_shift_m, fractions=lateral_fractions)
           if ev.kind == "cut_in" else None)
    other = ScriptedActor(name, geom(ev.other), initial(ev.other, lat),
                          accel_profile=accel_profile(ev.other.samples, accel_segment_s), lateral=lat)
    _, ex, ey, _, ev0 = ev.ego.samples[0]
    duration = ev.ego.samples[-1][0] - ev.ego.samples[0][0]
    scen = SimScenario(geom(ev.ego), VehicleState(ex, ey, 0.0, ev0), [other], duration=duration, dt=dt)
    return ReplayCase(scen, accel_profile(ev.ego.samples, accel_segment_s), name)


def trajectory_error(ev: Event, trace: dict[str, list], actor_name: str) -> dict[str, float]:
    """RMSE / max abs error (m) of sim trace vs measured, ego and other, on the sim time grid."""
    t_sim = np.array(trace["t"])
    out: dict[str, float] = {}
    for key, tr in (("ego", ev.ego), ("other", ev.other)):
        sim = np.array(trace["ego" if key == "ego" else actor_name])
        tm = np.array([s[0] for s in tr.samples])
        m = t_sim <= tm[-1]
        for j, ax in ((1, "x"), (2, "y")):
            meas = np.interp(t_sim[m], tm, [s[j] for s in tr.samples])
            err = sim[m, j - 1] - meas
            out[f"{key}_{ax}_rmse_m"] = float(np.sqrt(np.mean(err ** 2)))
            out[f"{key}_{ax}_max_m"] = float(np.max(np.abs(err)))
    return out


def event_to_dict(ev: Event) -> dict:
    """JSON-serialisable form (for Supabase rows or returning from Modal)."""
    d = asdict(ev)
    d["min_ttc_s"] = None if math.isinf(ev.min_ttc_s) else ev.min_ttc_s
    return d
