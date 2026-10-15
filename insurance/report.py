"""Plain-English report for a Verdict. Rendering only; no decisions are made here."""
from __future__ import annotations

from insurance.engine import Verdict

LABEL = {
    "HUMAN_DRIVER": "Human driver (and their motor insurer)",
    "TECH_COMPANY": "Technology company / authorised self-driving entity",
    "NO_FAULT_DRIVING": "No driving fault (unavoidable or no collision)",
    "NEEDS_REVIEW": "Needs human review",
}


def render_recovery(r) -> str:
    """Recovery block for a bridge.BridgedAssessment (finance/ numbers, rendered only)."""
    from finance.recovery import fmt_gbp
    out = ["RECOVERY (finance engine)", "-" * 25]
    rec = r.recovery
    if rec is None:
        out.append("Not priced.")
    else:
        iv = lambda i: f"{i.low:.0%} / {i.mid:.0%} / {i.high:.0%}"  # noqa: E731
        out += [f"Decision      : {rec.decision}",
                f"P(avoid)      : {iv(rec.p_avoid)}  (low / mid / high)",
                f"AV share      : {iv(rec.av_share)}"]
        if rec.expected_recovery:
            e = rec.expected_recovery
            out.append(f"Expected recovery: {fmt_gbp(e.low)} / {fmt_gbp(e.mid)} / {fmt_gbp(e.high)}")
        out += [f"  - {x}" for x in rec.reasons]
    out += [f"note: {n}" for n in r.notes]
    return "\n".join(out)


def render(v: Verdict) -> str:
    out = [f"CASE {v.case_id}", "=" * (5 + len(v.case_id)),
           f"Liable party : {LABEL[v.liable]}",
           f"Confidence   : {v.confidence}",
           f"Recovery case: {'yes, consider recovering from the tech company' if v.recovery_case else 'no'}",
           "", v.summary, "", "How we got here:"]
    for i, s in enumerate(v.steps, 1):
        out.append(f"  {i}. [{s.outcome}] {s.name}: {s.detail}")
    if v.counterfactual:
        c = v.counterfactual
        out += ["", f"Competent-driver test ({c.model}):",
                f"  P(human avoids) = {c.p_avoid:.0%} over {c.n_samples} sampled reaction times",
                f"  fast / median / slow reaction avoids: {c.avoids_at_p5} / {c.avoids_at_p50} / {c.avoids_at_p95}",
                f"  median human impact speed if not avoided: {c.median_impact_speed_mps:.1f} m/s"]
        out += [f"  note: {n}" for n in c.notes]
    for title, items in (("Findings", v.findings), ("Exclusions that may apply", v.exclusions),
                         ("Needs human review", v.review_items),
                         ("Evidence missing", v.evidence_missing)):
        if items:
            out += ["", f"{title}:"] + [f"  - {x}" for x in items]
    out += ["", v.disclaimer]
    return "\n".join(out)
