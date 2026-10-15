"""Vehicle geometry, state and kinematic bicycle model.

Frame: x is longitudinal (along the road), y is lateral (left positive),
heading in radians from +x. The ego lane is centred on y = 0. Positions are
vehicle centres. Units are SI throughout (m, s, m/s, m/s^2, rad).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Geometry:
    length: float
    width: float
    wheelbase: float


@dataclass(frozen=True)
class VehicleState:
    x: float
    y: float
    heading: float
    v: float

    def velocity(self) -> tuple[float, float]:
        return self.v * math.cos(self.heading), self.v * math.sin(self.heading)


def bicycle_step(s: VehicleState, g: Geometry, accel: float, steer: float, dt: float) -> VehicleState:
    """One Euler step of the kinematic bicycle model. Speed is clamped at 0 (no reversing)."""
    v = max(0.0, s.v + accel * dt)
    return replace(
        s,
        x=s.x + s.v * math.cos(s.heading) * dt,
        y=s.y + s.v * math.sin(s.heading) * dt,
        heading=s.heading + s.v / g.wheelbase * math.tan(steer) * dt,
        v=v,
    )


def corners(s: VehicleState, g: Geometry) -> list[tuple[float, float]]:
    c, sn = math.cos(s.heading), math.sin(s.heading)
    hl, hw = g.length / 2, g.width / 2
    return [(s.x + dx * c - dy * sn, s.y + dx * sn + dy * c)
            for dx, dy in ((hl, hw), (hl, -hw), (-hl, -hw), (-hl, hw))]


def overlaps(a: VehicleState, ga: Geometry, b: VehicleState, gb: Geometry) -> bool:
    """Separating-axis test for two oriented rectangles."""
    pa, pb = corners(a, ga), corners(b, gb)
    for h in (a.heading, b.heading):
        for ax in ((math.cos(h), math.sin(h)), (-math.sin(h), math.cos(h))):
            proj_a = [px * ax[0] + py * ax[1] for px, py in pa]
            proj_b = [px * ax[0] + py * ax[1] for px, py in pb]
            if max(proj_a) < min(proj_b) or max(proj_b) < min(proj_a):
                return False
    return True
