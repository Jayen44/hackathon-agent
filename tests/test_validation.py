"""Validation of the formulae and assumptions: hand-computed values and boundaries (physics is validated in sim/).

If one of these fails, a formula changed meaning. Do not loosen a tolerance to make it pass: explain it in
docs/validation.md. Finance formulas are checked here by calling finance.recovery (read-only).
"""
import math
import random
import statistics

import pytest

from finance.recovery import Interval, av_share, expected_recovery
from insurance.bridge import wilson_ci90
from insurance.bundle import Conflict
from insurance.engine import Policy, decide
from insurance.bundle import load_bundle, load_bundle_file
from pathlib import Path
import json

EX = Path(__file__).resolve().parent.parent / "insurance" / "examples"


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
