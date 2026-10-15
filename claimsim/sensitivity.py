"""What drives the exposure, and which evidence would most improve the estimate.

1. One-way (tornado): move one assumption to a low and a high value, re-run on the SAME random draws
   (common random numbers), and record the change in expected net exposure and its 95th percentile.
   The ranges are illustrative perturbations of synthetic parameters, not calibrated uncertainty, and
   one-way analysis misses interactions between inputs.
2. Global (rank correlation): Spearman correlation between each sampled driver and net exposure across
   iterations. It shows association within this model, not causation in the world, and it is only as
   good as the dependence structure assumed in distributions.py.
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from claimsim import distributions as dist
from claimsim.models import ClaimInput, LiabilityScenario
from claimsim.simulation import simulate

EVIDENCE = {
    "repair_severity": "independent engineer's assessment or final repair invoices for both vehicles",
    "injury_probability": "confirmation from the third party whether any injury is claimed (CNF / claims portal)",
    "injury_severity": "medical report and prognosis for each injured claimant",
    "liability_allocation": "vehicle event data (DSSAD), CCTV, dashcam, witness and police evidence on fault",
    "recovery_probability": "the third-party insurer's liability position and the manufacturer's response",
    "legal_expenses": "litigation status, solicitor instructions and cost estimates",
}

# driver -> (low factor, high factor, assumption paths to scale)
ONE_WAY = {
    "repair_severity": (0.8, 1.2, ["repair.median_to_estimate"]),
    "injury_probability": (0.5, 1.5, ["injury.probability_by_severity"]),
    "injury_severity": (0.7, 1.3, ["injury.tiers.0.median", "injury.tiers.1.median", "injury.tiers.2.median",
                                   "injury.known_sigma"]),
    "recovery_probability": (0.7, 1.3, ["recovery.third_party_insurer.probability", "recovery.manufacturer.probability"]),
    "legal_expenses": (0.5, 1.5, ["legal_and_handling.handling_fixed", "legal_and_handling.property_legal_share",
                                  "legal_and_handling.injury_legal_share"]),
}
LIABILITY_SHIFT = 0.1


def _shift(s: LiabilityScenario, delta: float) -> LiabilityScenario:
    """Move `delta` of liability from the third party to the insured vehicle (negative: the other way)."""
    delta = max(-s.insured_vehicle_share, min(delta, s.third_party_share))
    ins = s.insured_vehicle_share
    w_drv = s.insured_driver_share / ins if ins > 0 else 1.0
    return dataclasses.replace(s, insured_driver_share=s.insured_driver_share + delta * w_drv,
                               av_system_share=s.av_system_share + delta * (1 - w_drv),
                               third_party_share=s.third_party_share - delta, probability=None,
                               probability_source=None)


def _scale_claim_recovery(claim: ClaimInput, f: float) -> ClaimInput:
    ch = {}
    for k in ("third_party_recovery_probability", "manufacturer_recovery_probability"):
        v = getattr(claim, k)
        if v is not None:
            ch[k] = min(1.0, v * f)
    return dataclasses.replace(claim, **ch) if ch else claim


def one_way(claim: ClaimInput, scenario: str, assumptions: dist.Assumptions | None = None,
            n: int = 10_000, seed: int = 0) -> list[dict]:
    a = assumptions or dist.load()
    one = dataclasses.replace(claim, scenarios=tuple(s for s in claim.scenarios if s.name == scenario))
    if not one.scenarios:
        raise ValueError(f"unknown scenario {scenario!r}")

    def run(c: ClaimInput, aa: dist.Assumptions) -> tuple[float, float]:
        s = simulate(c, aa, n, seed)["scenarios"][scenario]
        return s["expected_net_exposure"], s["net_exposure_percentiles"]["p95"]

    base_mean, base_p95 = run(one, a)
    rows = []
    for name, (lo, hi, paths) in ONE_WAY.items():
        res = []
        for f in (lo, hi):
            c = _scale_claim_recovery(one, f) if name == "recovery_probability" else one
            res.append(run(c, a.scaled(**{p: f for p in paths})))
        rows.append(_row(name, f"x{lo} / x{hi} on {', '.join(paths)}", base_mean, base_p95, res))
    s0 = one.scenarios[0]
    res = [run(dataclasses.replace(one, scenarios=(_shift(s0, d),)), a) for d in (-LIABILITY_SHIFT, LIABILITY_SHIFT)]
    rows.append(_row("liability_allocation", f"insured vehicle share {-LIABILITY_SHIFT:+.0%} / {LIABILITY_SHIFT:+.0%} "
                     "(moved to/from the third party; a what-if, not an estimate)", base_mean, base_p95, res))
    return sorted(rows, key=lambda r: -abs(r["swing_expected"]))


def _row(name, perturbation, base_mean, base_p95, res) -> dict:
    (m_lo, p_lo), (m_hi, p_hi) = res
    return {"driver": name, "perturbation": perturbation, "base_expected": base_mean,
            "expected_low": m_lo, "expected_high": m_hi, "swing_expected": m_hi - m_lo,
            "p95_low": p_lo, "p95_high": p_hi, "swing_p95": p_hi - p_lo, "evidence_to_collect": EVIDENCE[name]}


def rank_correlation(claim: ClaimInput, scenario: str, assumptions: dist.Assumptions | None = None,
                     n: int = 10_000, seed: int = 0) -> list[dict]:
    r = simulate(claim, assumptions, n, seed, keep_arrays=True)["_arrays"]
    net = r["per_scenario"][scenario]["net_exposure"]
    drivers = dict(r["draws"].drivers)
    drivers["recovery_success_fraction"] = r["per_scenario"][scenario]["recoveries"] / np.maximum(
        r["per_scenario"][scenario]["recoverable.third_party_insurer"]
        + r["per_scenario"][scenario]["recoverable.manufacturer"], 1e-9)
    drivers["legal_and_handling_cost"] = r["per_scenario"][scenario]["legal_and_handling"]
    net_rank = pd.Series(net).rank()
    out = []
    for k, v in drivers.items():
        if np.ptp(v) == 0:
            out.append({"driver": k, "spearman_with_net_exposure": None, "note": "constant in this claim"})
            continue
        out.append({"driver": k, "spearman_with_net_exposure": float(pd.Series(v).rank().corr(net_rank))})
    return sorted(out, key=lambda x: -abs(x["spearman_with_net_exposure"] or 0))
