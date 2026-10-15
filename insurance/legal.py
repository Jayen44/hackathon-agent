"""Legal regime and limitation clocks for a claim (see docs/legal-basis.md).

    regime         which statute makes the AV's insurer pay the victim:
                   AEVA_listed | AEVA_authorised (after AV Act 2024 commencement) | conventional (no listed vehicle,
                   e.g. a supervised pilot) | unspecified
    recovery_route how the insurer gets money back: AEVA_s5 | contribution_1978 | CPA_1987 | policy_s4 | unspecified
    Limitation (all UK): AEVA s.5 = 2 years from settlement (Limitation Act 1980 s.10A); contribution = 2 years from
    judgment or agreed payment (LA s.10); CPA 1987 = 3 years from knowledge (LA s.11A) with a 10-year longstop from supply.
Pure functions; `today` is a parameter so results are reproducible. Lawyer review needed before relying on any deadline.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

REGIMES = ("AEVA_listed", "AEVA_authorised", "conventional", "unspecified")
ROUTES = ("AEVA_s5", "contribution_1978", "CPA_1987", "policy_s4", "unspecified")


@dataclass(frozen=True)
class Legal:
    regime: str = "unspecified"
    recovery_route: str = "unspecified"
    settlement_date: str | None = None    # ISO date the victim's claim was settled / judgment / agreed payment
    knowledge_date: str | None = None     # CPA: date of knowledge
    supply_date: str | None = None        # CPA: date the product was put into circulation (10-year longstop)
    # P(the other party is liable to the victim | careful driver avoids), as (low, mid, high). None = not assessed:
    # the model then treats avoidance as the whole liability case and says so. AEVA s.5 is derivative.
    p_liable_to_victim: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class Deadline:
    route: str
    due: date
    days_left: int
    basis: str

    @property
    def urgent(self) -> bool:
        return self.days_left < 90


def _add_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:            # 29 Feb
        return d.replace(year=d.year + n, day=28)


def limitation_deadline(l: Legal, today: date) -> Deadline | None:
    """Earliest limitation deadline for the claim's route, or None when the route/dates don't allow one."""
    def mk(route, due, basis):
        return Deadline(route, due, (due - today).days, basis)

    def iso(s):
        return date.fromisoformat(s)

    if l.recovery_route == "AEVA_s5" and l.settlement_date:
        return mk("AEVA_s5", _add_years(iso(l.settlement_date), 2), "2 years from settlement (Limitation Act 1980 s.10A)")
    if l.recovery_route == "contribution_1978" and l.settlement_date:
        return mk("contribution_1978", _add_years(iso(l.settlement_date), 2),
                  "2 years from judgment or agreed payment (Limitation Act 1980 s.10)")
    if l.recovery_route == "CPA_1987" and l.knowledge_date:
        due = _add_years(iso(l.knowledge_date), 3)
        if l.supply_date:
            longstop = _add_years(iso(l.supply_date), 10)
            if longstop < due:
                return mk("CPA_1987", longstop, "10-year longstop from supply (Limitation Act 1980 s.11A(3))")
        return mk("CPA_1987", due, "3 years from date of knowledge (Limitation Act 1980 s.11A)")
    return None


def regime_notes(l: Legal) -> list[str]:
    notes = []
    if l.regime == "conventional":
        notes.append("Conventional regime: no vehicle is on the AEVA list, so s.2/s.5 do not apply to this claim. "
                     "Pricing uses the s.5 recovery model as a proxy; the real route is contribution (1978 Act) or "
                     "CPA 1987. Take legal advice on the route.")
    elif l.regime == "AEVA_authorised":
        notes.append("Regime AEVA_authorised: assumes the AV Act 2024 authorisation regime is in force (prospective).")
    elif l.regime == "unspecified":
        notes.append("Legal regime not specified: assumed AEVA s.5. No vehicle is listed today, so confirm the route.")
    if l.recovery_route not in ("unspecified", "AEVA_s5") and l.regime != "conventional":
        notes.append(f"Recovery route {l.recovery_route} is priced with the AEVA s.5 model (a proxy).")
    if l.p_liable_to_victim is None:
        notes.append("P(other party liable to the victim) not assessed: avoidance by a careful driver is treated as the "
                     "whole liability case. AEVA s.5 recovery is derivative, so this may overstate the share.")
    return notes
