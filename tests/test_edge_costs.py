"""Edge cases found by the cost simulation: input validation and the track-limit warning."""
import pytest

from finance.recovery import AvoidanceResult, ClaimFacts, assess


def _av(p=0.9):
    return [AvoidanceResult("a", p, (p - 0.05, min(1, p + 0.05))), AvoidanceResult("b", p, (p - 0.05, min(1, p + 0.05)))]


def _f(**k):
    d = dict(claim_id="x", crash_type="cut_in", injury_severity="Slight", engagement_status="engaged_verified",
             within_odd="inside", reproduced=True, third_party_share=(0, 0), software_status="compliant")
    d.update(k)
    return ClaimFacts(**d)


@pytest.mark.parametrize("kw", [
    {"paid_claim_gbp": 0}, {"paid_claim_gbp": -100}, {"paid_claim_gbp": float("nan")},
    {"legal_cost_gbp": (0, 0)}, {"legal_cost_gbp": (-500, 100)}, {"legal_cost_gbp": (5000, 2000)},
    {"third_party_share": (0.8, 0.2)}, {"third_party_share": (0, 1.2)},
])
def test_bad_inputs_rejected_with_clear_error(kw):
    with pytest.raises(ValueError):
        assess(_f(**kw), _av())


def test_near_track_limit_warned():
    r = assess(_f(paid_claim_gbp=24_999), _av())
    assert any("track limit" in x for x in r.reasons)
    assert not any("track limit" in x for x in assess(_f(paid_claim_gbp=60_000), _av()).reasons)


def test_multitrack_hint_is_actionable():
    r = assess(_f(injury_severity="Serious"), _av())
    assert r.decision == "cannot_price" and any("legal_cost_gbp" in x for x in r.reasons)


def test_cost_shift_widens_worst_case_only():
    base = assess(_f(paid_claim_gbp=60_000), _av()).expected_recovery
    risk = assess(_f(paid_claim_gbp=60_000, cost_shift_risk=True), _av())
    ev = risk.expected_recovery
    assert ev.low < base.low and ev.mid == base.mid and ev.high == base.high
    assert any("CPR 44.2" in x for x in risk.reasons)
    assert not any("CPR 44.2" in x for x in assess(_f(paid_claim_gbp=60_000), _av()).reasons)


def test_serious_fatal_table_values_flagged_general_damages_only():
    assert any("general damages only" in x for x in assess(_f(injury_severity="Fatal"), _av()).reasons)
    assert any("general damages only" in x for x in assess(_f(injury_severity="Serious"), _av()).reasons)
    assert not any("general damages only" in x for x in assess(_f(injury_severity="Fatal", paid_claim_gbp=30_000), _av()).reasons)
