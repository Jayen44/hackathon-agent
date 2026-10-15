"""Tests for ukcrash/. The vehicle rows below are hand-made, not real STATS19 records."""
import pandas as pd

from finance import recovery
from ukcrash import stats19, synthetic


def test_classify_rear_end_and_cut_in():
    v = pd.DataFrame([
        # rear end: car going ahead hits the back of a slowing car
        ("A", 9, 19, 1), ("A", 9, 4, 2),
        # cut-in: taxi going ahead, front impact, other vehicle changing lane to the right
        ("B", 8, 19, 1), ("B", 9, 12, 4),
        # pedal cycle as ego: not a robotaxi analogue
        ("C", 1, 19, 1), ("C", 9, 4, 2),
        # three vehicles: excluded
        ("D", 9, 19, 1), ("D", 9, 4, 2), ("D", 9, 4, 2),
    ], columns=["collision_index", "vehicle_type", "vehicle_manoeuvre", "first_point_of_impact"])
    t = stats19.classify(v)
    assert t.to_dict() == {"A": "lead_vehicle_decel", "B": "cut_in", "C": "other"}


def test_synthetic_is_reproducible_and_labelled():
    a, b = synthetic.generate(10, seed=3), synthetic.generate(10, seed=3)
    assert [c.to_dict() for c in a] == [c.to_dict() for c in b]
    assert all(c.synthetic and c.facts.claim_id.startswith("SYN-") for c in a)
    assert {c.crash_type for c in synthetic.generate(200, seed=1)} == {"lead_vehicle_decel", "cut_in"}


def test_synthetic_crash_prices_end_to_end():
    crash = next(c for c in synthetic.generate(50, seed=2) if c.stats19_severity == "Slight")
    avoid = [recovery.AvoidanceResult("careful_a", 0.8, (0.7, 0.9)),
             recovery.AvoidanceResult("careful_b", 0.9, (0.85, 0.95))]
    a = recovery.assess(crash.facts, avoid)
    assert a.expected_recovery is not None and a.legal_cost is not None
