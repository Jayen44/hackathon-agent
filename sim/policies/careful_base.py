"""Generic reactive braking driver shared by the careful-driver models.

Behaviour: keep lane and speed until a hazard is perceived (an actor ahead,
laterally inside the ego corridor, with time-to-collision below a threshold or
braking harder than a threshold),
wait the reaction time, then brake with a jerk-limited ramp up to max decel
whenever closing on the hazard (stays alert until the hazard leaves the corridor).

This module contains NO parameter values. Values come from the caller
(careful_a / careful_b take them from UN R157 Annex 3; tests use labelled fixtures).
"""
from __future__ import annotations

from dataclasses import dataclass

from sim.world import ActorObs, Observation


@dataclass(frozen=True)
class DriverParams:
    reaction_time: float      # s, hazard perceived -> braking starts
    max_decel: float          # m/s^2, positive number
    jerk: float               # m/s^3, brake ramp rate
    ttc_threshold: float      # s, TTC below which the lead is perceived as a hazard
    lateral_margin: float     # m, extra lateral clearance counted as "in my corridor"
    lead_decel_threshold: float  # m/s^2, positive; lead braking harder than this is a hazard


class ParamsMissing(RuntimeError):
    pass


def lead_in_corridor(obs: Observation, lateral_margin: float) -> tuple[ActorObs, float, float] | None:
    """Nearest actor ahead overlapping the ego corridor: (actor, bumper gap m, closing speed m/s)."""
    best = None
    for a in obs.actors:
        dx = a.state.x - obs.ego.x
        if dx <= 0:
            continue
        if abs(a.state.y - obs.ego.y) >= (obs.ego_geometry.width + a.geometry.width) / 2 + lateral_margin:
            continue
        gap = dx - (obs.ego_geometry.length + a.geometry.length) / 2
        closing = obs.ego.velocity()[0] - a.state.velocity()[0]
        if best is None or gap < best[1]:
            best = (a, gap, closing)
    return best


class ReactiveBrakingDriver:
    def __init__(self, params: DriverParams):
        self.p = params
        self.reset()

    def reset(self) -> None:
        self.t_perceived: float | None = None
        self.decel = 0.0

    def hazard(self, obs: Observation) -> bool:
        lead = lead_in_corridor(obs, self.p.lateral_margin)
        if lead is None:
            return False
        a, gap, closing = lead
        if -a.accel > self.p.lead_decel_threshold:
            return True
        return closing > 0 and (gap <= 0 or gap / closing < self.p.ttc_threshold)

    def act(self, obs: Observation) -> tuple[float, float]:
        if self.t_perceived is None and self.hazard(obs):
            self.t_perceived = obs.t
        braking = (self.t_perceived is not None
                   and obs.t >= self.t_perceived + self.p.reaction_time)
        if braking:
            lead = lead_in_corridor(obs, self.p.lateral_margin)
            if lead is None:
                # Hazard gone: re-arm perception (a new hazard needs a new reaction time).
                self.reset()
                return 0.0, 0.0
            if lead[2] <= 0:
                # Not closing: ease off but stay alert (no second reaction delay if the lead brakes on).
                self.decel = 0.0
                return 0.0, 0.0
            self.decel = min(self.p.max_decel, self.decel + self.p.jerk * obs.dt)
            return -self.decel, 0.0
        return 0.0, 0.0
