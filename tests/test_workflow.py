"""Reconstruction uncertainty, provenance, ledger, deadline watch, sign-off and the HTML claims queue."""
from datetime import date
from pathlib import Path

import pytest

from insurance.bridge import assess_bundle
from insurance.bundle import Conflict, load_bundle_file
from insurance.counterfactual import KinematicEstimator
from insurance.ledger import changes, record
from insurance.portfolio import default_estimators, run
from insurance.queue_html import render_queue
from insurance.resolution import resolve
from insurance.uncertainty import PerturbedEstimator, ReconError
from insurance.watch import watch

EX = Path(__file__).resolve().parent.parent / "insurance" / "examples"
TODAY = date(2027, 2, 1)


def _b(name):
    return load_bundle_file(EX / f"{name}.json")


def test_recon_error_widens_but_keeps_nominal():
    c = Conflict("h", 0.0, 13.4, 30.0, 0.0, 0.7)
    base = KinematicEstimator(n=300)
    nominal = base.estimate(c)
    wide = PerturbedEstimator(base, ReconError.uniform(0.15)).estimate(c)
    assert wide.p_avoid == nominal.p_avoid and wide.p_range is not None
    lo, hi = wide.p_range
    assert lo <= nominal.p_avoid <= hi and hi - lo > 0
    assert PerturbedEstimator(base, ReconError()).estimate(c).p_range is None


def test_recon_error_validation_and_bridge_interval():
    with pytest.raises(ValueError):
        ReconError.uniform(1.2)
    b = _b("06_borderline_needs_review")
    plain = assess_bundle(b, estimators=default_estimators(), reproduced=True, today=TODAY)
    wide = assess_bundle(b, estimators=default_estimators(recon_error=0.15), reproduced=True, today=TODAY)
    if plain.recovery and wide.recovery:
        assert wide.recovery.p_avoid.low <= plain.recovery.p_avoid.low
        assert wide.recovery.p_avoid.high >= plain.recovery.p_avoid.high


def test_provenance_records_settings():
    r = assess_bundle(_b("21_pursue_cut_in"), estimators=default_estimators(recon_error=0.1), reproduced=True,
                      min_net_gbp=500, today=TODAY)
    p = r.provenance
    assert p["min_net_gbp"] == 500 and p["run_date"] == "2027-02-01" and p["policy"]["p_system_fell_short"] == 0.8
    assert any("recon error" in e for e in p["estimators"])


def test_ledger_reports_what_changed(tmp_path):
    led = tmp_path / "ledger.jsonl"
    b = _b("21_pursue_cut_in")
    r1 = assess_bundle(b, estimators=default_estimators(), reproduced=True, today=TODAY)
    x1 = resolve(r1, b)
    assert changes(led, r1, x1) == []                    # first run: nothing to compare
    record(led, r1, x1)
    r2 = assess_bundle(b, estimators=default_estimators(), reproduced=True, min_net_gbp=10**9, today=TODAY)
    x2 = resolve(r2, b)
    diff = changes(led, r2, x2)
    assert any("decision" in d for d in diff) and any("run settings" in d for d in diff)


def test_watch_sorts_by_urgency():
    rows = watch(EX, date(2029, 2, 1))
    assert rows and "URGENT" in rows[0][1]
    assert watch(EX, date(2026, 1, 1), within_days=10) == []


def test_sign_off_roles():
    b = _b("21_pursue_cut_in")
    r = assess_bundle(b, estimators=default_estimators(), reproduced=True, today=TODAY)
    x = resolve(r, b)
    assert x.outcome == "PURSUE" and "counsel" in x.sign_off and "claims manager" in x.sign_off


def test_queue_html_is_escaped_and_complete():
    cases = [(_b("21_pursue_cut_in"), True), (_b("02_human_driving_manual"), True)]
    results = run(cases)
    page = render_queue(results, TODAY)
    assert page.count("<tr>") == 3 and "PURSUE" in page and "MOTOR_CLAIM" in page and "<script" not in page
    results[0].verdict.case_id = "<script>x</script>"
    assert "<script>x" not in render_queue(results, TODAY)
