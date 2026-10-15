"""One call from crash bundle to counterfactual result: the sim -> insurance hand-off.

    from montecarlo.estimate import estimate
    res = estimate(bundle_dict)                     # local
    res = estimate(bundle_dict, map_fn=modal_map)   # fan out on Modal

    python -m montecarlo.estimate path/to/bundle.json [--tier 0|1|2] [--n 2000]

Per driver it returns the fields of insurance.counterfactual.CounterfactualResult
(p_avoid, avoids_at_p50, median_impact_speed_mps, n_samples, model, notes) plus
ci90. avoids_at_p5/p95 are None: with several uncertain inputs there is no single
"fast/slow driver" axis, so we report the CI instead.
"""
from __future__ import annotations

import functools
import json
import sys

import numpy as np

from sim.policies import careful_a, careful_b
from sim.policies.careful_base import DriverParams, ParamsMissing, ReactiveBrakingDriver
from sim.reproduce import ReportedOutcome
from sim.world import run

from montecarlo.counterfactual import compare, reproduce_rate
from montecarlo.evidence import ranges_from_bundle
from montecarlo.ranges import (PARAM_NAMES, av_replay_policy, build_scenario, data_sufficiency,
                               values_from_u)
from montecarlo.sensitivity import tornado

# PLACEHOLDER drivers, used only while R157 PARAMS are missing. NOT R157 values;
# every result says so. Same structure as the R157 A/B bracket (B reacts slower).
PLACEHOLDER = {
    "careful_a": DriverParams(reaction_time=0.75, max_decel=7.0, jerk=20.0, ttc_threshold=3.0,
                              lateral_margin=0.3, lead_decel_threshold=2.0),
    "careful_b": DriverParams(reaction_time=1.5, max_decel=7.0, jerk=20.0, ttc_threshold=3.0,
                              lateral_margin=0.3, lead_decel_threshold=2.0),
}
# DESIGN ASSUMPTION: reported impact speed reproduced if sim is within this band.
IMPACT_SPEED_BAND_MPS = 2.0
REPRODUCED_MIN_RATE = 0.5


def drivers() -> tuple[dict, dict[str, str]]:
    """Real R157 policies where available, else labelled placeholders."""
    facts, labels = {}, {}
    for name, mod in (("careful_a", careful_a), ("careful_b", careful_b)):
        try:
            mod.make_policy()
            facts[name] = mod.make_policy
            labels[name] = mod.NAME
        except ParamsMissing:
            facts[name] = functools.partial(ReactiveBrakingDriver, PLACEHOLDER[name])
            labels[name] = f"{name} PLACEHOLDER (not R157)"
    return facts, labels


def _replay_json(res) -> dict:
    return {"t": res.trace["t"][::2], "ego": res.trace["ego"][::2], "other": res.trace["other"][::2],
            "result": {"collided": res.collided, "t_collision": res.t_collision, "impact_type": res.impact_type,
                       "ego_speed_at_impact": res.ego_speed_at_impact, "ended_closing": res.ended_closing}}


def estimate(bundle: dict, tier: int | None = None, n: int = 2000, seed: int = 0, map_fn=None,
             sensitivity: bool = True, replays: bool = False) -> dict:
    ranges, info = ranges_from_bundle(bundle, tier=tier)
    facts, labels = drivers()
    mc = compare(ranges, facts, n, seed, map_fn=map_fn)

    v_med = values_from_u(ranges, np.full(len(PARAM_NAMES), 0.5))
    scen = build_scenario(ranges, v_med)
    med = {k: run(scen, f()) for k, f in facts.items()}

    out_drivers = {}
    for k, d in mc["drivers"].items():
        m = med[k]
        out_drivers[k] = {
            "p_avoid": d["p"], "ci90": list(d["ci90"]), "n_samples": d["n"],
            "avoids_at_p5": None, "avoids_at_p50": not (m.collided or m.ended_closing), "avoids_at_p95": None,
            "median_impact_speed_mps": m.relative_speed_at_impact if m.collided else 0.0,
            "model": labels[k],
            "notes": [f"evidence tier {info['tier']}", "avoids_at_p50 = all ranges at their median",
                      "runs ending still closing on the hazard count as not avoided"],
        }

    o = bundle.get("outcome", {}) or {}
    rep = None
    if "collided" in o:
        band = None
        if o.get("impact_speed_mps") is not None:
            s = float(o["impact_speed_mps"])
            band = (max(0.0, s - IMPACT_SPEED_BAND_MPS), s + IMPACT_SPEED_BAND_MPS)
        rr = reproduce_rate(ranges, None, ReportedOutcome(bool(o["collided"]), None, band),
                            n=min(n, 400), seed=seed)
        rep = {**rr, "ci90": list(rr["ci90"]), "reproduced_flag": rr["rate"] >= REPRODUCED_MIN_RATE}

    res = {
        "case_id": bundle.get("case_id"), "synthetic": bundle.get("synthetic"),
        "evidence_tier": info["tier"], "scenario_type": info["crash_type"], "sim_kind": info["kind"],
        "drivers": out_drivers, "paired": mc.get("paired"),
        "reproduction": rep,
        "data_sufficiency": data_sufficiency(ranges),
        "ranges": {k: {"lo": r.lo, "hi": r.hi, "source": r.source} for k, r in ranges.params().items()},
        "assumptions": info["assumptions"],
        "disclaimer": "Triage evidence for a human claims handler, not a liability ruling or legal advice.",
    }
    if sensitivity:
        t = tornado(ranges, facts, n=min(n, 500), seed=seed, map_fn=map_fn)
        res["top_sensitivity"] = ({"param": t["rows"][0]["param"], "swing_in_p_avoid": t["rows"][0]["swing"]}
                                  if t["rows"] else None)
        res["go_get"] = t["go_get"]
    if replays:
        res["replays"] = {"av": _replay_json(run(scen, av_replay_policy(ranges, v_med))),
                          **{k: _replay_json(m) for k, m in med.items()}}
    return res


def by_tier(bundle: dict, **kw) -> dict:
    """Same crash at evidence tiers 0, 1, 2: the CI should narrow (rubric C4)."""
    return {t: estimate(bundle, tier=t, sensitivity=False, **kw) for t in (0, 1, 2)}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("--tier", type=int, default=None)
    ap.add_argument("--n", type=int, default=2000)
    a = ap.parse_args()
    with open(a.bundle) as f:
        b = json.load(f)
    json.dump(estimate(b, tier=a.tier, n=a.n), sys.stdout, indent=2, default=float)
    print()
