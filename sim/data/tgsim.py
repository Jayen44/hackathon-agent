"""FHWA TGSIM (Third Generation Simulation) freeway trajectories -> events -> SimScenario.

Why this dataset: US federal government data, public domain, no sign-up, and it
contains vehicles with automated driving features (SAE L1 ACC / L2) driving
among human traffic. It replaces CitySim (non-commercial, signed request) as
the tier-2 "telemetry-grade" stand-in and the B2 reconstruction ground truth.

Dataset facts used here (all from the dataset pages / column descriptions on
data.transportation.gov, read 2026-10-15):
- Licence: "http://www.usa.gov/publicdomain/label/1.0/" (US public domain) on each
  dataset; the TGSIM hub page (uwv8-dpvx) lists CC0 1.0. Public Access Level: public.
  Recommended citation: U.S. DOT FHWA (2023), TGSIM <dataset>, ITS DataHub,
  https://doi.org/10.21949/1404218 (stationary set; other sets have their own DOI).
- One CSV row per vehicle per 0.1 s ("trajectory data at every 0.1 second").
- Columns: id, time (s from run start), xloc_kf, yloc_kf (m, reference-image
  coordinates, origin top-left, after Kalman filtering; 1 pixel = 0.3 m),
  lane_kf (lane id on the reference image), speed_kf (m/s), acceleration_kf
  (m/s^2), length_smoothed, width_smoothed (m, bounding-box proxies),
  type_most_common (small-vehicle / large-vehicle), av (I-90/94 sets) or acc
  (I-294 sets) = yes/no automated test vehicle, run_index.
- Vehicle ids are only unique within a run, so each run is its own Recording.
- Sizes are bounding-box proxies and look inflated/capped (small vehicles: max
  6.0 m x 2.67 m, mean ~5.6 x 2.5 m on I-90/94 stationary); bumper gaps are
  therefore conservative and events with overlapping boxes are flagged
  (meta["bbox_overlap"]) as likely tracking/box artefacts.
- No raw video is published (only aerial reference images per run). For B3
  (video -> trajectory) use NGSIM, which has video but is CC BY-SA 4.0.

Frames: global metric frame (X, Y) = (xloc_kf, yloc_kf), NOT mirrored, even
though the pages say the reference-image origin is top-left. Checked on the
real files (2026-10-15, lane_lateral_order()): unmirrored, I-90/94 stationary
lane 1 / 10 lies on the left of travel, matching the column description ("Lane
1 is the innermost lane"), and on I-294 L1 the ACC test vehicles drive mostly in
lane 4 with lane 5 to its left, matching "moved to the second from left most
lane". Mirroring would contradict both, so yloc_kf behaves as y-up. The collision
outcome is mirror-symmetric either way; only left/right labels depend on it.

Roads curve over kilometres, so instead of one straight axis (citysim.py) we
build a reference line per run from the data itself (middle of the occupied
band along the road) and project every point onto it (Frenet frame): x = arc
length along the vehicle's travel direction, y = signed lateral offset, left
positive, v = road-frame dx/dt. Lanes come from lane_kf, not from binning y.
Event frames then follow citysim.py exactly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from sim.data import citysim as cs
from sim.data.citysim import (  # re-exported: same API as citysim.py
    Event, EventThresholds, ReplayCase, VehicleTrack, accel_profile, event_to_dict,
    lateral_manoeuvre, to_sim_scenario, trajectory_error,
)

__all__ = [
    "DATASETS", "TGSIM_FPS", "Event", "EventThresholds", "ReplayCase", "VehicleTrack",
    "ade_fde", "accel_profile", "event_to_dict", "event_from_dict", "find_events", "lateral_manoeuvre",
    "load_recordings", "recording_from_frame", "reference_line", "frenet", "prepare",
    "lane_lateral_order", "to_sim_scenario", "trajectory_error",
]

# Documented sampling interval: "trajectory data at every 0.1 second".
TGSIM_FPS = 10.0
# lane_kf ids range from -5 to 15; shift so lane keys stay non-negative in citysim.
LANE_OFFSET = 50

# Socrata ids on data.transportation.gov (freeway sets only).
DATASETS: dict[str, dict] = {
    "i90_94_stationary": {"socrata": "9uas-hf8b", "file": "I90_94_stationary_final.csv",
                          "site": "I-90/I-94 Chicago IL (fixed helicopter view, weaving)",
                          "automation": "SAE L2", "doi": "https://doi.org/10.21949/1404218"},
    "i90_94_moving": {"socrata": "6a6e-vfvi", "file": "I90_94_moving_final.csv",
                      "site": "I-90/I-94 Chicago IL (helicopter following L2 vehicle)",
                      "automation": "SAE L2", "doi": None},
    "i294_l1": {"socrata": "7zjf-a4zf", "file": "I294_L1_final.csv",
                "site": "I-294 Hinsdale IL (helicopter following ACC string)",
                "automation": "SAE L1 (ACC)", "doi": None},
    "i294_l2": {"socrata": "tpsq-zrwa", "file": "I294_L2_final.csv",
                "site": "I-294 Hinsdale IL (helicopter following L2 lane changes)",
                "automation": "SAE L2", "doi": None},
}

MODAL_TGSIM_ROOT = "/data/tgsim"


# ---------------------------------------------------------------- loading

def recording_from_frame(raw: pd.DataFrame, location: str, *, run: int | None = None,
                         frame_rate: float = TGSIM_FPS, source: str = "",
                         mirror_y: bool = False) -> cs.Recording:
    """One run of a TGSIM CSV -> citysim.Recording (global metric frame).

    mirror_y=False is the checked default (see module docstring).

    df gets the citysim columns plus `automated` (bool) and `run`.
    """
    for need in ("id", "time", "xloc_kf", "yloc_kf", "speed_kf"):
        if need not in raw.columns:
            raise ValueError(f"TGSIM CSV missing column {need!r}")
    if run is not None and "run_index" in raw.columns:
        raw = raw[raw["run_index"] == run]
    n_in = len(raw)
    raw = raw.dropna(subset=["id", "time", "xloc_kf", "yloc_kf", "speed_kf"])
    flag = "av" if "av" in raw.columns else ("acc" if "acc" in raw.columns else None)
    df = pd.DataFrame({
        "frame": np.round(raw["time"].to_numpy(dtype=float) * frame_rate).astype(int),
        "id": raw["id"].to_numpy(dtype=int),
        "X": raw["xloc_kf"].to_numpy(dtype=float),
        "Y": (-1.0 if mirror_y else 1.0) * raw["yloc_kf"].to_numpy(dtype=float),
        "v": raw["speed_kf"].to_numpy(dtype=float),
        "a_meas": raw["acceleration_kf"].to_numpy(dtype=float) if "acceleration_kf" in raw else np.nan,
        "length": raw["length_smoothed"].to_numpy(dtype=float) if "length_smoothed" in raw else np.nan,
        "width": raw["width_smoothed"].to_numpy(dtype=float) if "width_smoothed" in raw else np.nan,
        "lane": (raw["lane_kf"].fillna(-999).to_numpy(dtype=int) if "lane_kf" in raw
                 else np.full(len(raw), -999)),
        "automated": (raw[flag].astype(str).str.strip().str.lower() == "yes").to_numpy()
        if flag else False,
        "vtype": raw["type_most_common"].astype(str).to_numpy() if "type_most_common" in raw else "",
    })
    df["run"] = int(run) if run is not None else -1
    df["t"] = df["frame"] / frame_rate
    df["hx"] = df["hy"] = np.nan
    for c in ("length", "width"):
        df[c] = df.groupby("id")[c].transform("median")
    df["automated"] = df.groupby("id")["automated"].transform("any")
    df = df.drop_duplicates(["id", "frame"]).sort_values(["id", "frame"]).reset_index(drop=True)
    df.attrs["dropped_rows"] = int(n_in - len(df))  # missing id/time/position/speed or duplicate frame
    return cs.Recording(location=location, frame_rate=frame_rate, df=df, source=source)


def load_recordings(path: str | Path, dataset: str, *, runs: list[int] | None = None) -> list[cs.Recording]:
    """Read a TGSIM CSV (as data only) and split it into one Recording per run."""
    p = Path(path)
    if not p.is_absolute() and not p.exists():
        p = Path(MODAL_TGSIM_ROOT) / p
    raw = pd.read_csv(p)
    all_runs = sorted(raw["run_index"].unique().tolist()) if "run_index" in raw else [None]
    out = []
    for r in all_runs:
        if runs is not None and r not in runs:
            continue
        out.append(recording_from_frame(raw, f"TGSIM {dataset} run {r}", run=r, source=str(p)))
    return out


# ---------------------------------------------------------------- reference line / Frenet

@dataclass(frozen=True)
class FrameParams:
    """Reference-line construction knobs (geometry processing, not data)."""
    bin_m: float = 5.0          # bin length along the road for the centre line
    min_bin_points: int = 20    # bins with fewer points are dropped
    smooth_bins: int = 9        # rolling-mean window (bins) over the centre line
    iterations: int = 3         # re-centre along the previous line's arc length
    band_quantiles: tuple[float, float] = (0.02, 0.98)  # lateral band edges per bin
    extend_m: float = 200.0     # straight extension beyond both ends
    search_vertices: int = 40   # local window for nearest-segment search
    project_step_m: float = 0.25  # vertex spacing used for the final projection


def _polyline_s(P: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(P, axis=0).T))])


def frenet(P: np.ndarray, X: np.ndarray, Y: np.ndarray, *, guess: np.ndarray | None = None,
           window: int = 40) -> tuple[np.ndarray, np.ndarray]:
    """Project points onto polyline P (M x 2): arc length s and signed offset d (left +).

    guess: approximate vertex index per point (search only +-window around it);
    None searches every segment (fine for small inputs).
    """
    A, B = P[:-1], P[1:]
    D = B - A
    L2 = np.maximum((D ** 2).sum(1), 1e-12)
    S0 = _polyline_s(P)[:-1]
    n = len(X)
    s_out, d_out = np.empty(n), np.empty(n)
    nseg = len(A)
    chunk = 200_000
    for c0 in range(0, n, chunk):
        x, y = X[c0:c0 + chunk], Y[c0:c0 + chunk]
        if guess is None:
            idx = np.broadcast_to(np.arange(nseg), (len(x), nseg))
        else:
            g = guess[c0:c0 + chunk]
            idx = np.clip(g[:, None] + np.arange(-window, window + 1)[None, :], 0, nseg - 1)
        ax, ay = A[idx, 0], A[idx, 1]
        dx, dy = D[idx, 0], D[idx, 1]
        u = np.clip(((x[:, None] - ax) * dx + (y[:, None] - ay) * dy) / L2[idx], 0.0, 1.0)
        px, py = ax + u * dx, ay + u * dy
        dist = (x[:, None] - px) ** 2 + (y[:, None] - py) ** 2
        k = np.argmin(dist, axis=1)
        r = np.arange(len(x))
        seg = idx[r, k]
        ln = np.sqrt(L2[seg])
        s_out[c0:c0 + chunk] = S0[seg] + u[r, k] * ln
        cross = dx[r, k] * (y - ay[r, k]) - dy[r, k] * (x - ax[r, k])
        d_out[c0:c0 + chunk] = cross / ln
    return s_out, d_out


def reference_line(X: np.ndarray, Y: np.ndarray, fp: FrameParams = FrameParams()) -> np.ndarray:
    """Road reference polyline from all positions, independent of traffic density.

    Start from the principal axis of the points. Each iteration projects every
    point onto the current line, bins by arc length, and moves the line in each
    bin to the middle of the occupied band ((q_lo + q_hi) / 2 of the lateral
    offsets; a median would jump between carriageways as their traffic counts
    change). The result is smoothed and extended straight at both ends. The line
    runs along the middle of the paved area in view (between carriageways when
    both directions are present). Assumes the road does not fold back on itself
    within one run (true for these freeway sites).
    """
    pts = np.stack([X, Y], 1)
    c = pts.mean(0)
    w, vecs = np.linalg.eigh(np.cov((pts - c).T))
    u = vecs[:, np.argmax(w)]
    s0 = (pts - c) @ u
    P = _dense(np.stack([c + (s0.min() - fp.extend_m) * u, c + (s0.max() + fp.extend_m) * u]), fp.bin_m)
    q_lo, q_hi = fp.band_quantiles
    for _ in range(fp.iterations):
        s, d = frenet(P, X, Y, guess=_guess(P, X, Y), window=fp.search_vertices)
        g = pd.DataFrame({"b": np.floor(s / fp.bin_m).astype(int), "s": s, "d": d}).groupby("b")
        keep = g.size() >= fp.min_bin_points
        sm = g["s"].median()[keep].to_numpy()
        dc = ((g["d"].quantile(q_lo) + g["d"].quantile(q_hi)) / 2)[keep].to_numpy()
        if len(sm) < 2:
            raise ValueError("too few points to build a reference line")
        dc = pd.Series(dc).rolling(fp.smooth_bins, center=True, min_periods=1).mean().to_numpy()
        sP = _polyline_s(P)
        bx, by = np.interp(sm, sP, P[:, 0]), np.interp(sm, sP, P[:, 1])
        tx = np.interp(sm, sP[:-1], np.diff(P[:, 0]) / np.diff(sP))
        ty = np.interp(sm, sP[:-1], np.diff(P[:, 1]) / np.diff(sP))
        nrm = np.hypot(tx, ty)
        Q = np.stack([bx - dc * ty / nrm, by + dc * tx / nrm], 1)
        Q = pd.DataFrame(Q).rolling(fp.smooth_bins, center=True, min_periods=1).mean().to_numpy()
        t0, t1 = Q[1] - Q[0], Q[-1] - Q[-2]
        t0, t1 = t0 / np.hypot(*t0), t1 / np.hypot(*t1)
        P = _dense(np.vstack([Q[0] - fp.extend_m * t0, Q, Q[-1] + fp.extend_m * t1]), fp.bin_m)
    return P


def _dense(P: np.ndarray, step: float) -> np.ndarray:
    s = _polyline_s(P)
    q = np.arange(0.0, s[-1], step)
    q = np.append(q, s[-1])
    return np.stack([np.interp(q, s, P[:, 0]), np.interp(q, s, P[:, 1])], 1)


def _guess(P: np.ndarray, X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Nearest vertex by a coarse-to-fine search (vertex grid every 10th, then local)."""
    step = 10
    coarse = P[::step]
    best = np.empty(len(X), dtype=int)
    chunk = 100_000
    for c0 in range(0, len(X), chunk):
        x, y = X[c0:c0 + chunk, None], Y[c0:c0 + chunk, None]
        best[c0:c0 + chunk] = np.argmin((x - coarse[None, :, 0]) ** 2 + (y - coarse[None, :, 1]) ** 2, 1) * step
    return np.clip(best, 0, len(P) - 2)


def prepare(rec: cs.Recording, th: EventThresholds, fp: FrameParams = FrameParams(),
            ref: np.ndarray | None = None) -> pd.DataFrame:
    """Road-frame table in the citysim prepare() format (+ automated, run, s, d)."""
    df = rec.df.copy()
    if ref is None:
        ref = reference_line(df["X"].to_numpy(), df["Y"].to_numpy(), fp)
    # Project onto a finely resampled line: at each polyline corner a point at
    # offset d jumps by d x (turn angle), which shows up as speed jitter.
    # Rolling mean over two bins rounds the corners off.
    ref = _dense(ref, fp.project_step_m)
    k = 2 * int(round(fp.bin_m / fp.project_step_m)) + 1
    ref = pd.DataFrame(ref).rolling(k, center=True, min_periods=1).mean().to_numpy()
    s, d = frenet(ref, df["X"].to_numpy(), df["Y"].to_numpy(),
                  guess=_guess(ref, df["X"].to_numpy(), df["Y"].to_numpy()), window=fp.search_vertices)
    df["s"], df["d"] = s, d
    g = df.groupby("id")["s"]
    df["direction"] = np.where(g.transform("last") - g.transform("first") >= 0, 1, -1)
    df["x"] = df["direction"] * df["s"]
    df["y"] = df["direction"] * df["d"]
    # Heading relative to the road from smoothed position differences; held when nearly stopped.
    win = max(1, int(round(th.accel_smoothing_s * rec.frame_rate)))
    gx = df.groupby("id")["x"].diff()
    gy = df.groupby("id")["y"].diff()
    sx = gx.groupby(df["id"]).transform(lambda c: c.rolling(win, center=True, min_periods=1).mean())
    sy = gy.groupby(df["id"]).transform(lambda c: c.rolling(win, center=True, min_periods=1).mean())
    moving = np.hypot(sx, sy) * rec.frame_rate > 0.5
    df["heading"] = pd.Series(np.where(moving, np.arctan2(sy, sx), np.nan), index=df.index)
    df["heading"] = df.groupby("id")["heading"].transform(lambda c: c.ffill().bfill()).fillna(0.0)
    # v in the road frame (dx/dt): measured speed x (Frenet distance / travelled distance).
    # Off the reference line, Frenet arc length runs 1/(1 - d * curvature) faster or
    # slower than distance travelled, and lane changes add a cos(heading) factor;
    # without this the replayed ego drifts away from its measured x.
    gX = df.groupby("id")["X"].diff()
    gY = df.groupby("id")["Y"].diff()
    sXY = np.hypot(gX, gY).groupby(df["id"]).transform(
        lambda c: c.rolling(win, center=True, min_periods=1).mean())
    ratio = pd.Series(np.where(moving & (sXY > 0), sx / sXY.where(sXY > 0, 1.0), np.nan), index=df.index)
    ratio = ratio.groupby(df["id"]).transform(lambda c: c.ffill().bfill()).fillna(1.0)
    df["speed_meas"] = df["v"]
    df["v"] = df["v"] * ratio
    valid = df["lane"] > -999
    df["lane_key"] = np.where(valid, (df["direction"] + 1) * cs.LANE_KEY_STRIDE + df["lane"] + LANE_OFFSET, -1)
    return df


def lane_lateral_order(df: pd.DataFrame) -> pd.DataFrame:
    """Median road-frame y per (direction, lane): checks that the dataset's inner
    lane comes out on the left (larger y) and lane spacing is plausible."""
    return (df[df["lane"] > -999].groupby(["direction", "lane"])["y"].median()
            .rename("median_y_m").reset_index())


# ---------------------------------------------------------------- events

def find_events(rec: cs.Recording, kind: cs.EventKind, thresholds: EventThresholds | None = None, *,
                fp: FrameParams = FrameParams(), df: pd.DataFrame | None = None) -> list[Event]:
    """citysim.find_events on the TGSIM Frenet frame; meta adds run, lane ids
    (dataset numbering), automation flags and vehicle types."""
    th = thresholds or EventThresholds()
    if df is None:
        df = prepare(rec, th, fp)
    evs = cs.find_events_in_frame(rec, df, kind, th)
    per_id = df.groupby("id").agg(automated=("automated", "first"), vtype=("vtype", "first"))
    for e in evs:
        for k in ("from_lane", "to_lane", "lane"):
            if k in e.meta:
                e.meta[k] = int(e.meta[k]) - LANE_OFFSET
        e.meta["run"] = int(df["run"].iloc[0])
        e.meta["ego_automated"] = bool(per_id.loc[e.ego.id, "automated"])
        e.meta["other_automated"] = bool(per_id.loc[e.other.id, "automated"])
        e.meta["ego_type"] = str(per_id.loc[e.ego.id, "vtype"])
        e.meta["other_type"] = str(per_id.loc[e.other.id, "vtype"])
        # length/width_smoothed are bounding-box proxies, capped in the data (small
        # vehicles <= 6.0 x 2.67 m, mean ~5.6 x 2.5 m), so they overstate car size and
        # bumper gaps come out too small. A negative min gap means the boxes overlap
        # while nothing in the dataset reports a crash: flag, do not trust.
        e.meta["bbox_overlap"] = bool(e.min_gap_m < 0)
    return evs


def event_from_dict(d: dict) -> Event:
    """Inverse of event_to_dict (e.g. events read back from the Modal volume)."""
    def tr(t: dict) -> VehicleTrack:
        return VehicleTrack(int(t["id"]), float(t["length"]), float(t["width"]),
                            [tuple(float(v) for v in s) for s in t["samples"]])
    return Event(kind=d["kind"], location=d["location"], ego=tr(d["ego"]), other=tr(d["other"]),
                 t_key=float(d["t_key"]),
                 min_ttc_s=math.inf if d["min_ttc_s"] is None else float(d["min_ttc_s"]),
                 min_gap_m=float(d["min_gap_m"]), meta=dict(d.get("meta", {})))


def ade_fde(ev: Event, trace: dict[str, list], actor_name: str) -> dict[str, float]:
    """Rubric B2: average / final displacement error (m) of the sim trace vs the
    measured track, ego and other, on the sim time grid within the event window."""
    t_sim = np.array(trace["t"])
    out: dict[str, float] = {}
    for key, tr in (("ego", ev.ego), ("other", ev.other)):
        sim = np.array(trace["ego" if key == "ego" else actor_name])
        tm = np.array([s[0] for s in tr.samples])
        m = t_sim <= tm[-1]
        mx = np.interp(t_sim[m], tm, [s[1] for s in tr.samples])
        my = np.interp(t_sim[m], tm, [s[2] for s in tr.samples])
        e = np.hypot(sim[m, 0] - mx, sim[m, 1] - my)
        out[f"{key}_ade_m"] = float(e.mean())
        out[f"{key}_fde_m"] = float(e[-1])
    return out
