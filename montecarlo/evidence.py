"""Evidence -> scenario ranges. The INPUT side of the counterfactual (owned by sim).

Takes a crash bundle (the JSON format defined on the `insurance` branch,
insurance/bundle.py, schema 0.1) as a plain dict, and builds a ScenarioRanges
for montecarlo. We read the dict directly so sim does not import insurance code.

Evidence tiers (root CLAUDE.md §3):
  0  report only                      -> wide ranges around the reported conflict
  1  + CCTV / dashcam                 -> measured, narrower ranges
  2  + AV logs (decision log + controls) -> telemetry-grade, narrowest ranges

The half-widths per tier and the priors for facts a bundle does not contain are
DESIGN ASSUMPTIONS (not measured, not from R157). They are named constants here,
tagged `prior` in the ranges, and so lower the data-sufficiency score. A bundle can
override any of them with an explicit `conflict_ranges` block:
  "conflict_ranges": {"gap": {"lo": 8, "hi": 12, "source": "reported"}, ...}
"""
from __future__ import annotations

from sim.vehicle import Geometry

from montecarlo.ranges import ParamRange, ScenarioRanges

G = 9.81

# DESIGN ASSUMPTION: +/- measurement half-width by evidence tier.
TIER_HALF_WIDTH = {
    0: {"speed_mps": 2.5, "gap_m": 4.0},   # narrative / report estimates
    1: {"speed_mps": 1.0, "gap_m": 1.5},   # video-derived trajectories
    2: {"speed_mps": 0.3, "gap_m": 0.5},   # vehicle logs
}
TIER_SOURCE = {0: "narrative", 1: "reported", 2: "reported"}

# DESIGN PRIOR: facts a bundle usually lacks. Tagged "prior".
PRIOR_LATERAL_OFFSET_M = (3.0, 3.7)        # one lane over
PRIOR_CUT_IN_START_S = (0.0, 0.5)          # after conflict t_start
PRIOR_CUT_IN_DURATION_S = (1.0, 2.5)
PRIOR_LEAD_DECEL_MPS2 = (3.0, 7.0)
PRIOR_LEAD_BRAKE_TIME_S = (0.0, 0.5)

# DESIGN ASSUMPTION: generic car geometry when the bundle gives none.
DEFAULT_GEOMETRY = Geometry(length=4.6, width=1.9, wheelbase=2.8)

CRASH_KIND = {"cut_in": "cut_in", "lead_vehicle_decel": "lead_brake",
              "cut_out": "lead_brake", "other": "lead_brake"}


def evidence_tier(bundle: dict) -> int:
    per = bundle.get("perception", {}) or {}
    veh = bundle.get("vehicle", {}) or {}
    ext = bundle.get("external", {}) or {}
    if per.get("decision_log_present") and veh.get("control_inputs"):
        return 2
    if ext.get("cctv"):
        return 1
    return 0


def _around(value: float, half: float, source: str, floor: float = 0.0) -> ParamRange:
    return ParamRange(max(floor, value - half), max(floor, value + half), source=source)


def _av_braking(bundle: dict, t0: float, mu: float) -> tuple[float, float] | None:
    """First system brake input after conflict start -> (time after t0, decel m/s^2).

    DESIGN ASSUMPTION: pedal/brake command 0..1 maps linearly to mu*g.
    """
    for ci in sorted((bundle.get("vehicle", {}) or {}).get("control_inputs", []), key=lambda c: c["t"]):
        if ci.get("source") == "system" and ci.get("brake", 0) > 0 and ci["t"] >= t0:
            return ci["t"] - t0, ci["brake"] * mu * G
    return None


def timeline_check(bundle: dict, tol_s: float = 0.5) -> dict:
    """Does the reported timeline fit the reported kinematics?

    Constant-speed time to close the gap vs (t_crash - t_start). If the vehicle
    would have hit far earlier than the reported crash time (before any braking
    could matter), the bundle contradicts itself: flag it for the claims handler.
    """
    c = bundle["conflict"]
    closing = c["ego_speed_mps"] - c.get("hazard_speed_mps", 0.0)
    reported = bundle.get("t_crash")
    if reported is None or closing <= 0:
        return {"consistent": None, "reason": "no crash time or not closing"}
    t_const = c["gap_m"] / closing
    t_rep = reported - c["t_start"]
    ok = t_rep <= t_const + tol_s or any(
        ci.get("brake", 0) > 0 and c["t_start"] <= ci["t"] <= c["t_start"] + t_const
        for ci in (bundle.get("vehicle", {}) or {}).get("control_inputs", []))
    return {"consistent": ok, "time_to_close_at_constant_speed_s": round(t_const, 2),
            "reported_time_to_crash_s": round(t_rep, 2),
            "reason": None if ok else "reported crash is later than the gap allows and no braking before impact"}


def ranges_from_bundle(bundle: dict, tier: int | None = None, duration: float = 10.0) -> tuple[ScenarioRanges, dict]:
    """Returns (ranges, info). `tier` forces an evidence tier (for the tier 0->1->2 demo)."""
    c = bundle["conflict"]
    tier = evidence_tier(bundle) if tier is None else tier
    hw, src = TIER_HALF_WIDTH[tier], TIER_SOURCE[tier]
    kind = CRASH_KIND.get(c.get("crash_type", "other"), "lead_brake")
    mu = float(c.get("friction_mu", 0.7))

    r: dict[str, ParamRange] = {
        "ego_speed": _around(c["ego_speed_mps"], hw["speed_mps"], src),
        "other_speed": _around(c.get("hazard_speed_mps", 0.0), hw["speed_mps"], src),
        "gap": _around(c["gap_m"], hw["gap_m"], src, floor=0.5),
    }
    if kind == "cut_in":
        r["lateral_offset"] = ParamRange(*PRIOR_LATERAL_OFFSET_M, source="prior")
        r["cut_in_start"] = ParamRange(*PRIOR_CUT_IN_START_S, source="prior")
        r["cut_in_duration"] = ParamRange(*PRIOR_CUT_IN_DURATION_S, source="prior")
    elif c.get("crash_type") == "lead_vehicle_decel":
        r["other_decel"] = ParamRange(*PRIOR_LEAD_DECEL_MPS2, source="prior")
        r["other_brake_time"] = ParamRange(*PRIOR_LEAD_BRAKE_TIME_S, source="prior")
    else:
        # cut_out / other: hazard keeps its reported speed (stationary obstacle if 0).
        r["other_decel"] = ParamRange.point(0.0, source=src)
        r["other_brake_time"] = ParamRange.point(0.0, source=src)

    av = _av_braking(bundle, float(c["t_start"]), mu)
    if av is not None:
        r["av_brake_start"] = ParamRange.point(av[0], source="reported")
        r["av_decel"] = ParamRange.point(av[1], source="reported")

    for name, o in (bundle.get("conflict_ranges") or {}).items():
        r[name] = ParamRange(float(o["lo"]), float(o["hi"]), source=o.get("source", "reported"))

    ranges = ScenarioRanges(kind=kind, ego_geometry=DEFAULT_GEOMETRY, other_geometry=DEFAULT_GEOMETRY,
                            duration=duration, sgo_report_id=bundle.get("case_id"), **r)
    info = {"timeline_check": timeline_check(bundle), "tier": tier, "kind": kind, "crash_type": c.get("crash_type", "other"),
            "av_braking": None if av is None else {"t_after_conflict_s": av[0], "decel_mps2": av[1]},
            "assumptions": [f"tier {tier} half-widths {hw} (design assumption)",
                            "missing facts use labelled priors (design assumption)",
                            "AV brake command 0..1 mapped linearly to mu*g (design assumption)"]}
    return ranges, info
