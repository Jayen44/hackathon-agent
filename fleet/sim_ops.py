"""Thin wrappers over sim/ + montecarlo/ used by the tools (reproduction check, estimate, triage)."""
from __future__ import annotations

from montecarlo import estimate as est
from montecarlo.counterfactual import reproduce_rate
from montecarlo.evidence import ranges_from_bundle
from sim.reproduce import ReportedOutcome

from fleet import insurance_link

REPRO_N = 200


def reproduce(bundle: dict, n: int = REPRO_N, seed: int = 0) -> dict:
    """Does the AV replay over the bundle's ranges reproduce the reported outcome?"""
    ranges, info = ranges_from_bundle(bundle)
    o = bundle.get("outcome", {}) or {}
    if "collided" not in o:
        return {"rate": None, "reproduced_flag": False, "reason": "no reported outcome to reproduce"}
    band = None
    if o.get("impact_speed_mps") is not None:
        s = float(o["impact_speed_mps"])
        band = (max(0.0, s - est.IMPACT_SPEED_BAND_MPS), s + est.IMPACT_SPEED_BAND_MPS)
    rr = reproduce_rate(ranges, None, ReportedOutcome(bool(o["collided"]), None, band), n=n, seed=seed)
    return {"rate": round(rr["rate"], 3), "ci90": [round(x, 3) for x in rr["ci90"]], "n": rr["n"],
            "mismatches": rr["mismatches"], "reproduced_flag": rr["rate"] >= est.REPRODUCED_MIN_RATE,
            "reported": {"collided": bool(o["collided"]), "impact_speed_band_mps": band},
            "ranges": {k: {"lo": round(r.lo, 2), "hi": round(r.hi, 2), "source": r.source}
                       for k, r in ranges.params().items()},
            "timeline_check": info.get("timeline_check"),
            "rule": f"reproduced if >= {est.REPRODUCED_MIN_RATE:.0%} of samples match (design assumption)"}


def make_estimate(map_fn=None, sensitivity: bool = True):
    def f(bundle: dict, tier: int | None = None, n: int = 1000) -> dict:
        return est.estimate(bundle, tier=tier, n=n, map_fn=map_fn, sensitivity=sensitivity)
    return f


def triage_one(bundle: dict, n: int = 60) -> dict:
    """Cheap first pass: small-n P(avoid) x claim value mid. Ranking only, never a price."""
    try:
        r = est.estimate(bundle, n=n, sensitivity=False)
        ps = [d["p_avoid"] for d in r["drivers"].values()]
        p = sum(ps) / len(ps)
    except Exception as e:  # noqa: BLE001
        return {"claim_id": bundle.get("case_id"), "p_avoid_mid": None, "value_gbp": 0.0, "error": str(e)[:200]}
    o = bundle.get("outcome", {}) or {}
    cv = insurance_link.claim_value_mid(o.get("injury_severity"), o.get("paid_claim_gbp"))
    qp = insurance_link.quick_price(bundle, r)
    if qp is not None and qp.get("expected_recovery_mid") is not None:
        value, basis = max(0.0, qp["expected_recovery_mid"]), "engine expected recovery (mid), no debate"
    elif qp is not None:
        # engine cannot price it yet (e.g. multi-track legal cost TODO, liability elsewhere): rank last
        value, basis = 0.0, f"engine: {qp.get('decision')} ({qp.get('reason') or 'not priced'})"
    else:
        value, basis = p * (cv or 0.0), "P(avoid) mid x claim value mid (pricing unavailable)"
    return {"claim_id": bundle.get("case_id"), "p_avoid_mid": round(p, 3), "n": n,
            "claim_value_mid_gbp": cv, "value_gbp": round(value, 0), "basis": basis,
            "engine_decision": None if qp is None else qp.get("decision")}
