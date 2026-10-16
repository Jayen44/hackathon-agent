"""Careful driver B: UN Regulation No. 157 Annex 3, Performance model 2 (FSM, Fuzzy Safety Model).

Source: ECE/TRANS/WP.29/2022/59/Rev.1 (01 series of amendments to UN R157),
Annex 3, paragraph 3.4, Figure 14 and Table 3. Verbatim quotes and the review
table are in sim/policies/R157_ANNEX3.md. Every constant cites its paragraph.

Model (para 3.4.1): "Lateral Safety Check" -> "Longitudinal Safety Check" ->
"Reaction". The longitudinal check uses two fuzzy surrogate safety metrics,
PFS (proactive) and CFS (critical), each in [0, 1]. Risk = PFS > 0 or CFS > 0
(3.4.2.2.3). Braking demand (3.4.2.3):
    b = CFS * (b_max - b_comf) + b_comf   if CFS > 0
    b = PFS * b_comf                      if CFS = 0
applied after the reaction time tau, rising at the maximum jerk (3.4.2.3.1).

Sim interpretation choices (NOT in R157) are marked "INTERPRETATION" and listed
in R157_ANNEX3.md.
"""
from __future__ import annotations

from dataclasses import dataclass

from sim.policies.careful_base import DriverParams, ParamsMissing, ReactiveBrakingDriver
from sim.policies.r157_common import LaneTracker, Seen
from sim.world import Observation

NAME = "careful_b_r157_pm2_fsm"


@dataclass(frozen=True)
class PM2Params:
    # Annex 3 Table 3 "Reaction time of the ALKS vehicle tau = 0.75 seconds".
    tau_s: float
    # Annex 3 Table 3 "Jerking (road friction 1.0) 12.65 m/s3"; used as "the maximum jerk" of 3.4.2.3.1.
    jerk: float
    # Annex 3 Table 3 "Safety distance when the two vehicles reach complete stop d1 = 2 meters".
    d1_m: float
    # Annex 3 Table 3 "Comfortable deceleration of the ALKS vehicle b_ego,comf = 4 m/s2".
    b_comf: float
    # Annex 3 Table 3 "Maximum deceleration of the ALKS vehicle b_ego,max = 6 m/s2".
    b_max: float
    # Annex 3 Table 3 "Maximum deceleration of the 'other vehicle' b_cut-in,max = 7 m/s2".
    b_other_max: float
    # Annex 3 3.4.3(c) / Table 3: "the wandering zone of 0.375 m from the centre of the lane".
    wander_m: float
    # Annex 3 3.4.2.1(d): the "+ 0.1" term of the lateral safety check (unit not stated; seconds
    # by dimensional analysis, both sides of the inequality are times).
    lateral_check_margin_s: float


PARAMS = PM2Params(
    tau_s=0.75,                   # Annex 3 Table 3
    jerk=12.65,                   # Annex 3 Table 3, m/s^3
    d1_m=2.0,                     # Annex 3 Table 3
    b_comf=4.0,                   # Annex 3 Table 3, m/s^2
    b_max=6.0,                    # Annex 3 Table 3, m/s^2
    b_other_max=7.0,              # Annex 3 Table 3, m/s^2
    wander_m=0.375,               # Annex 3 3.4.3(c), Table 3
    lateral_check_margin_s=0.1,   # Annex 3 3.4.2.1(d)
)


def lateral_safety_check(s: Seen, ego_lon_v: float, ego_length: float, margin_s: float) -> bool:
    """Annex 3 3.4.2.1 (a)-(d). True = potential risk.

    INTERPRETATION: dist_lat is the edge-to-edge lateral gap (time for the other vehicle to
    reach the ego's side), dist_lon the bumper gap (rear of other ahead of front of ego, (a)).
    """
    a = s.actor
    vx, vy = a.state.velocity()
    if s.gap <= 0:                       # (a) rear of other ahead of front of ALKS vehicle
        return False
    toward = vy * (-1.0 if s.dy > 0 else 1.0)
    if toward <= 0:                      # (b) other vehicle moving towards the ALKS vehicle
        return False
    if ego_lon_v <= vx:                  # (c) ALKS longitudinal speed greater than the other's
        return False
    # (d) dist_lat / u_cut-in,lat < (dist_lon + length_ego + length_cut-in) / (u_ego,lon - u_cut-in,lon) + 0.1
    return s.lat_gap / toward < (s.gap + ego_length + a.geometry.length) / (ego_lon_v - vx) + margin_s


def pfs(dist_lon: float, u_ego: float, u_other: float, p: PM2Params) -> float:
    """Annex 3 3.4.2.2.1 Proactive Fuzzy Surrogate Safety metric."""
    d_safe = u_ego * p.tau_s + u_ego**2 / (2 * p.b_comf) - u_other**2 / (2 * p.b_other_max) + p.d1_m
    d_unsafe = u_ego * p.tau_s + u_ego**2 / (2 * p.b_max) - u_other**2 / (2 * p.b_other_max)
    x = dist_lon - p.d1_m
    if x <= 0:
        return 1.0  # INTERPRETATION: text defines no case for dist_lon - d1 <= 0; treated as unsafe
    if x < d_unsafe:
        return 1.0
    if x > d_safe:
        return 0.0
    # Literal: (dist_lon - d_safe - d1) / (d_unsafe - d_safe), for d_unsafe < dist_lon - d1 < d_safe
    return (dist_lon - d_safe - p.d1_m) / (d_unsafe - d_safe)


def _cfs_distance(u_ego: float, u_other: float, a_ego: float, b: float, p: PM2Params) -> float:
    """d_safe (b = b_comf) or d_unsafe (b = b_max) of Annex 3 3.4.2.2.2."""
    a_mod = max(a_ego, -p.b_comf)                 # a'_ego = max(a_ego, -b_ego,comf)
    u_next = u_ego + a_mod * p.tau_s              # u_ego,lon,NEXT = u_ego,lon + a'_ego * tau
    if u_next <= u_other:
        # Text: (u_ego,lon - u_cut-in,lon)^2 / (2 a'_ego). INTERPRETATION: a'_ego is negative or zero
        # here whenever ego is faster; use |a'_ego| as a magnitude, and 0 when the ego is not
        # closing or not decelerating (the literal formula is negative or 0/0 in those cases).
        closing = u_ego - u_other
        if closing <= 0 or a_mod >= 0:
            return 0.0
        return closing**2 / (2 * -a_mod)
    d_new = ((u_ego + u_next) / 2 - u_other) * p.tau_s
    return d_new + (u_next - u_other) ** 2 / (2 * b)


def cfs(dist_lon: float, u_ego: float, u_other: float, a_ego: float, p: PM2Params) -> float:
    """Annex 3 3.4.2.2.2 Critical Fuzzy Surrogate Safety metric."""
    d_safe = _cfs_distance(u_ego, u_other, a_ego, p.b_comf, p)
    d_unsafe = _cfs_distance(u_ego, u_other, a_ego, p.b_max, p)
    if dist_lon <= 0:
        return 1.0  # INTERPRETATION: no case for dist_lon <= 0 in the text
    if dist_lon < d_unsafe:
        return 1.0
    if dist_lon >= d_safe:
        return 0.0
    return (dist_lon - d_safe) / (d_unsafe - d_safe)


def braking_demand(pfs_v: float, cfs_v: float, p: PM2Params) -> float:
    """Annex 3 3.4.2.3, positive m/s^2."""
    if cfs_v > 0:
        return cfs_v * (p.b_max - p.b_comf) + p.b_comf
    return pfs_v * p.b_comf


class FSMDriver:
    def __init__(self, params: PM2Params):
        self.p = params
        self.lanes = LaneTracker(params.wander_m)
        self.reset()

    def reset(self) -> None:
        self.lanes.reset()
        self.t_risk: float | None = None   # risk perception point, Table 3
        self.decel = 0.0
        self.max_decel_reached = 0.0
        self.last_pfs = 0.0
        self.last_cfs = 0.0

    def act(self, obs: Observation) -> tuple[float, float]:
        p = self.p
        # Visible actors only: the cut-out rule 3.4.3(c) (no reaction before the cutting-out
        # vehicle's centre leaves the 0.375 m wandering zone) is the reveal in LaneTracker.
        seen = self.lanes.update(obs)
        u_ego = obs.ego.velocity()[0]
        a_ego = -self.decel            # current longitudinal acceleration (the model never accelerates)
        demand, risk, max_pfs, max_cfs = 0.0, False, 0.0, 0.0
        for s in seen:
            if s.lat_gap > 0:
                # 3.4.2.1 Lateral Safety Check, only for vehicles not yet in the ego's path.
                # Vehicles laterally overlapping the ego are treated as in-lane (3.4.3(a), 3.4.4(a)).
                if not lateral_safety_check(s, u_ego, obs.ego_geometry.length, p.lateral_check_margin_s):
                    continue
            u_other = s.actor.state.velocity()[0]
            f_p = pfs(s.gap, u_ego, u_other, p)
            # INTERPRETATION (not literal 3.4.2.2.2): CFS is evaluated on the gap minus d1, Table 3's
            # "safety distance when the two vehicles reach complete stop". Literal CFS has no stop
            # margin, so the model brakes at b_comf to a zero-margin stop and grazes a stopped car.
            f_c = cfs(s.gap - p.d1_m, u_ego, u_other, a_ego, p)
            max_pfs, max_cfs = max(max_pfs, f_p), max(max_cfs, f_c)
            if f_p > 0 or f_c > 0:     # 3.4.2.2.3
                risk = True
                demand = max(demand, braking_demand(f_p, f_c, p))
        self.last_pfs, self.last_cfs = max_pfs, max_cfs

        if risk and self.t_risk is None:
            self.t_risk = obs.t
        if self.t_risk is None or obs.t < self.t_risk + p.tau_s:
            return 0.0, 0.0
        # 3.4.2.3.1: after tau the deceleration "starts to increase with a constant rate equal to
        # the maximum jerk". INTERPRETATION: demand is re-evaluated every step; when it falls the
        # deceleration is released at the same jerk (text is silent on release).
        step = p.jerk * obs.dt
        if demand > self.decel:
            self.decel = min(demand, self.decel + step)
        else:
            self.decel = max(demand, self.decel - step)
        self.max_decel_reached = max(self.max_decel_reached, self.decel)
        if not risk and self.decel == 0.0:
            self.t_risk = None         # risk gone and brakes released: a new risk needs a new tau
        return -self.decel, 0.0


def make_policy(params: PM2Params | DriverParams | None = None):
    """No argument: the R157 PM2 (FSM) driver. A DriverParams (test fixtures, montecarlo
    tests, viz lab) still gives the generic ReactiveBrakingDriver."""
    if isinstance(params, DriverParams):
        return ReactiveBrakingDriver(params)
    p = params or PARAMS
    if p is None:
        raise ParamsMissing(f"{NAME}: R157 Annex 3 Performance model 2 parameters not filled in")
    return FSMDriver(p)
