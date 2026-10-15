"""Resolution: every assessed crash ends in a named OUTCOME and an ordered NEXT-STEP list, never a dead end.

    resolve(bridged, bundle) -> Resolution(outcome, headline, next_steps)

Outcomes (the claims handler's queue):
  CLOSE_NO_CLAIM       no collision, nothing to do
  HUMAN_REVIEW         evidence failed integrity checks; fix the evidence, then re-run
  MOTOR_CLAIM          human driver at fault: settle as an ordinary motor claim, no recovery
  SETTLE_NO_RECOVERY   not worth pursuing: pay/close, do not pursue the tech company
  RECOVER_FROM_INSURED not an AV recovery (not engaged, or AEVA s.4 breach): look to the insured per the policy
  PULL_LOGS            promising but gated: close the named gaps, then re-run
  NEEDS_INPUTS         cannot be priced yet: supply the named figure (paid amount / counsel budget), then re-run
  PURSUE               open recovery against the tech company; steps are the pre-action checklist
Each step names who acts and what it unblocks. Pure function, no I/O; it only re-reads what the assessment found.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from finance.recovery import fmt_gbp
from insurance.bridge import BridgedAssessment
from insurance.bundle import CrashBundle


# Suggested approvers per outcome (labels only; the firm decides who actually signs).
SIGN_OFF = {"PURSUE": ["claims manager", "counsel"], "HUMAN_REVIEW": ["senior claims handler"],
            "SETTLE_NO_RECOVERY": ["claims handler"], "RECOVER_FROM_INSURED": ["claims handler"]}


@dataclass
class Step:
    who: str          # claims handler | engineer | counsel | insurer finance
    action: str
    unblocks: str     # the outcome this step can move the claim to


@dataclass
class Resolution:
    case_id: str
    outcome: str
    headline: str
    next_steps: list[Step] = field(default_factory=list)
    sign_off: list[str] = field(default_factory=list)   # suggested roles; a human decides, this only names who


# Codes that need no action of their own (decision-context or handled by the outcome itself).
INFORMATIONAL_CODES = {"NOT_ENGAGED", "S4_SOFTWARE_BREACH", "NO_SOURCED_VALUE", "NO_SOURCED_LEGAL_COST"}

_STEP_FOR_CODE = {
    "MODELS_DISAGREE": Step("engineer", "The careful-driver models fall either side of 50%: check the reconstruction inputs (gap, speed, "
                            "perception time) and gather evidence that separates the models before relying on the result",
                            "PURSUE or SETTLE_NO_RECOVERY"),
    "LITIGATION_DOWNSIDE": Step("counsel", "Worst case is a lost trial: open with a pre-action letter only, reserve the adverse-costs "
                                "exposure, and escalate to proceedings only if the response justifies it", "PURSUE"),
    "ENGAGEMENT_UNVERIFIED": Step("engineer", "Send a preservation letter for the vehicle's DSSAD/ADS logs and request them; if refused, apply for pre-action disclosure (CPR 31.16). No statutory right to the data exists",
                                  "PURSUE or RECOVER_FROM_INSURED"),
    "ODD_OUTSIDE": Step("engineer", "Confirm the operating conditions (ODD) at the crash location/time: the target may be the operator",
                        "PURSUE (against the right party)"),
    "ODD_UNKNOWN": Step("engineer", "Confirm the operating conditions (ODD) at the crash location/time with the manufacturer",
                        "PURSUE"),
    "NOT_REPRODUCED": Step("engineer", "Re-run the reconstruction with the raw logs until it reproduces the reported crash",
                           "PURSUE"),
    "CN_NOT_ASSESSED": Step("claims handler", "Assess the injured party's contributory negligence (give a low-high share)",
                            "PURSUE"),
    "ONE_MODEL": Step("engineer", "Run a second careful-driver model so the bracket closes (R157 Annex 3)", "PURSUE"),
    "RANGE_STRADDLES": Step("insurer finance", "Replace the table value with the actual paid amount to narrow the range",
                            "PURSUE or SETTLE_NO_RECOVERY"),
    "SOFTWARE_UNCONFIRMED": Step("claims handler",
                                 "Confirm no unauthorised software change or missed safety-critical update (AEVA s.4)", "PURSUE"),
    "NEAR_TRACK_LIMIT": Step("counsel", "Value is near a court-track limit: get counsel's costs estimate before deciding",
                             "PURSUE or SETTLE_NO_RECOVERY"),
}


def _gate_steps(codes: list[str]) -> list[Step]:
    return [_STEP_FOR_CODE[c] for c in codes if c in _STEP_FOR_CODE]


def resolve(r: BridgedAssessment, b: CrashBundle) -> Resolution:
    x = _with_legal_steps(_resolve(r, b), r, b)
    x.sign_off = list(SIGN_OFF.get(x.outcome, []))
    if r.deadline and r.deadline.urgent and "counsel" not in x.sign_off and x.outcome in ("PURSUE", "PULL_LOGS", "NEEDS_INPUTS"):
        x.sign_off.append("counsel")
    return x


def _with_legal_steps(x: Resolution, r: BridgedAssessment, b: CrashBundle) -> Resolution:
    """Limitation clock first (it is the one step that can lose the claim), then the regime caveat. Only for claims
    that are still open for recovery."""
    if x.outcome not in ("PURSUE", "PULL_LOGS", "NEEDS_INPUTS"):
        return x
    extra = []
    d = r.deadline
    if d:
        when = "OVERDUE" if d.days_left < 0 else f"{d.days_left} days"
        extra.append(Step("counsel", f"Limitation: {d.route} deadline {d.due.isoformat()} ({when}): {d.basis}" + (
            ". URGENT: issue or agree a standstill now" if d.urgent else ""), "PURSUE"))
    if b.legal.regime in ("conventional", "unspecified"):
        extra.append(Step("counsel", "Confirm the recovery route (no vehicle is AEVA-listed today: contribution under the 1978 Act or CPA 1987?)", "PURSUE"))
    if b.legal.p_liable_to_victim is None and x.outcome in ("PURSUE", "PULL_LOGS"):
        extra.append(Step("counsel", "Assess the chance the manufacturer/operator is liable to the victim (AEVA s.5 recovery is "
                          "derivative); set legal.p_liable_to_victim, otherwise avoidance is treated as the whole liability case",
                          "PURSUE (with a tighter range)"))
    x.next_steps = extra[:1] + x.next_steps + extra[1:]
    return x


def _resolve(r: BridgedAssessment, b: CrashBundle) -> Resolution:
    cid = r.verdict.case_id

    def done(outcome: str, headline: str, *steps: Step) -> Resolution:
        return Resolution(cid, outcome, headline, list(steps))

    if not b.outcome.collided:
        return done("CLOSE_NO_CLAIM", "No collision: nothing to recover.",
                    Step("claims handler", "Close the file", "CLOSE_NO_CLAIM"))
    if r.recovery is None:
        why = r.notes[0]
        if "integrity" in why:
            return done("HUMAN_REVIEW", "Evidence cannot be trusted yet.",
                        *[Step("claims handler", f"Resolve: {x}", "re-run") for x in r.verdict.review_items[:3]],
                        Step("engineer", "Obtain signed/hashed logs from the manufacturer, then re-run", "re-run"))
        if "human driver" in why.lower():
            return done("MOTOR_CLAIM", "Human driver at fault: ordinary motor claim, no recovery.",
                        Step("claims handler", "Settle under the policy as a normal motor claim", "CLOSE_NO_CLAIM"))
        if "invalid claim inputs" in why.lower():
            return done("NEEDS_INPUTS", why, Step("claims handler", "Correct the claim figures named above, then re-run", "re-run"))
        return done("NEEDS_INPUTS", why,
                    Step("engineer", "Provide a reconstructed conflict (speeds, gap, road) from the logs, then re-run", "re-run"))

    a = r.recovery
    d = a.decision
    gate = _gate_steps(a.codes)
    if d == "pursue":
        ev = a.expected_recovery
        head = ("Pursue the tech company." if "LITIGATION_DOWNSIDE" not in a.codes else
                f"Pursue pre-action only: central case {fmt_gbp(ev.mid)}, but a lost trial costs {fmt_gbp(ev.low)}.")
        return done("PURSUE", head,
                    Step("counsel", "Send a letter before action citing AEVA s.5", "PURSUE"),
                    Step("engineer", "Send a preservation letter for the vehicle logs and keep the reconstruction under chain of custody", "PURSUE"),
                    Step("insurer finance", "Reserve the legal-cost high end from the assessment", "PURSUE"),
                    *gate)
    if d == "not_av_recovery":
        if "S4_SOFTWARE_BREACH" in a.codes:
            act = "Check the policy wording for recovery from the insured (AEVA s.4(4)); do not pursue the manufacturer"
        else:   # NOT_ENGAGED
            act = "Settle as an ordinary motor claim: self-driving was not engaged, so there is no AEVA s.5 recovery"
        return done("RECOVER_FROM_INSURED", a.reasons[0], Step("claims handler", act, "CLOSE_NO_CLAIM"))
    if d == "dont_pursue":
        return done("SETTLE_NO_RECOVERY", "Not worth pursuing: " + a.reasons[0],
                    Step("claims handler", "Settle and close without pursuing the tech company", "CLOSE_NO_CLAIM"),
                    Step("insurer finance", "Consider bundling with similar small claims against the same manufacturer",
                         "PURSUE (as a batch)"))
    if d == "cannot_price":
        steps = []
        if "NO_SOURCED_VALUE" in a.codes:
            steps.append(Step("insurer finance", "Supply the amount actually paid (paid_claim_gbp): severity has no sourced value",
                              "re-run"))
        if "NO_SOURCED_LEGAL_COST" in a.codes:
            steps.append(Step("counsel", "Supply a legal-cost budget for this claim (legal_cost_gbp): above GBP 100k has no fixed costs",
                              "re-run"))
            steps.append(Step("insurer finance", "Or supply the amount actually paid (paid_claim_gbp) to narrow the value", "re-run"))
        return done("NEEDS_INPUTS", a.reasons[0], *steps)
    steps = gate or [Step("insurer finance", "Replace the table value with the actual paid amount",
                          "PURSUE or SETTLE_NO_RECOVERY")]
    return done("PULL_LOGS", "Promising but gated: close the gaps below, then re-run.", *steps)


def render_resolution(x: Resolution) -> str:
    lines = [f"OUTCOME: {x.outcome}. {x.headline}"]
    if x.sign_off:
        lines.append("  Suggested sign-off: " + ", ".join(x.sign_off))
    lines += [f"  {i}. [{s.who}] {s.action}  -> {s.unblocks}" for i, s in enumerate(x.next_steps, 1)]
    return "\n".join(lines)
