import copy

from montecarlo.estimate import by_tier, estimate
from montecarlo.evidence import evidence_tier, ranges_from_bundle, timeline_check

# Synthetic bundle in the insurance-branch schema 0.1 (test fixture, not a real crash).
BUNDLE = {
    "case_id": "fixture_lead_brake", "synthetic": True, "t_crash": 104.0,
    "vehicle": {"control_inputs": [{"t": 102.0, "source": "system", "brake": 0.5}]},
    "perception": {"decision_log_present": True},
    "external": {"cctv": ["cam1"]},
    "conflict": {"hazard_id": "lead", "t_start": 100.0, "ego_speed_mps": 15.0, "gap_m": 25.0,
                 "hazard_speed_mps": 15.0, "friction_mu": 0.7, "crash_type": "lead_vehicle_decel"},
    "outcome": {"collided": True, "impact_speed_mps": 6.0},
}


def test_tiers():
    assert evidence_tier(BUNDLE) == 2
    b = copy.deepcopy(BUNDLE); b["perception"]["decision_log_present"] = False
    assert evidence_tier(b) == 1
    b["external"]["cctv"] = []
    assert evidence_tier(b) == 0


def test_ranges_narrow_with_tier_and_priors_are_tagged():
    w = {t: ranges_from_bundle(BUNDLE, tier=t)[0].gap.width for t in (0, 1, 2)}
    assert w[0] > w[1] > w[2]
    r, info = ranges_from_bundle(BUNDLE)
    assert r.kind == "lead_brake" and r.other_decel.source == "prior"
    assert r.av_brake_start.lo == 2.0 and info["av_braking"]["decel_mps2"] > 0


def test_estimate_shape_and_ci_narrows():
    res = estimate(BUNDLE, n=300, sensitivity=False)
    for d in res["drivers"].values():
        assert 0 <= d["ci90"][0] <= d["p_avoid"] <= d["ci90"][1] <= 1
        assert "PLACEHOLDER" in d["model"] or "r157" in d["model"]
    assert "disclaimer" in res and res["reproduction"] is not None
    t = by_tier(BUNDLE, n=300)
    assert set(t) == {0, 1, 2}


def test_timeline_check_flags_contradiction():
    b = copy.deepcopy(BUNDLE)
    b["conflict"].update(hazard_speed_mps=0.0, gap_m=40.0, ego_speed_mps=13.4, crash_type="other")
    b["t_crash"] = 106.0
    b["vehicle"]["control_inputs"] = [{"t": 104.5, "source": "system", "brake": 0.4}]
    assert timeline_check(b)["consistent"] is False
    assert timeline_check(BUNDLE)["consistent"] is None  # equal speeds: not closing at t_start
