"""Tests for claimsim/. All inputs are illustrative, not real claims."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from claimsim import distributions as dist
from claimsim.agent_tools import TOOL_DEFINITION, make_tool, simulate_claim_cost
from claimsim.liability import attributable, recoverable
from claimsim.models import InputError, LiabilityScenario, PolicyTerms, claim_from_dict
from claimsim.policy import UKMotorRules
from claimsim.sensitivity import one_way, rank_correlation
from claimsim.simulation import simulate, stability

EXAMPLE = json.loads((Path(__file__).parents[1] / "claimsim/examples/illustrative_claim.json").read_text())
N = 4_000


def ex(**kw):
    d = copy.deepcopy(EXAMPLE)
    d.update(kw)
    return d


def claim(**kw):
    return claim_from_dict(ex(**kw))


def terms(**kw):
    base = dict(own_damage_covered=True, own_damage_excess=500, own_damage_limit=None,
                third_party_property_limit=None, bodily_injury_limit=None)
    return PolicyTerms(**{**base, **kw})


def arr(**kw):
    base = {c: np.array([0.0]) for c in ("insured_vehicle_repair", "third_party_vehicle_repair", "bodily_injury",
                                         "third_party_property", "other")}
    return base | {k: np.array([float(v)]) for k, v in kw.items()}


# ---------------------------------------------------------------- deterministic policy maths (hand-calculated)
def test_excess_applied_to_own_damage_only():
    r = UKMotorRules().apply(arr(insured_vehicle_repair=4_500, third_party_vehicle_repair=7_200), terms())
    assert r.paid["insured_vehicle_repair"][0] == 4_000           # 4,500 - 500 excess
    assert r.insured_retained[0] == 500
    assert r.paid["third_party_vehicle_repair"][0] == 7_200      # no excess on third-party liability


def test_loss_below_excess_pays_nothing():
    r = UKMotorRules().apply(arr(insured_vehicle_repair=300), terms())
    assert r.paid["insured_vehicle_repair"][0] == 0 and r.insured_retained[0] == 300


def test_own_damage_limit_caps_after_excess():
    r = UKMotorRules().apply(arr(insured_vehicle_repair=20_000), terms(own_damage_limit=15_000))
    assert r.paid["insured_vehicle_repair"][0] == 15_000          # min(19,500, 15,000)
    assert r.insured_retained[0] == 5_000


def test_combined_property_limit_split_pro_rata():
    r = UKMotorRules().apply(arr(third_party_vehicle_repair=800_000, third_party_property=400_000),
                             terms(third_party_property_limit=1_000_000))
    assert r.paid["third_party_vehicle_repair"][0] == pytest.approx(666_666.67, abs=0.01)   # 800k x 1m/1.2m
    assert r.paid["third_party_property"][0] == pytest.approx(333_333.33, abs=0.01)


def test_bodily_injury_limit_sublimit_and_exclusion():
    rules = UKMotorRules()
    assert rules.apply(arr(bodily_injury=50_000), terms(bodily_injury_limit=20_000)).paid["bodily_injury"][0] == 20_000
    assert rules.apply(arr(bodily_injury=50_000), terms(sublimits={"bodily_injury": 10_000})).paid["bodily_injury"][0] == 10_000
    r = rules.apply(arr(third_party_property=2_000), terms(excluded_categories=("third_party_property",)))
    assert r.covered["third_party_property"][0] == 0 and r.paid["third_party_property"][0] == 0


def test_liability_share_scales_third_party_loss_not_own_damage():
    s = LiabilityScenario("half", 0.5, 0.0, 0.5)
    a = attributable(s, arr(insured_vehicle_repair=4_500, third_party_vehicle_repair=7_200))
    assert a["insured_vehicle_repair"][0] == 4_500 and a["third_party_vehicle_repair"][0] == 3_600


def test_recoverable_excludes_the_excess_and_never_exceeds_payment():
    paid = arr(insured_vehicle_repair=4_000, third_party_vehicle_repair=3_600)
    r = recoverable(LiabilityScenario("tp", 0.0, 0.0, 1.0), paid)
    assert r["third_party_insurer"][0] == 4_000                   # the insurer's outlay, not the 4,500 incl. excess
    r = recoverable(LiabilityScenario("mix", 0.25, 0.25, 0.5), paid)
    assert r["third_party_insurer"][0] == 2_000                   # 50% of own outlay
    assert r["manufacturer"][0] == pytest.approx(0.25 * 4_000 + 0.5 * 3_600)   # AV part of own + of TP paid
    assert r["third_party_insurer"][0] + r["manufacturer"][0] <= 4_000 + 3_600


# ---------------------------------------------------------------- simulation
def test_reproducible_with_seed_and_different_without():
    a = simulate(claim(), n=N, seed=1)["scenarios"]["B_insured_50pct_liable"]
    b = simulate(claim(), n=N, seed=1)["scenarios"]["B_insured_50pct_liable"]
    c = simulate(claim(), n=N, seed=2)["scenarios"]["B_insured_50pct_liable"]
    assert a == b and a["expected_net_exposure"] != c["expected_net_exposure"]


def test_reconciliation_and_percentile_order_in_every_scenario():
    r = simulate(claim(), n=N, seed=3)
    for s in r["scenarios"].values():
        assert s["reconciliation"]["passed"], s["reconciliation"]
        p = s["net_exposure_percentiles"]
        assert p["p50"] <= p["p90"] <= p["p95"] <= p["p99"]
        probs = list(s["prob_net_exposure_exceeds"].values())
        assert probs == sorted(probs, reverse=True)


def test_scenario_ordering_and_no_double_counting():
    s = simulate(claim(), n=N, seed=4)["scenarios"]
    a, b, c = (s[k] for k in ("A_insured_not_liable", "B_insured_50pct_liable", "C_insured_fully_liable"))
    assert a["breakdown"]["third_party_vehicle_repair"]["insurer_payment"] == 0
    assert a["expected_insurer_payment"] < b["expected_insurer_payment"] < c["expected_insurer_payment"]
    assert c["expected_recoveries"] == 0                           # no-one else liable
    for x in (a, b, c):
        assert sum(v["insurer_payment"] for k, v in x["breakdown"].items() if k != "legal_and_handling") \
            == pytest.approx(x["expected_insurer_payment"])
        assert x["expected_insurer_payment"] <= x["expected_covered_loss"] <= x["expected_attributable_loss"] + 1e-6
    # gross economic loss is the same accident in every scenario; who pays differs
    assert a["expected_gross_loss"] == c["expected_gross_loss"] > c["expected_insurer_payment"]


def test_zero_loss_claim_costs_only_handling():
    z = claim(insured_repair_estimate=0, third_party_repair_estimate=0, injury_outcome="none",
              third_party_property_estimate=0)
    s = simulate(z, n=N, seed=5)["scenarios"]["C_insured_fully_liable"]
    handling = dist.load().raw["legal_and_handling"]["handling_fixed"]
    assert s["expected_gross_loss"] == 0 and s["expected_insurer_payment"] == 0 and s["expected_recoveries"] == 0
    assert s["expected_net_exposure"] == pytest.approx(handling)


def test_injury_two_stage_model():
    none = simulate(claim(injury_outcome="none"), n=N, seed=6)["scenarios"]["C_insured_fully_liable"]
    assert none["breakdown"]["bodily_injury"]["gross"] == 0
    known = simulate(claim(injury_outcome="known", injury_cost_estimate=20_000), n=20_000, seed=6)
    sig = dist.load().raw["injury"]["known_sigma"]
    assert known["scenarios"]["C_insured_fully_liable"]["breakdown"]["bodily_injury"]["gross"] == \
        pytest.approx(20_000 * np.exp(sig ** 2 / 2), rel=0.03)    # lognormal mean
    lo = simulate(claim(collision_severity="low"), n=N, seed=6, keep_arrays=True)["_arrays"]["draws"]
    hi = simulate(claim(collision_severity="high"), n=N, seed=6, keep_arrays=True)["_arrays"]["draws"]
    assert hi.drivers["injury_occurred"].mean() > 3 * lo.drivers["injury_occurred"].mean()


def test_recoveries_capped_even_when_certain():
    c = claim(third_party_recovery_probability=1.0, manufacturer_recovery_probability=1.0,
              recovery_probability_source="test fixture")
    r = simulate(c, n=N, seed=7, keep_arrays=True)["_arrays"]["per_scenario"]
    for x in r.values():
        for k in ("third_party_insurer", "manufacturer"):
            assert np.all(x[f"recovered.{k}"] <= x[f"recoverable.{k}"] + 1e-6)
        assert np.all(x["recoveries"] <= x["insurer_payment"] + 1e-6)


def test_unresolved_liability_is_conditional_only():
    r = simulate(claim(), n=N, seed=8)
    assert r["probability_weighted"] is None and "conditional" in r["conditional_only"]


def test_supplied_probabilities_give_a_weighted_mix():
    d = ex()
    for s, p in zip(d["scenarios"], (0.4, 0.3, 0.2, 0.1)):
        s.update(probability=p, probability_source="test fixture")
    r = simulate(claim_from_dict(d), n=20_000, seed=9)
    w = r["probability_weighted"]
    means = [s["expected_net_exposure"] for s in r["scenarios"].values()]
    expected = sum(p * m for p, m in zip((0.4, 0.3, 0.2, 0.1), means))
    assert w["expected_net_exposure"] == pytest.approx(expected, rel=0.05)
    assert w["reconciliation"]["passed"]


def test_stability_error_shrinks_with_more_iterations():
    st = stability(claim(), "B_insured_50pct_liable", ns=(2_500, 10_000, 40_000), seed=10)
    assert st[0]["se_expected"] > st[1]["se_expected"] > st[2]["se_expected"]
    assert abs(st[2]["expected_net_exposure"] - st[1]["expected_net_exposure"]) < 4 * st[1]["se_expected"]


# ---------------------------------------------------------------- validation
@pytest.mark.parametrize("bad", [
    dict(insured_repair_estimate=-1), dict(injury_outcome="maybe"), dict(injury_outcome="known"),
    dict(scenarios=[]), dict(surprise=1), dict(collision_severity="extreme"),
    dict(third_party_recovery_probability=0.5),   # probability without a source
])
def test_invalid_claim_inputs_rejected(bad):
    with pytest.raises(InputError):
        claim(**bad)


@pytest.mark.parametrize("scen", [
    {"name": "x", "insured_driver_share": 0.6, "av_system_share": 0.0, "third_party_share": 0.6},
    {"name": "x", "insured_driver_share": 1.2, "av_system_share": 0.0, "third_party_share": -0.2},
    {"name": "x", "insured_driver_share": 1, "av_system_share": 0, "third_party_share": 0, "probability": 0.5},
])
def test_invalid_scenarios_rejected(scen):
    with pytest.raises(InputError):
        claim(scenarios=[scen])


def test_probabilities_must_sum_to_one():
    d = ex()
    for s in d["scenarios"]:
        s.update(probability=0.5, probability_source="test")
    with pytest.raises(InputError):
        simulate(claim_from_dict(d), n=N, seed=0)


def test_invalid_assumptions_rejected():
    raw = dist.load().raw
    bad = copy.deepcopy(raw)
    bad["injury"]["tiers"][0]["weight"] = 0.5            # weights no longer sum to 1
    with pytest.raises(InputError):
        dist.load(data=bad)
    bad = copy.deepcopy(raw)
    bad["recovery"]["manufacturer"]["probability"] = 1.4
    with pytest.raises(InputError):
        dist.load(data=bad)
    with pytest.raises(InputError):
        simulate(claim(), n=10, seed=0)                  # too few iterations


# ---------------------------------------------------------------- sensitivity and the agent tool
def test_one_way_sensitivity_covers_all_drivers_and_names_evidence():
    rows = one_way(claim(), "B_insured_50pct_liable", n=N, seed=11)
    assert {r["driver"] for r in rows} == {"repair_severity", "injury_probability", "injury_severity",
                                          "recovery_probability", "legal_expenses", "liability_allocation"}
    assert all(r["evidence_to_collect"] for r in rows)
    swings = [abs(r["swing_expected"]) for r in rows]
    assert swings == sorted(swings, reverse=True)
    liab = next(r for r in rows if r["driver"] == "liability_allocation")
    assert liab["swing_expected"] > 0                    # more insured liability -> more exposure
    rc = rank_correlation(claim(), "B_insured_50pct_liable", n=N, seed=11)
    assert rc[0]["spearman_with_net_exposure"] is not None


def test_tool_output_is_json_and_flags_missing_info_and_review():
    out = simulate_claim_cost(EXAMPLE, n_simulations=N, seed=12)
    json.dumps(out)                                      # machine-readable
    assert out["warnings"][0].startswith("ILLUSTRATIVE INPUT")
    items = {m["item"] for m in out["missing_information"]}
    assert {"bodily-injury outcome", "liability allocation", "own-damage limit (vehicle value)"} <= items
    assert out["human_review"]["required"] and "does not approve" in out["human_review"]["note"]
    assert out["limitations"] and out["model_version"].startswith("claimsim")


def test_agent_tool_cannot_change_inputs_and_rejects_unknown_refs():
    from agents.llm import ToolInputError, run_agent
    defn, execute = make_tool({"C1": EXAMPLE}, n_simulations=N)
    assert defn["strict"] and set(defn["input_schema"]["properties"]) == {"claim_ref", "scenarios", "include_sensitivity"}
    with pytest.raises(ToolInputError):
        execute("simulate_claim_cost", {"claim_ref": "nope", "scenarios": [], "include_sensitivity": False})
    with pytest.raises(ToolInputError):
        execute("simulate_claim_cost", {"claim_ref": "C1", "scenarios": ["Z"], "include_sensitivity": False})

    calls = [NS(stop_reason="tool_use", content=[NS(type="tool_use", id="t1", name="simulate_claim_cost",
                                                    input={"claim_ref": "C1", "scenarios": ["A_insured_not_liable"],
                                                           "include_sensitivity": False})]),
             NS(stop_reason="end_turn", content=[NS(type="text", text='{"summary": "ok"}')])]
    client = NS(beta=NS(messages=NS(create=lambda **kw: calls.pop(0))))
    trace = []
    out = run_agent(client, name="adjuster", system="s", prompt="p", tools=[TOOL_DEFINITION], execute=execute,
                    schema={"type": "object"}, effort="low", trace=lambda *a: trace.append(a))
    assert out == {"summary": "ok"}
    result = trace[0][2]["output"]
    assert list(result["scenarios"]) == ["A_insured_not_liable"] and result["config"]["n_simulations"] == N
