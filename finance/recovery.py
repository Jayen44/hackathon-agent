"""Culpability and recovery value for one AV claim. Finance owns this file.

Pure functions: inputs in, GBP out. No I/O, no LLM calls. The Adjuster agent calls
assess(); Defence counsel calls weakest_assumption(); the orchestrator calls
rank() and recoverability_map().

Legal frame (UK):
- Automated and Electric Vehicles Act 2018 s.2: the insurer pays the victim first;
  s.5: it may then recover from anyone else liable (e.g. the manufacturer).
- Automated Vehicles Act 2024: the standard is a careful and competent human driver.
  We read P(a careful driver avoids the crash) as the probability that the AV is found
  to have fallen below that standard.
- Law Reform (Contributory Negligence) Act 1945: the other party's share of fault
  reduces what can be recovered.

    AV share of fault    = P(careful driver avoids) x (1 - third-party share)
    expected recovery    = AV share of fault x claim value - legal cost

Every figure is an Interval (low, central, high), never a bare number. Low and high
combine the worst and best ends of every input, so they are deliberately wide.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from finance import tables

DISCLAIMER = (
    "Triage evidence for a human claims handler. Not a liability ruling and not legal advice. "
    "Based on public NHTSA SGO data and a simulation with stated assumptions."
)

Decision = Literal["pursue", "dont_pursue", "pull_logs_first", "not_av_recovery", "cannot_price"]


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
    claim_id: str                 # SGO Report ID, or the insurer's claim reference
    crash_type: str               # e.g. "cut_in", "lead_vehicle_decel", "other"
    injury_severity: str          # SGO field 73, exact drop-down value
    engagement_status: str        # SGO field 22, exact drop-down value
    within_odd: str               # SGO field 113, exact drop-down value
    reproduced: bool              # Reconstructor reproduced the reported crash
    third_party_share: tuple[float, float] = (0.0, 0.0)  # other party's share of fault, range
    paid_claim_gbp: float | None = None   # amount the insurer actually paid; beats the table
    legal_cost_gbp: tuple[float, float] | None = None    # override for the legal cost table


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


def _is_redacted(v: str) -> bool:
    return v.startswith("[REDACTED")


def avoidance_bracket(results: list[AvoidanceResult]) -> Interval:
    """Run both R157 models and treat them as bounds: lowest CI end to highest CI end."""
    if not results:
        raise ValueError("need at least one careful-driver result")
    return Interval(
        min(r.ci90[0] for r in results),
        sum(r.p_avoid for r in results) / len(results),
        max(r.ci90[1] for r in results),
    )


def av_share(p: Interval, third_party: tuple[float, float]) -> Interval:
    tp_lo, tp_hi = third_party
    if not 0 <= tp_lo <= tp_hi <= 1:
        raise ValueError(f"third_party_share must be 0 <= low <= high <= 1, got {third_party}")
    return Interval(p.low * (1 - tp_hi), p.mid * (1 - (tp_lo + tp_hi) / 2), p.high * (1 - tp_lo))


def expected_recovery(share: Interval, value: Interval, cost: Interval) -> Interval:
    return Interval(
        share.low * value.low - cost.high,
        share.mid * value.mid - cost.mid,
        share.high * value.high - cost.low,
    )


def _gates(f: ClaimFacts) -> list[str]:
    """Facts that stop a 'pursue' until someone pulls the vehicle logs."""
    g = []
    if f.engagement_status != "Verified Engaged":
        g.append(f"ADS engagement not verified ({f.engagement_status})")
    if f.within_odd in ("No, see Narrative", "Exiting ODD"):
        g.append(f"outside ODD ({f.within_odd}): recovery target may be the operator, not the manufacturer")
    elif f.within_odd != "Yes":
        g.append(f"ODD status unknown ({f.within_odd})")
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
    row = tables.legal_cost_for_claim(value.high)
    if not row.priced:
        return None, row.source
    return Interval.span(row.low, row.high), f"{row.source} [{row.status}]"


def assess(f: ClaimFacts, avoidance: list[AvoidanceResult], min_net_gbp: float = 0.0) -> RecoveryAssessment:
    """Culpability, expected recovery in GBP and a pursue / don't / pull-logs decision."""
    p = avoidance_bracket(avoidance)
    share = av_share(p, f.third_party_share)
    base = dict(claim_id=f.claim_id, crash_type=f.crash_type, p_avoid=p, av_share=share)

    if f.engagement_status == "Verified Not Engaged":
        return RecoveryAssessment(**base, decision="not_av_recovery",
                                  reasons=["ADS verified not engaged: ordinary motor claim, no s.5 recovery"],
                                  claim_value=None, legal_cost=None, expected_recovery=None)

    value, value_src = _claim_value(f)
    cost, cost_src = (None, "") if value is None else _legal_cost(f, value)
    if value is None or cost is None:
        missing = value_src if value is None else cost_src
        return RecoveryAssessment(**base, decision="cannot_price", reasons=[f"no sourced figure: {missing}"],
                                  claim_value=value, legal_cost=cost, expected_recovery=None,
                                  sources=[s for s in (value_src, cost_src) if s])

    ev = expected_recovery(share, value, cost)
    gates = _gates(f)
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

    return RecoveryAssessment(**base, decision=decision, reasons=reasons, claim_value=value,
                              legal_cost=cost, expected_recovery=ev, sources=[value_src, cost_src])


@dataclass(frozen=True)
class Attack:
    assumption: str
    expected_recovery_mid: float
    flips_decision: bool


def weakest_assumption(f: ClaimFacts, avoidance: list[AvoidanceResult],
                       min_net_gbp: float = 0.0) -> list[Attack]:
    """For Defence counsel: push each input to the AV company's best case, one at a time.

    Returns attacks sorted most damaging first. flips_decision is True when the central
    expected recovery crosses min_net_gbp under that attack.
    """
    a = assess(f, avoidance, min_net_gbp)
    if a.expected_recovery is None:
        return []
    tp = sum(f.third_party_share) / 2
    p, v, c = a.p_avoid.mid, a.claim_value.mid, a.legal_cost.mid

    def ev(p_=p, tp_=tp, v_=v, c_=c) -> float:
        return p_ * (1 - tp_) * v_ - c_

    trials = [(f"use {r.model} only (p_avoid {r.p_avoid:.2f})", ev(p_=r.p_avoid)) for r in avoidance]
    trials += [
        (f"p_avoid at lower 90% bound ({a.p_avoid.low:.2f})", ev(p_=a.p_avoid.low)),
        (f"third party at max share ({f.third_party_share[1]:.0%})", ev(tp_=f.third_party_share[1])),
        (f"claim value at low end ({fmt_gbp(a.claim_value.low)})", ev(v_=a.claim_value.low)),
        (f"legal cost at high end ({fmt_gbp(a.legal_cost.high)})", ev(c_=a.legal_cost.high)),
    ]
    central = ev() > min_net_gbp
    return sorted((Attack(name, x, (x > min_net_gbp) != central) for name, x in trials),
                  key=lambda t: t.expected_recovery_mid)


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
