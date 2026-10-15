"""Counterfactual interface: would a careful and competent human have avoided this crash?

The physics lives in `sim/` + `montecarlo/` (Vakhtang, branch `sim`; UN R157 Annex 3 driver models A and B). insurance/
only defines the result type and the Estimator protocol it consumes. `insurance/sim_estimator.py` produces the results
from the sim; `FixedEstimator` wraps a ready-made result (what the sim returns, or a test double).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from insurance.bundle import Conflict


@dataclass(frozen=True)
class CounterfactualResult:
    p_avoid: float                      # fraction of sampled scenarios in which the careful driver avoids the crash
    # None = not reported (the sim reports a CI instead of a single fast/slow driver)
    avoids_at_p5: bool | None
    avoids_at_p50: bool
    avoids_at_p95: bool | None
    median_impact_speed_mps: float      # median over samples (0.0 if most avoid)
    n_samples: int
    model: str
    notes: list[str] = field(default_factory=list)


class Estimator(Protocol):
    def estimate(self, c: Conflict) -> CounterfactualResult: ...


class FixedEstimator:
    """Returns a result computed elsewhere (the sim's `estimate()` per driver, or a test double)."""

    def __init__(self, result: CounterfactualResult):
        self.result = result

    def estimate(self, _conflict: Conflict | None = None) -> CounterfactualResult:
        return self.result
