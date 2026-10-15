"""Case ledger: an append-only JSONL record of every run, so a re-run after new evidence shows what changed.

    record(path, assessment, resolution)     append one line per run
    changes(path, assessment, resolution)    human-readable differences versus the last run of the same case (call BEFORE record)

Plain files, no database: easy to inspect, diff and commit. Each line keeps the outcome, decision, codes, the expected
recovery range, the deadline and the provenance (estimators, thresholds, date) that produced it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _row(r, x) -> dict:
    ev = r.recovery.expected_recovery if r.recovery else None
    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "case_id": r.verdict.case_id, "liable": r.verdict.liable, "outcome": x.outcome,
        "decision": r.recovery.decision if r.recovery else None,
        "codes": sorted(r.recovery.codes) if r.recovery else [],
        "ev_gbp": [round(ev.low), round(ev.mid), round(ev.high)] if ev else None,
        "deadline": r.deadline.due.isoformat() if r.deadline else None,
        "provenance": r.provenance,
    }


def record(path: str | Path, r, x) -> dict:
    row = _row(r, x)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def last(path: str | Path, case_id: str) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    found = None
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            if d["case_id"] == case_id:
                found = d
    return found


def changes(path: str | Path, r, x) -> list[str]:
    """Differences between this run and the previous run of the same case ([] = first run or unchanged)."""
    old, new = last(path, r.verdict.case_id), _row(r, x)
    if old is None:
        return []
    out = []
    for k, label in (("liable", "liable party"), ("outcome", "outcome"), ("decision", "decision"), ("ev_gbp", "expected recovery"),
                     ("deadline", "limitation deadline")):
        if old[k] != new[k]:
            out.append(f"{label}: {old[k]} -> {new[k]}")
    gone, added = set(old["codes"]) - set(new["codes"]), set(new["codes"]) - set(old["codes"])
    if gone:
        out.append("gates/caveats cleared: " + ", ".join(sorted(gone)))
    if added:
        out.append("new gates/caveats: " + ", ".join(sorted(added)))
    if old["provenance"] != new["provenance"]:
        out.append("run settings changed (estimators, thresholds or date)")
    return out
