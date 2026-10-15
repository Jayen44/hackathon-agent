"""Estimator backed by the `sim` package (kinematic simulator from the `sim` branch).

Only importable once `sim/` is on the path (e.g. after merging the sim branch). The engine
works without it: `KinematicEstimator` is the default.

IMPORTANT: the driver parameters below are PLACEHOLDERS (not UN R157 Annex 3). `sim/policies/
careful_a.py` and `careful_b.py` hold the real R157 models once their PARAMS are filled in.
`make_estimator()` uses those when available and falls back to the labelled placeholder.
"""
from __future__ import annotations

import random

from insurance.bundle import Conflict
from insurance.counterfactual import G, CounterfactualResult, _tri_quantile

try:
    from sim.policies import careful_a, careful_b
    from sim.policies.careful_base import DriverParams, ParamsMissing, ReactiveBrakingDriver
    from sim.scenario import ScriptedActor, SimScenario
    from sim.vehicle import Geometry, VehicleState
    from sim.world import run
except ImportError as e:  # pragma: no cover
    raise ImportError("insurance.sim_adapter needs the `sim` package (merge the sim branch)") from e

EGO = Geometry(length=4.6, width=1.9, wheelbase=2.8)
HAZARD = Geometry(length=4.5, width=1.8, wheelbase=2.7)


def scenario_from_conflict(c: Conflict, duration: float = 15.0) -> SimScenario:
    """Ego drives at constant speed toward a hazard `gap_m` ahead (bumper to bumper)."""
    centre_gap = c.gap_m + (EGO.length + HAZARD.length) / 2
    return SimScenario(
        ego_geometry=EGO,
        ego_initial=VehicleState(0.0, 0.0, 0.0, c.ego_speed_mps),
        actors=[ScriptedActor("hazard", HAZARD, VehicleState(centre_gap, 0.0, 0.0, c.hazard_speed_mps))],
        duration=duration,
    )


def placeholder_params(c: Conflict, reaction_s: float) -> DriverParams:
    """PLACEHOLDER (not R157). Hazard is treated as perceived at t=0 (conflict start is defined
    as the earliest human-perceivable moment), so only reaction time delays braking."""
    return DriverParams(reaction_time=reaction_s, max_decel=min(c.friction_mu * G, 9.0), jerk=1000.0,
                        ttc_threshold=1e6, lateral_margin=0.0, lead_decel_threshold=99.0)


class SimEstimator:
    def __init__(self, n: int = 200, seed: int = 7, reaction_range: tuple[float, float, float] = (0.7, 1.0, 1.5)):
        self.n, self.seed, self.rr = n, seed, reaction_range

    def _impact(self, c: Conflict, reaction_s: float) -> float:
        res = run(scenario_from_conflict(c), ReactiveBrakingDriver(placeholder_params(c, reaction_s)))
        return res.relative_speed_at_impact if res.collided else 0.0

    def estimate(self, c: Conflict) -> CounterfactualResult:
        lo, mode, hi = self.rr
        rng = random.Random(self.seed)
        impacts = sorted(self._impact(c, rng.triangular(lo, hi, mode)) for _ in range(self.n))
        at = lambda q: self._impact(c, _tri_quantile(q, lo, mode, hi)) == 0.0  # noqa: E731
        return CounterfactualResult(
            p_avoid=sum(1 for s in impacts if s == 0.0) / self.n,
            avoids_at_p5=at(0.05), avoids_at_p50=at(0.50), avoids_at_p95=at(0.95),
            median_impact_speed_mps=impacts[self.n // 2], n_samples=self.n,
            model="SimEstimator [placeholder driver params, not R157]",
            notes=["sim.world.run with ReactiveBrakingDriver; hazard perceived at conflict start.",
                   "Swap in sim.policies.careful_a/careful_b once R157 PARAMS are filled in."],
        )


def r157_available() -> dict[str, bool]:
    """Which real R157 models are ready (PARAMS filled in on the sim branch)."""
    out = {}
    for mod in (careful_a, careful_b):
        try:
            mod.make_policy()
            out[mod.NAME] = True
        except ParamsMissing:
            out[mod.NAME] = False
    return out
