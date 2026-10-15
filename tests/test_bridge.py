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
from insurance.bridge import (assess_bundle, claim_facts, engagement_status, to_avoidance_result,
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


def test_contract_example_severities_are_valid_sgo_values():
    for p in EX.glob("*.json"):
        sev = load_bundle_file(p).outcome.injury_severity
        assert sev in tables.CLAIM_VALUE_BY_SGO_SEVERITY, f"{p.name}: {sev!r} not a finance/ severity key"


def test_contract_engagement_and_odd_strings_match_finance_gates():
    # finance/_gates() compares against these exact strings.
    assert engagement_status(bundle("01_av_late_detection")) == "Verified Engaged"
    assert engagement_status(bundle("02_human_driving_manual")) == "Verified Not Engaged"
    assert within_odd_status(bundle("01_av_late_detection")) == "Yes"
    assert within_odd_status(bundle("07_outside_odd")) == "No, see Narrative"
    # finance/ normalises these legacy SGO strings to its UK codes; check the mapping, not source text.
    assert recovery.engagement_code("Verified Engaged") == "engaged_verified"
    assert recovery.engagement_code("Verified Not Engaged") == "not_engaged"
    assert recovery.odd_code("Yes") == "inside" and recovery.odd_code("No, see Narrative") == "outside"


# Verbatim from the official NHTSA "SGO-2021-01 Data Element Definitions" (dictionary dated 17 Aug 2026):
# field 22 (engagement status), field 73 (Highest Injury Severity Alleged), field 113 (Within ODD?).
SGO_ENGAGEMENT = {"Verified Engaged", "Alleged Engaged", "Verified Not Engaged", "Unknown, see Narrative"}
SGO_ODD = {"Yes", "No, see Narrative", "Unknown, see Narrative", "Exiting ODD"}
SGO_SEVERITY = {"Fatality", "Serious With Hospitalization", "Serious Without Hospitalization",
                "Moderate With Hospitalization", "Moderate Without Hospitalization",
                "Minor With Hospitalization", "Minor Without Hospitalization",
                "No Injuries Reported", "Property Damage, No Injury", "Unknown"}


def test_finance_severity_keys_are_exactly_the_official_sgo_values():
    assert set(tables.CLAIM_VALUE_BY_SGO_SEVERITY) == SGO_SEVERITY


def test_bridge_only_emits_official_sgo_strings():
    seen_eng, seen_odd = set(), set()
    for p in EX.glob("*.json"):
        b = load_bundle_file(p)
        seen_eng.add(engagement_status(b))
        seen_odd.add(within_odd_status(b))
    assert seen_eng <= SGO_ENGAGEMENT and seen_odd <= SGO_ODD
    d = raw("01_av_late_detection")
    d["vehicle"]["odd_inside"] = None
    assert within_odd_status(load_bundle(d)) in SGO_ODD
    assert load_bundle(d).outcome.injury_severity in SGO_SEVERITY


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


def test_small_claim_is_eaten_by_legal_cost():
    # Table-priced minor injury (about GBP 4-5k) against GBP 2-5k legal cost: finance/ must not say "pursue".
    r = assess_bundle(bundle("01_av_late_detection"), legal_cost_gbp=LEGAL, estimators=TWO_MODELS, reproduced=True)
    assert r.verdict.liable == "TECH_COMPANY"
    assert r.recovery.decision == "pull_logs_first"
    assert any("straddles" in x for x in r.recovery.reasons)
    assert any("SI 2025/615" in s for s in r.recovery.sources)


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
        "05_unavoidable_close_cutin", "cut_in", "Minor Without Hospitalization")
