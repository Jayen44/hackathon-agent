"""Point-value scenario the simulator runs.

The Investigator produces parameter RANGES (contracts/scenario.py, TBD);
montecarlo/ samples those into one SimScenario per run. Other road users are
scripted (they do what the crash report says they did); only the ego vehicle
is driven by a policy (AV replay or a careful-driver model).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from sim.vehicle import Geometry, VehicleState


def piecewise_constant(profile: list[tuple[float, float]], t: float) -> float:
    """Value of a [(t_start, value), ...] profile at time t (0 before the first entry)."""
    out = 0.0
    for t_start, value in profile:
        if t >= t_start:
            out = value
        else:
            break
    return out


@dataclass(frozen=True)
class LateralManoeuvre:
    """Smooth (cosine) lane change from y_from to y_to, starting at t_start, lasting duration."""
    t_start: float
    duration: float
    y_from: float
    y_to: float

    def y(self, t: float) -> float:
        if t <= self.t_start:
            return self.y_from
        if t >= self.t_start + self.duration:
            return self.y_to
        u = (t - self.t_start) / self.duration
        return self.y_from + (self.y_to - self.y_from) * (1 - math.cos(math.pi * u)) / 2

    def dy_dt(self, t: float) -> float:
        if not self.t_start < t < self.t_start + self.duration:
            return 0.0
        u = (t - self.t_start) / self.duration
        return (self.y_to - self.y_from) * math.pi * math.sin(math.pi * u) / (2 * self.duration)


@dataclass(frozen=True)
class ScriptedActor:
    name: str
    geometry: Geometry
    initial: VehicleState
    # Longitudinal acceleration profile [(t_start, accel_mps2)], e.g. [(2.0, -6.0)] = brakes at t=2 s.
    accel_profile: list[tuple[float, float]] = field(default_factory=list)
    lateral: LateralManoeuvre | None = None


@dataclass(frozen=True)
class SimScenario:
    ego_geometry: Geometry
    ego_initial: VehicleState
    actors: list[ScriptedActor]
    duration: float
    dt: float = 0.02
