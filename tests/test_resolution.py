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
