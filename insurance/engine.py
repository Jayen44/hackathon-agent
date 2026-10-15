"""Liability decision engine. Implements the flow in CLAUDE.md section 3.2.

Deterministic: same bundle + policy + estimator -> same verdict. No LLM, no I/O.
Output is triage evidence for a human claims handler, not a legal ruling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from insurance.bundle import CrashBundle
from insurance.counterfactual import CounterfactualResult, Estimator, KinematicEstimator
from insurance.integrity import check_integrity

Liable = Literal["HUMAN_DRIVER", "TECH_COMPANY", "NO_FAULT_DRIVING", "NEEDS_REVIEW"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]

DISCLAIMER = ("Decision support only: synthetic/simplified inputs, UK assumptions, placeholder human-driver "
              "model unless stated. Not legal or financial advice. A human claims handler decides.")


@dataclass(frozen=True)
class Policy:
    """Tunable thresholds. Values are ILLUSTRATIVE, not drawn from law or regulation."""
    min_handover_s: float = 10.0        # shortest handover warning we treat as adequate
    override_window_s: float = 2.0      # human input this close to the crash counts as an override
    p_system_fell_short: float = 0.8    # P(competent human avoids) at/above this -> system fell short
    p_unavoidable: float = 0.2          # at/below this -> unavoidable for a competent human
    detection_delay_flag_s: float = 1.0
    critical_fault_lookback_s: float = 60.0


@dataclass(frozen=True)
class Step:
    name: str
    outcome: str   # "continue" | "decided" | "review"
    detail: str


@dataclass
class Verdict:
    case_id: str
    liable: Liable
    confidence: Confidence
    recovery_case: bool                 # True when the victim's insurer should look at recovering from the tech company
    summary: str
    steps: list[Step] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    evidence_missing: list[str] = field(default_factory=list)
    review_items: list[str] = field(default_factory=list)
    counterfactual: CounterfactualResult | None = None
    disclaimer: str = DISCLAIMER


def control_state(b: CrashBundle, policy: Policy) -> tuple[str, str]:
    """(state, detail) at the moment of the crash: manual | assisted | automated | human_override."""
    current = "manual"
    for e in b.vehicle.mode_events:
        if e.t <= b.t_crash:
            current = e.mode
    if current == "automated":
        for c in b.vehicle.control_inputs:
            if c.source == "human" and 0 <= b.t_crash - c.t <= policy.override_window_s:
                return "human_override", f"human control input at t={c.t:.1f}s while automated"
    return current, f"last mode event at or before t={b.t_crash:.1f}s"


def missing_evidence(b: CrashBundle) -> list[str]:
    m: list[str] = []
    for s in ("camera", "lidar"):
        if s not in b.perception.sensors:
            m.append(f"{s} data")
    if not b.perception.decision_log_present:
        m.append("planning/decision log")
    if not b.external.cctv:
        m.append("independent CCTV")
    if not b.external.police_report:
        m.append("police report")
    if b.vehicle.occupant == "user_in_charge" and not b.vehicle.driver_monitoring:
        m.append("driver-monitoring data")
    if b.vehicle.odd_inside is None:
        m.append("operational design domain (ODD) status")
    if b.conflict is None:
        m.append("reconstructed conflict (needed for the competent-driver test)")
    return m


def decide(b: CrashBundle, policy: Policy = Policy(), estimator: Estimator | None = None) -> Verdict:
    estimator = estimator or KinematicEstimator()
    v = Verdict(b.case_id, "NEEDS_REVIEW", "LOW", False, "")
    v.evidence_missing = missing_evidence(b)

    def done(liable: Liable, conf: Confidence, summary: str, why: str, name: str) -> Verdict:
        v.liable, v.confidence, v.summary = liable, conf, summary
        v.recovery_case = liable == "TECH_COMPANY"
        v.steps.append(Step(name, "decided", why))
        return v

    # 0. Was there a collision at all?
    if not b.outcome.collided:
        return done("NO_FAULT_DRIVING", "HIGH", "No collision recorded; nothing to allocate.",
                    "outcome.collided is false", "outcome")

    # 1. Evidence integrity
    integ = check_integrity(b)
    v.findings += [f"Integrity warning: {w}" for w in integ.warnings]
    if not integ.ok:
        v.review_items += integ.blocking
        v.steps.append(Step("integrity", "review", "; ".join(integ.blocking)))
        v.summary = "Evidence failed integrity checks, so no liability decision is made."
        return v
    v.steps.append(Step("integrity", "continue", "hashes present, clocks within tolerance, no log gap at the crash"))

    # 2. Who was in control?
    state, detail = control_state(b, policy)
    if state in ("manual", "assisted"):
        return done("HUMAN_DRIVER", "HIGH", f"Human was driving ({state}); a normal motor claim applies.",
                    f"{state}: {detail}", "control_state")
    if state == "human_override":
        v.review_items.append("Check whether the human override was a reasonable reaction to the system's behaviour.")
        return done("HUMAN_DRIVER", "MEDIUM", "Human overrode the automated system just before the crash.",
                    detail, "control_state")
    v.steps.append(Step("control_state", "continue", f"automated driving engaged ({detail})"))

    # 3. Software approved?
    sw = b.vehicle
    if sw.approved_software and sw.software_version not in sw.approved_software:
        return done("TECH_COMPANY", "MEDIUM",
                    f"Software {sw.software_version} was not an approved version.",
                    f"{sw.software_version} not in approved list {sw.approved_software}", "software")
    v.steps.append(Step("software", "continue", f"version {sw.software_version} is approved or no list supplied"))

    # 4. Inside the operational design domain?
    if sw.odd_inside is False:
        return done("TECH_COMPANY", "MEDIUM", "The system was operating outside its approved conditions (ODD).",
                    "odd_inside is false", "odd")
    v.steps.append(Step("odd", "continue", "inside ODD" if sw.odd_inside else "ODD status unknown (flagged as missing)"))

    # 5. Critical fault shortly before the crash?
    crit = [f for f in sw.faults if f.severity == "critical"
            and 0 <= b.t_crash - f.t <= policy.critical_fault_lookback_s]
    if crit:
        codes = ", ".join(f.code for f in crit)
        v.findings.append("Critical fault logged before the crash: subrogation against the manufacturer is worth checking.")
        return done("TECH_COMPANY", "MEDIUM", f"A critical system fault ({codes}) preceded the crash.",
                    f"critical faults within {policy.critical_fault_lookback_s:.0f}s: {codes}", "faults")
    v.steps.append(Step("faults", "continue", "no critical fault in the lookback window"))

    # 6. Handover
    h = sw.handover
    if h.demand_t is not None and h.demand_t < b.t_crash:
        lead = b.t_crash - h.demand_t
        responded = h.human_response_t is not None and h.human_response_t <= b.t_crash
        if responded and b.t_crash - h.human_response_t >= policy.override_window_s:
            return done("HUMAN_DRIVER", "MEDIUM", "The human took control before the crash.",
                        f"response at t={h.human_response_t:.1f}s, {b.t_crash - h.human_response_t:.1f}s before the crash",
                        "handover")
        if not responded:
            if lead >= policy.min_handover_s:
                off = [d for d in sw.driver_monitoring if h.demand_t <= d.t <= b.t_crash and not d.eyes_on_road]
                if off:
                    v.findings.append("Driver-monitoring shows eyes off the road during the handover warning.")
                v.review_items.append("Confirm the failure to respond was reckless; immunity for the user-in-charge "
                                      "may still apply if it was not (see CLAUDE.md 3.1).")
                return done("HUMAN_DRIVER", "MEDIUM",
                            f"Handover was requested {lead:.0f}s before the crash and the human did not respond.",
                            f"lead {lead:.1f}s >= minimum {policy.min_handover_s}s, no response", "handover")
            return done("TECH_COMPANY", "MEDIUM",
                        f"Handover warning was only {lead:.1f}s, shorter than the {policy.min_handover_s:.0f}s we treat as adequate.",
                        f"lead {lead:.1f}s < minimum {policy.min_handover_s}s", "handover")
    v.steps.append(Step("handover", "continue", "no handover before the crash, or the human responded too late to matter"))

    # 7. Competent-driver counterfactual
    if b.conflict is None:
        v.review_items.append("No reconstructed conflict: the competent-driver test can't be run.")
        v.steps.append(Step("counterfactual", "review", "conflict missing"))
        v.summary = "Cannot decide: the crash has not been reconstructed."
        return v

    cf = estimator.estimate(b.conflict)
    v.counterfactual = cf
    obj = next((o for o in b.perception.objects if o.id == b.conflict.hazard_id), None)
    if obj is not None:
        delay = obj.first_detected_t - b.conflict.t_start
        if delay > policy.detection_delay_flag_s:
            v.findings.append(f"System first detected the hazard {delay:.1f}s after a human could have seen it.")
        elif delay < 0:
            v.findings.append("System detected the hazard before the human-visible conflict start.")
    elif b.perception.objects or b.perception.decision_log_present:
        v.findings.append("The hazard does not appear in the system's object list.")

    pct = (f"avoids at fast/median/slow reaction: {cf.avoids_at_p5}/{cf.avoids_at_p50}/{cf.avoids_at_p95}; "
           f"P(avoid)={cf.p_avoid:.0%} via {cf.model}")
    if cf.p_avoid >= policy.p_system_fell_short:
        conf = "HIGH" if cf.avoids_at_p95 else "MEDIUM"
        return done("TECH_COMPANY", conf, "A competent human would very likely have avoided this crash.", pct, "counterfactual")
    if cf.p_avoid <= policy.p_unavoidable:
        conf = "HIGH" if not cf.avoids_at_p5 else "MEDIUM"
        return done("NO_FAULT_DRIVING", conf,
                    "A competent human would very likely not have avoided this crash either; no driving fault.",
                    pct, "counterfactual")
    v.review_items.append(f"Counterfactual is borderline (P(avoid)={cf.p_avoid:.0%}); needs human review.")
    v.steps.append(Step("counterfactual", "review", pct))
    v.summary = "Borderline: the competent-driver test does not clearly favour either side."
    return v
