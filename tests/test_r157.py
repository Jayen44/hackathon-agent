"""UN R157 Annex 3 careful-driver models (careful_a = Performance model 1, careful_b = model 2).

Source: ECE/TRANS/WP.29/2022/59/Rev.1, Annex 3 (see sim/policies/R157_ANNEX3.md).
Scenario geometry here (car size, speeds, gaps) is test setup, not crash data.
The "reference" tests rebuild example cases the regulation itself plots
(Annex 3 paras 3.3.4.1-3.3.4.3) and check the model lands on the same side.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

import pytest

from sim.policies import careful_a, careful_b
from sim.policies.careful_base import ParamsMissing, ReactiveBrakingDriver
from sim.scenario import ScriptedActor, SimScenario
from sim.vehicle import Geometry, VehicleState
from sim.world import run
from tests.test_sim import TEST_DRIVER, cut_in, lead_brake

MODELS = {"A_pm1": careful_a, "B_pm2": careful_b}
# Annex 3 Figure 6 note: "Lane width : 3.5 [m] Vehicle width:1.9 [m] ... dy=1.6 [m]". Length is test setup.
REF_CAR = Geometry(length=4.5, width=1.9, wheelbase=2.7)
KPH = 1 / 3.6


@dataclass(frozen=True)
class ConstantLateral:
    """Lane change at constant lateral speed (the R157 data sheets' Vy), duck-types LateralManoeuvre."""
    y_from: float
    y_to: float
    vy: float
    t_start: float = 0.0

    def _u(self, t: float) -> float:
        return max(0.0, t - self.t_start) * self.vy

    def y(self, t: float) -> float:
        d = self.y_to - self.y_from
        return self.y_to if self._u(t) >= abs(d) else self.y_from + math.copysign(self._u(t), d)

    def dy_dt(self, t: float) -> float:
        if t <= self.t_start or self._u(t) >= abs(self.y_to - self.y_from):
            return 0.0
        return math.copysign(self.vy, self.y_to - self.y_from)


def run_policy(scen: SimScenario, model):
    pol = model.make_policy()
    return run(scen, pol, record_trace=False), pol


# ---------------------------------------------------------------- constants are the cited ones

def test_pm1_constants_match_annex3_table1():
    p = careful_a.PARAMS
    assert p.wander_m == 0.375              # Table 1, 3.3.2.1, 3.3.2.2
    assert p.risk_perception_s == 0.4       # Table 1 "Risk evaluation time"
    assert p.perception_to_decel_s == 0.75  # Table 1
    assert p.cut_in_ttc_s == 2.0            # 3.3.2.1
    assert p.cut_out_thw_s == 2.0           # 3.3.2.2
    assert p.lead_decel_threshold == 5.0    # 3.3.2.3
    assert p.full_decel_g == 0.774          # Table 1
    assert p.full_wrap_decel_g == 0.85      # Table 1
    assert p.jerk_time_s == 0.6             # Table 1


def test_pm2_constants_match_annex3_table3():
    p = careful_b.PARAMS
    assert (p.tau_s, p.jerk, p.d1_m, p.b_comf, p.b_max, p.b_other_max) == (0.75, 12.65, 2.0, 4.0, 6.0, 7.0)
    assert p.wander_m == 0.375              # 3.4.3(c)
    assert p.lateral_check_margin_s == 0.1  # 3.4.2.1(d)


def test_g_is_consistent_with_the_text():
    # PM1 0.774 g reached in 0.6 s equals PM2's Table 3 jerk 12.65 m/s^3, and Annex 5 App. 1
    # para 1.1(c) quotes 7.6 m/s^2 for the PM1 maximum.
    assert careful_a.PARAMS.full_decel / careful_a.PARAMS.jerk_time_s == pytest.approx(careful_b.PARAMS.jerk, abs=0.01)
    assert careful_a.PARAMS.full_decel == pytest.approx(7.6, abs=0.05)


def test_make_policy_keeps_fixture_path_and_params_missing():
    assert isinstance(careful_a.make_policy(TEST_DRIVER), ReactiveBrakingDriver)
    assert isinstance(careful_b.make_policy(TEST_DRIVER), ReactiveBrakingDriver)
    assert isinstance(careful_a.make_policy(), careful_a.CCDMDriver)
    assert isinstance(careful_b.make_policy(), careful_b.FSMDriver)


@pytest.mark.parametrize("m", [careful_a, careful_b])
def test_params_missing_still_raised_when_unset(m, monkeypatch):
    monkeypatch.setattr(m, "PARAMS", None)
    with pytest.raises(ParamsMissing):
        m.make_policy()


# ---------------------------------------------------------------- FSM metric unit checks (3.4.2.2)

def test_pfs_cfs_edges():
    p = careful_b.PARAMS
    # Same speed, far apart: safe (PFS 0, CFS 0).
    assert careful_b.pfs(200.0, 20.0, 20.0, p) == 0.0
    assert careful_b.cfs(200.0, 20.0, 20.0, 0.0, p) == 0.0
    # Stopped vehicle 10 m ahead at 20 m/s: unsafe (both 1).
    assert careful_b.pfs(10.0, 20.0, 0.0, p) == 1.0
    assert careful_b.cfs(10.0, 20.0, 0.0, 0.0, p) == 1.0
    # PFS on the ramp: linear between d_unsafe and d_safe (3.4.2.2.1).
    u = 20.0
    d_safe = u * 0.75 + u**2 / 8 - u**2 / 14 + 2
    d_unsafe = u * 0.75 + u**2 / 12 - u**2 / 14
    mid = (d_safe + d_unsafe) / 2 + 2  # dist_lon with dist_lon - d1 at the midpoint
    assert careful_b.pfs(mid, u, u, p) == pytest.approx(0.5)
    # Braking demand (3.4.2.3).
    assert careful_b.braking_demand(0.5, 0.0, p) == pytest.approx(2.0)
    assert careful_b.braking_demand(0.0, 0.5, p) == pytest.approx(5.0)
    assert careful_b.braking_demand(1.0, 1.0, p) == pytest.approx(6.0)


# ---------------------------------------------------------------- behaviour

@pytest.mark.parametrize("name", MODELS)
def test_brakes_in_obvious_cut_in(name):
    r, pol = run_policy(cut_in(gap_m=30.0), MODELS[name])
    assert pol.max_decel_reached > 2.0
    assert not r.collided


@pytest.mark.parametrize("name", MODELS)
def test_brakes_in_obvious_lead_brake(name):
    r, pol = run_policy(lead_brake(gap_m=40.0, decel=-6.0), MODELS[name])
    assert pol.max_decel_reached > 3.0
    assert not r.collided


def _no_hazard() -> SimScenario:
    car = REF_CAR
    lead = ScriptedActor("lead", car, VehicleState(80.0, 0.0, 0.0, 20.0))          # same speed, 4 s ahead
    beside = ScriptedActor("beside", car, VehicleState(10.0, 3.5, 0.0, 18.0))      # adjacent lane, no lane change
    return SimScenario(car, VehicleState(0.0, 0.0, 0.0, 20.0), [lead, beside], duration=10.0)


@pytest.mark.parametrize("name", MODELS)
def test_no_braking_without_hazard(name):
    for scen in (_no_hazard(), SimScenario(REF_CAR, VehicleState(0, 0, 0, 20.0), [], duration=5.0)):
        r, pol = run_policy(scen, MODELS[name])
        assert not r.collided and pol.max_decel_reached == 0.0


def test_pm1_waits_perception_and_decision_time_then_ramps():
    # Lead brakes at 8 m/s^2 from t = 1.0 s: trigger (3.3.2.3) at 1.0 s, braking starts at
    # 1.0 + 0.4 + 0.75 = 2.15 s, reaches 0.774 g 0.6 s later.
    scen = lead_brake(gap_m=60.0, decel=-8.0)
    r = run(scen, careful_a.make_policy())
    t, ego = r.trace["t"], r.trace["ego"]
    v = [e[3] for e in ego]
    first_drop = next(t[i] for i in range(1, len(v)) if v[i] < v[i - 1] - 1e-9)
    assert first_drop == pytest.approx(2.15 + 0.02, abs=0.021)
    dv = [(v[i - 1] - v[i]) / 0.02 for i in range(1, len(v))]
    assert max(dv) == pytest.approx(0.774 * careful_a.G, abs=1e-6)
    assert not r.collided


def test_pm1_uses_lateral_wandering_threshold_for_cut_in():
    # Cosine lane change from y=3.5 starting t=0.5 s over 2 s: centre passes 0.375 m deviation at
    # u = acos(1 - 2*0.375/3.5)/pi of the manoeuvre.
    pol = careful_a.make_policy()
    run(cut_in(gap_m=30.0), pol)
    t0, kind = pol.trigger["cutter"]
    u = math.acos(1 - 2 * 0.375 / 3.5) / math.pi
    assert kind == "cut_in"
    assert t0 == pytest.approx(0.5 + 2.0 * u, abs=0.021)


# ---------------------------------------------------------------- regulation reference cases

@pytest.mark.parametrize("dx0, collides", [(4.0, True), (20.0, False), (40.0, False)])
def test_pm1_matches_annex3_fig8_panel2(dx0, collides):
    """Annex 3 3.3.4.1 Figure 8 panel 2: Ve0 60 km/h, Ve0-Vo0 20 km/h, dy0 1.6 m, Vy 2.0 m/s.
    The plot is red (collision) for dx0 below ~10 m and green above."""
    cutter = ScriptedActor("cutter", REF_CAR, VehicleState(dx0 + REF_CAR.length, 3.5, 0.0, 40 * KPH),
                           lateral=ConstantLateral(3.5, 0.0, 2.0))
    scen = SimScenario(REF_CAR, VehicleState(0, 0, 0, 60 * KPH), [cutter], duration=15.0)
    assert run_policy(scen, careful_a)[0].collided == collides


@pytest.mark.parametrize("name, kph", [("A_pm1", 20), ("A_pm1", 40), ("A_pm1", 60),
                                       ("B_pm2", 20), ("B_pm2", 40)])
def test_lead_decel_1g_at_thw2_is_avoided(name, kph):
    """Annex 3 3.3.4.3 (a Performance model 1 statement): 'It is possible to avoid sudden
    deceleration of -1.0G or less in the follow-up driving situation at THW 2.0sec'
    (data sheet: Vo0 = Ve0, dG/dt infinite). PM2 (b_ego,max = 6 m/s^2, Table 3) is not claimed
    to meet this; it does at 20 and 40 km/h and just fails at 60 km/h (see test below)."""
    v = kph * KPH
    lead = ScriptedActor("lead", REF_CAR, VehicleState(2.0 * v + REF_CAR.length, 0, 0, v),
                         accel_profile=[(0.0, -careful_a.G)])
    scen = SimScenario(REF_CAR, VehicleState(0, 0, 0, v), [lead], duration=15.0)
    assert not run_policy(scen, MODELS[name])[0].collided


def test_pm2_lead_decel_1g_at_thw2_60kph_is_avoided_with_d1_margin():
    # With the Table 3 d1 stop margin applied in CFS (interpretation, see careful_b.py) PM2 avoids the
    # 1 g lead stop at THW 2 s, consistent with Annex 3 3.3.4.3. Literal CFS gave a <1 m/s contact.
    v = 60 * KPH
    lead = ScriptedActor("lead", REF_CAR, VehicleState(2.0 * v + REF_CAR.length, 0, 0, v),
                         accel_profile=[(0.0, -careful_a.G)])
    r, _ = run_policy(SimScenario(REF_CAR, VehicleState(0, 0, 0, v), [lead], duration=15.0), careful_b)
    assert not r.collided


@pytest.mark.parametrize("name", MODELS)
@pytest.mark.parametrize("kph", [30, 60])
def test_cut_out_reveal_of_stopped_vehicle_at_thw2_is_avoided(name, kph):
    """Annex 3 3.3.4.2 Figure 13: lead at THW 2 s cuts out (Vy 2 m/s) revealing a stopped
    vehicle 40 m beyond it; the data sheets show no ego collision."""
    v = kph * KPH
    lead_x = 2.0 * v + REF_CAR.length
    lead = ScriptedActor("lead", REF_CAR, VehicleState(lead_x, 0, 0, v), lateral=ConstantLateral(0.0, 3.5, 2.0))
    stopped = ScriptedActor("stopped", REF_CAR, VehicleState(lead_x + REF_CAR.length + 40.0, 0, 0, 0.0))
    scen = SimScenario(REF_CAR, VehicleState(0, 0, 0, v), [lead, stopped], duration=20.0)
    r, pol = run_policy(scen, MODELS[name])
    assert not r.collided and pol.max_decel_reached > 0


def test_cut_out_stopped_vehicle_is_hidden_until_reveal():
    # 3.4.3(c) / 3.3.2.2: no reaction to the stopped vehicle while the lead is inside the 0.375 m zone.
    v = 60 * KPH
    lead_x = 2.0 * v + REF_CAR.length
    lead = ScriptedActor("lead", REF_CAR, VehicleState(lead_x, 0, 0, v))  # never leaves
    stopped = ScriptedActor("stopped", REF_CAR, VehicleState(lead_x + 30.0, 0, 0, 0.0))
    scen = SimScenario(REF_CAR, VehicleState(0, 0, 0, v), [lead, stopped], duration=1.0)
    for m in MODELS.values():
        _, pol = run_policy(scen, m)
        assert pol.max_decel_reached == 0.0


# ---------------------------------------------------------------- sanity sweep on the test_sim fixture

GAPS = [2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 25, 30, 40]


def sweep() -> dict[str, list[float]]:
    """Gaps (m) of tests/test_sim.cut_in (ego 20 m/s, cutter 12 m/s) each model avoids."""
    return {name: [g for g in GAPS if not run(cut_in(gap_m=g), m.make_policy(), record_trace=False).collided]
            for name, m in MODELS.items()}


def test_cut_in_gap_sweep_brackets():
    avoided = sweep()
    print("\navoided gaps:", avoided)
    for name, gaps in avoided.items():
        assert 30 in gaps and 40 in gaps, name           # generous cut-ins avoided by both
        assert 4 not in gaps and 8 not in gaps, name     # tight cut-ins not avoidable
        # monotone: once avoided, larger gaps also avoided
        first = min(gaps)
        assert all(g in gaps for g in GAPS if g >= first), (name, gaps)
    # PM2 anticipates (proportionate early braking), so it avoids at least what PM1 avoids here.
    assert set(avoided["A_pm1"]) <= set(avoided["B_pm2"])


def test_r157_runs_stay_fast():
    import time
    t0 = time.perf_counter()
    for m in MODELS.values():
        for _ in range(10):
            run(cut_in(gap_m=25.0), m.make_policy(), record_trace=False)
    assert (time.perf_counter() - t0) / 20 < 0.05
