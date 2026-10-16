"""tracks.json + user calibration -> measured bundle -> montecarlo.estimate -> replay JSON.

Used by the Sim Lab "From CCTV" page (viz/lab/app.py) and runnable locally:

    from sim.video.pipeline import run
    out = run(tracks_json, {"calibration": {...}, "ego_track": 3, "lane_width_m": 3.5})
"""
from __future__ import annotations

import numpy as np

from montecarlo.estimate import drivers, estimate
from montecarlo.evidence import ranges_from_bundle
from montecarlo.ranges import N_PARAMS, av_replay_policy, build_scenario, values_from_u
from sim.video.calibrate import calibrate_from_request
from sim.video.trajectories import TrajectoryError, analyse, tracks_from_json
from sim.world import run as sim_run
from viz.export import scenario_meta, trace_json

MAX_N = 20000


def replay_json(bundle: dict, est: dict, analysis: dict, title: str) -> dict:
    """Viewer format of viz/export.py: median sample of the measured ranges, AV vs A vs B."""
    ranges, _ = ranges_from_bundle(bundle)
    v = values_from_u(ranges, np.full(N_PARAMS, 0.5))
    scen = build_scenario(ranges, v)
    facts, labels = drivers()
    placeholder = any("PLACEHOLDER" in l for l in labels.values())
    runs = {"av": trace_json(sim_run(scen, av_replay_policy(ranges, v))),
            **{k: trace_json(sim_run(scen, f())) for k, f in facts.items()}}
    m = analysis["measured"]
    return {
        "scenario": {**scenario_meta(scen), "id": bundle.get("case_id"), "title": title,
                     "label": "from CCTV · placeholder drivers, not R157" if placeholder else "from CCTV",
                     "crash_type": bundle["conflict"]["crash_type"],
                     "notes": (f"Measured from video: AV {m['ego_speed_mps']['value']:.1f} ± {m['ego_speed_mps']['sd']:.1f} m/s, "
                               f"other {m['other_speed_mps']['value']:.1f} ± {m['other_speed_mps']['sd']:.1f} m/s, "
                               f"gap {m['gap_m']['value']:.1f} ± {m['gap_m']['sd']:.1f} m (1 sigma). "
                               "Replay = median of the measured ranges. Triage evidence, not a liability ruling."),
                     "measured": {"ego": analysis["ego"], "other": analysis["other"]}},
        "runs": runs,
        "p_avoid": {k: {"p": d["p_avoid"], "ci90": d["ci90"], "n": d["n_samples"]} for k, d in est["drivers"].items()},
    }


def _track_ids(x) -> list[int]:
    """Track id or list of ids (fragments of one vehicle). Untrusted: ints only, at most 20."""
    if x in (None, "", "auto"):
        return []
    ids = x if isinstance(x, list) else [x]
    if len(ids) > 20:
        raise TrajectoryError("too many track ids")
    return [int(i) for i in ids]


def run(tracks_json: dict, req: dict, map_fn=None, case_id: str = "cctv", video_sha256: str | None = None,
        synthetic: bool = False) -> dict:
    """req: {"calibration": {...}, "ego_track": int|[int], "other_track": int|[int]|None, "lane_width_m": float,
    "crash_type": str|None, "collided": bool|None, "n": int, "seed": int}. Untrusted: validated."""
    calib = calibrate_from_request(req["calibration"])
    tracks = tracks_from_json(tracks_json)
    fps = float(tracks_json["fps"])
    ct = req.get("crash_type") or None
    if ct not in (None, "cut_in", "lead_vehicle_decel"):
        raise TrajectoryError("crash_type must be cut_in or lead_vehicle_decel")
    col = req.get("collided")
    col = None if col in (None, "", "auto") else bool(col)
    a = analyse(tracks, calib, fps, ego_id=_track_ids(req.get("ego_track")), lane_width_m=float(req["lane_width_m"]),
                other_id=_track_ids(req.get("other_track")) or None, crash_type=ct, collided=col,
                case_id=case_id, video_sha256=video_sha256, synthetic=synthetic)
    n = int(min(max(int(req.get("n", 2000)), 100), MAX_N))
    est = estimate(a["bundle"], n=n, seed=int(req.get("seed", 0)), map_fn=map_fn,
                   sensitivity=bool(req.get("sensitivity", True)))
    title = (f"CCTV {a['bundle']['conflict']['crash_type'].replace('_', ' ')}: AV track {a['ego_id']} "
             f"vs track {a['other_id']}")
    return {"analysis": a, "estimate": est, "replay": replay_json(a["bundle"], est, a, title)}
