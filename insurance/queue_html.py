"""Insurer-facing claims queue as one self-contained HTML file (no server, no dependencies).

    python -m insurance.queue_html --dir insurance/examples -o queue.html [--min-net 2000]

One row per claim: outcome, who is liable, GBP range, deadline; click a row for the next steps, reasons and provenance.
Open the file in a browser or attach it to an email.
"""
from __future__ import annotations

import argparse
import html
from datetime import date
from pathlib import Path

from finance.recovery import fmt_gbp
from insurance.bundle import load_bundle_file
from insurance.portfolio import run

ORDER = ["PURSUE", "PULL_LOGS", "NEEDS_INPUTS", "HUMAN_REVIEW", "SETTLE_NO_RECOVERY", "RECOVER_FROM_INSURED",
         "MOTOR_CLAIM", "CLOSE_NO_CLAIM"]
CSS = ("body{font:14px system-ui,sans-serif;margin:24px;color:#1a1a1a}table{border-collapse:collapse;width:100%}"
       "th,td{border-bottom:1px solid #ddd;padding:6px 10px;text-align:left;vertical-align:top}th{background:#f4f4f4}"
       ".PURSUE{color:#0a6b2d;font-weight:600}.HUMAN_REVIEW,.NEEDS_INPUTS{color:#9a5b00;font-weight:600}"
       ".urgent{color:#b00020;font-weight:600}details{margin:4px 0}small{color:#555}")


def _row(r, x) -> str:
    e = html.escape
    ev = r.recovery.expected_recovery if r.recovery else None
    money = f"{fmt_gbp(ev.low)} / {fmt_gbp(ev.mid)} / {fmt_gbp(ev.high)}" if ev else "not priced"
    dl = ""
    if r.deadline:
        dl = f'<span class="{"urgent" if r.deadline.urgent else ""}">{r.deadline.due.isoformat()} ({r.deadline.days_left} d)</span>'
    steps = "".join(f"<li>[{e(s.who)}] {e(s.action)} <small>&rarr; {e(s.unblocks)}</small></li>" for s in x.next_steps)
    reasons = "".join(f"<li>{e(t)}</li>" for t in (r.recovery.reasons if r.recovery else r.notes[:2]))
    sign = f"<p><b>Suggested sign-off:</b> {e(', '.join(x.sign_off))}</p>" if x.sign_off else ""
    prov = e("; ".join(r.provenance.get("estimators", [])))
    return (f'<tr><td><details><summary>{e(r.verdict.case_id)}</summary><p>{e(x.headline)}</p>{sign}<ol>{steps}</ol>'
            f'<p><b>Why:</b></p><ul>{reasons}</ul><small>Estimators: {prov}. Illustrative thresholds. {e(r.verdict.summary)}</small>'
            f'</details></td><td class="{e(x.outcome)}">{e(x.outcome)}</td><td>{e(r.verdict.liable)}</td>'
            f'<td>{e(money)}</td><td>{dl}</td></tr>')


def render_queue(results: list, today: date) -> str:
    rows = sorted(results, key=lambda r: (ORDER.index(r.resolution.outcome) if r.resolution.outcome in ORDER else 99,
                                          r.deadline.days_left if r.deadline else 10**9))
    body = "".join(_row(r, r.resolution) for r in rows)
    counts = {}
    for r in results:
        counts[r.resolution.outcome] = counts.get(r.resolution.outcome, 0) + 1
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    return (f"<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>Claims queue</title><style>{CSS}</style><h1>Claims queue</h1><p>{html.escape(summary)} &middot; run {today}</p>"
            "<table><tr><th>Claim</th><th>Outcome</th><th>Liable</th><th>Expected recovery (low / mid / high)</th><th>Deadline</th></tr>"
            f"{body}</table><p><small>Triage evidence for a claims handler, not legal advice or a liability finding. Synthetic data, "
            "R157 careful-driver models from the sim, thresholds illustrative.</small></p></html>")


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--dir", type=Path, required=True)
    a.add_argument("-o", "--out", type=Path, default=Path("queue.html"))
    a.add_argument("--min-net", type=float, default=0.0)
    args = a.parse_args(argv)
    cases = [load_bundle_file(p) for p in sorted(args.dir.glob("*.json"))]
    results = run(cases, min_net_gbp=args.min_net)
    args.out.write_text(render_queue(results, date.today()), encoding="utf-8")
    print(f"wrote {args.out} ({len(results)} claims)")


if __name__ == "__main__":
    main()
