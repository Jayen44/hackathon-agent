"""Careful driver A: UN Regulation 157 Annex 3, Performance model 1 (CCDM).

Lower/upper bound pair with careful_b (Olleja et al. 2025: one model brakes
late, the other is over-cautious).

TODO(Vakhtang): fill PARAMS from the R157 Annex 3 text (reaction time, max
deceleration, jerk, risk-perception rule for cut-in / cut-out / lead decel).
Do not guess values. Also check whether CCDM's perception rule (lateral
wandering threshold for cut-in) needs logic beyond ReactiveBrakingDriver.
"""
from __future__ import annotations

from sim.policies.careful_base import DriverParams, ParamsMissing, ReactiveBrakingDriver

NAME = "careful_a_r157_pm1_ccdm"

PARAMS: DriverParams | None = None  # TODO(Vakhtang): from R157 Annex 3, Performance model 1


def make_policy(params: DriverParams | None = None) -> ReactiveBrakingDriver:
    p = params or PARAMS
    if p is None:
        raise ParamsMissing(f"{NAME}: R157 Annex 3 Performance model 1 parameters not filled in yet")
    return ReactiveBrakingDriver(p)
