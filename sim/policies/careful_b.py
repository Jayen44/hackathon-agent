"""Careful driver B: UN Regulation 157 Annex 3, Performance model 2 (FSM).

TODO(Vakhtang): fill PARAMS from the R157 Annex 3 text. FSM uses fuzzy
surrogate safety metrics for risk perception; ReactiveBrakingDriver's TTC
trigger is a stand-in until that rule is implemented. Do not guess values.
"""
from __future__ import annotations

from sim.policies.careful_base import DriverParams, ParamsMissing, ReactiveBrakingDriver

NAME = "careful_b_r157_pm2_fsm"

PARAMS: DriverParams | None = None  # TODO(Vakhtang): from R157 Annex 3, Performance model 2


def make_policy(params: DriverParams | None = None) -> ReactiveBrakingDriver:
    p = params or PARAMS
    if p is None:
        raise ParamsMissing(f"{NAME}: R157 Annex 3 Performance model 2 parameters not filled in yet")
    return ReactiveBrakingDriver(p)
