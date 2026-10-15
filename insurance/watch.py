"""Deadline watch: which claims are about to become time-barred?

    python -m insurance.watch --dir insurance/examples [--today 2027-02-01] [--within 180]

Reads the `legal` block of every bundle (route + dates) and lists claims by days left. Limitation errors lose a claim
outright, so this runs without the pricing engine. Lawyer review needed before relying on any date.
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from insurance.bundle import load_bundle_file
from insurance.legal import limitation_deadline


def watch(directory: Path, today: date, within_days: int | None = None) -> list[tuple[str, str]]:
    rows = []
    for p in sorted(directory.glob("*.json")):
        b = load_bundle_file(p)
        d = limitation_deadline(b.legal, today)
        if d and (within_days is None or d.days_left <= within_days):
            rows.append((d.days_left, b.case_id, d))
    rows.sort(key=lambda t: t[0])
    return [(cid, ("OVERDUE " if d.days_left < 0 else "URGENT  " if d.urgent else "        ")
             + f"{d.due.isoformat()} ({d.days_left} days) {d.route}: {d.basis}") for _, cid, d in rows]


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--dir", type=Path, required=True)
    a.add_argument("--today", type=date.fromisoformat, default=date.today())
    a.add_argument("--within", type=int, default=None, help="only claims with this many days or fewer left")
    args = a.parse_args(argv)
    rows = watch(args.dir, args.today, args.within)
    print("\n".join(f"{cid:38} {line}" for cid, line in rows) or "No claims with a computable deadline.")


if __name__ == "__main__":
    main()
