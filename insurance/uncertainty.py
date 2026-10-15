"""Reconstruction uncertainty: how much does P(avoid) move if the reconstructed conflict is slightly wrong?

The Monte Carlo interval only covers sampling noise. The gap, ego speed and friction in a bundle are themselves
estimates from logs. `PerturbedEstimator` wraps any Estimator and re-runs it at the pessimistic and optimistic corners of
the reconstruction error (smaller gap, faster ego, lower friction for the human; the reverse for the optimistic case).
P(avoid) is monotone in all three, so the two corners bound the range. The nominal result is unchanged; the range is
returned as `CounterfactualResult.p_range` and widens the interval the bridge sends to finance.

The error fractions are the CALLER'S ASSUMPTION (there is no sourced value): pass them explicitly, they are logged in the
result notes and in the provenance record. Default everywhere is OFF.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from insurance.bundle import Conflict
from insurance.counterfactual import CounterfactualResult, Estimator


@dataclass(frozen=True)
class ReconError:
    gap_frac: float = 0.0      # +- fraction of the reconstructed gap
    speed_frac: float = 0.0    # +- fraction of ego speed
    mu_frac: float = 0.0       # +- fraction of road friction

    def __post_init__(self):
        for v in (self.gap_frac, self.speed_frac, self.mu_frac):
            if not 0.0 <= v < 1.0:
                raise ValueError("reconstruction error fractions must satisfy 0 <= f < 1")

    @classmethod
    def uniform(cls, frac: float) -> "ReconError":
        return cls(frac, frac, frac)

    @property
    def active(self) -> bool:
        return bool(self.gap_frac or self.speed_frac or self.mu_frac)

    def label(self) -> str:
        return f"gap +-{self.gap_frac:.0%}, speed +-{self.speed_frac:.0%}, mu +-{self.mu_frac:.0%}"


def _shift(c: Conflict, e: ReconError, sign: int) -> Conflict:
    """sign=-1: pessimistic for the human (less room, more speed, less grip); +1: optimistic."""
    return dataclasses.replace(
        c,
        gap_m=c.gap_m * (1 + sign * e.gap_frac),
        ego_speed_mps=c.ego_speed_mps * (1 - sign * e.speed_frac),
        friction_mu=min(1.2, c.friction_mu * (1 + sign * e.mu_frac)),
    )


class PerturbedEstimator:
    def __init__(self, base: Estimator, error: ReconError):
        self.base, self.error = base, error

    def estimate(self, c: Conflict) -> CounterfactualResult:
        nominal = self.base.estimate(c)
        if not self.error.active:
            return nominal
        lo = self.base.estimate(_shift(c, self.error, -1)).p_avoid
        hi = self.base.estimate(_shift(c, self.error, +1)).p_avoid
        lo, hi = min(lo, nominal.p_avoid), max(hi, nominal.p_avoid)
        return dataclasses.replace(
            nominal, p_range=(lo, hi),
            notes=nominal.notes + [f"Reconstruction error ASSUMED ({self.error.label()}): P(avoid) ranges "
                                   f"{lo:.0%} to {hi:.0%} across it (caller's assumption, not sourced)."])
