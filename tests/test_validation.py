"""Validation of the formulae and assumptions: independent cross-checks, hand-computed values, properties.

If one of these fails, a formula changed meaning. Do not loosen a tolerance to make it pass: explain it in
docs/validation.md. Finance formulas are checked here by calling finance.recovery (read-only).
"""
import itertools
import math
import random
import statistics

import pytest

from finance.recovery import Interval, av_share, expected_recovery
from insurance.bridge import wilson_ci90
from insurance.bundle import Conflict
from insurance.counterfactual import (G, HumanParams, KinematicEstimator, _impact_speed, _tri_quantile,
                                      impact_speed, numeric_impact)
from insurance.engine import Policy, decide
from insurance.bundle import load_bundle, load_bundle_file
from pathlib import Path
import json

EX = Path(__file__).resolve().parent.parent / "insurance" / "examples"


def conflict(**kw) -> Conflict:
    base = dict(hazard_id="h", t_start=0.0, ego_speed_mps=13.4, gap_m=40.0, hazard_speed_mps=0.0, friction_mu=0.7)
    base.update(kw)
    return Conflict(**base)


# ------------------------------------------------------------------ kinematics
def test_hand_computed_stop_before_obstacle():
    # 13.4 m/s, 40 m gap, 1.0 s reaction, mu 0.7 -> a = 6.867. Closes 13.4 m in reaction; stopping needs
    # 13.4^2 / (2*6.867) = 13.07 m; 13.4 + 13.07 = 26.5 < 40, so no collision.
    assert _impact_speed(conflict(), 1.0, 0.7 * G) == 0.0


def test_hand_computed_impact_speed():
    # gap 20: after reaction 6.6 m remain; v^2 = 13.4^2 - 2*6.867*6.6 = 88.9 -> 9.43 m/s
    assert _impact_speed(conflict(gap_m=20.0), 1.0, 0.7 * G) == pytest.approx(9.43, abs=0.01)


def test_hits_before_braking_starts():
    # reaction 2 s closes 26.8 m of a 20 m gap: impact at the full closing speed
    assert _impact_speed(conflict(gap_m=20.0), 2.0, 0.7 * G) == pytest.approx(13.4)


def test_numeric_integrator_agrees_with_closed_form():
    """Independent implementation (forward Euler) vs the closed form, over a grid. Tolerance covers dt=0.01."""
    worst = 0.0
    for v, gap, r, mu, vh in itertools.product((8, 13.4, 20, 30), (10, 25, 40, 80), (0.7, 1.0, 1.5, 2.0),
                                               (0.4, 0.7), (0.0, 5.0)):
        c = conflict(ego_speed_mps=v, gap_m=gap, friction_mu=mu, hazard_speed_mps=vh)
        a = mu * G
        closed, num = _impact_speed(c, r, a), numeric_impact(c, r, a)
        worst = max(worst, abs(closed - num))
        assert abs(closed - num) < 0.6, (v, gap, r, mu, vh, closed, num)
    assert worst < 0.6


def test_dispatch_uses_closed_form_for_constant_hazard():
    c = conflict(gap_m=20.0)
    assert impact_speed(c, 1.0, 6.867) == _impact_speed(c, 1.0, 6.867)


def test_matched_lead_braking_never_closes():
    # Lead brakes at 6, ego brakes at 6.87 after 1 s from a 30 m gap at equal speed: the gap shrinks then recovers.
    c = conflict(kind="lead_braking", ego_speed_mps=20.0, hazard_speed_mps=20.0, gap_m=30.0, hazard_decel_mps2=6.0)
    assert numeric_impact(c, 1.0, 6.867) == 0.0


def test_lead_braking_harder_than_ego_can_match_collides():
    c = conflict(kind="lead_braking", ego_speed_mps=20.0, hazard_speed_mps=20.0, gap_m=15.0, hazard_decel_mps2=8.0)
    assert numeric_impact(c, 1.0, 6.867) > 5.0


def test_cut_in_behind_the_ego_is_not_a_collision():
    # Hazard that is already behind the ego's front when it "enters" the lane cannot be struck
    c = conflict(kind="cut_in", gap_m=-0.0, hazard_speed_mps=5.0, t_in_path_s=2.0, ego_speed_mps=20.0)
    assert numeric_impact(c, 1.0, 6.867) == 0.0


def test_decel_is_mu_g_capped_at_9():
    est = KinematicEstimator(n=50)
    assert "6.9 m/s^2" in est.estimate(conflict(friction_mu=0.7)).notes[0]
    assert "9.0 m/s^2" in est.estimate(conflict(friction_mu=1.1)).notes[0]   # 1.1*9.81 = 10.8 -> capped at 9.0


# ------------------------------------------------------------------ properties
def p_avoid(**kw) -> float:
    return KinematicEstimator(n=800).estimate(conflict(**kw)).p_avoid


def test_p_avoid_is_monotone_in_the_inputs():
    gaps = [p_avoid(gap_m=g) for g in (15, 22, 28, 34, 40, 60)]
    speeds = [p_avoid(gap_m=30, ego_speed_mps=v) for v in (8, 11, 13.4, 16, 20)]
    mus = [p_avoid(gap_m=28, friction_mu=m) for m in (0.3, 0.5, 0.7, 0.9)]
    assert gaps == sorted(gaps) and speeds == sorted(speeds, reverse=True) and mus == sorted(mus)


def test_p_avoid_bounds_and_percentile_consistency():
    for g in (10, 20, 28, 35, 50):
        r = KinematicEstimator(n=800).estimate(conflict(gap_m=g))
        assert 0.0 <= r.p_avoid <= 1.0
        # a faster reaction can never do worse than a slower one
        assert (not r.avoids_at_p95) or r.avoids_at_p50
        assert (not r.avoids_at_p50) or r.avoids_at_p5


def test_estimator_is_deterministic_and_sampling_error_is_small():
    c = conflict(gap_m=28.0)
    assert KinematicEstimator(n=1000).estimate(c) == KinematicEstimator(n=1000).estimate(c)
    ps = [KinematicEstimator(n=2000, seed=s).estimate(c).p_avoid for s in range(12)]
    se = math.sqrt(0.6 * 0.4 / 2000)   # worst-case binomial standard error is about 1.1%
    assert statistics.pstdev(ps) < 2.5 * se, ps


def test_triangular_quantile_matches_the_sampled_distribution():
    p = HumanParams()
    rng = random.Random(1)
    xs = sorted(rng.triangular(p.reaction_low_s, p.reaction_high_s, p.reaction_mode_s) for _ in range(40000))
    for q in (0.05, 0.5, 0.95):
        assert _tri_quantile(q, p.reaction_low_s, p.reaction_mode_s, p.reaction_high_s) == pytest.approx(
            xs[int(q * len(xs))], abs=0.02)
    assert statistics.mean(xs) == pytest.approx((0.7 + 1.0 + 1.5) / 3, abs=0.01)


# ------------------------------------------------------------------ Wilson interval
def test_wilson_matches_hand_computed_value():
    # p=0.5, n=100, z=1.6449: centre 0.5, half-width 0.0812 -> (0.4188, 0.5812)
    lo, hi = wilson_ci90(0.5, 100)
    assert (lo, hi) == (pytest.approx(0.4188, abs=2e-3), pytest.approx(0.5812, abs=2e-3))


def test_wilson_coverage_is_about_90_percent():
    rng = random.Random(3)
    true_p, n, hits, trials = 0.62, 400, 0, 1500
    for _ in range(trials):
        k = sum(rng.random() < true_p for _ in range(n))
        lo, hi = wilson_ci90(k / n, n)
        hits += lo <= true_p <= hi
    assert 0.86 <= hits / trials <= 0.94


# ------------------------------------------------------------------ finance formulas (read-only checks)
def test_av_share_hand_computed():
    s = av_share(Interval(0.6, 0.8, 0.9), (0.1, 0.2))
    assert (s.low, s.mid, s.high) == (pytest.approx(0.48), pytest.approx(0.68), pytest.approx(0.81))


def test_expected_recovery_hand_computed():
    e = expected_recovery(Interval(0.48, 0.68, 0.81), Interval(4000, 5000, 6000), Interval(1000, 2000, 3000))
    assert (e.low, e.mid, e.high) == (pytest.approx(-1080), pytest.approx(1400), pytest.approx(3860))


def test_expected_recovery_equals_win_probability_times_value_minus_cost():
    """finance treats P(avoid) as a fault share; in expectation that equals P(win) x value - cost."""
    p, value, cost = 0.62, 5000.0, 2000.0
    rng = random.Random(5)
    wins = [value if rng.random() < p else 0.0 for _ in range(200000)]
    assert statistics.mean(wins) - cost == pytest.approx(p * value - cost, abs=30)


# ------------------------------------------------------------------ engine thresholds (boundaries)
class FixedP:
    """Stub estimator returning a chosen P(avoid), to test the decision thresholds exactly."""
    def __init__(self, p, p5=True, p95=True):
        self.p, self.p5, self.p95 = p, p5, p95

    def estimate(self, c):
        from insurance.counterfactual import CounterfactualResult
        return CounterfactualResult(self.p, self.p5, True, self.p95, 0.0, 1000, "stub")


def verdict_at(p, **kw):
    return decide(load_bundle_file(EX / "01_av_late_detection.json"), estimator=FixedP(p, **kw)).liable


def test_threshold_boundaries_are_inclusive():
    pol = Policy()
    assert verdict_at(pol.p_system_fell_short) == "TECH_COMPANY"
    assert verdict_at(pol.p_system_fell_short - 1e-9) == "NEEDS_REVIEW"
    assert verdict_at(pol.p_unavoidable) == "NO_FAULT_DRIVING"
    assert verdict_at(pol.p_unavoidable + 1e-9) == "NEEDS_REVIEW"


def test_confidence_drops_when_slow_human_would_not_have_avoided():
    d = decide(load_bundle_file(EX / "01_av_late_detection.json"), estimator=FixedP(0.9, p95=False))
    assert d.liable == "TECH_COMPANY" and d.confidence == "MEDIUM"
    d = decide(load_bundle_file(EX / "01_av_late_detection.json"), estimator=FixedP(0.9, p95=True))
    assert d.confidence == "HIGH"
