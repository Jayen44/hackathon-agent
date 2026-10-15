"""Counterfactual: would a careful and competent human have avoided this crash?

`Estimator` is the plug point. `KinematicEstimator` is a self-contained PLACEHOLDER:
closed-form straight-line braking against a hazard moving at constant speed, with a
sampled reaction time. Its parameters are NOT from UN R157 Annex 3 or any published
model; they are illustrative and labelled as such in every result. The simulator on the
`sim` branch (R157 CCDM/FSM policies) is the intended real estimator: see sim_adapter.py.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Protocol

from insurance.bundle import Conflict

G = 9.81


@dataclass(frozen=True)
class HumanParams:
    """PLACEHOLDER human driver. Replace with R157 Annex 3 values via the sim estimator."""
    reaction_low_s: float = 0.7
    reaction_mode_s: float = 1.0
    reaction_high_s: float = 1.5
    max_decel_cap_mps2: float = 9.0
    label: str = "placeholder (not R157)"


@dataclass(frozen=True)
class CounterfactualResult:
    p_avoid: float                      # fraction of sampled human drivers who avoid the crash
    # Outcome for fast / median / slow reaction (5th / 50th / 95th percentile of the reaction distribution)
    avoids_at_p5: bool
    avoids_at_p50: bool
    avoids_at_p95: bool
    median_impact_speed_mps: float      # median over samples (0.0 if most avoid)
    n_samples: int
    model: str
    notes: list[str] = field(default_factory=list)


class Estimator(Protocol):
    def estimate(self, c: Conflict) -> CounterfactualResult: ...


def _impact_speed(c: Conflict, reaction_s: float, decel: float) -> float:
    """Relative impact speed (m/s) for a constant-speed hazard; 0.0 means no collision."""
    vr = c.ego_speed_mps - c.hazard_speed_mps
    if vr <= 0:
        return 0.0                              # not closing on the hazard
    closed_in_reaction = vr * reaction_s
    if closed_in_reaction >= c.gap_m:
        return vr                               # hits before braking starts
    remaining = c.gap_m - closed_in_reaction
    v2 = vr * vr - 2 * decel * remaining
    return math.sqrt(v2) if v2 > 0 else 0.0


def _tri_quantile(p: float, lo: float, mode: float, hi: float) -> float:
    fc = (mode - lo) / (hi - lo)
    if p < fc:
        return lo + math.sqrt(p * (hi - lo) * (mode - lo))
    return hi - math.sqrt((1 - p) * (hi - lo) * (hi - mode))


class KinematicEstimator:
    def __init__(self, params: HumanParams = HumanParams(), n: int = 2000, seed: int = 7):
        self.p, self.n, self.seed = params, n, seed

    def estimate(self, c: Conflict) -> CounterfactualResult:
        p = self.p
        decel = min(c.friction_mu * G, p.max_decel_cap_mps2)
        rng = random.Random(self.seed)               # deterministic: same bundle -> same result
        react = [rng.triangular(p.reaction_low_s, p.reaction_high_s, p.reaction_mode_s) for _ in range(self.n)]
        impacts = sorted(_impact_speed(c, r, decel) for r in react)
        avoided = sum(1 for s in impacts if s == 0.0)

        def at(q: float) -> bool:
            r = _tri_quantile(q, p.reaction_low_s, p.reaction_mode_s, p.reaction_high_s)
            return _impact_speed(c, r, decel) == 0.0

        return CounterfactualResult(
            p_avoid=avoided / self.n,
            avoids_at_p5=at(0.05), avoids_at_p50=at(0.50), avoids_at_p95=at(0.95),
            median_impact_speed_mps=impacts[self.n // 2],
            n_samples=self.n,
            model=f"KinematicEstimator [{p.label}]",
            notes=[f"decel {decel:.1f} m/s^2 (mu={c.friction_mu}), reaction {p.reaction_low_s}-{p.reaction_high_s}s "
                   f"(mode {p.reaction_mode_s}s)", "Straight-line braking only; no swerving."],
        )
