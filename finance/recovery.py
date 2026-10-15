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

from dataclasses import asdict, dataclass, field, replace
from typing import Literal

from finance import tables

DISCLAIMER = (
    "Triage evidence for a human claims handler. Not a liability ruling and not legal advice. "
    "UK law and UK figures; demo crashes are synthetic, sampled from DfT STATS19."
)

Decision = Literal["pursue", "dont_pursue", "pull_logs_first", "not_av_recovery", "cannot_price"]

# UK input codes. Engagement comes from the vehicle's data storage system (DSSAD, UN R157 as
# applied in GB); ODD is the operating conditions the self-driving feature is authorised for.
ENGAGEMENT = ("engaged_verified", "engaged_alleged", "not_engaged", "unknown")
ODD = ("inside", "outside", "exiting", "unknown")
SOFTWARE = ("compliant", "unauthorised_alteration", "safety_update_missing", "unknown")

# Legacy input: NHTSA SGO strings (US), still sent by insurance/bridge.py. Remove once the bridge
# sends UK codes (issue for Jayen).
_LEGACY_ENGAGEMENT = {"Verified Engaged": "engaged_verified", "Alleged Engaged": "engaged_alleged",
                      "Verified Not Engaged": "not_engaged", "Unknown, see Narrative": "unknown"}
_LEGACY_ODD = {"Yes": "inside", "No, see Narrative": "outside", "Exiting ODD": "exiting",
               "Unknown, see Narrative": "unknown"}


def engagement_code(v: str) -> str:
    return v if v in ENGAGEMENT else _LEGACY_ENGAGEMENT.get(v, "unknown")


def odd_code(v: str) -> str:
    return v if v in ODD else _LEGACY_ODD.get(v, "unknown")


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
    injury_severity: str          # UK: "Fatal" | "Serious" | "Slight" | "Damage only" | "Unknown" (legacy SGO accepted)
    engagement_status: str        # ENGAGEMENT code (legacy SGO accepted)
    within_odd: str               # ODD code (legacy SGO accepted)
    reproduced: bool              # Reconstructor reproduced the reported crash
    # The INJURED PARTY's contributory negligence share, low..high (AEVA s.3(1), 1945 Act).
    # None = not assessed. Not other drivers' fault. Name kept for the bridge contract.
    third_party_share: tuple[float, float] | None = None
    paid_claim_gbp: float | None = None   # amount the insurer actually paid (net of contributory negligence)
    legal_cost_gbp: tuple[float, float] | None = None    # override for the legal cost table
    software_status: str = "unknown"      # SOFTWARE code (AEVA s.4)


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


def contributory_negligence(f: ClaimFacts) -> tuple[tuple[float, float], str | None, str | None]:
    """(share range to apply, gate or None, note or None). Applied once, see module docstring."""
    if f.paid_claim_gbp is not None:
        note = ("paid amount is already net of the injured party's contributory negligence (AEVA s.3(1)); "
                "not applied again") if f.third_party_share else None
        return (0.0, 0.0), None, note
    if f.third_party_share is None:
        return (0.0, 1.0), "injured party's contributory negligence not assessed (AEVA s.3(1)): range 0-100%", None
    return f.third_party_share, None, None


def av_share(p: Interval, cn: tuple[float, float]) -> Interval:
    lo, hi = cn
    if not 0 <= lo <= hi <= 1:
        raise ValueError(f"contributory negligence must be 0 <= low <= high <= 1, got {cn}")
    return Interval(p.low * (1 - hi), p.mid * (1 - (lo + hi) / 2), p.high * (1 - lo))


def expected_recovery(share: Interval, value: Interval, cost: Interval) -> Interval:
    return Interval(
        share.low * value.low - cost.high,
        share.mid * value.mid - cost.mid,
        share.high * value.high - cost.low,
    )


def _gates(f: ClaimFacts) -> list[str]:
    """Facts that stop a 'pursue' until someone pulls the vehicle logs."""
    g = []
    eng, odd = engagement_code(f.engagement_status), odd_code(f.within_odd)
    if eng != "engaged_verified":
        g.append(f"self-driving engagement not verified from the vehicle data ({f.engagement_status})")
    if odd in ("outside", "exiting"):
        g.append(f"outside ODD, its authorised operating conditions ({f.within_odd}): recovery target may be "
                 "the operator, not the manufacturer")
    elif odd != "inside":
        g.append(f"operating-conditions (ODD) status unknown ({f.within_odd})")
    if not f.reproduced:
        g.append("simulation did not reproduce the reported crash (low confidence)")
    return g


def _claim_value(f: ClaimFacts) -> tuple[Interval | None, str]:
    if f.paid_claim_gbp is not None:
        return Interval.point(f.paid_claim_gbp), "insurer claim file (amount paid)"
    row = tables.claim_value_for_severity(f.injury_severity)
    if not row.priced:
        return None, row.source
    return Interval.span(row.low, row.high), f"{row.source} [{row.status}]"


def _legal_cost(f: ClaimFacts, value: Interval) -> tuple[Interval | None, str]:
    if f.legal_cost_gbp is not None:
        return Interval.span(*f.legal_cost_gbp), "legal cost supplied by caller"
    row = tables.legal_cost_for_claim(value.low, value.high)
    if not row.priced:
        return None, row.source
    return Interval.span(row.low, row.high), f"{row.source} [{row.status}]"


def assess(f: ClaimFacts, avoidance: list[AvoidanceResult], min_net_gbp: float = 0.0) -> RecoveryAssessment:
    """Culpability, expected recovery in GBP and a pursue / don't / pull-logs decision."""
    if f.software_status not in SOFTWARE:
        raise ValueError(f"software_status must be one of {SOFTWARE}, got {f.software_status!r}")
    p = avoidance_bracket(avoidance)
    cn, cn_gate, cn_note = contributory_negligence(f)
    share = av_share(p, cn)
    base = dict(claim_id=f.claim_id, crash_type=f.crash_type, p_avoid=p, av_share=share)

    if engagement_code(f.engagement_status) == "not_engaged":
        return RecoveryAssessment(**base, decision="not_av_recovery",
                                  reasons=["self-driving verified not engaged: ordinary motor claim, no s.5 recovery"],
                                  claim_value=None, legal_cost=None, expected_recovery=None)
    if f.software_status in ("unauthorised_alteration", "safety_update_missing"):
        return RecoveryAssessment(**base, decision="not_av_recovery",
                                  reasons=[f"AEVA s.4 ({f.software_status}): recover from the insured person to the "
                                           "extent the policy provides (s.4(4)), not from the manufacturer"],
                                  claim_value=None, legal_cost=None, expected_recovery=None)

    value, value_src = _claim_value(f)
    cost, cost_src = (None, "") if value is None else _legal_cost(f, value)
    if value is None or cost is None:
        missing = value_src if value is None else cost_src
        return RecoveryAssessment(**base, decision="cannot_price", reasons=[f"no sourced figure: {missing}"],
                                  claim_value=value, legal_cost=cost, expected_recovery=None,
                                  sources=[s for s in (value_src, cost_src) if s])

    ev = expected_recovery(share, value, cost)
    gates = _gates(f) + ([cn_gate] if cn_gate else [])
    if len(avoidance) < 2:
        gates.append("only one careful-driver model: bracket incomplete")

    if ev.high <= min_net_gbp:
        decision: Decision = "dont_pursue"
        reasons = [f"best case {fmt_gbp(ev.high)} does not exceed {fmt_gbp(min_net_gbp)}"]
    elif ev.low > min_net_gbp and not gates:
        decision = "pursue"
        reasons = [f"worst case {fmt_gbp(ev.low)} still exceeds {fmt_gbp(min_net_gbp)}"]
    else:
        decision = "pull_logs_first"
        reasons = gates + ([] if ev.low > min_net_gbp else
                           [f"range {fmt_gbp(ev.low)} to {fmt_gbp(ev.high)} straddles {fmt_gbp(min_net_gbp)}"])
    if f.software_status == "unknown" and decision != "dont_pursue":
        reasons.append("confirm no unauthorised software alteration or missed safety-critical update (AEVA s.4) "
                       "before issuing proceedings")
    if cn_note:
        reasons.append(cn_note)

    return RecoveryAssessment(**base, decision=decision, reasons=reasons, claim_value=value,
                              legal_cost=cost, expected_recovery=ev, sources=[value_src, cost_src])


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
        if not (0 < v and lo <= v <= hi):
            raise ChangeError(f"claim value {fmt_gbp(v)} outside the sourced range {fmt_gbp(lo)} to {fmt_gbp(hi)}")
        repl["paid_claim_gbp"] = v
    if (c["legal_cost_low"] is None) != (c["legal_cost_high"] is None):
        raise ChangeError("give both legal_cost_low and legal_cost_high, or neither")
    if c["legal_cost_low"] is not None:
        if not 0 <= c["legal_cost_low"] <= c["legal_cost_high"]:
            raise ChangeError("legal cost must satisfy 0 <= low <= high")
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
    trials = [(f"use {r.model} only (p_avoid {r.p_avoid:.2f})", {"keep_model": r.model}) for r in avoidance]
    trials += [
        (f"p_avoid at lower 90% bound ({a.p_avoid.low:.2f})", {"p_avoid_at_low_bound": True}),
        (f"injured party's contributory negligence at max ({cn[1]:.0%})", {"cn_low": cn[1], "cn_high": cn[1]}),
        (f"claim value at low end ({fmt_gbp(a.claim_value.low)})", {"claim_value_gbp": a.claim_value.low}),
        (f"legal cost at high end ({fmt_gbp(a.legal_cost.high)})",
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
