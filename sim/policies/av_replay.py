"""Replays the AV's reported behaviour: a scripted acceleration profile, lane kept.

The profile comes from the crash report as interpreted by the Investigator,
e.g. [(0.0, 0.0), (1.8, -3.0)] = constant speed, then braking at 3 m/s^2 from t=1.8 s.
"""
from __future__ import annotations

from sim.scenario import piecewise_constant
from sim.world import Observation


class AVReplayPolicy:
    def __init__(self, accel_profile: list[tuple[float, float]]):
        self.accel_profile = accel_profile

    def reset(self) -> None:
        pass

    def act(self, obs: Observation) -> tuple[float, float]:
        return piecewise_constant(self.accel_profile, obs.t), 0.0
