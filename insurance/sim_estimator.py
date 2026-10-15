"""Careful-driver counterfactual from the sim: one call per bundle, A and B as separate estimators.

    run = run_sim(bundle)             # montecarlo.estimate on the bundle's raw dict (UN R157 Annex 3 models A and B)
    run.estimators                    # {"careful_a": FixedEstimator, "careful_b": FixedEstimator} for bridge / engine
    run.reproduced                    # the sim's own reconstruction check (replaces a hand-set flag)

Results are cached per (bundle, n, tier): the sim costs about 3 s per claim at n=100.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from insurance import sim_link
from insurance.bundle import CrashBundle
from insurance.counterfactual import CounterfactualResult, FixedEstimator


@dataclass
class SimRun:
    case_id: str
    tier: int
    estimators: dict[str, FixedEstimator]
    reproduced: bool | None                 # None when the bundle has no reported outcome to reproduce
    reproduction: dict | None = None
    data_sufficiency: object = None
    top_sensitivity: dict | None = None
    timeline: dict | None = None            # sim's check that the reported timeline fits the reported kinematics
    source: dict = field(default_factory=dict)


_cache: dict = {}


def result_from_sim(d: dict) -> CounterfactualResult:
    return CounterfactualResult(
        p_avoid=d["p_avoid"], avoids_at_p5=d.get("avoids_at_p5"), avoids_at_p50=bool(d["avoids_at_p50"]),
        avoids_at_p95=d.get("avoids_at_p95"), median_impact_speed_mps=float(d["median_impact_speed_mps"]),
        n_samples=int(d["n_samples"]), model=d["model"], notes=list(d.get("notes", [])))


def run_sim(b: CrashBundle, n: int = 300, tier: int | None = None, sensitivity: bool = False) -> SimRun:
    if b.conflict is None or b.raw is None:
        raise ValueError("the sim needs a reconstructed conflict and the bundle's raw dict")
    key = (b.case_id, json.dumps(b.raw, sort_keys=True, default=str), n, tier, sensitivity)
    if key not in _cache:
        res = sim_link.load_estimate()(b.raw, tier=tier, n=n, sensitivity=sensitivity)
        rep = res.get("reproduction")
        _cache[key] = SimRun(
            case_id=b.case_id, tier=res["evidence_tier"],
            estimators={k: FixedEstimator(result_from_sim(d)) for k, d in res["drivers"].items()},
            reproduced=None if rep is None else bool(rep["reproduced_flag"]), reproduction=rep,
            data_sufficiency=res.get("data_sufficiency"), top_sensitivity=res.get("top_sensitivity"),
            timeline=sim_link.timeline_check(b.raw), source=sim_link.source_info())
    return _cache[key]
