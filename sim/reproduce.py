"""Reproduction check for the Reconstructor loop: does the AV replay match the report?"""
from __future__ import annotations

from dataclasses import dataclass, field

from sim.world import ImpactType, SimResult


@dataclass(frozen=True)
class ReportedOutcome:
    collided: bool
    impact_type: ImpactType | None = None
    # Reported AV speed band at impact (m/s). SGO reports give speed ranges, so check a band.
    ego_speed_range: tuple[float, float] | None = None


@dataclass
class ReproductionCheck:
    reproduced: bool
    mismatches: list[str] = field(default_factory=list)


def check(result: SimResult, reported: ReportedOutcome) -> ReproductionCheck:
    m: list[str] = []
    if result.collided != reported.collided:
        m.append(f"collision: sim={result.collided} reported={reported.collided}")
    elif result.collided:
        if reported.impact_type and result.impact_type != reported.impact_type:
            m.append(f"impact_type: sim={result.impact_type} reported={reported.impact_type}")
        if reported.ego_speed_range:
            lo, hi = reported.ego_speed_range
            if not lo <= result.ego_speed_at_impact <= hi:
                m.append(f"ego_speed: sim={result.ego_speed_at_impact:.1f} m/s reported {lo}-{hi} m/s")
    return ReproductionCheck(reproduced=not m, mismatches=m)
