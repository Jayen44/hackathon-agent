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
    base = dict(claim_id="TEST-1", crash_type="cut_in", injury_severity="Property Damage, No Injury",
                engagement_status="Verified Engaged", within_odd="Yes", reproduced=True,
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


def test_contributory_negligence_reduces_share():
    a = r.assess(facts(third_party_share=(0.4, 0.6)), BOTH_HIGH)
    assert a.av_share.low == pytest.approx(0.78 * 0.4)
    assert a.av_share.high == pytest.approx(0.98 * 0.6)


@pytest.mark.parametrize("kw", [dict(engagement_status="Alleged Engaged"),
                                dict(within_odd="Unknown, see Narrative"),
                                dict(within_odd="Exiting ODD"),
                                dict(reproduced=False)])
def test_unverified_facts_block_pursue(kw):
    assert r.assess(facts(**kw), BOTH_HIGH).decision == "pull_logs_first"


def test_not_engaged_is_not_an_av_recovery():
    a = r.assess(facts(engagement_status="Verified Not Engaged"), BOTH_HIGH)
    assert a.decision == "not_av_recovery" and a.expected_recovery is None


def test_unsourced_value_refuses_to_price():
    a = r.assess(facts(paid_claim_gbp=None, injury_severity="Moderate With Hospitalization"), BOTH_HIGH)
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


def test_severity_table_uses_exact_sgo_values():
    assert tables.claim_value_for_severity("Minor Without Hospitalization").priced
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
    a3 = r.assess(facts(claim_id="C", injury_severity="Moderate With Hospitalization", paid_claim_gbp=None), BOTH_HIGH)
    assert [a.claim_id for a in r.rank([a3, a2, a1])] == ["A", "B", "C"]
    m = r.recoverability_map([a1, a2, a3])
    assert m["cut_in"].mid == pytest.approx(a1.expected_recovery.mid + a2.expected_recovery.mid)


def test_fmt_gbp():
    assert r.fmt_gbp(12345.6) == "£12,346" and r.fmt_gbp(-500) == "-£500"


def test_serious_and_fatal_are_priced_with_sources():
    s = tables.claim_value_for_severity("Serious With Hospitalization")
    assert s.priced and (s.low, s.high) == (5_750, 533_720) and "JCG 18th" in s.source
    f = tables.claim_value_for_severity("Fatality")
    assert f.priced and (f.low, f.high) == (15_120, 15_120 + 31_460) and "s.1A(3)" in f.source


def test_fatal_claim_prices_end_to_end_on_intermediate_track():
    a = r.assess(facts(injury_severity="Fatality", paid_claim_gbp=None, legal_cost_gbp=None), BOTH_HIGH)
    assert a.decision in ("pursue", "pull_logs_first", "dont_pursue") and a.expected_recovery is not None


def test_serious_range_above_100k_needs_multi_track_costs():
    a = r.assess(facts(injury_severity="Serious With Hospitalization", paid_claim_gbp=None,
                       legal_cost_gbp=None), BOTH_HIGH)
    assert a.decision == "cannot_price" and "multi-track" in a.reasons[0]
