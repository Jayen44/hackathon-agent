"""Parameter RANGES for a crash scenario, and sampling them into point-value SimScenarios.

The Investigator turns one SGO report into a ScenarioRanges (e.g. cut-in gap
8-15 m). Every ParamRange carries a `source` tag:

  reported   taken from a structured SGO field (e.g. posted speed, pre-crash speed)
  narrative  read from the free-text narrative (e.g. "the vehicle cut in ~10 m ahead")
  prior      no evidence in the report; a generic plausible range

`data_sufficiency()` turns those tags into a score so the Adjuster and the
claims handler can see how much of the counterfactual rests on assumptions.

Sampling is done by inverse CDF from uniforms u in [0, 1). The same u row
always maps to the same quantile of each range, which is what lets
counterfactual.py use common random numbers (driver A and driver B see the
same sampled crashes) and sensitivity.py pin one parameter while holding the
rest of the sample fixed.

Frame and units follow sim/ (x along road, y lateral left +, ego lane at y=0, SI).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace
from typing import Literal

import numpy as np

from sim.policies.av_replay import AVReplayPolicy
from sim.scenario import LateralManoeuvre, ScriptedActor, SimScenario
from sim.vehicle import Geometry, VehicleState

Dist = Literal["uniform", "triangular"]
Source = Literal["reported", "narrative", "prior"]
ScenarioKind = Literal["cut_in", "lead_brake"]

SOURCE_WEIGHT: dict[str, float] = {"reported": 1.0, "narrative": 0.5, "prior": 0.0}


@dataclass(frozen=True)
class ParamRange:
    lo: float
    hi: float
    dist: Dist = "uniform"
    mode: float | None = None  # triangular only; defaults to the midpoint
    source: Source = "prior"

    def __post_init__(self) -> None:
        if not (math.isfinite(self.lo) and math.isfinite(self.hi)) or self.lo > self.hi:
            raise ValueError(f"bad range [{self.lo}, {self.hi}]")
        if self.dist not in ("uniform", "triangular"):
            raise ValueError(f"unknown dist {self.dist!r}")
        if self.source not in SOURCE_WEIGHT:
            raise ValueError(f"unknown source {self.source!r}")
        if self.mode is not None and not self.lo <= self.mode <= self.hi:
            raise ValueError(f"mode {self.mode} outside [{self.lo}, {self.hi}]")

    @classmethod
    def point(cls, value: float, source: Source = "reported") -> "ParamRange":
        return cls(value, value, source=source)

    @property
    def width(self) -> float:
        return self.hi - self.lo

    def ppf(self, u: float) -> float:
        """Inverse CDF: maps u in [0, 1] to a value in [lo, hi]."""
        lo, hi = self.lo, self.hi
        if hi == lo:
            return lo
        if self.dist == "uniform":
            return lo + u * (hi - lo)
        c = self.mode if self.mode is not None else (lo + hi) / 2
        fc = (c - lo) / (hi - lo)
        if u < fc:
            return lo + math.sqrt(u * (hi - lo) * (c - lo))
        return hi - math.sqrt((1 - u) * (hi - lo) * (hi - c))

    def pinned(self, value: float) -> "ParamRange":
        return ParamRange(value, value, source=self.source)


@dataclass(frozen=True)
class ScenarioRanges:
    """A cut-in or lead-vehicle-braking crash described by ranges.

    Speeds in m/s, distances in m, times in s from scenario start, decels as
    positive m/s^2. `gap` is bumper to bumper at t=0, other vehicle ahead.

    cut_in:     other vehicle starts `lateral_offset` m to the side (left +) and
                moves into the ego lane at `cut_in_start` over `cut_in_duration`;
                optionally brakes at `other_decel` from `other_brake_time`
                (default: when the lane change completes).
    lead_brake: other vehicle ahead in the ego lane brakes at `other_decel`
                from `other_brake_time`.

    `av_brake_start` / `av_decel` describe what the AV reportedly did (for the
    Reconstructor's AV replay). They are not used by the careful-driver runs.
    Geometries are required: the Investigator supplies them (vehicle type).
    """
    kind: ScenarioKind
    ego_geometry: Geometry
    other_geometry: Geometry
    ego_speed: ParamRange
    other_speed: ParamRange
    gap: ParamRange
    lateral_offset: ParamRange | None = None
    cut_in_start: ParamRange | None = None
    cut_in_duration: ParamRange | None = None
    other_decel: ParamRange | None = None
    other_brake_time: ParamRange | None = None
    av_brake_start: ParamRange | None = None
    av_decel: ParamRange | None = None
    duration: float = 10.0
    dt: float = 0.02
    sgo_report_id: str | None = None

    def __post_init__(self) -> None:
        missing = [n for n in REQUIRED[self.kind] if getattr(self, n) is None]
        if missing:
            raise ValueError(f"{self.kind} scenario missing ranges: {missing}")
        if (self.av_brake_start is None) != (self.av_decel is None):
            raise ValueError("av_brake_start and av_decel must be given together")

    def params(self) -> dict[str, ParamRange]:
        """All ranges that are set, in canonical PARAM_NAMES order."""
        return {n: getattr(self, n) for n in PARAM_NAMES if getattr(self, n) is not None}

    def with_param(self, name: str, rng_: ParamRange) -> "ScenarioRanges":
        if name not in PARAM_NAMES:
            raise KeyError(name)
        return replace(self, **{name: rng_})


# Canonical order of sampled parameters. One uniform column per name, ALWAYS
# (even when a range is unset), so a u row means the same thing across
# scenarios, drivers and pinned variants. Append only; never reorder.
PARAM_NAMES: tuple[str, ...] = tuple(
    f.name for f in fields(ScenarioRanges)
    if f.name not in ("kind", "ego_geometry", "other_geometry", "duration", "dt", "sgo_report_id")
)
N_PARAMS = len(PARAM_NAMES)

REQUIRED: dict[str, tuple[str, ...]] = {
    "cut_in": ("ego_speed", "other_speed", "gap", "lateral_offset", "cut_in_start", "cut_in_duration"),
    "lead_brake": ("ego_speed", "other_speed", "gap", "other_decel", "other_brake_time"),
}

# Parameters that decide whether a careful driver avoids the crash. Used for
# data_sufficiency(). AV behaviour and lane offset are not decisive for P(avoid).
DECISIVE: dict[str, tuple[str, ...]] = {
    "cut_in": ("ego_speed", "other_speed", "gap", "cut_in_start", "cut_in_duration", "other_decel"),
    "lead_brake": ("ego_speed", "other_speed", "gap", "other_decel"),
}


def draw_uniforms(n: int, seed: int) -> np.ndarray:
    """(n, N_PARAMS) uniforms. Row i depends only on (seed, i) for a fixed N_PARAMS."""
    return np.random.default_rng(seed).random((n, N_PARAMS))


def values_from_u(ranges: ScenarioRanges, u_row) -> dict[str, float]:
    return {n: getattr(ranges, n).ppf(float(u_row[i]))
            for i, n in enumerate(PARAM_NAMES) if getattr(ranges, n) is not None}


def build_scenario(ranges: ScenarioRanges, v: dict[str, float]) -> SimScenario:
    eg, og = ranges.ego_geometry, ranges.other_geometry
    x0 = v["gap"] + (eg.length + og.length) / 2
    profile: list[tuple[float, float]] = []
    lateral = None
    y0 = 0.0
    if ranges.kind == "cut_in":
        y0 = v["lateral_offset"]
        lateral = LateralManoeuvre(v["cut_in_start"], v["cut_in_duration"], y_from=y0, y_to=0.0)
        if "other_decel" in v:
            t_b = v.get("other_brake_time", v["cut_in_start"] + v["cut_in_duration"])
            profile = [(t_b, -v["other_decel"])]
    else:
        profile = [(v["other_brake_time"], -v["other_decel"])]
    other = ScriptedActor("other", og, VehicleState(x0, y0, 0.0, v["other_speed"]),
                          accel_profile=profile, lateral=lateral)
    return SimScenario(eg, VehicleState(0.0, 0.0, 0.0, v["ego_speed"]), [other],
                       duration=ranges.duration, dt=ranges.dt)


def av_replay_policy(ranges: ScenarioRanges, v: dict[str, float]) -> AVReplayPolicy:
    """AV replay for one sample: constant speed, then brakes at av_decel from av_brake_start."""
    if "av_brake_start" in v:
        return AVReplayPolicy([(v["av_brake_start"], -v["av_decel"])])
    return AVReplayPolicy([])


def sample(ranges: ScenarioRanges, rng: np.random.Generator) -> SimScenario:
    """Draw one SimScenario. Consumes exactly N_PARAMS uniforms from rng."""
    return build_scenario(ranges, values_from_u(ranges, rng.random(N_PARAMS)))


def data_sufficiency(ranges: ScenarioRanges) -> dict:
    """How much of the decisive evidence comes from the report rather than priors.

    score = (reported + 0.5 * narrative) / decisive params set. 1.0 = every
    decisive parameter is a structured SGO field; 0.0 = all priors.
    """
    names = [n for n in DECISIVE[ranges.kind] if getattr(ranges, n) is not None]
    by_source = {s: [n for n in names if getattr(ranges, n).source == s] for s in SOURCE_WEIGHT}
    score = sum(SOURCE_WEIGHT[getattr(ranges, n).source] for n in names) / len(names)
    return {"score": round(score, 4), "decisive": names, **by_source}
