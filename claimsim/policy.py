"""Policy layer: from attributable loss to covered loss to insurer payment.

    attributable loss   what the insurer answers for (own damage + liability share of third-party loss)
    covered loss        attributable loss that is within cover: eligible and not excluded
    insurer payment     covered loss after the excess, sublimits and limits
    insured retained    covered own damage the insured bears (excess, amounts above the limit)

Jurisdiction rules plug in through the PolicyRules protocol; UKMotorRules is the first implementation.
Legal and handling costs are the insurer's own expense and sit outside the indemnity limits (a stated
simplification: some policies include defence costs within limits).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from claimsim.models import LOSS_CATEGORIES, PolicyTerms


@dataclass
class PolicyResult:
    covered: dict[str, np.ndarray]
    paid: dict[str, np.ndarray]
    insured_retained: np.ndarray
    notes: list[str]


class PolicyRules(Protocol):
    def apply(self, attributable: dict[str, np.ndarray], terms: PolicyTerms) -> PolicyResult: ...


def _cap(x: np.ndarray, limit: float | None) -> np.ndarray:
    return x if limit is None else np.minimum(x, limit)


class UKMotorRules:
    """Simplified UK private motor (comprehensive) policy.

    - Own damage: paid above the excess, up to the own-damage limit (market value); the excess is retained
      by the insured.
    - Third-party vehicle and other property share one combined property limit, split pro rata if capped.
    - Bodily injury: up to the bodily-injury limit if one is given. [Knowledge, unverified here: UK
      compulsory cover for death and personal injury is unlimited under the Road Traffic Act 1988.]
    - Sublimits cap a single category before the combined limits.
    - Excluded categories are not covered. For compulsory third-party cover an exclusion may still have
      to be paid and recovered from the insured; that is NOT modelled here.
    """
    jurisdiction = "UK"

    def apply(self, attributable: dict[str, np.ndarray], terms: PolicyTerms) -> PolicyResult:
        notes = []
        covered = {}
        for c in LOSS_CATEGORIES:
            eligible = c not in terms.excluded_categories
            if c == "insured_vehicle_repair":
                eligible = eligible and terms.own_damage_covered
            if c == "other":
                eligible = eligible and terms.other_expenses_covered
            covered[c] = attributable[c] if eligible else np.zeros_like(attributable[c])

        paid = {c: _cap(covered[c], terms.sublimits.get(c)) for c in LOSS_CATEGORIES}

        own_after_excess = np.maximum(paid["insured_vehicle_repair"] - terms.own_damage_excess, 0.0)
        paid["insured_vehicle_repair"] = _cap(own_after_excess, terms.own_damage_limit)
        insured_retained = covered["insured_vehicle_repair"] - paid["insured_vehicle_repair"]

        prop = paid["third_party_vehicle_repair"] + paid["third_party_property"]
        if terms.third_party_property_limit is not None:
            scale = np.where(prop > terms.third_party_property_limit,
                             terms.third_party_property_limit / np.maximum(prop, 1e-12), 1.0)
            paid["third_party_vehicle_repair"] = paid["third_party_vehicle_repair"] * scale
            paid["third_party_property"] = paid["third_party_property"] * scale
        else:
            notes.append("third-party property limit unknown: no cap applied")
        paid["bodily_injury"] = _cap(paid["bodily_injury"], terms.bodily_injury_limit)
        if terms.bodily_injury_limit is None:
            notes.append("bodily-injury limit not given: no cap applied")
        if terms.own_damage_limit is None and terms.own_damage_covered:
            notes.append("own-damage limit (vehicle value) unknown: total-loss cap not applied")
        return PolicyResult(covered, paid, insured_retained, notes)


RULES: dict[str, PolicyRules] = {"UK": UKMotorRules()}


def rules_for(jurisdiction: str) -> PolicyRules:
    try:
        return RULES[jurisdiction]
    except KeyError:
        raise ValueError(f"no policy rules for jurisdiction {jurisdiction!r}; available: {sorted(RULES)}") from None
