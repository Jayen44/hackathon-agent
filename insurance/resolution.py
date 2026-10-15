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

from insurance.bridge import BridgedAssessment
from insurance.bundle import CrashBundle


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


def _gate_steps(reasons: list[str]) -> list[Step]:
    out: list[Step] = []
    for r in reasons:
        low = r.lower()
        if "engagement not verified" in low:
            out.append(Step("engineer", "Pull the vehicle data storage (DSSAD) log to verify self-driving was engaged at impact",
                            "PURSUE or RECOVER_FROM_INSURED"))
        elif "odd" in low and ("outside" in low or "unknown" in low):
            out.append(Step("engineer", "Confirm the operating conditions (ODD) at the crash location/time with the manufacturer",
                            "PURSUE (target may be the operator instead)"))
        elif "did not reproduce" in low:
            out.append(Step("engineer", "Re-run the reconstruction with the raw logs until it reproduces the reported crash",
                            "PURSUE"))
        elif "contributory negligence not assessed" in low:
            out.append(Step("claims handler", "Assess the injured party's contributory negligence (give a low-high share)",
                            "PURSUE"))
        elif "one careful-driver model" in low:
            out.append(Step("engineer", "Run a second careful-driver model so the bracket closes (R157 Annex 3)", "PURSUE"))
        elif "straddles" in low:
            out.append(Step("insurer finance", "Replace the table value with the actual paid amount to narrow the range",
                            "PURSUE or SETTLE_NO_RECOVERY"))
        elif "aeva s.4" in low or "software" in low:
            out.append(Step("claims handler", "Confirm no unauthorised software change or missed safety-critical update (AEVA s.4)",
                            "PURSUE"))
        elif "track limit" in low:
            out.append(Step("counsel", "Value is near a court-track limit: get counsel's costs estimate before deciding",
                            "PURSUE or SETTLE_NO_RECOVERY"))
    return out


def resolve(r: BridgedAssessment, b: CrashBundle) -> Resolution:
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
    gate = _gate_steps(a.reasons)
    if d == "pursue":
        return done("PURSUE", "Pursue the tech company.",
                    Step("counsel", "Send a letter before action citing AEVA s.5", "PURSUE"),
                    Step("engineer", "Preserve the vehicle logs and the reconstruction (chain of custody)", "PURSUE"),
                    Step("insurer finance", "Reserve the legal-cost high end from the assessment", "PURSUE"),
                    *gate)
    if d == "not_av_recovery":
        return done("RECOVER_FROM_INSURED", a.reasons[0],
                    Step("claims handler", "Check the policy wording for recovery from the insured (AEVA s.4(4)) or settle as a motor claim",
                         "CLOSE_NO_CLAIM"))
    if d == "dont_pursue":
        return done("SETTLE_NO_RECOVERY", "Not worth pursuing: " + a.reasons[0],
                    Step("claims handler", "Settle and close without pursuing the tech company", "CLOSE_NO_CLAIM"),
                    Step("insurer finance", "Consider bundling with similar small claims against the same manufacturer",
                         "PURSUE (as a batch)"))
    if d == "cannot_price":
        return done("NEEDS_INPUTS", a.reasons[0],
                    Step("insurer finance", "Supply the amount actually paid (paid_claim_gbp)", "re-run"),
                    Step("counsel", "Supply a legal-cost budget for this claim (legal_cost_gbp)", "re-run"))
    steps = gate or [Step("insurer finance", "Replace the table value with the actual paid amount",
                          "PURSUE or SETTLE_NO_RECOVERY")]
    return done("PULL_LOGS", "Promising but gated: close the gaps below, then re-run.", *steps)


def render_resolution(x: Resolution) -> str:
    lines = [f"OUTCOME: {x.outcome}. {x.headline}"]
    lines += [f"  {i}. [{s.who}] {s.action}  -> {s.unblocks}" for i, s in enumerate(x.next_steps, 1)]
    return "\n".join(lines)
