import time

import pytest

from sim.policies import careful_a, careful_b
from sim.policies.av_replay import AVReplayPolicy
from sim.policies.careful_base import DriverParams, ParamsMissing
from sim.reproduce import ReportedOutcome, check
from sim.scenario import LateralManoeuvre, ScriptedActor, SimScenario
from sim.vehicle import Geometry, VehicleState, bicycle_step, overlaps
from sim.world import run

# Test fixtures only. These are NOT R157 values and must not be used outside tests.
CAR = Geometry(length=4.5, width=1.8, wheelbase=2.7)
TEST_DRIVER = DriverParams(reaction_time=0.75, max_decel=7.0, jerk=20.0,
                           ttc_threshold=3.0, lateral_margin=0.3,
                           lead_decel_threshold=2.0)


def cut_in(gap_m: float, ego_v: float = 20.0, cutter_v: float = 12.0) -> SimScenario:
    """Cutter in the left lane, gap_m ahead (bumper to bumper), moves into ego lane at t=0.5 s."""
    x0 = gap_m + CAR.length
    cutter = ScriptedActor("cutter", CAR, VehicleState(x0, 3.5, 0.0, cutter_v),
                           lateral=LateralManoeuvre(t_start=0.5, duration=2.0, y_from=3.5, y_to=0.0))
    return SimScenario(CAR, VehicleState(0.0, 0.0, 0.0, ego_v), [cutter], duration=10.0)


def lead_brake(gap_m: float, v: float = 20.0, decel: float = -8.0) -> SimScenario:
    lead = ScriptedActor("lead", CAR, VehicleState(gap_m + CAR.length, 0.0, 0.0, v),
                         accel_profile=[(1.0, decel)])
    return SimScenario(CAR, VehicleState(0.0, 0.0, 0.0, v), [lead], duration=10.0)


def test_bicycle_straight_line():
    s = VehicleState(0, 0, 0, 10)
    for _ in range(100):
        s = bicycle_step(s, CAR, 0.0, 0.0, 0.01)
    assert s.x == pytest.approx(10.0)
    assert s.y == pytest.approx(0.0)


def test_overlap():
    a = VehicleState(0, 0, 0, 0)
    assert overlaps(a, CAR, VehicleState(4.0, 0, 0, 0), CAR)
    assert not overlaps(a, CAR, VehicleState(4.6, 0, 0, 0), CAR)
    assert not overlaps(a, CAR, VehicleState(0, 1.9, 0, 0), CAR)


def test_av_that_never_brakes_rear_ends_cutter():
    r = run(cut_in(gap_m=15.0), AVReplayPolicy([]))
    assert r.collided and r.impact_type == "rear_end" and r.other_actor == "cutter"
    assert r.ego_speed_at_impact == pytest.approx(20.0)


def test_careful_driver_avoids_generous_cut_in_but_not_tight_one():
    assert not run(cut_in(gap_m=25.0), careful_a.make_policy(TEST_DRIVER)).collided
    assert run(cut_in(gap_m=3.0), careful_a.make_policy(TEST_DRIVER)).collided


def test_lead_vehicle_braking():
    assert run(lead_brake(gap_m=3.0), AVReplayPolicy([])).collided
    assert not run(lead_brake(gap_m=30.0, decel=-5.0), careful_b.make_policy(TEST_DRIVER)).collided


def test_r157_params_are_not_invented():
    for m in (careful_a, careful_b):
        if m.PARAMS is None:
            with pytest.raises(ParamsMissing):
                m.make_policy()


def test_reproduction_check():
    r = run(cut_in(gap_m=15.0), AVReplayPolicy([]))
    assert check(r, ReportedOutcome(True, "rear_end", (15.0, 25.0))).reproduced
    bad = check(r, ReportedOutcome(True, "side", (0.0, 5.0)))
    assert not bad.reproduced and len(bad.mismatches) == 2
    assert not check(r, ReportedOutcome(False)).reproduced


def test_single_run_is_fast():
    t0 = time.perf_counter()
    for _ in range(20):
        run(cut_in(gap_m=25.0), careful_a.make_policy(TEST_DRIVER))
    per_run = (time.perf_counter() - t0) / 20
    assert per_run < 0.1, per_run
