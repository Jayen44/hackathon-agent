"""Careful driver A: UN Regulation No. 157 Annex 3, Performance model 1 (CCDM).

Source: ECE/TRANS/WP.29/2022/59/Rev.1 (01 series of amendments to UN R157, as
adopted by GRVA-13 and submitted to WP.29 June 2022), Annex 3, paragraph 3.3,
Table 1 and Figures 1-4. Verbatim quotes and the review table are in
sim/policies/R157_ANNEX3.md. Every constant below cites its paragraph.

Model (para 3.3.1): avoidance by braking only; "Perception", "Decision",
"Reaction". Per hazard:
  trigger (scenario-specific risk perception point, Table 1 / 3.3.2.x)
  -> risk perception / evaluation time 0.4 s
  -> danger check (cut-in: TTC < 2 s, 3.3.2.1; cut-out: THW < 2 s, 3.3.2.2)
  -> 0.75 s from end of perception to start of deceleration (accelerator
     release + foot transfer, Figure 1; the ego coasts, no braking)
  -> linear brake build-up over 0.6 s to 0.774 g (0.85 g after full wrap of a
     cut-in vehicle), Table 1.

Sim interpretation choices (NOT in R157) are marked "INTERPRETATION" and listed
in R157_ANNEX3.md for human review.

Lower/upper bound pair with careful_b (Olleja et al. 2025: one model brakes
late, the other is over-cautious).
"""
from __future__ import annotations

from dataclasses import dataclass

from sim.policies.careful_base import DriverParams, ParamsMissing, ReactiveBrakingDriver
from sim.policies.r157_common import LaneTracker, Seen
from sim.world import Observation

NAME = "careful_a_r157_pm1_ccdm"

# Standard gravity. R157 Annex 3 gives decelerations in g without a value for g.
# 9.80665 m/s^2 (ISO 80000-3 standard gravity) is consistent with the text:
# 0.774 g / 0.6 s = 12.65 m/s^3, the jerk Annex 3 Table 3 gives for model 2, and
# 0.774 g = 7.6 m/s^2 as used in Annex 5 Appendix 1 para 1.1(c).
G = 9.80665


@dataclass(frozen=True)
class PM1Params:
    # Annex 3 Table 1 "Risk perception point / Lane change (cutting in, cutting out)":
    # "Deviation of the centre of a vehicle over 0.375m from the centre of the driving lane";
    # also 3.3.2.1 / 3.3.2.2 "The lateral wandering distance ... is 0.375m."
    wander_m: float
    # Annex 3 Table 1 "Risk evaluation time 0.4 seconds"; 3.3.2.1-3.3.2.3 "Risk perception time [a] (0.4sec)".
    risk_perception_s: float
    # Annex 3 Table 1 "Time duration from having finished perception until starting deceleration 0.75 seconds".
    perception_to_decel_s: float
    # Annex 3 3.3.2.1 "2sec* is specified as the maximum Time To Collision (TTC) below which it
    # was concluded that there is a danger of collision in the longitudinal direction."
    cut_in_ttc_s: float
    # Annex 3 3.3.2.2 "The time 2 sec is specified as the maximum Time Head Way (THW) for which
    # it was concluded that there is a danger in longitudinal direction."
    cut_out_thw_s: float
    # Annex 3 3.3.2.3 "begins when the leading vehicle exceeds a deceleration threshold 5m/s2."
    lead_decel_threshold: float
    # Annex 3 Table 1 "Jerking time to full deceleration (road friction 1.0) 0.6 seconds to 0.774g".
    full_decel_g: float
    # Annex 3 Table 1 "Jerking time to full deceleration (after full wrap of ego vehicle and
    # cut-in vehicle, road friction 1.0) 0.6 seconds to 0.85g".
    full_wrap_decel_g: float
    # Annex 3 Table 1 (both rows): "0.6 seconds".
    jerk_time_s: float
    # INTERPRETATION, NOT R157: also perceive an in-lane vehicle that is not braking >5 m/s^2
    # (e.g. slow or stopped traffic) once TTC < cut_in_ttc_s. Without it PM1 never reacts to a
    # gently braking or stationary lead. Set False for the literal three-scenario model.
    in_lane_ttc_extension: bool = True
    # INTERPRETATION, NOT R157: a hazard already in the ego lane and visible when the scenario
    # starts is perceived from t=0. Used when the claim bundle defines t_start as "the earliest
    # moment a competent human could perceive the hazard" (insurance bundle schema, constant
    # hazards). R157 has no scenario for a stopped vehicle visible from far away; without this,
    # PM1 only reacts at TTC < 2 s, which a careful driver seeing a stopped car would not wait for.
    perceive_visible_at_start: bool = False

    @property
    def full_decel(self) -> float:
        return self.full_decel_g * G

    @property
    def full_wrap_decel(self) -> float:
        return self.full_wrap_decel_g * G


PARAMS = PM1Params(
    wander_m=0.375,               # Annex 3 Table 1; 3.3.2.1; 3.3.2.2
    risk_perception_s=0.4,        # Annex 3 Table 1 "Risk evaluation time"; 3.3.2.1-3.3.2.3
    perception_to_decel_s=0.75,   # Annex 3 Table 1
    cut_in_ttc_s=2.0,             # Annex 3 3.3.2.1 (the "*" has no footnote in the text)
    cut_out_thw_s=2.0,            # Annex 3 3.3.2.2
    lead_decel_threshold=5.0,     # Annex 3 3.3.2.3, m/s^2
    full_decel_g=0.774,           # Annex 3 Table 1
    full_wrap_decel_g=0.85,       # Annex 3 Table 1
    jerk_time_s=0.6,              # Annex 3 Table 1
)


class CCDMDriver:
    """R157 Annex 3 Performance model 1, one perception chain per other vehicle."""

    def __init__(self, params: PM1Params):
        self.p = params
        self.lanes = LaneTracker(params.wander_m)
        self.reset()

    def reset(self) -> None:
        self.lanes.reset()
        self.trigger: dict[str, tuple[float, str]] = {}  # name -> (t risk perception starts, scenario kind)
        self.decided: dict[str, float] = {}              # name -> t perception finished and danger confirmed
        self.reveal_thw: dict[str, float] = {}           # revealed name -> ego THW to the cut-out vehicle
        self.decel = 0.0
        self.max_decel_reached = 0.0

    # Risk perception point (Annex 3 Table 1, 3.3.2.1-3.3.2.3).
    def _trigger(self, s: Seen) -> str | None:
        p = self.p
        if not s.ego_lane_origin:
            # 3.3.2.1 cut-in: "The perceived boundary for cut-in occurs when the vehicle exceeds the
            # normal lateral wandering distance". Only movement towards the ego lane counts.
            return "cut_in" if self.lanes.deviation_toward_ego_lane(s) > p.wander_m else None
        if s.was_hidden:
            # 3.3.2.2 cut-out: perception "begins when the leading vehicle exceeds the cut-out
            # boundary threshold", i.e. when the vehicle that hid this one left the wandering zone.
            return "cut_out"
        if -s.actor.accel > p.lead_decel_threshold:
            return "decel"  # 3.3.2.3
        if p.in_lane_ttc_extension and s.closing > 0 and s.gap / s.closing < p.cut_in_ttc_s:
            return "ttc_extension"  # INTERPRETATION, not R157 (see PM1Params)
        return None

    def _danger(self, s: Seen, kind: str) -> bool:
        p = self.p
        if kind == "cut_in":    # 3.3.2.1 TTC < 2 s
            return s.closing > 0 and s.gap / s.closing < p.cut_in_ttc_s
        if kind == "cut_out":
            # 3.3.2.2: THW 2 s is "the maximum Time Head Way (THW) for which it was concluded that
            # there is a danger". INTERPRETATION: the THW of the ego to the cut-out vehicle at the
            # moment of the reveal (Figure 3 draws THW to that vehicle). If the ego was following
            # further back, fall back to the labelled TTC extension.
            if s.closing <= 0:
                return False
            if self.reveal_thw.get(s.actor.name, float("inf")) <= p.cut_out_thw_s + 1e-9:  # float tolerance
                return True
            return p.in_lane_ttc_extension and s.gap / s.closing < p.cut_in_ttc_s
        return True             # 3.3.2.3 deceleration and the TTC extension: no further condition

    @staticmethod
    def _thw_to(obs: Observation, name: str | None) -> float:
        """Ego time headway (s) to the named vehicle: bumper gap / ego speed."""
        ego_v = obs.ego.velocity()[0]
        for a in obs.actors:
            if a.name == name and ego_v > 0:
                return (a.state.x - obs.ego.x - (obs.ego_geometry.length + a.geometry.length) / 2) / ego_v
        return float("inf")

    def _still_relevant(self, s: Seen, kind: str) -> bool:
        """INTERPRETATION: a cut-in that is abandoned (back inside its own wandering zone and not
        overlapping the ego laterally) stops being a hazard."""
        if kind != "cut_in":
            return True
        return s.lat_gap <= 0 or self.lanes.deviation_toward_ego_lane(s) > self.p.wander_m

    def act(self, obs: Observation) -> tuple[float, float]:
        p = self.p
        t = obs.t
        seen = self.lanes.update(obs)

        braking_on: list[tuple[Seen, str]] = []
        for s in seen:
            name = s.actor.name
            if (p.perceive_visible_at_start and t == 0.0 and name not in self.trigger
                    and s.ego_lane_origin and not s.was_hidden and s.closing > 0):
                self.trigger[name] = (t, "visible_at_start")  # INTERPRETATION, see PM1Params
            if name in self.trigger and not self._still_relevant(s, self.trigger[name][1]):
                self.trigger.pop(name)
                self.decided.pop(name, None)
            if name not in self.trigger:
                kind = self._trigger(s)
                if kind is None:
                    continue
                self.trigger[name] = (t, kind)
                if kind == "cut_out":
                    self.reveal_thw[name] = self._thw_to(obs, s.hidden_by)
            t0, kind = self.trigger[name]
            if name not in self.decided and t >= t0 + p.risk_perception_s and self._danger(s, kind):
                self.decided[name] = t
            if name in self.decided and t >= self.decided[name] + p.perception_to_decel_s:
                braking_on.append((s, kind))

        closing = [(s, k) for s, k in braking_on if s.closing > 0]
        if not closing:
            # Not closing on any confirmed hazard: ease off but stay alert (no second
            # perception delay if it closes again). INTERPRETATION: R157 is silent on release.
            self.decel = 0.0
            return 0.0, 0.0
        target = p.full_decel
        # Table 1: 0.85 g "after full wrap of ego vehicle and cut-in vehicle". INTERPRETATION of
        # "full wrap": the cut-in vehicle's centre is inside the ego lane's wandering zone.
        if any(k == "cut_in" and self.lanes.in_ego_lane_zone(s.actor) for s, k in closing):
            target = p.full_wrap_decel
        # Table 1: linear build-up, 0 -> target in jerk_time_s.
        self.decel = min(target, self.decel + target / p.jerk_time_s * obs.dt)
        self.max_decel_reached = max(self.max_decel_reached, self.decel)
        return -self.decel, 0.0


def make_policy(params: PM1Params | DriverParams | None = None):
    """No argument: the R157 PM1 driver. A DriverParams (test fixtures, montecarlo tests,
    viz lab) still gives the generic ReactiveBrakingDriver."""
    if isinstance(params, DriverParams):
        return ReactiveBrakingDriver(params)
    p = params or PARAMS
    if p is None:
        raise ParamsMissing(f"{NAME}: R157 Annex 3 Performance model 1 parameters not filled in")
    return CCDMDriver(p)
