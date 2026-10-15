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
    # No collision, but still closing on an in-lane vehicle when the horizon ended:
    # the "avoidance" is not proven. Monte Carlo should count these separately.
    ended_closing: bool = False
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


SAME_DIRECTION_RAD = math.radians(30)


def classify_impact(ego: VehicleState, eg: Geometry, other: VehicleState) -> ImpactType:
    """Where the other vehicle is, in the ego frame, at first contact.

    Front-to-rear needs both vehicles heading roughly the same way and the other
    mostly ahead (or behind). A cut-in hit mid-lane-change is front-to-rear, as
    crash reports usually code it; a broadside or steep-angle contact is "side".
    """
    c, s = math.cos(ego.heading), math.sin(ego.heading)
    dx, dy = other.x - ego.x, other.y - ego.y
    lon, lat = dx * c + dy * s, -dx * s + dy * c
    dh = abs((other.heading - ego.heading + math.pi) % (2 * math.pi) - math.pi)
    if dh < SAME_DIRECTION_RAD and abs(lon) > max(abs(lat), eg.length / 2):
        return "rear_end" if lon > 0 else "struck_from_rear"
    return "side"


# A run that ends while still closing counts as "avoidance not proven" only if the remaining
# time-to-collision is short. Borrowed from R157 Annex 3 3.3.2.1's 2 s TTC danger threshold;
# INTERPRETATION: a careful driver creeping slowly up to a stopped car (TTC well above 2 s)
# is not on course for a collision.
UNPROVEN_TTC_S = 2.0


def _closing_in_lane(ego: VehicleState, eg: Geometry, actors: dict[str, VehicleState],
                     geoms: dict[str, Geometry]) -> bool:
    for n, st in actors.items():
        if st.x > ego.x and abs(st.y - ego.y) < (eg.width + geoms[n].width) / 2:
            closing = ego.velocity()[0] - st.velocity()[0]
            gap = st.x - ego.x - (eg.length + geoms[n].length) / 2
            if closing > 0 and gap / closing < UNPROVEN_TTC_S:
                return True
    return False


def run(scenario: SimScenario, policy: Policy, record_trace: bool = True) -> SimResult:
    """record_trace=False skips the per-step trace (Monte Carlo doesn't need it)."""
    dt = scenario.dt
    ego = scenario.ego_initial
    actors = {a.name: a.initial for a in scenario.actors}
    trace: dict[str, list] = {"t": [], "ego": [], **{n: [] for n in actors}}
    policy.reset()

    steps = int(round(scenario.duration / dt))
    for i in range(steps + 1):
        t = i * dt
        if record_trace:
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

    geoms = {a.name: a.geometry for a in scenario.actors}
    return SimResult(collided=False, ended_closing=_closing_in_lane(ego, scenario.ego_geometry, actors, geoms),
                     trace=trace)
