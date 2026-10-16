"""100-Car Naturalistic Driving Study (VTTI, 2001-2004, Northern Virginia / Washington DC):
real crash and near-crash time series -> lead-vehicle (rear-end) events for the sim.

Licence (checked 2026-10-15):
- Data: VTTI Dataverse, "100-Car data", doi:10.15787/VTT1/CEU6RB. Dataset API
  (https://dataverse.vtti.vt.edu/api/datasets/:persistentId/?persistentId=doi:10.15787/VTT1/CEU6RB)
  reports license "CC0 1.0" (http://creativecommons.org/publicdomain/zero/1.0), no terms of
  access, no restricted files, fileAccessRequest false. No sign-up, no data-use agreement.
- The Dataverse file store returned HTTP 404 ("Failed to locate and/or open physical file")
  for the time-series files on 2026-10-15, so the files were taken from the CC0 copies that
  github.com/Yiru-Jiao/Reconstruct100CarNDSData (MIT licence, (c) 2024 Yiru Jiao) redistributes
  under RawData/. Only the raw data files were downloaded; none of that repo's code is run.
- Files used: HundredCar_Crash_Public_Compiled.txt, HundredCar_NearCrash_Public_Compiled.txt
  (time series, 30 s before to 10 s after each event), 100CarEventVideoReducedData_v1_5.txt
  (event table, tab separated, no header).

Units (DataDictionary_TimeSeries_v1_2.pdf, VTTI 2010): speed mph (composite speed -1 = not
available), longitudinal accel g (positive = accelerating from a stop), radar range ft,
range rate ft/s (positive = range increasing), azimuth rad (positive = right), 10 Hz.
Event start/end in the event table are `sync` row numbers in the time series.

Privacy: the event table holds driver age, gender and distraction coding. We never load
those columns; only event id, severity, conflict and precipitating-event codes are kept.

Read files with `python -I`; they are data only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

MPH = 0.44704
FT = 0.3048
G = 9.80665

# Event table columns (0-based, tab separated, no header). Names from
# "Researcher Dictionary for Video Reduction Data v1.3" order; only non-personal fields kept.
EVENT_COLS = {0: "event_id", 2: "sync_start", 3: "sync_end", 4: "severity",
              8: "event_nature", 9: "incident_type", 12: "precipitating_event"}

# DESIGN ASSUMPTIONS for picking the lead vehicle out of the radar tracks.
LEAD_MAX_LATERAL_M = 2.0      # |range * sin(azimuth)| at the reference time: same lane
MAX_TRACK_GAP_S = 0.35        # a radar track with a hole longer than this is cut
SEGMENT_S = 0.5               # lead accel profile: piecewise constant per 0.5 s
LEAD_SMOOTH_SAMPLES = 5       # lead speed (ego speed + range rate) moving average, 0.5 s at 10 Hz
# Physical bounds on the fitted lead acceleration: ~0.9 g braking on a dry road, +4 m/s^2
# for a 2000s passenger car. Fitted values outside are radar noise. DESIGN ASSUMPTION.
LEAD_ACCEL_BOUNDS = (-0.9 * 9.80665, 4.0)
PRE_REF_S = 5.0               # scenario starts this long before the reference time
MIN_PRE_REF_S = 2.5           # ... or as far back as the lead track goes, but at least this
POST_REF_S = 2.0              # and runs this long after it
STITCH_DT_S = 2.0             # radar ID hand-over / dropout: earlier track ends at most this before
STITCH_RANGE_M = 2.0          # ... and its predicted range is within this + STITCH_RANGE_PER_S * dt
STITCH_RANGE_PER_S = 1.5     #     (constant range-rate prediction drifts while the lead brakes)
STITCH_LAT_M = 1.0            # ... and lateral position within this


SOURCE_COMMIT = "a9db69192bbc2c9c743b7a8a2d7687671159c0e4"
SOURCE_BASE = f"https://raw.githubusercontent.com/Yiru-Jiao/Reconstruct100CarNDSData/{SOURCE_COMMIT}/RawData/"
# local name -> (file in RawData/, sha256 of the copy used on 2026-10-15)
FILES = {
    "crash.txt": ("HundredCar_Crash_Public_Compiled.txt",
                  "0ac5d7974146afe091cfc06a955b4cb35c52a022d165d70b092eb43325cc1310"),
    "nearcrash.txt": ("HundredCar_NearCrash_Public_Compiled.txt",
                      "64d12c2ef4e2bb463f2de4ffc43a573100430a852b5fa53537790b905511dab4"),
    "events.txt": ("100CarEventVideoReducedData_v1_5.txt",
                   "ad064ebfab1108a202bc44ecb0e905ab8faa097be128681966243d53eb753cc0"),
}


def fetch(dest: str | Path) -> dict:
    """Download the three data files (~97 MB) into an empty data-only folder and check sha256.
    Data only: nothing downloaded is executed or unpacked."""
    import hashlib
    import urllib.parse
    import urllib.request
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    out = {}
    for local, (remote, sha) in FILES.items():
        p = dest / local
        if not p.exists():
            urllib.request.urlretrieve(SOURCE_BASE + urllib.parse.quote(remote), p)
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if h != sha:
            raise ValueError(f"{local}: sha256 {h} != pinned {sha}")
        out[local] = {"path": str(p), "sha256": h}
    return out


def load_event_table(path: str | Path) -> pd.DataFrame:
    rows = []
    with open(path, encoding="latin-1") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 13:
                continue
            rows.append({name: p[i] for i, name in EVENT_COLS.items()})
    df = pd.DataFrame(rows)
    for c in ("event_id", "sync_start", "sync_end"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["event_id"]).astype({"event_id": int}).set_index("event_id")


def is_lead_rear_end(row) -> bool:
    """Lead-vehicle conflict coded as the subject striking the rear of the vehicle ahead, with
    the precipitating event "Other vehicle ahead - ..." (decelerating, slowed and stopped,
    stopped, slower constant speed): the R157 lead-vehicle-deceleration family. Cut-ins
    ("Other vehicle lane change ...") are excluded: the radar track starts mid-manoeuvre."""
    return ("lead vehicle" in str(row["event_nature"]).lower()
            and str(row["incident_type"]).lower().startswith("rear-end, striking")
            and str(row["precipitating_event"]).lower().startswith("other vehicle ahead"))


def load_timeseries(path: str | Path) -> dict[int, pd.DataFrame]:
    df = pd.read_csv(path, low_memory=False, na_values=["."])
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = pd.to_numeric(df[c].astype(str).str.strip().str.strip('"'), errors="coerce")
    return {int(k): g.sort_values("sync").reset_index(drop=True) for k, g in df.groupby("trip_id")}


@dataclass
class LeadEvent:
    """One lead-vehicle event, all SI, t = 0 at the scenario start (t_ref - PRE_REF_S)."""
    event_id: int
    severity: str                       # "Crash" | "Near-Crash"
    precipitating_event: str
    t: np.ndarray                       # sample times (s), from 0
    ego_v: np.ndarray                   # m/s
    ego_a: np.ndarray                   # m/s^2 (bias corrected so it integrates to ego_v)
    gap: np.ndarray                     # m, radar range (NaN where the lead is not tracked)
    lead_v: np.ndarray                  # m/s, ego_v + range_rate (NaN where not tracked)
    t_ref: float                        # reference time (min radar range) from start
    min_gap_m: float
    ego_brake: np.ndarray | None = None  # 1 = brake pedal switch on (NaN-free; see extract)
    meta: dict = field(default_factory=dict)

    @property
    def initial(self) -> dict:
        return {"ego_speed": float(self.ego_v[0]), "lead_speed": float(self.lead_v[0]),
                "gap": float(self.gap[0])}


def _piecewise(t: np.ndarray, y: np.ndarray, seg: float, t_end: float) -> list[tuple[float, float]]:
    """Least-squares slope of y(t) per `seg`-long window -> [(t_start, slope)]."""
    out = []
    t0 = 0.0
    while t0 < t_end - 1e-9:
        m = (t >= t0) & (t < t0 + seg) & np.isfinite(y)
        if m.sum() >= 3 and np.ptp(t[m]) > 0:
            slope = float(np.polyfit(t[m], y[m], 1)[0])
        else:
            slope = out[-1][1] if out else 0.0
        out.append((round(t0, 6), slope))
        t0 += seg
    return out


def ego_accel_profile(ev: LeadEvent, seg: float = 0.1) -> list[tuple[float, float]]:
    """Recorded human ego acceleration, piecewise constant per `seg` s (from the bias-corrected
    accelerometer)."""
    out = []
    t0 = 0.0
    while t0 < ev.t[-1] - 1e-9:
        m = (ev.t >= t0) & (ev.t < t0 + seg)
        a = float(np.nanmean(ev.ego_a[m])) if m.any() else (out[-1][1] if out else 0.0)
        out.append((round(t0, 6), a))
        t0 += seg
    return out


def _smooth(y: np.ndarray, k: int) -> np.ndarray:
    """Centred moving average over finite samples (NaN stays NaN)."""
    out = np.full(len(y), np.nan)
    h = k // 2
    for i in range(len(y)):
        if np.isfinite(y[i]):
            w = y[max(0, i - h): i + h + 1]
            out[i] = np.nanmean(w)
    return out


def lead_accel_profile(ev: LeadEvent, seg: float = SEGMENT_S) -> list[tuple[float, float]]:
    """Lead acceleration, piecewise constant per `seg` s, fitted to the radar-derived lead speed
    (smoothed over LEAD_SMOOTH_SAMPLES, clipped to LEAD_ACCEL_BOUNDS). After the radar track
    ends the lead holds its last speed (accel 0). All DESIGN ASSUMPTIONS, see constants."""
    good = np.isfinite(ev.lead_v)
    t_last = float(ev.t[good][-1]) if good.any() else 0.0
    v = _smooth(ev.lead_v, LEAD_SMOOTH_SAMPLES)
    lo, hi = LEAD_ACCEL_BOUNDS
    prof = [(t0, float(np.clip(a, lo, hi))) for t0, a in _piecewise(ev.t, v, seg, max(seg, t_last))]
    # A stopped vehicle does not reverse: the sim clamps speed at 0, so negative accel is harmless.
    t_end = prof[-1][0] + seg if prof else 0.0
    return prof + [(round(t_end, 6), 0.0)]


def _ego_speed(df: pd.DataFrame) -> np.ndarray:
    v = df["speed_vehicle_composite"].to_numpy(float)
    gps = df["speed_gps_horizontal"].to_numpy(float)
    v = np.where(v >= 0, v, np.nan)
    v = np.where(np.isfinite(v), v, np.where(gps >= 0, gps, np.nan))
    t = df["time"].to_numpy(float)
    ok = np.isfinite(v)
    if ok.sum() < 2:
        return np.full(len(t), np.nan)
    return np.interp(t, t[ok], v[ok]) * MPH


def _tracks(df: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """Forward radar targets as {id: frame(time, range_m, rate_mps, az)} (ids reused -> split)."""
    rows = []
    t = df["time"].to_numpy(float)
    for k in range(1, 8):
        ids = df[f"radar_forward_ID_{k}"].to_numpy(float)
        rng = df[f"radar_forward_range_{k}"].to_numpy(float)
        rr = df[f"radar_forward_range_rate_{k}"].to_numpy(float)
        az = df[f"radar_forward_azimuth_{k}"].to_numpy(float)
        m = (ids > 0) & np.isfinite(rng) & (rng > 0)
        rows.append(pd.DataFrame({"time": t[m], "id": ids[m].astype(int), "range_m": rng[m] * FT,
                                  "rate_mps": rr[m] * FT, "az": az[m]}))
    allr = pd.concat(rows).sort_values("time")
    out: dict[int, pd.DataFrame] = {}
    key = 0
    for _, g in allr.groupby("id"):
        g = g.drop_duplicates("time")
        cut = np.r_[0, np.where(np.diff(g["time"].to_numpy()) > MAX_TRACK_GAP_S)[0] + 1, len(g)]
        for a, b in zip(cut[:-1], cut[1:]):
            if b - a >= 5:
                out[key] = g.iloc[a:b].reset_index(drop=True)
                key += 1
    return out


def _stitch_back(tr: pd.DataFrame, key: int, tracks: dict[int, pd.DataFrame]) -> tuple[pd.DataFrame, int]:
    """The radar re-labels targets; prepend earlier tracks that end just before this one starts
    and continue it in range (constant range-rate prediction) and lateral position.
    DESIGN ASSUMPTION: same vehicle if the hand-over is within STITCH_DT_S and STITCH_RANGE_M."""
    n = 0
    used = {key}
    while True:
        t_s, r_s = tr["time"].iloc[0], tr["range_m"].iloc[0]
        lat_s = r_s * math.sin(tr["az"].iloc[0])
        cand = None
        for k, o in tracks.items():
            if k in used:
                continue
            t_e = o["time"].iloc[-1]
            if not (0 < t_s - t_e <= STITCH_DT_S or (t_e >= t_s and o["time"].iloc[0] < t_s)):
                continue
            # predicted range of the earlier track at the start of this one
            j = o["time"].searchsorted(t_s) - 1 if t_e >= t_s else len(o) - 1
            if j < 0:
                continue
            pr = o["range_m"].iloc[j] + o["rate_mps"].iloc[j] * (t_s - o["time"].iloc[j])
            lat = o["range_m"].iloc[j] * math.sin(o["az"].iloc[j])
            err = abs(pr - r_s)
            if err < STITCH_RANGE_M + STITCH_RANGE_PER_S * max(0.0, t_s - o["time"].iloc[j]) and abs(lat - lat_s) < STITCH_LAT_M and (cand is None or err < cand[0]):
                cand = (err, k, o[o["time"] < t_s])
        if cand is None or cand[2].empty:
            return tr, n
        used.add(cand[1])
        tr = pd.concat([cand[2], tr]).reset_index(drop=True)
        n += 1


def extract_lead_event(df: pd.DataFrame, row, event_id: int, pre_s: float = PRE_REF_S,
                       post_s: float = POST_REF_S, min_pre_s: float = MIN_PRE_REF_S) -> tuple[LeadEvent | None, str]:
    """Pick the in-lane forward radar track closest during the coded event window, set the
    reference time at its minimum range, and cut [t_ref - pre, t_ref + post_s], where
    pre = pre_s if the (stitched) lead track reaches that far back, else as far as it goes
    (at least min_pre_s). Returns (event, "") or (None, reason)."""
    t = df["time"].to_numpy(float)
    sync = df["sync"].to_numpy(float)
    in_ev = (sync >= row["sync_start"]) & (sync <= row["sync_end"])
    if not in_ev.any():
        return None, "event window not in time series"
    t_ev0, t_ev1 = t[in_ev][0], t[in_ev][-1]
    ego_v = _ego_speed(df)
    if not np.isfinite(ego_v).all():
        return None, "no ego speed"

    best = None
    for k, tr in _tracks(df).items():
        lat = np.abs(tr["range_m"] * np.sin(tr["az"]))
        m = (tr["time"] >= t_ev0 - 1.0) & (tr["time"] <= t_ev1 + 1.0) & (lat < LEAD_MAX_LATERAL_M)
        if not m.any():
            continue
        i = tr.loc[m, "range_m"].idxmin()
        if best is None or tr.loc[i, "range_m"] < best[1]:
            best = (k, tr.loc[i, "range_m"], tr.loc[i, "time"], tr)
    if best is None:
        return None, "no in-lane forward radar target during the event"
    k_best, min_rng, t_ref, tr = best
    tr, n_stitched = _stitch_back(tr, k_best, _tracks(df))
    avail = t_ref - tr["time"].iloc[0]
    if avail < min_pre_s - 1e-6:
        return None, f"lead track starts only {avail:.1f} s before min range (< {min_pre_s} s)"
    pre = min(pre_s, avail)
    t0 = t_ref - pre
    if t0 < t[0] or t_ref + post_s > t[-1] + 0.05:
        return None, "window outside time series"

    w = (t >= t0 - 1e-9) & (t <= t_ref + post_s + 1e-9)
    tw = t[w] - t0
    v = ego_v[w]
    a_raw = pd.to_numeric(df["longitudinal_accel"], errors="coerce").to_numpy(float)[w] * G
    ok = np.isfinite(a_raw)
    if ok.sum() < 0.8 * len(a_raw):
        return None, "longitudinal accel missing"
    a = np.interp(tw, tw[ok], a_raw[ok])
    # Accelerometer bias (mounting, grade): remove the constant offset so that the integrated
    # accel matches the measured speed change over the window. DESIGN ASSUMPTION.
    dur = tw[-1] - tw[0]
    integ = float(np.trapezoid(a, tw))
    a = a - (integ - (v[-1] - v[0])) / dur

    trt = tr["time"].to_numpy() - t0
    gap = np.interp(tw, trt, tr["range_m"].to_numpy(), left=np.nan, right=np.nan)
    rate = np.interp(tw, trt, tr["rate_mps"].to_numpy(), left=np.nan, right=np.nan)
    if not np.isfinite(gap[0]):
        gap[0] = float(tr["range_m"].iloc[np.argmin(np.abs(trt))])
        rate[0] = float(tr["rate_mps"].iloc[np.argmin(np.abs(trt))])
    lead_v = np.maximum(0.0, v + rate)
    brk = pd.to_numeric(df["brake_on_off"], errors="coerce").to_numpy(float)[w]
    # Brake switch missing -> infer "on" from decel stronger than 1 m/s^2 (DESIGN ASSUMPTION).
    brk = np.where(np.isfinite(brk), brk > 0, a < -1.0).astype(float)
    return LeadEvent(event_id=event_id, severity=str(row["severity"]),
                     precipitating_event=str(row["precipitating_event"]), t=tw, ego_v=v, ego_a=a,
                     gap=gap, lead_v=lead_v, t_ref=float(t_ref - t0), min_gap_m=float(min_rng), ego_brake=brk,
                     meta={"track_samples": int(len(tr)), "stitched_tracks": n_stitched, "pre_s": round(pre, 2),
                           "accel_bias_mps2": round((integ - (v[-1] - v[0])) / dur, 3),
                           "track_end_s": round(float(trt[-1]), 2)}), ""
