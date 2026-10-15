"""Bridge tests, including CONTRACT tests that fail if finance/ changes under us.

If a contract test fails after pulling Antonio's work, the bridge (insurance/bridge.py) needs
updating to match: tell him, don't edit finance/ to make the test pass.
"""
import copy
import dataclasses
import inspect
import json
from pathlib import Path

import pytest

from finance import recovery, tables
from insurance.bridge import (assess_bundle, claim_facts, engagement_status, software_status, to_avoidance_result,
                              wilson_ci90, within_odd_status)
from insurance.bundle import load_bundle, load_bundle_file
from insurance.counterfactual import KinematicEstimator

EX = Path(__file__).resolve().parent.parent / "insurance" / "examples"
LEGAL = (2000.0, 5000.0)  # TEST FIXTURE ONLY: finance/tables.py legal cost is still TODO


def bundle(name):
    return load_bundle_file(EX / f"{name}.json")


def raw(name):
    return json.loads((EX / f"{name}.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------- contract with finance/
def test_contract_avoidance_result_fields():
    assert [f.name for f in dataclasses.fields(recovery.AvoidanceResult)] == ["model", "p_avoid", "ci90"]


def test_contract_claim_facts_fields_we_fill():
    names = {f.name for f in dataclasses.fields(recovery.ClaimFacts)}
    assert {"claim_id", "crash_type", "injury_severity", "engagement_status", "within_odd", "reproduced",
            "third_party_share", "paid_claim_gbp", "legal_cost_gbp"} <= names
    required = {f.name for f in dataclasses.fields(recovery.ClaimFacts)
                if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING}
    assert required <= {"claim_id", "crash_type", "injury_severity", "engagement_status", "within_odd", "reproduced"}, \
        "finance/ added a new REQUIRED ClaimFacts field the bridge doesn't fill"


def test_contract_assess_signature():
    params = list(inspect.signature(recovery.assess).parameters)
    assert params[:2] == ["f", "avoidance"]


def test_contract_example_severities_are_valid_uk_values():
    for p in EX.glob("*.json"):
        sev = load_bundle_file(p).outcome.injury_severity
        assert sev in tables.CLAIM_VALUE_BY_UK_SEVERITY, f"{p.name}: {sev!r} not a finance/ UK severity key"


def test_contract_bridge_sends_finance_uk_codes():
    # The bridge sends finance's own codes (recovery.ENGAGEMENT / ODD / SOFTWARE), no legacy strings.
    assert engagement_status(bundle("01_av_late_detection")) == "engaged_verified"
    assert engagement_status(bundle("02_human_driving_manual")) == "not_engaged"
    assert within_odd_status(bundle("01_av_late_detection")) == "inside"
    assert within_odd_status(bundle("07_outside_odd")) == "outside"
    assert software_status(bundle("01_av_late_detection")) == "compliant"
    assert software_status(bundle("19_s4_unauthorised_software_change")) == "unauthorised_alteration"
    for p in EX.glob("*.json"):
        b = load_bundle_file(p)
        assert engagement_status(b) in recovery.ENGAGEMENT
        assert within_odd_status(b) in recovery.ODD
        assert software_status(b) in recovery.SOFTWARE


def test_contract_uk_severity_keys_are_the_stats19_values():
    assert set(tables.CLAIM_VALUE_BY_UK_SEVERITY) == {"Fatal", "Serious", "Slight", "Damage only", "Unknown"}


def test_contract_software_needs_positive_confirmation():
    d = raw("01_av_late_detection")
    d["vehicle"]["software_verified"] = False
    assert software_status(load_bundle(d)) == "unknown"          # an approved version alone is not enough
    d["vehicle"]["safety_update_missed"] = True
    assert software_status(load_bundle(d)) == "safety_update_missing"


def test_contract_third_party_share_none_means_not_assessed():
    f = claim_facts(bundle("01_av_late_detection"), reproduced=True)
    assert f.third_party_share is None                           # finance then gates 'pursue' (AEVA s.3(1))
    d = raw("01_av_late_detection")
    d["outcome"]["third_party_share"] = [0.0, 0.2]
    assert claim_facts(load_bundle(d), reproduced=True).third_party_share == (0.0, 0.2)
    assert claim_facts(load_bundle(d), True, third_party_share=(0.1, 0.1)).third_party_share == (0.1, 0.1)


# ------------------------------------------------------------- bridge behaviour
def test_wilson_interval_properties():
    lo, hi = wilson_ci90(0.5, 100)
    assert 0 < lo < 0.5 < hi < 1
    assert wilson_ci90(0.5, 1000)[1] - wilson_ci90(0.5, 1000)[0] < hi - lo   # more samples -> tighter
    lo0, hi0 = wilson_ci90(0.0, 50)
    assert lo0 == 0.0 and hi0 > 0.0                                          # never claims certainty
    lo1, hi1 = wilson_ci90(1.0, 50)
    assert hi1 == 1.0 and lo1 < 1.0
    with pytest.raises(ValueError):
        wilson_ci90(0.5, 0)


def test_avoidance_result_carries_the_estimator_numbers():
    cf = KinematicEstimator().estimate(bundle("06_borderline_needs_review").conflict)
    r = to_avoidance_result("kinematic_placeholder", cf)
    assert r.p_avoid == cf.p_avoid and r.ci90[0] <= r.p_avoid <= r.ci90[1]


TWO_MODELS = {"a": KinematicEstimator(), "b": KinematicEstimator(seed=11)}


def test_tech_liable_case_gets_priced_in_gbp():
    d = raw("01_av_late_detection")
    d["outcome"]["paid_claim_gbp"] = 40000.0   # a claim big enough to clear the legal cost
    r = assess_bundle(load_bundle(d), legal_cost_gbp=LEGAL, estimators=TWO_MODELS, reproduced=True)
    assert r.verdict.liable == "TECH_COMPANY"
    rec = r.recovery
    assert rec.decision == "pursue", rec.reasons
    assert rec.expected_recovery.low <= rec.expected_recovery.mid <= rec.expected_recovery.high
    assert rec.p_avoid.mid > 0.9


def test_small_clean_claim_is_pursued_pre_issue_with_downside_stated():
    # Table-priced minor injury (about GBP 4-5k), clear liability, no gates: finance decides on the central case
    # (open with a pre-action letter) and states the trial-and-lose worst case instead of vetoing on it.
    r = assess_bundle(bundle("01_av_late_detection"), legal_cost_gbp=LEGAL, estimators=TWO_MODELS, reproduced=True)
    assert r.verdict.liable == "TECH_COMPANY"
    rec = r.recovery
    assert rec.decision == "pursue", rec.reasons
    assert rec.expected_recovery.mid > 0 >= rec.expected_recovery.low
    assert "LITIGATION_DOWNSIDE" in rec.codes and any("pre-action letter" in x for x in rec.reasons)
    assert "CN_NOT_ASSESSED" in rec.codes                       # stated caveat, not a gate
    assert any("SI 2025/615" in s for s in rec.sources)


def test_one_model_or_unreproduced_holds_at_pull_logs():
    r = assess_bundle(bundle("01_av_late_detection"), legal_cost_gbp=LEGAL)  # one model, reproduced=False
    assert r.recovery.decision == "pull_logs_first"
    assert any("one careful-driver model" in x for x in r.recovery.reasons)
    assert any("did not reproduce" in x for x in r.recovery.reasons)
    assert any("one careful-driver model" in n for n in r.notes)


def test_legal_cost_todo_means_cannot_price_not_a_guess():
    # Legal costs up to GBP 100k come from CPR PD 45; above that (multi-track) they are still TODO.
    d = raw("01_av_late_detection")
    d["outcome"]["paid_claim_gbp"] = 250000.0
    r = assess_bundle(load_bundle(d))  # no legal cost supplied
    assert r.recovery.decision == "cannot_price"
    assert r.recovery.expected_recovery is None


def test_unavoidable_crash_is_not_worth_pursuing():
    r = assess_bundle(bundle("05_unavoidable_close_cutin"), legal_cost_gbp=LEGAL, reproduced=True,
                      estimators={"a": KinematicEstimator(), "b": KinematicEstimator(seed=3)})
    assert r.verdict.liable == "NO_FAULT_DRIVING"
    assert r.recovery.decision == "dont_pursue"


@pytest.mark.parametrize("name,fragment", [
    ("02_human_driving_manual", "human driver"),
    ("03_handover_ignored_by_human", "human driver"),
    ("08_integrity_failure", "integrity"),
])
def test_cases_that_must_not_be_priced(name, fragment):
    r = assess_bundle(bundle(name), legal_cost_gbp=LEGAL)
    assert r.recovery is None
    assert fragment in r.notes[0].lower()


def test_no_collision_or_no_conflict_is_not_priced():
    d = raw("01_av_late_detection")
    d["outcome"]["collided"] = False
    assert assess_bundle(load_bundle(d)).recovery is None
    d = raw("01_av_late_detection")
    d["conflict"] = None
    assert assess_bundle(load_bundle(d)).recovery is None


def test_outside_odd_is_gated_by_finance():
    r = assess_bundle(bundle("07_outside_odd"), legal_cost_gbp=LEGAL, reproduced=True,
                      estimators={"a": KinematicEstimator(), "b": KinematicEstimator(seed=5)})
    assert r.recovery.decision == "pull_logs_first"
    assert any("outside ODD" in x for x in r.recovery.reasons)


def test_paid_claim_beats_the_table():
    d = copy.deepcopy(raw("01_av_late_detection"))
    d["outcome"]["paid_claim_gbp"] = 12000.0
    r = assess_bundle(load_bundle(d), legal_cost_gbp=LEGAL, reproduced=True,
                      estimators={"a": KinematicEstimator(), "b": KinematicEstimator(seed=2)})
    assert r.recovery.claim_value.low == r.recovery.claim_value.high == 12000.0


def test_unknown_severity_cannot_be_priced():
    d = copy.deepcopy(raw("01_av_late_detection"))
    d["outcome"].pop("injury_severity")
    r = assess_bundle(load_bundle(d), legal_cost_gbp=LEGAL, reproduced=True)
    assert r.recovery.decision == "cannot_price"


def test_claim_facts_roundtrip():
    f = claim_facts(bundle("05_unavoidable_close_cutin"), reproduced=True)
    assert (f.claim_id, f.crash_type, f.injury_severity) == (
        "05_unavoidable_close_cutin", "cut_in", "Slight")
