"""One vocabulary for claim outcomes, and the single API entry point (insurance/api.py)."""
import json
from datetime import date
from pathlib import Path

import pytest

from finance.recovery import Decision
from insurance.api import price_claim
from insurance.vocab import FINANCE_TO_OUTCOME, LEGACY_FLEET_TO_OUTCOME, OUTCOMES, normalise

EX = Path(__file__).resolve().parent.parent / "insurance" / "examples"
TODAY = date(2027, 2, 1)


def _raw(name):
    return json.loads((EX / f"{name}.json").read_text(encoding="utf-8"))


def test_every_finance_decision_and_legacy_label_maps_to_an_outcome():
    import typing
    decisions = set(typing.get_args(Decision))
    assert decisions == set(FINANCE_TO_OUTCOME), "finance added/removed a decision: update insurance/vocab.py"
    assert set(FINANCE_TO_OUTCOME.values()) <= set(OUTCOMES) and set(LEGACY_FLEET_TO_OUTCOME.values()) <= set(OUTCOMES)
    assert normalise("get_more_evidence") == "PULL_LOGS" and normalise("PURSUE") == "PURSUE"
    with pytest.raises(ValueError):
        normalise("maybe")


def test_resolution_outcome_matches_the_vocab_mapping_for_priced_claims():
    from insurance.bridge import assess_bundle
    from insurance.bundle import load_bundle_file
    from insurance.resolution import resolve
    for p in sorted(EX.glob("*.json")):
        b = load_bundle_file(p)
        r = assess_bundle(b, today=TODAY)
        if r.recovery is not None:
            assert resolve(r, b).outcome == FINANCE_TO_OUTCOME[r.recovery.decision], b.case_id


def test_price_claim_returns_outcome_steps_deadline_and_no_new_numbers():
    out = price_claim(_raw("21_pursue_cut_in"), today=TODAY)
    assert out["outcome"] == "PURSUE" and out["decision"] == "pursue" and out["next_steps"] and out["sign_off"]
    assert out["deadline"]["due"] == "2029-03-01" and out["priced"] and out["recovery"]["expected_recovery"]["mid"] > 0
    assert out["outcome"] in OUTCOMES


def test_price_claim_accepts_drivers_from_the_caller_and_handles_unpriced_and_bad_bundles():
    d = _raw("21_pursue_cut_in")
    drivers = {k: {"p_avoid": p, "avoids_at_p50": p > 0.5, "median_impact_speed_mps": 0.0, "n_samples": 300,
                   "model": "caller"} for k, p in (("careful_a", 0.0), ("careful_b", 0.0))}
    assert price_claim(d, drivers=drivers, reproduced=True, today=TODAY)["outcome"] == "SETTLE_NO_RECOVERY"
    assert price_claim(_raw("02_human_driving_manual"), today=TODAY)["outcome"] == "MOTOR_CLAIM"
    bad = dict(d, schema_version="9")
    out = price_claim(bad)
    assert out["outcome"] == "NEEDS_INPUTS" and not out["priced"]


def test_p_liable_flows_into_the_priced_result():
    d = _raw("21_pursue_cut_in")
    plain = price_claim(d, today=TODAY)["recovery"]["p_avoid"]["mid"]
    d["legal"]["p_liable_to_victim"] = [0.4, 0.5, 0.6]
    assert price_claim(d, today=TODAY)["recovery"]["p_avoid"]["mid"] == pytest.approx(plain * 0.5)
