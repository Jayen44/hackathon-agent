"""One entry point for callers that already hold a claim as a dict (the fleet orchestrator, the dashboard, scripts).

    from insurance.api import price_claim
    out = price_claim(bundle_dict)                                  # runs the sim itself
    out = price_claim(bundle_dict, drivers=sim_result["drivers"],   # or reuse a sim result the caller already has
                      reproduced=True, debate=True, debate_client=None)

It does everything `fleet.insurance_link.price_and_debate` did, with our own code, and fixes two gaps:
  * the debate is priced from the SAME avoidance numbers as the main result (including legal.p_liable_to_victim),
  * the result carries our canonical `outcome` (insurance/vocab.py), next steps, sign-off roles and the limitation deadline,
    so callers do not invent their own decision labels. `evidence_requests` is derived from the steps in code.
All GBP figures and probabilities come from finance/; this function adds no numbers.
"""
from __future__ import annotations

import dataclasses
from datetime import date

from insurance.bridge import assess_bundle, claim_facts, to_avoidance_result
from insurance.bundle import BundleError, load_bundle
from insurance.counterfactual import FixedEstimator
from insurance.resolution import resolve
from insurance.sim_estimator import result_from_sim

DISCLAIMER = ("Triage evidence for a human claims handler, not a liability ruling or legal advice. "
              "Simulation-based, with stated assumptions and a sim-to-real gap.")
_EVIDENCE_WHO = ("engineer",)          # steps owned by the engineer ask for logs or analysis: surface them as evidence requests


def _steps(x) -> list[dict]:
    return [dataclasses.asdict(s) for s in x.next_steps]


def price_claim(bundle: dict, drivers: dict | None = None, reproduced: bool | None = None, *, debate: bool = False,
                debate_client=None, min_net_gbp: float = 0.0, today: date | None = None) -> dict:
    try:
        b = load_bundle(bundle)
    except BundleError as e:
        return {"available": True, "priced": False, "outcome": "NEEDS_INPUTS",
                "reason": f"bundle rejected by insurance schema: {e}", "disclaimer": DISCLAIMER}
    estimators = None
    if drivers is not None:
        estimators = {k: FixedEstimator(result_from_sim(d)) for k, d in drivers.items()}
    ba = assess_bundle(b, estimators=estimators, reproduced=reproduced, min_net_gbp=min_net_gbp, today=today)
    x = resolve(ba, b)
    v = ba.verdict
    out = {
        "available": True, "case_id": b.case_id, "disclaimer": DISCLAIMER,
        "liability": {"liable": v.liable, "confidence": v.confidence, "summary": v.summary,
                      "evidence_missing": list(v.evidence_missing)},
        "outcome": x.outcome, "headline": x.headline, "next_steps": _steps(x), "sign_off": list(x.sign_off),
        "evidence_requests": [{"item": s.action, "why": f"unblocks {s.unblocks}"} for s in x.next_steps
                              if s.who in _EVIDENCE_WHO][:5],
        "deadline": None if ba.deadline is None else {"due": ba.deadline.due.isoformat(), "days_left": ba.deadline.days_left,
                                                      "route": ba.deadline.route},
        "notes": list(ba.notes), "provenance": ba.provenance, "priced": ba.recovery is not None
        and ba.recovery.expected_recovery is not None,
    }
    rec = ba.recovery
    if rec is None:
        return {**out, "decision": None, "reason": ba.notes[0] if ba.notes else "not priced"}
    out.update(decision=rec.decision, reasons=list(rec.reasons), codes=list(rec.codes), recovery=rec.to_dict())
    if not debate or rec.expected_recovery is None:
        return out
    from agents import debate as dbt
    # price the debate from the bridge's own avoidance numbers (p_liable applied), not from raw sim output
    est = estimators or {}
    if not est:
        from insurance.sim_estimator import run_sim
        est = run_sim(b).estimators
    avoidance = [to_avoidance_result(k, e.estimate(b.conflict), b.legal.p_liable_to_victim) for k, e in est.items()]
    claim = dbt.Claim(claim_facts(b, bool(ba.provenance.get("reproduced"))), avoidance, min_net_gbp=min_net_gbp,
                      case_file={"liability_verdict": out["liability"], "legal": dataclasses.asdict(b.legal),
                                 "provenance": ba.provenance})
    try:
        d = dbt.run_debate(claim, client=debate_client)
    except Exception as e:  # noqa: BLE001 - an LLM failure falls back to the scripted debate
        if debate_client is None:
            raise
        d = dbt.run_debate(claim, client=None)
        out["notes"].append(f"Claude debate failed ({type(e).__name__}); scripted debate used")
    out.update(original=dbt.summary(rec), final=d.final, adjuster=d.adjuster, challenge=d.challenge, challenged=d.challenged,
               rebuttal=d.rebuttal, contested=d.contested, debate_mode=d.mode)
    if d.contested:
        out["outcome"] = "PULL_LOGS" if out["outcome"] == "PURSUE" else out["outcome"]
        out["headline"] += " CONTESTED: a rejected challenge would change the decision; a human decides."
    return out
