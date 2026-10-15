"""Load and validate eval/labels.csv (issue #5). See eval/README.md for how the labels were made."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

PATH = Path(__file__).with_name("labels.csv")
COLUMNS = ("crash_id", "source", "crash_type", "avoidable_by_careful_driver", "pursue_recovery", "who_pays",
           "reason", "labeller")
ALLOWED = {
    "avoidable_by_careful_driver": {"yes", "no", "unsure"},
    "pursue_recovery": {"yes", "no", "pull_logs"},
    "who_pays": {"human", "tech", "no_fault", "review"},
    "labeller": {"claude-draft", "antonio"},
}


@dataclass(frozen=True)
class Label:
    crash_id: str
    source: str
    crash_type: str
    avoidable_by_careful_driver: str
    pursue_recovery: str
    who_pays: str
    reason: str
    labeller: str


def load_labels(path: Path | str = PATH) -> list[Label]:
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError(f"columns must be {COLUMNS}, got {reader.fieldnames}")
        rows = [Label(**row) for row in reader]
    ids = [r.crash_id for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("crash_id values must be unique")
    for r in rows:
        for col, ok in ALLOWED.items():
            if getattr(r, col) not in ok:
                raise ValueError(f"{r.crash_id}: {col}={getattr(r, col)!r} not in {sorted(ok)}")
        if not r.reason.strip() or not r.source.startswith("synthetic:"):
            raise ValueError(f"{r.crash_id}: needs a reason and a 'synthetic:' source")
    return rows
