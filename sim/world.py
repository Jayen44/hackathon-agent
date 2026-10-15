"""Run one SimScenario with an ego policy and report the outcome."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Protocol

from sim.scenario import ScriptedActor, SimScenario, piecewise_constant
from sim.vehicle import Geometry, VehicleState, bicycle_step, overlaps

ImpactType = Literal["rear_end", "struck_from_rear", "side"]


@dataclass(frozen=True)
class ActorObs:
    name: str
    state: VehicleState
    geometry: Geometry
    accel: float  # current longitudinal accel (m/s^2); negative = braking, i.e. brake lights


@dataclass(frozen=True)
class Observation:
    t: float
    dt: float
    ego: VehicleState
    ego_geometry: Geometry
    actors: list[ActorObs]


class Policy(Protocol):
    def reset(self) -> None: ...
    def act(self, obs: Observation) -> tuple[float, float]:
        """Return (accel_mps2, steer_rad)."""
        ...


@dataclass
class SimResult:
    collided: bool
    t_collision: float | None = None
    impact_type: ImpactType | None = None
    other_actor: str | None = None
    ego_speed_at_impact: float | None = None
    relative_speed_at_impact: float | None = None
    # Per-step trace for viz/: {"t": [...], "ego": [(x, y, heading, v)], "<actor>": [...]}
    trace: dict[str, list] = field(default_factory=dict)


def _actor_state(a: ScriptedActor, prev: VehicleState, t: float, dt: float) -> VehicleState:
    v = max(0.0, prev.v + piecewise_constant(a.accel_profile, t) * dt)
    x = prev.x + prev.v * dt
    if a.lateral is None:
        return VehicleState(x, prev.y, 0.0, v)
    y = a.lateral.y(t + dt)
    heading = math.atan2(a.lateral.dy_dt(t + dt), max(v, 1e-3))
    return VehicleState(x, y, heading, v)


def classify_impact(ego: VehicleState, eg: Geometry, other: VehicleState) -> ImpactType:
    """Where the other vehicle is, in the ego frame, at first contact."""
    c, s = math.cos(ego.heading), math.sin(ego.heading)
    dx, dy = other.x - ego.x, other.y - ego.y
    lon, lat = dx * c + dy * s, -dx * s + dy * c
    if abs(lat) < eg.width / 2 and lon > 0:
        return "rear_end"
    if abs(lat) < eg.width / 2 and lon < 0:
        return "struck_from_rear"
    return "side"


def run(scenario: SimScenario, policy: Policy) -> SimResult:
    dt = scenario.dt
    ego = scenario.ego_initial
    actors = {a.name: a.initial for a in scenario.actors}
    trace: dict[str, list] = {"t": [], "ego": [], **{n: [] for n in actors}}
    policy.reset()

    steps = int(round(scenario.duration / dt))
    for i in range(steps + 1):
        t = i * dt
        trace["t"].append(t)
        trace["ego"].append((ego.x, ego.y, ego.heading, ego.v))
        for n, st in actors.items():
            trace[n].append((st.x, st.y, st.heading, st.v))

        for a in scenario.actors:
            st = actors[a.name]
            if overlaps(ego, scenario.ego_geometry, st, a.geometry):
                ev, ov = ego.velocity(), st.velocity()
                return SimResult(
                    collided=True,
                    t_collision=t,
                    impact_type=classify_impact(ego, scenario.ego_geometry, st),
                    other_actor=a.name,
                    ego_speed_at_impact=ego.v,
                    relative_speed_at_impact=math.hypot(ev[0] - ov[0], ev[1] - ov[1]),
                    trace=trace,
                )
        if i == steps:
            break

        obs = Observation(t, dt, ego, scenario.ego_geometry,
                          [ActorObs(a.name, actors[a.name], a.geometry,
                                    piecewise_constant(a.accel_profile, t) if actors[a.name].v > 0 else 0.0)
                           for a in scenario.actors])
        accel, steer = policy.act(obs)
        ego = bicycle_step(ego, scenario.ego_geometry, accel, steer, dt)
        actors = {a.name: _actor_state(a, actors[a.name], t, dt) for a in scenario.actors}

    return SimResult(collided=False, trace=trace)
