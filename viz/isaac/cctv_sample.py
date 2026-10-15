"""Synthetic CCTV cut-in -> rear-end clip with KNOWN ground truth (Isaac render input + truth file).

    python -m viz.isaac.cctv_sample      # writes samples/cctv_cut_in_trace.json + samples/cctv_cut_in_truth.json

SYNTHETIC, ILLUSTRATIVE ONLY. Hand-built scenario, not a real crash; the AV braking profile is
illustrative, not from an SGO report. Pre-impact motion comes from sim/world.run (2D kinematic).
After the impact sim/ stops; the post-impact roll-out (speed exchange + braking to rest) is a
simple illustrative extension so the clip shows the vehicles stopping. It is NOT simulated and
is flagged in the trace meta and the truth file. Never use post-impact numbers as evidence.

The truth file is the answer key for the CCTV page: the camera used by render_trace.py
(--camera cctv) is assets.CCTV, so the calibration clicks below are exact projections.
"""
from __future__ import annotations

import json
import math
import pathlib
from dataclasses import asdict

from sim.policies.av_replay import AVReplayPolicy
from sim.scenario import LateralManoeuvre, ScriptedActor, SimScenario
from sim.vehicle import Geometry, VehicleState
from sim.world import run

from viz.isaac import assets as A
from viz.isaac.export_trace import export, write

OUT = pathlib.Path(__file__).parent / "samples"
NAME = "cctv_cut_in"

LANE_W = 3.5
LANE_CENTRES = [-LANE_W, 0.0, LANE_W]          # 3 lanes; AV in the middle lane
DASH_PERIOD, DASH_L = 12.0, 3.0                  # render_trace.py lane-line dashes start at x = 12 k
CAR = Geometry(length=4.5, width=1.8, wheelbase=2.7)

# Scenario (hand-built, illustrative)
EGO_V = 15.5            # m/s  (55.8 km/h)
OTHER_V = 9.0           # m/s  (32.4 km/h)
CUT_START = 3.2         # s, cutter starts its lane change
CUT_DUR = 2.0           # s
GAP_AT_CUT = 14.0       # m, bumper to bumper at CUT_START
AV_PROFILE = [(0.0, 0.0), (4.6, -2.5)]   # illustrative late, soft braking (not from a report)
DURATION = 9.6          # s total clip
DT = 0.02

# Post-impact roll-out (ILLUSTRATIVE, not simulated): equal masses, restitution E, then both brake.
RESTITUTION = 0.3
POST_DECEL = 6.0        # m/s^2

# Calibration rectangle on the AV lane lines (y = -1.75 and +1.75), dash ends at x = 72 and 96.
CAL_X_NEAR, CAL_X_FAR = 96.0, 72.0     # camera looks back down the road: larger x is nearer the camera


def scenario() -> SimScenario:
    x_cut = CAR.length + GAP_AT_CUT + (EGO_V - OTHER_V) * CUT_START
    cutter = ScriptedActor("cutter", CAR, VehicleState(x_cut, LANE_W, 0.0, OTHER_V),
                           lateral=LateralManoeuvre(CUT_START, CUT_DUR, LANE_W, 0.0))
    # Background traffic in the nearside lane; clears the camera before the cut-in.
    traffic = ScriptedActor("traffic", CAR, VehicleState(70.0, -LANE_W, 0.0, 16.0))
    return SimScenario(CAR, VehicleState(0.0, 0.0, 0.0, EGO_V), [cutter, traffic], duration=DURATION, dt=DT)


def _extend_post_impact(trace: dict, t_end: float, dt: float, hit: str) -> int:
    """Append an illustrative roll-out after the collision step. Returns the impact index."""
    i_imp = len(trace["t"]) - 1
    e = list(trace["ego"][i_imp])
    o = list(trace[hit][i_imp])
    dv = e[3] - o[3]
    e[3] -= (1 + RESTITUTION) / 2 * dv
    o[3] += (1 + RESTITUTION) / 2 * dv
    others = {k: list(v[i_imp]) for k, v in trace.items() if k not in ("t", "ego", hit)}
    n_extra = int(round((t_end - trace["t"][i_imp]) / dt))
    for k in range(1, n_extra + 1):
        for s in (e, o):
            s[0] += s[3] * dt
            s[3] = max(0.0, s[3] - POST_DECEL * dt)
            s[2] = 0.0
        for s in others.values():
            s[0] += s[3] * math.cos(s[2]) * dt
        trace["t"].append(trace["t"][i_imp] + k * dt)
        trace["ego"].append(tuple(e))
        trace[hit].append(tuple(o))
        for name, s in others.items():
            trace[name].append(tuple(s))
    return i_imp


def calibration_world() -> list[tuple[float, float, float]]:
    """A, B along the right lane line (A near camera, B far), C across from B, D across from A."""
    yr, yl = -LANE_W / 2, LANE_W / 2
    return [(CAL_X_NEAR, yr, 0.0), (CAL_X_FAR, yr, 0.0), (CAL_X_FAR, yl, 0.0), (CAL_X_NEAR, yl, 0.0)]


def calibration_clicks(cam: "A.CctvCamera") -> list[list[float]]:
    return [[round(u, 2), round(v, 2)] for u, v, _ in (cam.project(p) for p in calibration_world())]


def build(cam: "A.CctvCamera" = A.CCTV, fps: int = 25):
    scen = scenario()
    res = run(scen, AVReplayPolicy(AV_PROFILE))
    assert res.collided and res.other_actor == "cutter", "sample must end in a rear-end on the cutter"
    i_imp = _extend_post_impact(res.trace, DURATION, DT, res.other_actor)
    label = "SYNTHETIC CCTV sample: hand-built cut-in, illustrative AV braking (not a real crash)"
    doc = export(res, scen, NAME, policy="av_replay (late, soft braking; illustrative)", label=label,
                 lane_width=LANE_W, lane_centres=LANE_CENTRES)
    doc["meta"]["post_impact"] = (f"from t={res.t_collision:.2f} s: illustrative roll-out (restitution "
                                  f"{RESTITUTION}, {POST_DECEL} m/s^2 braking), NOT simulated by sim/")
    doc["meta"]["synthetic"] = True
    doc["cctv_camera"] = asdict(cam)
    doc["dash"] = {"period_m": DASH_PERIOD, "length_m": DASH_L, "phase_m": 0.0}

    t = doc["t"]
    ego, oth = doc["actors"]["ego"]["states"], doc["actors"]["cutter"]["states"]
    step = int(round(1 / fps / DT))
    samples = [{"t": round(t[i], 3), "ego_mps": round(ego[i][3], 3), "other_mps": round(oth[i][3], 3),
                "ego_kmh": round(ego[i][3] * 3.6, 2), "other_kmh": round(oth[i][3] * 3.6, 2),
                "ego_xy": [round(ego[i][0], 3), round(ego[i][1], 3)],
                "other_xy": [round(oth[i][0], 3), round(oth[i][1], 3)],
                "post_impact_illustrative": i > i_imp}
               for i in range(0, len(t), step)]
    i_cut = int(round(CUT_START / DT))
    gap_cut = oth[i_cut][0] - ego[i_cut][0] - CAR.length
    # Moment the cutter's body first crosses the lane line (|y| < 1.75 + width/2 ... body edge on the line)
    i_cross = next(i for i in range(len(t)) if oth[i][1] - CAR.width / 2 <= LANE_W / 2)
    gap_cross = oth[i_cross][0] - ego[i_cross][0] - CAR.length
    clicks = calibration_clicks(cam)
    scale720 = 1280 / cam.width
    truth = {
        "name": NAME, "synthetic": True, "fps": fps,
        "video": f"{NAME}_trace.mp4", "resolution": [cam.width, cam.height],
        "note": ("SYNTHETIC render of a hand-built 2D sim trace (viz/isaac/cctv_sample.py). Not real footage, "
                 "not a real crash. Post-impact motion is illustrative, not simulated."),
        "camera": {**asdict(cam), "fx_px": cam.fx, "cx_px": cam.width / 2, "cy_px": cam.height / 2,
                   "model": "pinhole, no distortion, square pixels; yaw from +x towards +y, pitch below horizontal"},
        "calibration": {
            "mode": "rectangle", "img_pts": clicks, "length_m": CAL_X_NEAR - CAL_X_FAR, "width_m": LANE_W,
            "img_pts_1280x720": [[round(u * scale720, 2), round(v * scale720, 2)] for u, v in clicks],
            "world_pts_sim_frame": [list(p[:2]) for p in calibration_world()],
            "note": ("click order A, B, C, D: A = near end on the camera-side (right) lane line of the middle lane, "
                     "B = far end on the same line, C = across from B on the far-side lane line, D = across from A. "
                     "Each point is the end of a 3 m dash FARTHER from the camera (dashes run x = 12k..12k+3 m), centre of the 0.12 m line. "
                     f"L = {CAL_X_NEAR - CAL_X_FAR:.0f} m (two 12 m dash periods), W = {LANE_W} m line centre to line centre."),
        },
        "truth": {
            "crash_type": "cut_in", "collided": True, "impact_type": res.impact_type,
            "ego_speed_mps": EGO_V, "ego_speed_kmh": round(EGO_V * 3.6, 2),
            "other_speed_mps": OTHER_V, "other_speed_kmh": round(OTHER_V * 3.6, 2),
            "cut_in_start_s": CUT_START, "cut_in_duration_s": CUT_DUR, "lateral_offset_m": LANE_W,
            "gap_at_cut_in_start_m": round(gap_cut, 3),
            "gap_when_cutter_reaches_lane_line_m": round(gap_cross, 3), "t_cutter_reaches_lane_line_s": round(t[i_cross], 3),
            "av_brake_start_s": AV_PROFILE[-1][0], "av_decel_mps2": -AV_PROFILE[-1][1],
            "av_brake_start_after_cut_in_s": round(AV_PROFILE[-1][0] - CUT_START, 3),
            "impact_t_s": round(res.t_collision, 3),
            "ego_speed_at_impact_mps": round(res.ego_speed_at_impact, 3),
            "ego_speed_at_impact_kmh": round(res.ego_speed_at_impact * 3.6, 2),
            "other_speed_at_impact_mps": round(oth[i_imp][3], 3),
            "relative_speed_at_impact_mps": round(res.relative_speed_at_impact, 3),
            "relative_speed_at_impact_kmh": round(res.relative_speed_at_impact * 3.6, 2),
            "impact_xy_ego_centre": [round(ego[i_imp][0], 3), round(ego[i_imp][1], 3)],
            "post_impact": doc["meta"]["post_impact"],
            "vehicle_length_m": CAR.length, "vehicle_width_m": CAR.width,
            "background_vehicle": "track 'traffic' in the nearside lane at 16 m/s, not involved",
        },
        "speeds": samples,
    }
    return doc, truth


def main() -> None:
    doc, truth = build()
    p1 = write(doc, OUT / f"{NAME}_trace.json")
    p2 = OUT / f"{NAME}_truth.json"
    p2.write_text(json.dumps(truth, indent=1))
    tr = truth["truth"]
    print(f"{p1}\n{p2}\nimpact t={tr['impact_t_s']} s ego {tr['ego_speed_at_impact_kmh']} km/h "
          f"rel {tr['relative_speed_at_impact_kmh']} km/h; clicks {truth['calibration']['img_pts']}")


if __name__ == "__main__":
    main()
