"""Claim value and legal cost tables (GBP). Finance owns this file.

Every row carries its source and a status:
  "statutory": quoted from UK legislation, exact.
  "secondary": a published figure read via a secondary source, to verify against the primary.
  "TODO":      not yet sourced. Value is None; the engine refuses to price with it.

Never put a number here without a source. If the insurer knows the amount it actually
paid on a claim, pass that instead (ClaimValue.paid); these tables only estimate
a value for public SGO crashes, which carry no claim amounts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Status = Literal["statutory", "secondary", "TODO"]


@dataclass(frozen=True)
class GBPRange:
    low: float | None
    high: float | None
    source: str
    status: Status

    @property
    def priced(self) -> bool:
        return self.status != "TODO" and self.low is not None and self.high is not None


# Whiplash Injury (Amendment) Regulations 2025 (SI 2025/615), reg. 2, Table 2:
# tariff for causes of action accruing on or after 31 May 2025, whiplash only, reg. 2(1)(a).
# Covers pain, suffering and loss of amenity only (no special damages such as lost earnings, repairs).
WHIPLASH_TARIFF_2025 = {
    "<=3m": 275, "3-6m": 565, "6-9m": 965, "9-12m": 1510,
    "12-15m": 2335, "15-18m": 3445, "18-24m": 4830,
}
_SI_2025_615 = "Whiplash Injury (Amendment) Regulations 2025, SI 2025/615, Table 2, reg. 2(1)(a)"

# FCA General Insurance Value Measures, motor, 2025: average claim payout GBP 3,858
# (reported via ABI/trade press Feb 2026; verify against the FCA data release).
FCA_AVG_MOTOR_CLAIM_2025 = 3858

# Keys are the exact SGO "Highest Injury Severity Alleged" drop-down values
# (NHTSA SGO-2021-01 Data Element Definitions, field 73).
CLAIM_VALUE_BY_SGO_SEVERITY: dict[str, GBPRange] = {
    "Property Damage, No Injury": GBPRange(
        FCA_AVG_MOTOR_CLAIM_2025, FCA_AVG_MOTOR_CLAIM_2025,
        "FCA GI Value Measures 2025, average motor claim payout (all claim types, used as a "
        "property-damage proxy)", "secondary"),
    "No Injuries Reported": GBPRange(
        FCA_AVG_MOTOR_CLAIM_2025, FCA_AVG_MOTOR_CLAIM_2025,
        "FCA GI Value Measures 2025, average motor claim payout (property-damage proxy)", "secondary"),
    # Assumption (finance to confirm): minor injury = whiplash tariff, up to 12 months, plus the
    # average property claim. Lower bound <=3m tariff, upper bound 9-12m tariff.
    "Minor Without Hospitalization": GBPRange(
        WHIPLASH_TARIFF_2025["<=3m"] + FCA_AVG_MOTOR_CLAIM_2025,
        WHIPLASH_TARIFF_2025["9-12m"] + FCA_AVG_MOTOR_CLAIM_2025,
        f"{_SI_2025_615} (<=3m to 9-12m) + FCA 2025 average claim", "secondary"),
    "Minor With Hospitalization": GBPRange(
        WHIPLASH_TARIFF_2025["3-6m"] + FCA_AVG_MOTOR_CLAIM_2025,
        WHIPLASH_TARIFF_2025["18-24m"] + FCA_AVG_MOTOR_CLAIM_2025,
        f"{_SI_2025_615} (3-6m to 18-24m) + FCA 2025 average claim", "secondary"),
    # TODO(finance): Judicial College Guidelines, 18th edition (April 2026) brackets.
    # Needs the official text; web snippets disagree, so nothing is entered yet.
    "Moderate Without Hospitalization": GBPRange(None, None, "TODO: JCG 18th ed.", "TODO"),
    "Moderate With Hospitalization": GBPRange(None, None, "TODO: JCG 18th ed.", "TODO"),
    "Serious Without Hospitalization": GBPRange(None, None, "TODO: JCG 18th ed.", "TODO"),
    "Serious With Hospitalization": GBPRange(None, None, "TODO: JCG 18th ed.", "TODO"),
    "Fatality": GBPRange(None, None, "TODO: Fatal Accidents Act 1976 bereavement + dependency", "TODO"),
    "Unknown": GBPRange(None, None, "Severity unknown: needs insurer claim file", "TODO"),
}

# Cost of running the recovery action (insurer v manufacturer/operator), by claim value band.
# TODO(finance): source from CPR Part 45 fixed recoverable costs (fast/intermediate track) and a
# multi-track estimate for large product-liability recoveries. Upper bound of each band in GBP.
LEGAL_COST_BY_CLAIM_VALUE: list[tuple[float, GBPRange]] = [
    (25_000, GBPRange(None, None, "TODO: CPR 45 fast track FRC", "TODO")),
    (100_000, GBPRange(None, None, "TODO: CPR 45 intermediate track FRC", "TODO")),
    (float("inf"), GBPRange(None, None, "TODO: multi-track estimate", "TODO")),
]


def claim_value_for_severity(severity: str) -> GBPRange:
    try:
        return CLAIM_VALUE_BY_SGO_SEVERITY[severity]
    except KeyError:
        raise ValueError(f"not an SGO injury severity value: {severity!r}") from None


def legal_cost_for_claim(claim_value_high: float) -> GBPRange:
    for upper, cost in LEGAL_COST_BY_CLAIM_VALUE:
        if claim_value_high <= upper:
            return cost
    raise AssertionError("unreachable: last band is unbounded")
