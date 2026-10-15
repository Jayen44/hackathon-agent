"""Tests for finance/. Fixtures below are made-up test values, not real claims or sourced figures."""
import pytest

from finance import recovery as r
from finance import tables

BOTH_HIGH = [r.AvoidanceResult("careful_a", 0.85, (0.78, 0.91)),
             r.AvoidanceResult("careful_b", 0.95, (0.90, 0.98))]
SPLIT = [r.AvoidanceResult("careful_a", 0.20, (0.12, 0.30)),
         r.AvoidanceResult("careful_b", 0.90, (0.84, 0.95))]
BOTH_LOW = [r.AvoidanceResult("careful_a", 0.02, (0.00, 0.03)),
            r.AvoidanceResult("careful_b", 0.02, (0.01, 0.03))]


def facts(**kw):
    base = dict(claim_id="TEST-1", crash_type="cut_in", injury_severity="Damage only",
                engagement_status="engaged_verified", within_odd="inside", reproduced=True,
                paid_claim_gbp=50_000, legal_cost_gbp=(2_000, 6_000))
    return r.ClaimFacts(**{**base, **kw})


def test_clear_case_is_pursued_with_gbp_range():
    a = r.assess(facts(), BOTH_HIGH)
    assert a.decision == "pursue"
    assert a.expected_recovery.low == pytest.approx(0.78 * 50_000 - 6_000)
    assert a.expected_recovery.high == pytest.approx(0.98 * 50_000 - 2_000)
    assert a.disclaimer


def test_models_disagreeing_means_pull_logs():
    a = r.assess(facts(), SPLIT, min_net_gbp=10_000)
    assert a.decision == "pull_logs_first"
    assert any("straddles" in x for x in a.reasons)


def test_careful_driver_would_also_crash_means_dont_pursue():
    assert r.assess(facts(), BOTH_LOW).decision == "dont_pursue"


def test_contributory_negligence_reduces_share_of_a_table_value():
    a = r.assess(facts(injury_severity="Fatal", paid_claim_gbp=None, third_party_share=(0.4, 0.6)), BOTH_HIGH)
    assert a.av_share.low == pytest.approx(0.78 * 0.4)
    assert a.av_share.high == pytest.approx(0.98 * 0.6)


def test_paid_amount_is_already_net_of_contributory_negligence():
    a = r.assess(facts(third_party_share=(0.4, 0.6)), BOTH_HIGH)
    assert a.av_share.low == pytest.approx(0.78) and a.decision == "pursue"
    assert any("not applied again" in x for x in a.reasons)


def test_unassessed_contributory_negligence_blocks_pursue_on_table_values():
    a = r.assess(facts(injury_severity="Fatal", paid_claim_gbp=None), BOTH_HIGH)
    assert a.decision == "pull_logs_first" and a.av_share.low == 0
    assert any("not assessed" in x for x in a.reasons)


@pytest.mark.parametrize("status", ["unauthorised_alteration", "safety_update_missing"])
def test_s4_software_points_recovery_at_the_insured(status):
    a = r.assess(facts(software_status=status), BOTH_HIGH)
    assert a.decision == "not_av_recovery" and "s.4(4)" in a.reasons[0]


def test_unknown_software_status_is_flagged_not_blocking():
    a = r.assess(facts(), BOTH_HIGH)
    assert a.decision == "pursue" and any("AEVA s.4" in x for x in a.reasons)
    assert r.assess(facts(software_status="compliant"), BOTH_HIGH).reasons == [a.reasons[0]]


def test_bad_software_status_is_rejected():
    with pytest.raises(ValueError):
        r.assess(facts(software_status="fine"), BOTH_HIGH)


@pytest.mark.parametrize("kw", [dict(engagement_status="Verified Engaged"), dict(within_odd="Yes"),
                                dict(injury_severity="Property Damage, No Injury"), dict(engagement_status="engaged")])
def test_us_sgo_and_unknown_codes_are_rejected(kw):
    with pytest.raises(ValueError):
        r.assess(facts(**kw), BOTH_HIGH)


@pytest.mark.parametrize("kw", [dict(engagement_status="engaged_alleged"),
                                dict(within_odd="unknown"),
                                dict(within_odd="exiting"),
                                dict(reproduced=False)])
def test_unverified_facts_block_pursue(kw):
    assert r.assess(facts(**kw), BOTH_HIGH).decision == "pull_logs_first"


def test_not_engaged_is_not_an_av_recovery():
    a = r.assess(facts(engagement_status="not_engaged"), BOTH_HIGH)
    assert a.decision == "not_av_recovery" and a.expected_recovery is None


def test_unsourced_value_refuses_to_price():
    a = r.assess(facts(paid_claim_gbp=None, injury_severity="Unknown"), BOTH_HIGH)
    assert a.decision == "cannot_price" and a.expected_recovery is None


def test_legal_cost_from_pd45_when_not_supplied():
    a = r.assess(facts(legal_cost_gbp=None, paid_claim_gbp=20_000), BOTH_HIGH)
    # PD 45 Table 12: band 2 pre-issue 2,374 + 10% over 10k; band 4 trial 8,155 + 40% + 2,994 advocacy
    assert a.legal_cost.low == pytest.approx(3_374)
    assert a.legal_cost.high == pytest.approx(19_149)
    assert "Table 12" in a.sources[1]


def test_intermediate_track_costs():
    c = tables.legal_cost_for_claim(50_000, 80_000)
    assert c.low == pytest.approx(5_162 + 3_000)
    assert c.high == pytest.approx(29_938 + 17_600 + 1_445 + 5_988)


def test_multi_track_legal_cost_refuses_to_price():
    a = r.assess(facts(legal_cost_gbp=None, paid_claim_gbp=250_000), BOTH_HIGH)
    assert a.decision == "cannot_price"


def test_severity_table_uses_exact_uk_values():
    assert tables.claim_value_for_severity("Slight").priced
    with pytest.raises(ValueError):
        tables.claim_value_for_severity("minor")


def test_weakest_assumption_finds_the_flip():
    attacks = r.weakest_assumption(facts(), SPLIT, min_net_gbp=20_000)
    assert attacks[0].flips_decision
    assert attacks == sorted(attacks, key=lambda a: a.expected_recovery_mid)
    assert any("careful_a only" in a.assumption and a.flips_decision for a in attacks)


def test_rank_and_map():
    a1 = r.assess(facts(claim_id="A"), BOTH_HIGH)
    a2 = r.assess(facts(claim_id="B", paid_claim_gbp=10_000), BOTH_HIGH)
    a3 = r.assess(facts(claim_id="C", injury_severity="Unknown", paid_claim_gbp=None), BOTH_HIGH)
    assert [a.claim_id for a in r.rank([a3, a2, a1])] == ["A", "B", "C"]
    m = r.recoverability_map([a1, a2, a3])
    assert m["cut_in"].mid == pytest.approx(a1.expected_recovery.mid + a2.expected_recovery.mid)


def test_fmt_gbp():
    assert r.fmt_gbp(12345.6) == "£12,346" and r.fmt_gbp(-500) == "-£500"


def test_serious_and_fatal_are_priced_with_sources():
    s = tables.claim_value_for_severity("Serious")
    assert s.priced and (s.low, s.high) == (5_750, 533_720) and "JCG 18th" in s.source
    f = tables.claim_value_for_severity("Fatal")
    assert f.priced and (f.low, f.high) == (15_120, 15_120 + 31_460) and "s.1A(3)" in f.source


def test_fatal_claim_prices_end_to_end_on_intermediate_track():
    a = r.assess(facts(injury_severity="Fatal", paid_claim_gbp=None, legal_cost_gbp=None,
                       third_party_share=(0.0, 0.0)), BOTH_HIGH)
    assert a.decision in ("pursue", "pull_logs_first", "dont_pursue") and a.expected_recovery is not None


def test_serious_range_above_100k_needs_multi_track_costs():
    a = r.assess(facts(injury_severity="Serious", paid_claim_gbp=None,
                       legal_cost_gbp=None), BOTH_HIGH)
    assert a.decision == "cannot_price" and "multi-track" in a.reasons[0]


def test_legal_cost_centre_is_issued_and_settled_not_the_average():
    c = tables.legal_cost_for_claim(5_000, 5_000)
    assert c.mid == pytest.approx(2_374 + 0.20 * 5_000)          # PD 45 Table 12 B(2), band 2
    assert c.low < c.mid < (c.low + c.high) / 2
    i = tables.legal_cost_for_claim(50_000, 80_000)
    assert i.mid == pytest.approx(9_704 + 0.14 * 65_000)          # PD 45 Table 14 S4, band 2
    a = r.assess(facts(legal_cost_gbp=None, paid_claim_gbp=5_000), BOTH_HIGH)
    assert a.legal_cost.mid == pytest.approx(3_374)


# ---------------------------------------------------------------- review fixes (Jayen's finance changes)
def test_loser_pays_worst_case_is_losing_outright():
    a = r.assess(facts(cost_shift_risk=True), BOTH_HIGH)
    assert a.expected_recovery.low == pytest.approx(-2 * 6_000)   # our high cost + theirs, nothing recovered
    assert a.expected_recovery.mid == r.assess(facts(), BOTH_HIGH).expected_recovery.mid


def test_early_returns_carry_codes():
    assert r.assess(facts(engagement_status="not_engaged"), BOTH_HIGH).codes == ["NOT_ENGAGED"]
    assert r.assess(facts(software_status="safety_update_missing"), BOTH_HIGH).codes == ["S4_SOFTWARE_BREACH"]
    assert r.assess(facts(paid_claim_gbp=None, injury_severity="Unknown"), BOTH_HIGH).codes == ["NO_SOURCED_VALUE"]
    assert r.assess(facts(paid_claim_gbp=250_000, legal_cost_gbp=None), BOTH_HIGH).codes == ["NO_SOURCED_LEGAL_COST"]


@pytest.mark.parametrize("kw,code", [
    (dict(engagement_status="engaged_alleged"), "ENGAGEMENT_UNVERIFIED"),
    (dict(within_odd="outside"), "ODD_OUTSIDE"),
    (dict(within_odd="unknown"), "ODD_UNKNOWN"),
    (dict(reproduced=False), "NOT_REPRODUCED"),
    (dict(paid_claim_gbp=None, injury_severity="Fatal"), "CN_NOT_ASSESSED"),
])
def test_every_gate_has_a_code(kw, code):
    a = r.assess(facts(**kw), BOTH_HIGH)
    assert a.decision == "pull_logs_first" and code in a.codes
    gate_codes = {"ENGAGEMENT_UNVERIFIED", "ODD_OUTSIDE", "ODD_UNKNOWN", "NOT_REPRODUCED", "CN_NOT_ASSESSED", "ONE_MODEL"}
    gate_reasons = [x for x in a.reasons if x in r._gates(facts(**kw)) or "not assessed" in x]
    assert len(gate_reasons) == len(gate_codes & set(a.codes))


def test_what_if_bounds_match_validate_facts():
    with pytest.raises(r.ChangeError):
        r.apply_change(facts(), BOTH_HIGH, {"legal_cost_low": 0, "legal_cost_high": 0})
