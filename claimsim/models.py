"""Validated inputs and outputs for the claim cost simulation. GBP throughout.

Unknown is kept as unknown: a None estimate is modelled from the (synthetic) assumptions and reported as
missing information; it is never silently replaced by zero.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

MODEL_VERSION = "claimsim-0.1.0"

# Loss categories. Gross economic loss is the sum over all of them for everyone involved in the accident.
LOSS_CATEGORIES = ("insured_vehicle_repair", "third_party_vehicle_repair", "bodily_injury",
                   "third_party_property", "other")
EXPENSE_CATEGORY = "legal_and_handling"   # insurer's own expense, kept separate from indemnity
ALL_CATEGORIES = LOSS_CATEGORIES + (EXPENSE_CATEGORY,)

InjuryOutcome = Literal["unknown", "none", "known"]
Severity = Literal["low", "medium", "high"]


class InputError(ValueError):
    """Invalid claim, policy, scenario or configuration input."""


def _check_amount(name: str, v: float | None, allow_none: bool = True) -> None:
    if v is None:
        if not allow_none:
            raise InputError(f"{name} is required")
        return
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        raise InputError(f"{name} must be a finite amount >= 0, got {v!r}")


def _check_prob(name: str, v: float | None) -> None:
    if v is None:
        return
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
        raise InputError(f"{name} must be a probability in [0, 1], got {v!r}")


@dataclass(frozen=True)
class LiabilityScenario:
    """Who is legally liable for the accident, as explicit shares that sum to 1.

    These are INPUTS (from a claims handler, a court, an agreement or a stated hypothesis), never outputs
    of the simulation. Factual causation, legal liability, policy coverage and recovery stay separate:
    this object only states legal liability shares.
    """
    name: str
    insured_driver_share: float      # insured driver / operator / user-in-charge
    av_system_share: float           # automated driving system: manufacturer or software provider
    third_party_share: float         # the other party
    probability: float | None = None          # only when supplied with a source
    probability_source: str | None = None
    description: str = ""

    def __post_init__(self):
        if not self.name:
            raise InputError("scenario name is required")
        for n in ("insured_driver_share", "av_system_share", "third_party_share"):
            _check_prob(f"{self.name}.{n}", getattr(self, n))
        total = self.insured_driver_share + self.av_system_share + self.third_party_share
        if abs(total - 1) > 1e-9:
            raise InputError(f"{self.name}: liability shares must sum to 1, got {total:.6f}")
        _check_prob(f"{self.name}.probability", self.probability)
        if self.probability is not None and not self.probability_source:
            raise InputError(f"{self.name}: a scenario probability needs a probability_source")

    @property
    def insured_vehicle_share(self) -> float:
        """Share for which the insured vehicle's insurer answers to third parties (AEVA 2018 s.2 when self-driving)."""
        return self.insured_driver_share + self.av_system_share


@dataclass(frozen=True)
class PolicyTerms:
    """Motor policy terms. None = unknown (reported as missing; no cap applied)."""
    own_damage_covered: bool                      # comprehensive cover for the insured vehicle
    own_damage_excess: float
    own_damage_limit: float | None                # e.g. vehicle market value (total-loss cap)
    third_party_property_limit: float | None      # vehicle + other property, combined
    bodily_injury_limit: float | None
    other_expenses_covered: bool = False
    excluded_categories: tuple[str, ...] = ()
    sublimits: dict[str, float] = field(default_factory=dict)   # category -> cap
    jurisdiction: str = "UK"

    def __post_init__(self):
        _check_amount("own_damage_excess", self.own_damage_excess, allow_none=False)
        for n in ("own_damage_limit", "third_party_property_limit", "bodily_injury_limit"):
            _check_amount(n, getattr(self, n))
        bad = set(self.excluded_categories) - set(LOSS_CATEGORIES)
        if bad:
            raise InputError(f"unknown excluded categories: {sorted(bad)}")
        for k, v in self.sublimits.items():
            if k not in LOSS_CATEGORIES:
                raise InputError(f"unknown sublimit category {k!r}")
            _check_amount(f"sublimit {k}", v, allow_none=False)


@dataclass(frozen=True)
class ClaimInput:
    claim_id: str
    insured_repair_estimate: float | None
    third_party_repair_estimate: float | None
    injury_outcome: InjuryOutcome
    policy: PolicyTerms
    scenarios: tuple[LiabilityScenario, ...]
    injury_cost_estimate: float | None = None          # required when injury_outcome == "known"
    third_party_property_estimate: float | None = None  # None = unknown (modelled)
    other_expenses_estimate: float = 0.0
    collision_severity: Severity | None = None           # None = unknown
    third_party_recovery_probability: float | None = None   # claim-specific, with a source; else synthetic default
    manufacturer_recovery_probability: float | None = None
    recovery_probability_source: str | None = None
    exceedance_thresholds: tuple[float, ...] = (5_000, 10_000, 25_000, 50_000, 100_000)
    human_review_threshold: float | None = None
    synthetic: bool = True     # illustrative input, not a real claim

    def __post_init__(self):
        if not self.claim_id:
            raise InputError("claim_id is required")
        for n in ("insured_repair_estimate", "third_party_repair_estimate", "injury_cost_estimate",
                  "third_party_property_estimate", "human_review_threshold"):
            _check_amount(n, getattr(self, n))
        _check_amount("other_expenses_estimate", self.other_expenses_estimate, allow_none=False)
        if self.injury_outcome not in ("unknown", "none", "known"):
            raise InputError(f"injury_outcome must be unknown | none | known, got {self.injury_outcome!r}")
        if self.injury_outcome == "known" and self.injury_cost_estimate is None:
            raise InputError("injury_outcome 'known' needs injury_cost_estimate")
        if self.injury_outcome != "known" and self.injury_cost_estimate is not None:
            raise InputError("injury_cost_estimate given but injury_outcome is not 'known'")
        if self.collision_severity not in (None, "low", "medium", "high"):
            raise InputError(f"collision_severity must be low | medium | high | null, got {self.collision_severity!r}")
        for n in ("third_party_recovery_probability", "manufacturer_recovery_probability"):
            _check_prob(n, getattr(self, n))
        if (self.third_party_recovery_probability is not None or self.manufacturer_recovery_probability is not None) \
                and not self.recovery_probability_source:
            raise InputError("claim-specific recovery probabilities need recovery_probability_source")
        if not self.scenarios:
            raise InputError("at least one liability scenario is required (use several when liability is unresolved)")
        names = [s.name for s in self.scenarios]
        if len(set(names)) != len(names):
            raise InputError(f"scenario names must be unique: {names}")
        for t in self.exceedance_thresholds:
            _check_amount("exceedance threshold", t, allow_none=False)


def _scenario(d: dict) -> LiabilityScenario:
    return LiabilityScenario(**_only(d, LiabilityScenario, "scenario"))


def _only(d: dict, cls, what: str) -> dict:
    if not isinstance(d, dict):
        raise InputError(f"{what} must be an object")
    allowed = set(cls.__dataclass_fields__)
    extra = set(d) - allowed
    if extra:
        raise InputError(f"unknown {what} fields: {sorted(extra)}")
    return d


def claim_from_dict(d: dict) -> ClaimInput:
    """Build a validated ClaimInput from JSON-like data. Unknown fields are rejected, not ignored."""
    d = dict(_only(d, ClaimInput, "claim"))
    try:
        pol = dict(_only(d.pop("policy"), PolicyTerms, "policy"))
        pol["excluded_categories"] = tuple(pol.get("excluded_categories", ()))
        d["policy"] = PolicyTerms(**pol)
        d["scenarios"] = tuple(_scenario(s) for s in d.pop("scenarios"))
    except KeyError as e:
        raise InputError(f"missing required field {e.args[0]!r}") from None
    except TypeError as e:
        raise InputError(str(e)) from None
    if "exceedance_thresholds" in d:
        d["exceedance_thresholds"] = tuple(d["exceedance_thresholds"])
    try:
        return ClaimInput(**d)
    except TypeError as e:
        raise InputError(str(e)) from None
