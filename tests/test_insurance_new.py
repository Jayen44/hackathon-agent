"""Tests for: new examples (11-20), AEVA s.3(2)/s.4 rules, hazard kinds, synthetic bundles, portfolio, gap audit."""
import copy
import json
from pathlib import Path

import pytest

from insurance import gaps, portfolio, synth_bundles
from insurance.bundle import BundleError, load_bundle, load_bundle_file
from insurance.counterfactual import KinematicEstimator
from insurance.engine import decide

EX = Path(__file__).resolve().parent.parent / "insurance" / "examples"


def raw(name):
    return json.loads((EX / f"{name}.json").read_text(encoding="utf-8"))


def verdict(name):
    return decide(load_bundle_file(EX / f"{name}.json"))


@pytest.mark.parametrize("name,liable,code", [
    ("11_no_collision", "NO_FAULT_DRIVING", "outcome.no_collision"),
    ("12_missing_conflict", "NEEDS_REVIEW", "cf.no_conflict"),
    ("13_unapproved_software", "TECH_COMPANY", "software.unapproved"),
    ("14_human_took_control_in_time", "HUMAN_DRIVER", "handover.human_took_control"),
    ("15_lead_braking_avoidable", "TECH_COMPANY", "cf.system_fell_short"),
    ("16_lead_braking_unavoidable", "NO_FAULT_DRIVING", "cf.unavoidable"),
    ("17_cut_in_avoidable", "TECH_COMPANY", "cf.system_fell_short"),
    ("18_cut_in_unavoidable", "NO_FAULT_DRIVING", "cf.unavoidable"),
    ("19_s4_unauthorised_software_change", "HUMAN_DRIVER", "law.s4_software_exclusion"),
    ("20_s3_2_engaged_when_inappropriate", "TECH_COMPANY", "cf.system_fell_short"),
])
def test_new_examples(name, liable, code):
    v = verdict(name)
    assert v.liable == liable
    assert v.steps[-1].code == code


def test_s4_points_recovery_at_the_insured_not_the_tech_company():
    v = verdict("19_s4_unauthorised_software_change")
    assert not v.recovery_case
    assert any("s.4" in e for e in v.exclusions) and v.review_items


def test_missed_safety_update_is_also_s4():
    d = raw("01_av_late_detection")
    d["vehicle"]["safety_update_missed"] = True
    v = decide(load_bundle(d))
    assert v.steps[-1].code == "law.s4_software_exclusion" and v.liable == "HUMAN_DRIVER"


def test_s3_2_only_excludes_the_person_in_charge_and_does_not_change_third_party_liability():
    base, flagged = verdict("01_av_late_detection"), verdict("20_s3_2_engaged_when_inappropriate")
    assert flagged.liable == base.liable == "TECH_COMPANY"
    assert any("s.3(2)" in e for e in flagged.exclusions) and not base.exclusions
    assert any(s.code == "law.s3_2_person_in_charge_negligence" for s in flagged.steps)


def test_s4_beats_unapproved_software():
    d = raw("13_unapproved_software")
    d["vehicle"]["unauthorised_software_change"] = True
    assert decide(load_bundle(d)).steps[-1].code == "law.s4_software_exclusion"


# ------------------------------------------------------------------ bundle validation for the new fields
@pytest.mark.parametrize("mutate", [
    lambda d: d["conflict"].update(kind="teleport"),
    lambda d: d["conflict"].update(kind="lead_braking", hazard_decel_mps2=0.0),
    lambda d: d["conflict"].update(hazard_decel_mps2=-1.0),
    lambda d: d["conflict"].update(t_in_path_s=-0.1),
])
def test_rejects_bad_hazard_fields(mutate):
    d = copy.deepcopy(raw("01_av_late_detection"))
    mutate(d)
    with pytest.raises(BundleError):
        load_bundle(d)


def test_crash_type_defaults_follow_the_hazard_kind():
    for name, ct in [("15_lead_braking_avoidable", "lead_vehicle_decel"), ("17_cut_in_avoidable", "cut_in"),
                     ("01_av_late_detection", "other")]:
        assert load_bundle_file(EX / f"{name}.json").conflict.crash_type == ct


# ------------------------------------------------------------------ synthetic bundles and portfolio
def test_synthetic_bundles_are_valid_deterministic_and_labelled():
    a, b = synth_bundles.generate_cases(20, 7), synth_bundles.generate_cases(20, 7)
    assert [c.bundle for c in a] == [c.bundle for c in b]
    assert all(c.bundle.synthetic for c in a)
    assert {c.bundle.conflict.kind for c in a} <= {"lead_braking", "cut_in"}
    assert len({c.bundle.case_id for c in a}) == 20
    assert synth_bundles.generate_cases(20, 8)[0].bundle != a[0].bundle


def test_alleged_engagement_becomes_a_log_gap_that_forces_review():
    from finance.recovery import engagement_code
    cases = synth_bundles.generate_cases(60, 3)
    alleged = [c for c in cases if engagement_code(c.source.facts.engagement_status) == "engaged_alleged"]
    verified = [c for c in cases if engagement_code(c.source.facts.engagement_status) == "engaged_verified"]
    assert alleged and verified, "seed should contain both verified and alleged engagement"
    for c in alleged:
        assert decide(c.bundle).steps[-1].code == "integrity.blocked"
    # Guard against silent code drift between finance/ and this generator: verified crashes must NOT be blocked
    fast = KinematicEstimator(n=100)
    assert all(decide(c.bundle, estimator=fast).steps[-1].code != "integrity.blocked" for c in verified)


def test_portfolio_prices_and_never_invents_a_figure():
    cases = [(c.bundle, c.reproduced) for c in synth_bundles.generate_cases(20, 7)]
    results = portfolio.run(cases)
    assert len(results) == 20
    for r in results:
        if r.recovery is not None and r.recovery.expected_recovery is not None:
            e = r.recovery.expected_recovery
            assert e.low <= e.mid <= e.high
        if r.recovery is not None and r.recovery.decision == "cannot_price":
            assert r.recovery.expected_recovery is None
    text = portfolio.render(results)
    assert "Recoverable by crash type" in text and "placeholder" in text


def test_single_estimator_keeps_the_bracket_gate_open():
    cases = [(c.bundle, True) for c in synth_bundles.generate_cases(10, 7)]
    for r in portfolio.run(cases, single=True):
        if r.recovery is not None and r.recovery.decision in ("pursue",):
            pytest.fail("one model must never reach 'pursue'")


# ------------------------------------------------------------------ gap audit
def test_every_expected_decision_path_has_an_example():
    """Fails the moment a path loses its example, or a new EXPECTED_PATH is added with no example."""
    missing = [g.id for g in gaps.audit() if g.id.startswith("path:") or g.id.startswith("scenario:")]
    assert missing == []


def test_audit_reports_only_other_peoples_open_work_or_unbuilt_deliverables():
    mine = [g for g in gaps.audit() if g.owner == "insurance"]
    assert mine == [], [g.id for g in mine]


def test_audit_detects_a_missing_path(monkeypatch):
    monkeypatch.setitem(gaps.EXPECTED_PATHS, "fake.never_exercised", "a path nobody covers")
    assert "path:fake.never_exercised" in [g.id for g in gaps.audit()]
