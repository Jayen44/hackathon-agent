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

# Legal cost of the recovery action (insurer v manufacturer/operator under AEVA 2018 s.5).
# Proxy: the fixed recoverable costs (FRC) a court allows for a claim of that size, from
# CPR Practice Direction 45 (justice.gov.uk, 2024 text). Real spend can exceed FRC.
# Track by value, CPR 26.9: fast track <= GBP 25,000, intermediate <= GBP 100,000.
# Band, CPR 26.15 Table 1: a money claim is band 2, a complex one band 4. A product-liability
# recovery against an AV company could be either, so the range runs from the cheapest outcome
# (band 2, settled pre-issue) to the dearest (band 4, one-day trial).
_PD45 = "CPR PD 45 (2024)"
FAST_TRACK_LIMIT = 25_000
INTERMEDIATE_TRACK_LIMIT = 100_000


def _fast_band2_pre_issue(d: float) -> float:
    """PD 45 Table 12, row A, band 2: settled before Part 7 proceedings issued."""
    if d <= 5_000:
        return max(681, 124 + 0.20 * d)
    if d <= 10_000:
        return 1_342 + 0.15 * (d - 5_000)
    return 2_374 + 0.10 * (d - 10_000)


def _fast_band4_trial(d: float) -> float:
    """PD 45 Table 12, row C (disposed of at trial) + row D (trial advocacy fee), band 4, one defendant."""
    advocacy = 1_652 if d <= 10_000 else 2_168 if d <= 15_000 else 2_994
    return 8_155 + 0.40 * d + advocacy


def _intermediate_band2_pre_issue(d: float) -> float:
    """PD 45 Table 14, stage S1 (pre-issue to defence), band 2."""
    return 5_162 + 0.06 * d


def _intermediate_band4_trial(d: float) -> float:
    """PD 45 Table 14, band 4: S8 (to trial, bundle prepared) + S9 (one trial day) + S10 (day-1 advocacy)."""
    return 29_938 + 0.22 * d + 1_445 + 5_988


def legal_cost_for_claim(value_low: float, value_high: float) -> GBPRange:
    """Legal cost range for a recovery claim worth value_low..value_high GBP.

    Low: band 2, settled pre-issue, at value_low. High: band 4, one-day trial, at value_high.
    """
    if value_high <= FAST_TRACK_LIMIT:
        return GBPRange(_fast_band2_pre_issue(value_low), _fast_band4_trial(value_high),
                        f"{_PD45} Table 12 (fast track): band 2 pre-issue to band 4 trial", "statutory")
    if value_high <= INTERMEDIATE_TRACK_LIMIT:
        low = (_fast_band2_pre_issue if value_low <= FAST_TRACK_LIMIT else _intermediate_band2_pre_issue)(value_low)
        return GBPRange(low, _intermediate_band4_trial(value_high),
                        f"{_PD45} Tables 12/14 (fast/intermediate track): band 2 pre-issue to band 4 trial",
                        "statutory")
    # Multi-track: no fixed costs; costs are budgeted case by case (CPR Part 3, Section II).
    return GBPRange(None, None, "TODO: multi-track (> GBP 100,000) has no fixed costs; needs a budget estimate",
                    "TODO")


def claim_value_for_severity(severity: str) -> GBPRange:
    try:
        return CLAIM_VALUE_BY_SGO_SEVERITY[severity]
    except KeyError:
        raise ValueError(f"not an SGO injury severity value: {severity!r}") from None

