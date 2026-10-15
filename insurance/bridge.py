"""Bridge: crash bundle -> finance.recovery (Antonio's culpability and recovery-value engine).

insurance/ decides WHO is liable from the evidence; finance/ prices WHAT the insurer can
recover. This module is the only place that imports both.

    assess_bundle(bundle) -> BridgedAssessment(verdict, recovery, notes)

Honest limits (also written into `notes` on every result):
  * ci90 is a Wilson interval on Monte Carlo SAMPLING error only. It does not include
    uncertainty in the human-driver model or the reconstruction.
  * finance/ wants two careful-driver models (R157 A and B) as bounds. With one estimator
    its "only one careful-driver model" gate stays open. Pass two to close it.
  * Legal costs in finance/tables.py come from CPR PD 45 up to GBP 100k; above that (multi-track)
    they are still TODO, so unless the caller passes `legal_cost_gbp` the result is `cannot_price`.
    Nothing is guessed here.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from finance.recovery import AvoidanceResult, ClaimFacts, RecoveryAssessment, assess
from insurance.bundle import CrashBundle
from insurance.counterfactual import CounterfactualResult, Estimator, KinematicEstimator
from insurance.engine import Policy, Verdict, control_state, decide
from insurance.integrity import check_integrity

Z90 = 1.6449  # two-sided 90%


def wilson_ci90(p: float, n: int) -> tuple[float, float]:
    """Wilson score interval for a proportion p observed over n samples."""
    if n <= 0:
        raise ValueError("n must be positive")
    z2 = Z90 * Z90
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = Z90 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    # Clamp to [0,1] and make sure p itself is inside: float rounding can leave the upper end at
    # 0.9999999999999999 when p == 1.0, and finance.recovery.Interval rejects low <= mid <= high violations.
    return min(p, max(0.0, centre - half)), max(p, min(1.0, centre + half))


def to_avoidance_result(model: str, cf: CounterfactualResult) -> AvoidanceResult:
    lo, hi = wilson_ci90(cf.p_avoid, cf.n_samples)
    return AvoidanceResult(model=model, p_avoid=cf.p_avoid, ci90=(lo, hi))


def engagement_status(b: CrashBundle, policy: Policy = Policy()) -> str:
    """SGO 'engagement status' string finance/ expects."""
    state, _ = control_state(b, policy)
    if state == "automated":
        return "Verified Engaged"
    if state in ("manual", "assisted"):
        return "Verified Not Engaged"
    # human_override: engagement at the moment of the crash is ambiguous
    return "Unknown, see Narrative"


def within_odd_status(b: CrashBundle) -> str:
    """SGO field 113 values: Yes | No, see Narrative | Unknown, see Narrative | Exiting ODD."""
    return {True: "Yes", False: "No, see Narrative", None: "Unknown, see Narrative"}[b.vehicle.odd_inside]


def claim_facts(b: CrashBundle, reproduced: bool, third_party_share: tuple[float, float] = (0.0, 0.0),
                legal_cost_gbp: tuple[float, float] | None = None, policy: Policy = Policy()) -> ClaimFacts:
    return ClaimFacts(
        claim_id=b.case_id,
        crash_type=b.conflict.crash_type if b.conflict else "other",
        injury_severity=b.outcome.injury_severity,
        engagement_status=engagement_status(b, policy),
        within_odd=within_odd_status(b),
        reproduced=reproduced,
        third_party_share=third_party_share,
        paid_claim_gbp=b.outcome.paid_claim_gbp,
        legal_cost_gbp=legal_cost_gbp,
    )


@dataclass
class BridgedAssessment:
    verdict: Verdict
    recovery: RecoveryAssessment | None   # None = not priced, see notes
    notes: list[str] = field(default_factory=list)


def assess_bundle(b: CrashBundle, *, estimators: dict[str, Estimator] | None = None, reproduced: bool = False,
                  third_party_share: tuple[float, float] = (0.0, 0.0),
                  legal_cost_gbp: tuple[float, float] | None = None, policy: Policy = Policy(),
                  min_net_gbp: float = 0.0) -> BridgedAssessment:
    """Decide liability, then price the recovery when that makes sense.

    `reproduced` is False unless the caller has checked (e.g. sim.reproduce.check) that the
    simulation reproduces the reported crash; finance/ then holds the decision at pull_logs_first.
    """
    estimators = estimators or {"kinematic_placeholder": KinematicEstimator()}
    verdict = decide(b, policy, next(iter(estimators.values())))
    notes = ["ci90 covers Monte Carlo sampling error only, not model or reconstruction uncertainty."]

    def unpriced(why: str) -> BridgedAssessment:
        return BridgedAssessment(verdict, None, [why] + notes)

    if not b.outcome.collided:
        return unpriced("No collision: nothing to recover.")
    if not check_integrity(b).ok:
        return unpriced("Evidence failed integrity checks: not priced until a human clears it.")
    if verdict.liable == "HUMAN_DRIVER":
        return unpriced("Liability points at the human driver: ordinary motor claim, no recovery from the tech company.")
    if b.conflict is None:
        return unpriced("No reconstructed conflict: P(avoid) can't be computed, so nothing can be priced.")

    avoidance = [to_avoidance_result(name, est.estimate(b.conflict)) for name, est in estimators.items()]
    if len(avoidance) < 2:
        notes.append("Only one careful-driver model supplied: finance/ will hold 'pursue' at pull_logs_first.")
    if not reproduced:
        notes.append("Simulation not confirmed to reproduce the reported crash (reproduced=False).")
    facts = claim_facts(b, reproduced, third_party_share, legal_cost_gbp, policy)
    return BridgedAssessment(verdict, assess(facts, avoidance, min_net_gbp), notes)
