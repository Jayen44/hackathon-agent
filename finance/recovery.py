"""Culpability and recovery value for one AV claim. Finance owns this file.

Pure functions: inputs in, GBP out. No I/O, no LLM calls. The Adjuster agent calls
assess(); Defence counsel calls weakest_assumption(); the orchestrator calls
rank() and recoverability_map().

Legal frame (UK, all read on legislation.gov.uk unless marked):
- Automated and Electric Vehicles Act 2018 (AEVA) s.2: the insurer pays the injured party first.
- AEVA s.5(1): anyone else liable to the injured party (e.g. the AV company) is under the same
  liability to the insurer once the insurer's liability is settled; s.5(4): never more than that
  person's liability to the injured party.
- AEVA s.3(1) + Law Reform (Contributory Negligence) Act 1945: the injured party's own fault
  reduces what is owed to them, by the insurer AND by the AV company.
- AEVA s.4: unauthorised software alterations or a missed safety-critical update shift recovery
  to the insured person under the policy (s.4(4)), not the manufacturer.
- Automated Vehicles Act 2024: the safety benchmark is a careful and competent human driver.
  We read P(a careful driver avoids the crash) as P(the AV company is liable). Proxy, not the
  civil test: say so in the pitch.

    AV share          = P(careful driver avoids) x (1 - injured party's contributory negligence)
    expected recovery = AV share x claim value - legal cost

Contributory negligence is applied once: a paid amount is already net of it (s.3(1)), a table
value is gross. Other drivers' fault does not reduce recovery: the AV company is liable for the
whole of the injured party's (reduced) loss jointly with them [Knowledge: joint and several
liability in English tort law].

Every figure is an Interval (low, central, high), never a bare number.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace
from typing import Literal

from finance import tables

DISCLAIMER = (
    "Triage evidence for a human claims handler. Not a liability ruling and not legal advice. "
    "UK law and UK figures; demo crashes are synthetic, sampled from DfT STATS19."
)

Decision = Literal["pursue", "dont_pursue", "pull_logs_first", "not_av_recovery", "cannot_price"]

# UK input codes. Engagement comes from the vehicle's data storage system (DSSAD, UN R157 as
# applied in GB); ODD is the operating conditions the automated driving system (ADS) is authorised for.
ENGAGEMENT = ("engaged_verified", "engaged_alleged", "not_engaged", "unknown")
ODD = ("inside", "outside", "exiting", "unknown")
SOFTWARE = ("compliant", "unauthorised_alteration", "safety_update_missing", "unknown")
ROUTES = ("AEVA_s5", "contribution_1978", "CPA_1987", "policy_s4", "unspecified")   # = insurance/legal.py

# AEVA 2018 s.2(4): property-damage liability per accident capped at the RTA 1988 s.145(4)(b) amount,
# GBP 1,200,000 since 31 Dec 2016 (SI 2016/1193). CPA 1987 s.5(4): no property damages of GBP 275 or less.
PROPERTY_CAP_GBP = 1_200_000
CPA_PROPERTY_THRESHOLD_GBP = 275



def engagement_code(v: str) -> str:
    """The UK engagement code, validated. Unrecognised values are rejected, never guessed."""
    if v not in ENGAGEMENT:
        raise ValueError(f"engagement_status must be one of {ENGAGEMENT}, got {v!r}")
    return v


def odd_code(v: str) -> str:
    """The UK ODD code, validated. Unrecognised values are rejected, never guessed."""
    if v not in ODD:
        raise ValueError(f"within_odd must be one of {ODD}, got {v!r}")
    return v


@dataclass(frozen=True)
class Interval:
    low: float
    mid: float
    high: float

    def __post_init__(self):
        if not self.low <= self.mid <= self.high:
            raise ValueError(f"interval out of order: {self}")

    @classmethod
    def point(cls, v: float) -> "Interval":
        return cls(v, v, v)

    @classmethod
    def span(cls, low: float, high: float) -> "Interval":
        return cls(low, (low + high) / 2, high)


@dataclass(frozen=True)
class AvoidanceResult:
    """Counterfactual analyst output for one careful-driver model."""
    model: str            # e.g. "careful_a" (R157 model 1), "careful_b" (R157 model 2)
    p_avoid: float        # share of Monte Carlo runs where the careful driver avoided the crash
    ci90: tuple[float, float]


@dataclass(frozen=True)
class ClaimFacts:
    claim_id: str                 # insurer's claim reference
    crash_type: str               # e.g. "cut_in", "lead_vehicle_decel", "other"
    injury_severity: str          # UK (DfT STATS19): "Fatal" | "Serious" | "Slight" | "Damage only" | "Unknown"
    engagement_status: str        # ENGAGEMENT code
    within_odd: str               # ODD code
    reproduced: bool              # Reconstructor reproduced the reported crash
    # The INJURED PARTY's contributory negligence share, low..high (AEVA s.3(1), 1945 Act).
    # None = not assessed. Not other drivers' fault. Name kept for the bridge contract.
    third_party_share: tuple[float, float] | None = None
    paid_claim_gbp: float | None = None   # amount the insurer actually paid (net of contributory negligence)
    legal_cost_gbp: tuple[float, float] | None = None    # override for the legal cost table
    software_status: str = "unknown"      # SOFTWARE code (AEVA s.4)
    # Caller-set ASSUMPTION, default off. CPR 44.2(2): the unsuccessful party normally pays the winner's costs.
    # True widens the worst case by the other side's costs, assumed equal to our own high legal cost (no sourced
    # figure for the defendant's spend). Mid and best cases are unchanged: no win probability is modelled.
    cost_shift_risk: bool = False
    # Claim-value scope (#23). Parts of the PAID amount, so they apply only when paid_claim_gbp is known.
    recovery_route: str = "unspecified"           # ROUTES; CPA_1987 adds the s.5 property rules
    excluded_damage_gbp: float = 0.0              # outside AEVA s.2(3): the AV itself, goods carried for hire or
                                                  # reward, property in the insured's / person in charge's custody
    property_damage_gbp: float | None = None      # property-damage part of the in-scope paid amount
    property_private: bool | None = None          # CPA s.5(3): ordinarily and mainly for private use? None = unknown


@dataclass
class RecoveryAssessment:
    claim_id: str
    crash_type: str
    decision: Decision
    reasons: list[str]
    p_avoid: Interval
    av_share: Interval
    claim_value: Interval | None
    legal_cost: Interval | None
    expected_recovery: Interval | None
    sources: list[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER
    # Machine-readable twins of the gate/caveat reasons, so callers never parse prose. Stable names:
    # ENGAGEMENT_UNVERIFIED, ODD_OUTSIDE, ODD_UNKNOWN, NOT_REPRODUCED, CN_NOT_ASSESSED, ONE_MODEL,
    # RANGE_STRADDLES, SOFTWARE_UNCONFIRMED, NEAR_TRACK_LIMIT; on early returns NOT_ENGAGED, S4_SOFTWARE_BREACH,
    # NO_SOURCED_VALUE, NO_SOURCED_LEGAL_COST
    codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def fmt_gbp(x: float) -> str:
    return f"-£{-x:,.0f}" if x < 0 else f"£{x:,.0f}"


def avoidance_bracket(results: list[AvoidanceResult]) -> Interval:
    """Run both R157 models and treat them as bounds: lowest CI end to highest CI end."""
    if not results:
        raise ValueError("need at least one careful-driver result")
    return Interval(
        min(r.ci90[0] for r in results),
        sum(r.p_avoid for r in results) / len(results),
        max(r.ci90[1] for r in results),
    )


def contributory_negligence(f: ClaimFacts) -> tuple[tuple[float, float], float, str | None]:
    """(share range to apply, central share, note or None). Applied once, see module docstring.

    Not assessed: the central case assumes none, because the party alleging contributory negligence has to
    plead and prove it [Knowledge, secondary sources]; the worst case still allows up to 100%. It is a caveat
    for the claims handler, not a reason to pull vehicle logs (the logs cannot answer it).
    """
    if f.paid_claim_gbp is not None:
        note = ("paid amount is already net of the injured party's contributory negligence (AEVA s.3(1)); "
                "not applied again") if f.third_party_share else None
        return (0.0, 0.0), 0.0, note
    if f.third_party_share is None:
        return (0.0, 1.0), 0.0, ("injured party's contributory negligence not assessed (AEVA s.3(1)): central case "
                                 "assumes none (it must be alleged and proved), worst case allows up to 100%")
    lo, hi = f.third_party_share
    return (lo, hi), (lo + hi) / 2, None


def av_share(p: Interval, cn: tuple[float, float], cn_mid: float | None = None) -> Interval:
    lo, hi = cn
    mid = (lo + hi) / 2 if cn_mid is None else cn_mid
    if not 0 <= lo <= mid <= hi <= 1:
        raise ValueError(f"contributory negligence must be 0 <= low <= central <= high <= 1, got {cn}, {mid}")
    return Interval(p.low * (1 - hi), p.mid * (1 - mid), p.high * (1 - lo))


def expected_recovery(share: Interval, value: Interval, cost: Interval) -> Interval:
    return Interval(
        share.low * value.low - cost.high,
        share.mid * value.mid - cost.mid,
        share.high * value.high - cost.low,
    )


def validate_facts(f: ClaimFacts) -> None:
    """Reject inputs that would silently flatter or crash a claim. Raises ValueError with the field named."""
    def finite(x): return isinstance(x, (int, float)) and math.isfinite(x)
    if f.paid_claim_gbp is not None and not (finite(f.paid_claim_gbp) and f.paid_claim_gbp > 0):
        raise ValueError(f"paid_claim_gbp must be a positive finite amount, got {f.paid_claim_gbp!r}")
    if f.legal_cost_gbp is not None:
        lo, hi = f.legal_cost_gbp
        if not (finite(lo) and finite(hi) and 0 < lo <= hi):
            raise ValueError(f"legal_cost_gbp must be (low, high) with 0 < low <= high, got {f.legal_cost_gbp!r}")
    engagement_code(f.engagement_status)
    odd_code(f.within_odd)
    if f.recovery_route not in ROUTES:
        raise ValueError(f"recovery_route must be one of {ROUTES}, got {f.recovery_route!r}")
    for name in ("excluded_damage_gbp", "property_damage_gbp"):
        x = getattr(f, name)
        if x is not None and not (finite(x) and x >= 0):
            raise ValueError(f"{name} must be a finite amount >= 0, got {x!r}")
    if f.paid_claim_gbp is not None:
        if f.excluded_damage_gbp >= f.paid_claim_gbp:
            raise ValueError("excluded_damage_gbp must be less than paid_claim_gbp")
        if (f.property_damage_gbp or 0) > f.paid_claim_gbp - f.excluded_damage_gbp:
            raise ValueError("property_damage_gbp cannot exceed the in-scope paid amount")
    tables.claim_value_for_severity(f.injury_severity)
    if f.third_party_share is not None:
        lo, hi = f.third_party_share
        if not (finite(lo) and finite(hi) and 0 <= lo <= hi <= 1):
            raise ValueError(f"third_party_share must be 0 <= low <= high <= 1, got {f.third_party_share!r}")


def _special_damages_note(f: ClaimFacts) -> list[str]:
    """Table values for Serious/Fatal are general damages only; flag that real claims run higher."""
    if f.paid_claim_gbp is None and f.injury_severity in ("Serious", "Fatal"):
        return [f"{f.injury_severity} claim value is general damages only (care, lost earnings, dependency excluded): "
                "the real claim is likely higher; use the insurer's paid amount if known"]
    return []


def _near_track_limit(v: Interval) -> str | None:
    """Legal cost is a step function of claim value (CPR 26.9 tracks), so a value close to a limit can flip the decision."""
    for limit in (tables.FAST_TRACK_LIMIT, tables.INTERMEDIATE_TRACK_LIMIT):
        if v.low <= limit * 1.1 and v.high >= limit * 0.9:
            return (f"claim value {fmt_gbp(v.low)} to {fmt_gbp(v.high)} is within 10% of the {fmt_gbp(limit)} track limit: "
                    "legal cost steps up sharply across it, so a small change in value can flip the decision")
    return None


def _models_disagree(avoidance: list[AvoidanceResult]) -> bool:
    """Civil standard is the balance of probabilities: models either side of 50% leave liability unclear."""
    ps = [r.p_avoid for r in avoidance]
    return len(ps) >= 2 and min(ps) < 0.5 < max(ps)


def _gates(f: ClaimFacts) -> list[str]:
    """Facts that stop a 'pursue' until someone pulls the vehicle logs."""
    g = []
    eng, odd = engagement_code(f.engagement_status), odd_code(f.within_odd)
    if eng != "engaged_verified":
        g.append(f"ADS engagement not verified from the vehicle data ({f.engagement_status})")
    if odd in ("outside", "exiting"):
        g.append(f"outside ODD, its authorised operating conditions ({f.within_odd}): recovery target may be "
                 "the operator, not the manufacturer")
    elif odd != "inside":
        g.append(f"operating-conditions (ODD) status unknown ({f.within_odd})")
    if not f.reproduced:
        g.append("simulation did not reproduce the reported crash (low confidence)")
    return g


def _codes(f: ClaimFacts, cn_gate: str | None, n_models: int, decision: str, ev: Interval,
           min_net: float, near_limit: bool) -> list[str]:
    c = []
    eng, odd = engagement_code(f.engagement_status), odd_code(f.within_odd)
    if eng != "engaged_verified":
        c.append("ENGAGEMENT_UNVERIFIED")
    if odd in ("outside", "exiting"):
        c.append("ODD_OUTSIDE")
    elif odd != "inside":
        c.append("ODD_UNKNOWN")
    if not f.reproduced:
        c.append("NOT_REPRODUCED")
    if cn_gate:
        c.append("CN_NOT_ASSESSED")
    if n_models < 2:
        c.append("ONE_MODEL")
    if decision == "pull_logs_first" and ev.low <= min_net:
        c.append("RANGE_STRADDLES")
    if f.software_status == "unknown" and decision != "dont_pursue":
        c.append("SOFTWARE_UNCONFIRMED")
    if near_limit and decision != "dont_pursue":
        c.append("NEAR_TRACK_LIMIT")
    return c


def _claim_value(f: ClaimFacts) -> tuple[Interval | None, str]:
    if f.paid_claim_gbp is not None:
        v = _in_scope(f)[0]
        return v, "insurer claim file (amount paid)" + (", scoped to recoverable damage" if v.high < f.paid_claim_gbp else "")
    row = tables.claim_value_for_severity(f.injury_severity)
    if not row.priced:
        return None, row.source
    return Interval.span(row.low, row.high), f"{row.source} [{row.status}]"


def _in_scope(f: ClaimFacts) -> tuple[Interval, list[str], list[str]]:
    """Recoverable part of the paid amount (#23): (value, reasons, codes). Only meaningful when paid is known.

    AEVA s.2(3): damage to the AV itself, goods carried for hire or reward and property in the insured's or
    person in charge's custody are not s.2 damage, so they are not recoverable under s.5.
    AEVA s.2(4): property damage above GBP 1.2m per accident is outside the insurer's s.2 liability.
    CPA 1987 route: no property damage unless ordinarily and mainly for private use (s.5(3)), and none at
    all if it is GBP 275 or less (s.5(4)); damage to the product itself is excluded (s.5(2), same as s.2(3)(a)).
    """
    reasons, codes = [], []
    base = f.paid_claim_gbp - f.excluded_damage_gbp
    if f.excluded_damage_gbp > 0:
        reasons.append(f"{fmt_gbp(f.excluded_damage_gbp)} of the paid amount is outside AEVA s.2(3) "
                       "(AV itself, goods carried for hire or reward, insured's own property): not recoverable")
        codes.append("SCOPE_EXCLUDED")
    prop = f.property_damage_gbp or 0.0
    if prop > PROPERTY_CAP_GBP:
        reasons.append(f"property damage above the {fmt_gbp(PROPERTY_CAP_GBP)} AEVA s.2(4) cap is not recoverable")
        codes.append("PROPERTY_CAP")
        base -= prop - PROPERTY_CAP_GBP
        prop = PROPERTY_CAP_GBP
    low = base
    if f.recovery_route == "CPA_1987" and f.property_damage_gbp is not None and prop > 0:
        if prop <= CPA_PROPERTY_THRESHOLD_GBP or f.property_private is False:
            why = (f"£275 or less (CPA s.5(4))" if prop <= CPA_PROPERTY_THRESHOLD_GBP
                   else "not for private use (CPA s.5(3))")
            reasons.append(f"CPA route: property damage {fmt_gbp(prop)} is {why}, so it is not recoverable")
            codes.append("CPA_PROPERTY_EXCLUDED")
            base -= prop
            low = base
        elif f.property_private is None:
            reasons.append(f"CPA route: property damage {fmt_gbp(prop)} counts only if it was for private use "
                           "(CPA s.5(3)): unknown, so the low end excludes it")
            codes.append("CPA_PRIVATE_UNKNOWN")
            low = base - prop
    return Interval(low, (low + base) / 2, base), reasons, codes


def _legal_cost(f: ClaimFacts, value: Interval) -> tuple[Interval | None, str]:
    if f.legal_cost_gbp is not None:
        return Interval.span(*f.legal_cost_gbp), "legal cost supplied by caller"
    row = tables.legal_cost_for_claim(value.low, value.high)
    if not row.priced:
        return None, row.source
    mid = row.mid if row.mid is not None else (row.low + row.high) / 2
    return Interval(row.low, mid, row.high), f"{row.source} [{row.status}]"


def assess(f: ClaimFacts, avoidance: list[AvoidanceResult], min_net_gbp: float = 0.0) -> RecoveryAssessment:
    """Culpability, expected recovery in GBP and a pursue / don't / pull-logs decision."""
    validate_facts(f)
    if f.software_status not in SOFTWARE:
        raise ValueError(f"software_status must be one of {SOFTWARE}, got {f.software_status!r}")
    p = avoidance_bracket(avoidance)
    cn, cn_mid, cn_note = contributory_negligence(f)
    cn_unassessed = f.paid_claim_gbp is None and f.third_party_share is None
    share = av_share(p, cn, cn_mid)
    base = dict(claim_id=f.claim_id, crash_type=f.crash_type, p_avoid=p, av_share=share)

    if engagement_code(f.engagement_status) == "not_engaged":
        return RecoveryAssessment(**base, decision="not_av_recovery",
                                  reasons=["ADS verified not engaged: ordinary motor claim, no s.5 recovery"],
                                  claim_value=None, legal_cost=None, expected_recovery=None, codes=["NOT_ENGAGED"])
    if f.software_status in ("unauthorised_alteration", "safety_update_missing"):
        return RecoveryAssessment(**base, decision="not_av_recovery",
                                  reasons=[f"AEVA s.4 ({f.software_status}): recover from the insured person to the "
                                           "extent the policy provides (s.4(4)), not from the manufacturer"],
                                  claim_value=None, legal_cost=None, expected_recovery=None,
                                  codes=["S4_SOFTWARE_BREACH"])

    value, value_src = _claim_value(f)
    cost, cost_src = (None, "") if value is None else _legal_cost(f, value)
    if value is None or cost is None:
        missing = value_src if value is None else cost_src
        breakeven = [] if value is None else [
            f"break-even legal cost: recovery is worth pursuing only if counsel's budget is below "
            f"{fmt_gbp(share.mid * value.mid)} (central) or {fmt_gbp(share.low * value.low)} (worst case)"]
        return RecoveryAssessment(**base, decision="cannot_price", reasons=[f"no sourced figure: {missing}",
                                           "supply paid_claim_gbp and/or legal_cost_gbp (a counsel budget) to price this claim",
                                           *breakeven, *_special_damages_note(f)],
                                  claim_value=value, legal_cost=cost, expected_recovery=None,
                                  sources=[s for s in (value_src, cost_src) if s],
                                  codes=["NO_SOURCED_VALUE" if value is None else "NO_SOURCED_LEGAL_COST"])

    ev = expected_recovery(share, value, cost)
    if f.cost_shift_risk:
        # Adverse costs arise only if the claim FAILS, and then nothing is recovered: the worst case is losing
        # outright (our high cost + the defendant's), not a partial recovery minus adverse costs.
        ev = Interval(min(ev.low, -2 * cost.high), ev.mid, ev.high)
    gates = _gates(f)
    if len(avoidance) < 2:
        gates.append("only one careful-driver model: bracket incomplete")
    if _models_disagree(avoidance):
        gates.append("careful-driver models disagree on the balance of probabilities (one below 50%, one above): "
                     "liability is genuinely unclear")

    # Decision on the central case, not the worst corner: a recovery opens with a pre-action letter and can be
    # dropped if the response is bad, so the trial-and-lose worst case is a stated downside, not a veto.
    if ev.high <= min_net_gbp:
        decision: Decision = "dont_pursue"
        reasons = [f"best case {fmt_gbp(ev.high)} does not exceed {fmt_gbp(min_net_gbp)}"]
    elif gates:
        decision = "pull_logs_first"
        reasons = gates + ([] if ev.low > min_net_gbp else
                           [f"range {fmt_gbp(ev.low)} to {fmt_gbp(ev.high)} straddles {fmt_gbp(min_net_gbp)}"])
    elif ev.mid > min_net_gbp:
        decision = "pursue"
        reasons = [f"central case {fmt_gbp(ev.mid)} exceeds {fmt_gbp(min_net_gbp)}"]
        if ev.low <= min_net_gbp:
            reasons.append(f"worst case {fmt_gbp(ev.low)} only if litigated to trial and lost: open with a pre-action "
                           "letter and escalate only if the response justifies the cost")
    else:
        decision = "pull_logs_first"
        reasons = [f"range {fmt_gbp(ev.low)} to {fmt_gbp(ev.high)} straddles {fmt_gbp(min_net_gbp)} and the central "
                   f"case {fmt_gbp(ev.mid)} does not clear it: firm up the claim value before deciding"]
    if f.software_status == "unknown" and decision != "dont_pursue":
        reasons.append("confirm no unauthorised software alteration or missed safety-critical update (AEVA s.4) "
                       "before issuing proceedings")
    if cn_note:
        reasons.append(cn_note)
    if f.cost_shift_risk:
        reasons.append("worst case includes adverse costs if the claim fails (CPR 44.2(2)); the defendant's costs are "
                       "ASSUMED equal to our own high legal cost, not sourced")
    reasons += _special_damages_note(f)
    near = _near_track_limit(value)
    if near and decision != "dont_pursue":
        reasons.append(near)

    codes = _codes(f, "unassessed" if cn_unassessed else None, len(avoidance), decision, ev, min_net_gbp, bool(near))
    if f.paid_claim_gbp is not None:
        _, scope_reasons, scope_codes = _in_scope(f)
        reasons += scope_reasons
        codes += scope_codes
    elif f.excluded_damage_gbp or f.property_damage_gbp is not None:
        reasons.append("scope exclusions (AEVA s.2(3), CPA s.5) apply to the paid amount; this value is a table "
                       "estimate, so they were not applied")
    if _models_disagree(avoidance):
        codes.append("MODELS_DISAGREE")
    if decision == "pursue" and ev.low <= min_net_gbp:
        codes.append("LITIGATION_DOWNSIDE")
    return RecoveryAssessment(**base, decision=decision, reasons=reasons, claim_value=value,
                              legal_cost=cost, expected_recovery=ev, sources=[value_src, cost_src], codes=codes)


CHANGE_KEYS = ("keep_model", "p_avoid_at_low_bound", "cn_low", "cn_high", "claim_value_gbp",
               "legal_cost_low", "legal_cost_high")


def blank_change() -> dict:
    """A 'what if' with nothing changed. Every challenge to a claim is expressed in these keys."""
    return {"keep_model": None, "p_avoid_at_low_bound": False, "cn_low": None, "cn_high": None,
            "claim_value_gbp": None, "legal_cost_low": None, "legal_cost_high": None}


class ChangeError(ValueError):
    """A proposed 'what if' outside what the evidence and sources allow."""


def apply_change(f: ClaimFacts, avoidance: list[AvoidanceResult],
                 change: dict) -> tuple[ClaimFacts, list[AvoidanceResult]]:
    """Re-state a claim under a challenged assumption, within bounds the evidence allows.

    keep_model            use one careful-driver model only (must be one we ran)
    p_avoid_at_low_bound  each model's P(avoid) at the low end of its own 90% interval
    cn_low / cn_high      injured party's contributory negligence range, 0..1
    claim_value_gbp       recoverable loss; must sit inside the sourced range for the severity,
                          or at most the amount paid
    legal_cost_low/high   legal cost range, GBP >= 0
    """
    unknown = set(change) - set(CHANGE_KEYS)
    if unknown:
        raise ChangeError(f"unknown change keys: {sorted(unknown)}")
    c = {**blank_change(), **change}
    av = list(avoidance)
    if c["keep_model"] is not None:
        av = [r for r in avoidance if r.model == c["keep_model"]]
        if not av:
            raise ChangeError(f"keep_model {c['keep_model']!r} is not one of {[r.model for r in avoidance]}")
    if c["p_avoid_at_low_bound"]:
        av = [AvoidanceResult(r.model, r.ci90[0], r.ci90) for r in av]
    repl: dict = {}
    if (c["cn_low"] is None) != (c["cn_high"] is None):
        raise ChangeError("give both cn_low and cn_high, or neither")
    if c["cn_low"] is not None:
        if not 0 <= c["cn_low"] <= c["cn_high"] <= 1:
            raise ChangeError("contributory negligence must satisfy 0 <= cn_low <= cn_high <= 1")
        repl["third_party_share"] = (float(c["cn_low"]), float(c["cn_high"]))
    if c["claim_value_gbp"] is not None:
        v = float(c["claim_value_gbp"])
        row = tables.claim_value_for_severity(f.injury_severity)
        lo = row.low if row.priced else 0.0
        hi = max(f.paid_claim_gbp or 0.0, row.high if row.priced else 0.0)
        if f.paid_claim_gbp is not None:
            lo = min(lo, f.paid_claim_gbp)   # the paid amount itself is always a valid value, even below the table range
        if not (0 < v and lo <= v <= hi):
            raise ChangeError(f"claim value {fmt_gbp(v)} outside the sourced range {fmt_gbp(lo)} to {fmt_gbp(hi)}")
        repl["paid_claim_gbp"] = v
    if (c["legal_cost_low"] is None) != (c["legal_cost_high"] is None):
        raise ChangeError("give both legal_cost_low and legal_cost_high, or neither")
    if c["legal_cost_low"] is not None:
        if not 0 < c["legal_cost_low"] <= c["legal_cost_high"]:
            raise ChangeError("legal cost must satisfy 0 < low <= high")
        repl["legal_cost_gbp"] = (float(c["legal_cost_low"]), float(c["legal_cost_high"]))
    return replace(f, **repl), av


@dataclass(frozen=True)
class Attack:
    assumption: str
    expected_recovery_mid: float
    flips_decision: bool
    change: dict = field(default_factory=blank_change)  # the same attack as an apply_change() input


def weakest_assumption(f: ClaimFacts, avoidance: list[AvoidanceResult],
                       min_net_gbp: float = 0.0) -> list[Attack]:
    """For Defence counsel: push each input to the AV company's best case, one at a time.

    Returns attacks sorted most damaging first. flips_decision is True when the decision
    changes once the attack is applied through apply_change() and assess().
    """
    a = assess(f, avoidance, min_net_gbp)
    if a.expected_recovery is None:
        return []
    cn, _, _ = contributory_negligence(f)
    def name(m: str) -> str:
        return m.replace("_", " ")

    trials = [(f"rely on the {name(r.model)} driver model alone (it avoids the crash {r.p_avoid:.0%} of the time)",
               {"keep_model": r.model}) for r in avoidance]
    trials += [
        (f"take the low end of the careful-driver result ({a.p_avoid.low:.0%} chance of avoiding the crash)",
         {"p_avoid_at_low_bound": True}),
        (f"assume the injured person was {cn[1]:.0%} to blame", {"cn_low": cn[1], "cn_high": cn[1]}),
        (f"value the claim at the low end of its range ({fmt_gbp(a.claim_value.low)})",
         {"claim_value_gbp": a.claim_value.low}),
        (f"assume legal costs at the top of the range ({fmt_gbp(a.legal_cost.high)}, a full trial)",
         {"legal_cost_low": a.legal_cost.high, "legal_cost_high": a.legal_cost.high}),
    ]
    out = []
    for name, ch in trials:
        b = assess(*apply_change(f, avoidance, ch), min_net_gbp)
        mid = b.expected_recovery.mid if b.expected_recovery else float("-inf")
        out.append(Attack(name, mid, b.decision != a.decision, {**blank_change(), **ch}))
    return sorted(out, key=lambda t: (not t.flips_decision, t.expected_recovery_mid))


def rank(assessments: list[RecoveryAssessment]) -> list[RecoveryAssessment]:
    """Priced claims by central expected recovery, highest first; unpriced ones last."""
    return sorted(assessments, key=lambda a: (a.expected_recovery is None,
                                              -(a.expected_recovery.mid if a.expected_recovery else 0)))


def recoverability_map(assessments: list[RecoveryAssessment]) -> dict[str, Interval]:
    """Recoverable GBP by crash type, counting only claims worth pursuing or investigating."""
    out: dict[str, list[float]] = {}
    for a in assessments:
        if a.decision not in ("pursue", "pull_logs_first"):
            continue
        acc = out.setdefault(a.crash_type, [0.0, 0.0, 0.0])
        ev = a.expected_recovery
        for i, x in enumerate((ev.low, ev.mid, ev.high)):
            acc[i] += max(0.0, x)
    return {k: Interval(*v) for k, v in out.items()}
