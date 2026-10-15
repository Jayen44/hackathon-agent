"""Liability scenarios: conditional calculations only. The simulation never decides who is liable.

A scenario states legal liability shares (insured driver, automated driving system, third party). From
those shares and the insurer's payments this module derives what is RECOVERABLE, and from whom:

  third-party insurer   third_party_share of the insurer's own-damage outlay
  AV manufacturer       av_system_share of the own-damage outlay, plus the AV's part of the third-party
                        payments (AEVA 2018 s.5: recovery after the insurer's liability is settled)
  insured driver share  not recoverable (the insurer stands behind its own insured)

Recoverable amounts never exceed what was paid in that category; the insured's excess is the insured's
uninsured loss and is not part of the insurer's recovery.
"""
from __future__ import annotations

import numpy as np

from claimsim.models import InputError, LiabilityScenario

THIRD_PARTY_LOSSES = ("third_party_vehicle_repair", "bodily_injury", "third_party_property")


def attributable(s: LiabilityScenario, gross: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Losses the insurer answers for before policy terms.

    Own damage is first-party cover, independent of fault. Third-party losses follow the insured
    vehicle's liability share. 'other' is first-party and follows the policy, not liability.
    """
    out = {"insured_vehicle_repair": gross["insured_vehicle_repair"], "other": gross["other"]}
    for c in THIRD_PARTY_LOSSES:
        out[c] = s.insured_vehicle_share * gross[c]
    return out


def recoverable(s: LiabilityScenario, paid: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Maximum recoverable from each source, given the insurer's payments in each category."""
    own = paid["insured_vehicle_repair"]
    tp_paid = sum(paid[c] for c in THIRD_PARTY_LOSSES)
    av_part_of_tp = (s.av_system_share / s.insured_vehicle_share) * tp_paid if s.insured_vehicle_share > 0 \
        else np.zeros_like(own)
    return {
        "third_party_insurer": s.third_party_share * own,
        "manufacturer": s.av_system_share * own + av_part_of_tp,
    }


def can_probability_weight(scenarios: tuple[LiabilityScenario, ...]) -> tuple[bool, str]:
    """Probability-weighted results only when every scenario has a sourced probability and they sum to 1."""
    if any(s.probability is None for s in scenarios):
        return False, ("Liability is unresolved and scenario probabilities were not supplied: results are "
                       "conditional on each scenario and must not be averaged.")
    total = sum(s.probability for s in scenarios)
    if abs(total - 1) > 1e-9:
        raise InputError(f"scenario probabilities must sum to 1 when all are supplied, got {total:.6f}")
    return True, "Probability-weighted using the supplied scenario probabilities (see probability_source)."
