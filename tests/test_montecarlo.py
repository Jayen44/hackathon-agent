"""Tests for montecarlo/.

Scenario ranges and driver params here are TEST FIXTURES ONLY, not values from
any crash report and NOT UN R157 values. Driver params derive from
tests/test_sim.py TEST_DRIVER.
"""
from dataclasses import replace
from functools import partial

import numpy as np
import pytest

from montecarlo.counterfactual import compare, p_avoid, p_avoid_adaptive, reproduce_rate, wilson
from montecarlo.ranges import (N_PARAMS, ParamRange, ScenarioRanges, data_sufficiency, draw_uniforms,
                               sample)
from montecarlo.sensitivity import tornado
from sim.policies import careful_a, careful_b
from sim.policies.av_replay import AVReplayPolicy
from sim.reproduce import ReportedOutcome
from sim.scenario import SimScenario
from tests.test_sim import CAR, TEST_DRIVER

# Fixture B: TEST_DRIVER with a slower reaction. Test fixture, not R157 Performance model 2.
TEST_DRIVER_SLOW = replace(TEST_DRIVER, reaction_time=1.5)


def fixture_drivers() -> dict:
    return {"fixture_A": partial(careful_a.make_policy, TEST_DRIVER),
            "fixture_B": partial(careful_b.make_policy, TEST_DRIVER_SLOW)}


def cut_in_ranges(**overrides) -> ScenarioRanges:
    kw = dict(kind="cut_in", ego_geometry=CAR, other_geometry=CAR,
              ego_speed=ParamRange(17.0, 20.0, source="reported"),
              other_speed=ParamRange(10.0, 13.0, source="narrative"),
              gap=ParamRange(4.0, 25.0, "triangular", mode=12.0, source="prior"),
              lateral_offset=ParamRange.point(3.5, source="prior"),
              cut_in_start=ParamRange(0.3, 1.0, source="prior"),
              cut_in_duration=ParamRange(1.5, 3.0, source="narrative"))
    kw.update(overrides)
    return ScenarioRanges(**kw)


def lead_brake_ranges(**overrides) -> ScenarioRanges:
    kw = dict(kind="lead_brake", ego_geometry=CAR, other_geometry=CAR,
              ego_speed=ParamRange.point(20.0, source="reported"),
              other_speed=ParamRange(19.5, 20.0, source="reported"),
              gap=ParamRange(2.0, 40.0, source="prior"),
              other_decel=ParamRange(5.0, 5.5, source="narrative"),
              other_brake_time=ParamRange(0.9, 1.1, source="prior"))
    kw.update(overrides)
    return ScenarioRanges(**kw)


# ---------- ranges ----------

def test_param_range_validation():
    with pytest.raises(ValueError):
        ParamRange(2.0, 1.0)
    with pytest.raises(ValueError):
        ParamRange(0.0, 1.0, "triangular", mode=2.0)
    with pytest.raises(ValueError):
        ParamRange(0.0, 1.0, source="guess")
    with pytest.raises(ValueError):
        cut_in_ranges(cut_in_start=None)


def test_ppf_uniform_and_triangular():
    u = ParamRange(10.0, 20.0)
    assert u.ppf(0.0) == 10.0 and u.ppf(1.0) == 20.0 and u.ppf(0.5) == 15.0
    t = ParamRange(0.0, 10.0, "triangular", mode=2.0)
    assert t.ppf(0.0) == pytest.approx(0.0) and t.ppf(1.0) == pytest.approx(10.0)
    assert t.ppf(0.2) == pytest.approx(2.0)  # CDF at the mode = (mode-lo)/(hi-lo)
    xs = [t.ppf(x) for x in np.random.default_rng(1).random(20000)]
    assert np.mean(xs) == pytest.approx(12.0 / 3, abs=0.05)
    assert ParamRange.point(7.0).ppf(0.3) == 7.0


def test_sample_returns_scenario_within_ranges():
    r = cut_in_ranges()
    rng = np.random.default_rng(3)
    for _ in range(50):
        s = sample(r, rng)
        assert isinstance(s, SimScenario)
        assert 17.0 <= s.ego_initial.v <= 20.0
        other = s.actors[0]
        assert 4.0 <= other.initial.x - CAR.length <= 25.0
        assert other.initial.y == 3.5 and other.lateral.y_to == 0.0
    # Consumes exactly N_PARAMS uniforms per sample (keeps streams aligned).
    a, b = np.random.default_rng(9), np.random.default_rng(9)
    sample(r, a)
    b.random(N_PARAMS)
    assert a.random() == b.random()


def test_uniform_stream_is_prefix_stable():
    assert np.array_equal(draw_uniforms(100, 5)[:40], draw_uniforms(40, 5))


def test_data_sufficiency():
    ds = data_sufficiency(cut_in_ranges())
    # decisive set: ego_speed(reported), other_speed(narr), gap(prior), cut_in_start(prior), cut_in_duration(narr)
    assert ds["reported"] == ["ego_speed"] and set(ds["prior"]) == {"gap", "cut_in_start"}
    assert ds["score"] == pytest.approx((1 + 0.5 + 0.5) / 5)
    all_reported = lead_brake_ranges(gap=ParamRange(2.0, 40.0, source="reported"),
                                     other_decel=ParamRange(5.0, 5.5, source="reported"))
    assert data_sufficiency(all_reported)["score"] == 1.0


# ---------- Wilson ----------

def test_wilson_known_values():
    lo, hi = wilson(50, 100, conf=0.95)
    assert lo == pytest.approx(0.4038, abs=1e-4) and hi == pytest.approx(0.5962, abs=1e-4)
    lo, hi = wilson(0, 10, conf=0.95)
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=1e-4)
    lo90, hi90 = wilson(50, 100)
    assert 0.4038 < lo90 < 0.5 < hi90 < 0.5962  # 90% is narrower than 95%
    assert wilson(0, 0) == (0.0, 1.0)


def test_wilson_symmetry_and_coverage():
    lo, hi = wilson(3, 20)
    lo2, hi2 = wilson(17, 20)
    assert lo == pytest.approx(1 - hi2) and hi == pytest.approx(1 - lo2)
    rng = np.random.default_rng(0)
    p, n, trials = 0.3, 50, 4000
    ks = rng.binomial(n, p, trials)
    covered = np.mean([lo <= p <= hi for lo, hi in (wilson(int(k), n) for k in ks)])
    assert 0.86 <= covered <= 0.95


# ---------- counterfactual ----------

def test_p_avoid_is_deterministic_and_chunk_independent():
    r, f = cut_in_ranges(), fixture_drivers()["fixture_A"]
    a = p_avoid(r, f, n=150, seed=11)
    b = p_avoid(r, f, n=150, seed=11, chunk=7)
    assert a == b
    assert 0.0 < a["p"] < 1.0  # fixture is not degenerate
    assert a["ci90"][0] <= a["p"] <= a["ci90"][1]
    assert a["collisions"] == round((1 - a["p"]) * a["n"])
    c = compare(r, fixture_drivers(), n=150, seed=12, keep_outcomes=True)
    d = compare(r, fixture_drivers(), n=150, seed=11, keep_outcomes=True)
    assert c["outcomes"] != d["outcomes"]


def test_paired_common_random_numbers():
    r = cut_in_ranges()
    drivers = fixture_drivers()
    both = compare(r, drivers, n=200, seed=4, keep_outcomes=True)
    alone = compare(r, {"fixture_A": drivers["fixture_A"]}, n=200, seed=4, keep_outcomes=True)
    # Driver A's per-sample outcomes do not depend on B being evaluated alongside it.
    assert both["outcomes"]["fixture_A"] == alone["outcomes"]["fixture_A"]
    # Same driver twice on paired samples: zero discordant pairs.
    same = compare(r, {"x": drivers["fixture_A"], "y": drivers["fixture_A"]}, n=200, seed=4)
    assert same["paired"]["only_x_avoids"] == 0 and same["paired"]["only_y_avoids"] == 0
    # Slower reaction never helps on the same crash in this fixture.
    pr = both["paired"]
    assert pr["only_fixture_B_avoids"] == 0 and pr["only_fixture_A_avoids"] > 0
    assert pr["p_diff"] == pytest.approx(both["drivers"]["fixture_A"]["p"] - both["drivers"]["fixture_B"]["p"])


def test_adaptive_stopping():
    r, f = cut_in_ranges(), fixture_drivers()["fixture_A"]
    res = p_avoid_adaptive(r, f, seed=2, target_half_width=0.05, n_start=100, n_max=3000, batch=100)
    assert res["half_width"] <= 0.05
    assert 100 < res["n"] < 3000
    # Same samples as a fixed run of the final n.
    assert res == p_avoid(r, f, n=res["n"], seed=2)
    # Cap respected when the target is unreachable.
    capped = p_avoid_adaptive(r, f, seed=2, target_half_width=0.001, n_start=100, n_max=300, batch=100)
    assert capped["n"] == 300 and capped["half_width"] > 0.001


def test_reproduce_rate():
    r = cut_in_ranges()
    yes = reproduce_rate(r, AVReplayPolicy([]), ReportedOutcome(True, ego_speed_range=(16.0, 21.0)), n=60)
    assert yes["rate"] > 0.9
    # Many contacts happen mid-lane-change (side); the mismatch tally tells the Reconstructor why.
    rear = reproduce_rate(r, AVReplayPolicy([]), ReportedOutcome(True, "rear_end"), n=60)
    assert rear["rate"] < yes["rate"] and rear["mismatches"]["impact_type"] > 0
    no = reproduce_rate(r, AVReplayPolicy([]), ReportedOutcome(False), n=60)
    assert no["rate"] < 0.1 and no["mismatches"].get("collision", 0) > 50
    # AV behaviour from ranges: hard early braking (fixture values) avoids most crashes.
    braking = cut_in_ranges(gap=ParamRange(15.0, 25.0, source="prior"),
                            av_brake_start=ParamRange(0.5, 0.6), av_decel=ParamRange(7.0, 8.0))
    assert reproduce_rate(braking, None, ReportedOutcome(False), n=40)["rate"] > 0.5


# ---------- sensitivity ----------

def test_sensitivity_ranks_decisive_param_first():
    r = lead_brake_ranges()
    t = tornado(r, fixture_drivers(), n=120, seed=0)
    names = [row["param"] for row in t["rows"]]
    assert names[0] == "gap"
    assert "ego_speed" not in names  # point value, nothing to learn
    gap = t["rows"][0]
    assert gap["p_at_lo"]["fixture_A"] < gap["p_at_hi"]["fixture_A"]
    assert gap["swing"] > 0.5 and all(row["swing"] < gap["swing"] for row in t["rows"][1:])
    assert t["go_get"] == "gap"
