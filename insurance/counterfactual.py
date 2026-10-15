"""Counterfactual: would a careful and competent human have avoided this crash?

`Estimator` is the plug point. `KinematicEstimator` is a self-contained PLACEHOLDER:
closed-form straight-line braking against a hazard moving at constant speed (numeric
integration for a braking lead vehicle or a cut-in), with a sampled reaction time. Its parameters are NOT from UN R157 Annex 3 or any published
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
    # None = not reported (sim's estimate() gives a CI instead of a single fast/slow driver)
    avoids_at_p5: bool | None
    avoids_at_p50: bool
    avoids_at_p95: bool | None
    median_impact_speed_mps: float      # median over samples (0.0 if most avoid)
    n_samples: int
    model: str
    notes: list[str] = field(default_factory=list)
    # (low, high) P(avoid) across the assumed reconstruction error (insurance/uncertainty.py); None = not assessed
    p_range: tuple[float, float] | None = None


class Estimator(Protocol):
    def estimate(self, c: Conflict) -> CounterfactualResult: ...


def numeric_impact(c: Conflict, reaction_s: float, decel: float, dt: float = 0.02, horizon_s: float = 40.0) -> float:
    """Relative impact speed (m/s) by forward integration; handles lead_braking and cut_in.

    Ego drives at constant speed until `reaction_s`, then brakes at `decel`. The hazard starts `gap_m` ahead at
    `hazard_speed_mps`; for lead_braking it brakes at `hazard_decel_mps2` until it stops; for cut_in it only blocks
    the lane from `t_in_path_s` (and only if it is still ahead of the ego at that moment).
    """
    x_e, v_e = 0.0, c.ego_speed_mps
    x_h, v_h = c.gap_m, c.hazard_speed_mps
    blocking = c.kind != "cut_in"
    activated = blocking
    t = 0.0
    while t < horizon_s:
        if not activated and t >= c.t_in_path_s:
            activated, blocking = True, x_h > x_e
        if blocking and x_h - x_e <= 0.0:
            return max(0.0, v_e - v_h)
        a_h = -c.hazard_decel_mps2 if (c.kind == "lead_braking" and v_h > 0.0) else 0.0
        v_e = max(0.0, v_e - (decel * dt if t >= reaction_s else 0.0))
        v_h = max(0.0, v_h + a_h * dt)
        x_e += v_e * dt
        x_h += v_h * dt
        t += dt
        if activated and t >= reaction_s and v_e <= v_h and a_h == 0.0 and (x_h - x_e > 0.0 or not blocking):
            return 0.0   # no longer closing and the hazard is not slowing further: safe from here on
    return 0.0


def impact_speed(c: Conflict, reaction_s: float, decel: float) -> float:
    """Closed form for a constant hazard; numeric integration for the other hazard kinds."""
    if c.kind == "constant_hazard":
        return _impact_speed(c, reaction_s, decel)
    return numeric_impact(c, reaction_s, decel)


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
        impacts = sorted(impact_speed(c, r, decel) for r in react)
        avoided = sum(1 for s in impacts if s == 0.0)

        def at(q: float) -> bool:
            r = _tri_quantile(q, p.reaction_low_s, p.reaction_mode_s, p.reaction_high_s)
            return impact_speed(c, r, decel) == 0.0

        return CounterfactualResult(
            p_avoid=avoided / self.n,
            avoids_at_p5=at(0.05), avoids_at_p50=at(0.50), avoids_at_p95=at(0.95),
            median_impact_speed_mps=impacts[self.n // 2],
            n_samples=self.n,
            model=f"KinematicEstimator [{p.label}]",
            notes=[f"decel {decel:.1f} m/s^2 (mu={c.friction_mu}), reaction {p.reaction_low_s}-{p.reaction_high_s}s "
                   f"(mode {p.reaction_mode_s}s)", f"hazard kind: {c.kind}", "Straight-line braking only; no swerving."],
        )
