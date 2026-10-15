"""Every crash must resolve to an outcome with at least one next step."""
from insurance.bridge import assess_bundle
from insurance.portfolio import default_estimators
from insurance.resolution import resolve
from insurance.synth_bundles import generate_cases

OUTCOMES = {"CLOSE_NO_CLAIM", "HUMAN_REVIEW", "MOTOR_CLAIM", "SETTLE_NO_RECOVERY", "RECOVER_FROM_INSURED",
            "PULL_LOGS", "NEEDS_INPUTS", "PURSUE"}


def test_every_synthetic_crash_resolves_with_steps():
    for c in generate_cases(30, 3):
        r = assess_bundle(c.bundle, estimators=default_estimators(), reproduced=c.reproduced)
        x = resolve(r, c.bundle)
        assert x.outcome in OUTCOMES and x.next_steps, (c.bundle.case_id, x)


def test_gate_codes_drive_steps_not_prose():
    from finance.recovery import AvoidanceResult, ClaimFacts, assess
    f = ClaimFacts("x", "cut_in", "Slight", "unknown", "unknown", False, None, 30_000, None, "unknown")
    a = assess(f, [AvoidanceResult("a", .9, (.85, .95))])
    for c in ("ENGAGEMENT_UNVERIFIED", "ODD_UNKNOWN", "NOT_REPRODUCED", "ONE_MODEL", "SOFTWARE_UNCONFIRMED"):
        assert c in a.codes


def test_every_finance_code_is_mapped_or_declared_informational():
    """Drift guard: a code added in finance/recovery.py must get a step (or be declared informational) here."""
    import re
    from pathlib import Path
    from insurance.resolution import INFORMATIONAL_CODES, _STEP_FOR_CODE
    src = (Path(__file__).resolve().parent.parent / "finance" / "recovery.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'(?:codes\.append\(|c\.append\(|codes=\[[^\]]*?)"([A-Z][A-Z0-9_]+)"', src))
    emitted |= set(re.findall(r'"([A-Z][A-Z0-9_]{5,})"', src.split("def _codes")[1].split("def _claim_value")[0]))
    emitted -= {"SGO"}
    missing = {c for c in emitted if c not in _STEP_FOR_CODE and c not in INFORMATIONAL_CODES}
    assert not missing, f"codes without a resolution step: {missing}"


def test_new_codes_become_steps():
    from finance.recovery import AvoidanceResult, ClaimFacts, assess
    from insurance.resolution import _gate_steps
    f = ClaimFacts("x", "cut_in", "Slight", "engaged_verified", "inside", True, (0, 0), None, None, "compliant")
    a = assess(f, [AvoidanceResult("a", .9, (.85, .95)), AvoidanceResult("b", .3, (.25, .35))])
    assert "MODELS_DISAGREE" in a.codes and any("50%" in s.action for s in _gate_steps(a.codes))
