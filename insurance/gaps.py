"""Deterministic gap audit: what is still missing or unproven. No LLM, no network; costs ~nothing to run.

    python -m insurance.gaps            # compact table, highest priority first
    python -m insurance.gaps --json     # machine-readable (used by the gap-closer agent)
    python -m insurance.gaps --mine     # only gaps owned by the insurance side

Each gap has an owner ('insurance' | 'finance' | 'sim' | 'both'), a priority (1 = most important), a stable id and a
one-line `fix`. Gaps in other people's areas are reported, never fixed from here: file an issue instead.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from insurance.bundle import load_bundle_file
from insurance.engine import decide

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "insurance" / "examples"

# Every decision path the spec (docs/liability-spec.md section 3) says the engine must handle.
EXPECTED_PATHS = {
    "outcome.no_collision": "no collision recorded",
    "integrity.blocked": "evidence fails integrity checks",
    "control.human_driving": "human was driving (manual or assisted)",
    "control.human_override": "human overrode the system",
    "software.unapproved": "unapproved software version",
    "odd.outside": "outside the operational design domain",
    "faults.critical": "critical fault before the crash",
    "handover.human_took_control": "human took over in time",
    "handover.human_ignored": "adequate warning, human did not respond",
    "handover.short_warning": "inadequate handover warning",
    "cf.system_fell_short": "competent human would have avoided it",
    "cf.unavoidable": "unavoidable for a competent human",
    "cf.borderline": "borderline counterfactual -> review",
    "cf.no_conflict": "no reconstructed conflict -> review",
    # Verified in AEVA 2018 (docs/verification.md) but not yet implemented:
    "law.s3_2_person_in_charge_negligence": "AEVA s.3(2): wholly due to the person's negligence in engaging the system",
    "law.s4_software_exclusion": "AEVA s.4: unauthorised software change or missed safety-critical update",
}
# Hazard kinds R157 covers (cut-in, cut-out, lead-vehicle deceleration) plus the base case.
EXPECTED_SCENARIOS = {"constant_hazard", "lead_braking", "cut_in"}


@dataclass
class Gap:
    id: str
    owner: str
    priority: int
    what: str
    fix: str


def _todos() -> list[Gap]:
    out: list[Gap] = []
    owners = {"finance": "finance", "sim": "sim", "insurance": "insurance"}
    for folder, owner in owners.items():
        base = ROOT / folder
        if not base.exists():
            continue
        for f in base.rglob("*.py"):
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if re.search(r"#\s*(TODO|FIXME)|\bTODO\(", line):
                    out.append(Gap(f"todo:{f.relative_to(ROOT).as_posix()}:{n}", owner, 3,
                                   line.strip()[:90], "resolve or delete the marker"))
    return out


def _pricing_cells() -> list[Gap]:
    try:
        from finance import tables
    except Exception:  # finance missing: nothing to audit
        return []
    out: list[Gap] = []
    unpriced = [k for k, v in tables.CLAIM_VALUE_BY_UK_SEVERITY.items() if not v.priced]
    if unpriced:
        out.append(Gap("pricing:claim_value", "finance", 1,
                       f"{len(unpriced)} UK severities cannot be priced: {', '.join(unpriced[:4])}...",
                       "finance to source the missing value (issue #4)"))
    return out


def _path_coverage() -> list[Gap]:
    seen: set[str] = set()
    for p in sorted(EXAMPLES.glob("*.json")):
        v = decide(load_bundle_file(p))
        for s in v.steps:
            if s.code:
                seen.add(s.code)
    return [Gap(f"path:{code}", "insurance", 1 if code.startswith("law.") else 2,
                f"no example bundle exercises: {desc}", "add an example + a test (and the engine rule if missing)")
            for code, desc in EXPECTED_PATHS.items() if code not in seen]


def _scenario_coverage() -> list[Gap]:
    seen = set()
    for p in EXAMPLES.glob("*.json"):
        c = load_bundle_file(p).conflict
        seen.add(getattr(c, "kind", "constant_hazard") if c else "constant_hazard")
    return [Gap(f"scenario:{k}", "insurance", 2, f"no example or estimator support for hazard kind '{k}'",
                "extend Conflict + estimators (issue #13)") for k in sorted(EXPECTED_SCENARIOS - seen)]


def _files() -> list[Gap]:
    need = {"insurance/synth_bundles.py": ("insurance", 2, "no bundles generated from the UK synthetic crashes (issue #9)"),
            "insurance/portfolio.py": ("insurance", 3, "no ranked recoverability map across many crashes (issue #10)"),
            "eval/labels.csv": ("finance", 2, "no hand-labelled crashes for evaluation (issue #5)")}
    return [Gap(f"missing:{p}", o, pr, w, f"create {p}") for p, (o, pr, w) in need.items() if not (ROOT / p).exists()]


def audit() -> list[Gap]:
    gaps = _pricing_cells() + _path_coverage() + _scenario_coverage() + _files() + _todos()
    return sorted(gaps, key=lambda g: (g.priority, g.owner, g.id))


def main(argv: list[str]) -> int:
    gaps = audit()
    if "--mine" in argv:
        gaps = [g for g in gaps if g.owner in ("insurance", "both")]
    if "--json" in argv:
        print(json.dumps([asdict(g) for g in gaps], indent=2))
    else:
        for g in gaps:
            print(f"P{g.priority} {g.owner:9} {g.id:48} {g.what}")
        print(f"\n{len(gaps)} gap(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
