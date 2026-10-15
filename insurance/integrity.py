"""Evidence integrity checks (CLAUDE.md 1.4). Run before any liability decision."""
from __future__ import annotations

from dataclasses import dataclass, field

from insurance.bundle import CrashBundle


@dataclass
class IntegrityReport:
    blocking: list[str] = field(default_factory=list)  # evidence can't be trusted -> human review
    warnings: list[str] = field(default_factory=list)  # noted, decision may proceed

    @property
    def ok(self) -> bool:
        return not self.blocking


def check_integrity(b: CrashBundle, clock_tolerance_s: float = 0.25) -> IntegrityReport:
    r = IntegrityReport()
    i = b.integrity
    if i.tamper_flag:
        r.blocking.append("Tamper flag raised on the evidence.")
    if not i.hashes_present:
        r.blocking.append("No hashes/signatures: evidence is not tamper-evident.")
    if not i.chain_of_custody:
        r.warnings.append("No chain of custody recorded.")
    for src, off in i.clock_offsets_s.items():
        if abs(off) > clock_tolerance_s:
            r.blocking.append(f"Clock offset for '{src}' is {off:+.2f}s (tolerance {clock_tolerance_s}s).")
    for a, z in i.log_gaps:
        if a <= b.t_crash <= z or abs(a - b.t_crash) < 5 or abs(z - b.t_crash) < 5:
            r.blocking.append(f"Log gap {a:.1f}-{z:.1f}s overlaps or abuts the crash at {b.t_crash:.1f}s.")
        else:
            r.warnings.append(f"Log gap {a:.1f}-{z:.1f}s (away from the crash).")
    return r
