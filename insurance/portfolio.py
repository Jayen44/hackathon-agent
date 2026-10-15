"""Portfolio run: price many crashes and print a ranked recoverability map in GBP.

    python -m insurance.portfolio --n 20 --seed 7            # synthetic UK crashes (insurance/synth_bundles.py)
    python -m insurance.portfolio --dir insurance/examples   # your own bundle files
    add --single to use one careful-driver model (finance then holds every claim at pull_logs_first)

The counterfactual comes from the sim (UN R157 Annex 3 models A and B, via insurance/sim_estimator.py); about 3 s per claim.
First run: `python -m insurance.sim_link` to fetch the sim snapshot.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from finance.recovery import fmt_gbp, rank, recoverability_map
from insurance.bridge import BridgedAssessment, assess_bundle
from insurance.bundle import load_bundle_file
from insurance.resolution import resolve


def sim_inputs(b, single: bool = False):
    """(estimators, reproduced) to pass to assess_bundle. Normally (None, None): the bridge asks the sim for both models and
    takes the sim's own reproduction check. `single` keeps only careful driver A (finance then holds the claim at pull_logs)."""
    if not single or b.conflict is None or not b.outcome.collided:
        return None, None
    from insurance.sim_estimator import run_sim
    run = run_sim(b)
    return dict(list(run.estimators.items())[:1]), bool(run.reproduced)


def run(cases: list, single: bool = False, min_net_gbp: float = 0.0, ledger: Path | None = None) -> list[BridgedAssessment]:
    """cases: bundles, or (bundle, reproduced) pairs where reproduced=None lets the sim decide."""
    out = []
    for c in cases:
        b, rep = c if isinstance(c, tuple) else (c, None)
        est, sim_rep = sim_inputs(b, single)
        r = assess_bundle(b, estimators=est, reproduced=rep if rep is not None else sim_rep, min_net_gbp=min_net_gbp)
        r.resolution = resolve(r, b)   # outcome + next steps, see insurance/resolution.py
        if ledger:
            from insurance import ledger as L
            r.changes = L.changes(ledger, r, r.resolution)
            L.record(ledger, r, r.resolution)
        out.append(r)
    return out


def render(results: list[BridgedAssessment]) -> str:
    priced = [r.recovery for r in results if r.recovery is not None]
    order = {id(a): r for a, r in ((r.recovery, r) for r in results if r.recovery is not None)}
    lines = [f"{'claim':18} {'liable':16} {'decision':16} {'P(avoid) low/mid/high':22} {'expected recovery low / mid / high'}",
             "-" * 112]
    for a in rank(priced):
        r = order[id(a)]
        ev = a.expected_recovery
        money = f"{fmt_gbp(ev.low)} / {fmt_gbp(ev.mid)} / {fmt_gbp(ev.high)}" if ev else "n/a (" + a.reasons[0][:40] + ")"
        p = a.p_avoid
        lines.append(f"{a.claim_id:18} {r.verdict.liable:16} {a.decision:16} "
                     f"{p.low:5.0%}/{p.mid:4.0%}/{p.high:4.0%}{'':6} {money}")
    skipped = [r for r in results if r.recovery is None]
    if skipped:
        lines += ["", f"Not priced ({len(skipped)}): " + "; ".join(f"{r.verdict.case_id}: {r.notes[0][:60]}" for r in skipped[:6])
                  + (" ..." if len(skipped) > 6 else "")]
    lines += ["", "Recoverable by crash type (claims worth pursuing or investigating, GBP low / mid / high):"]
    rmap = recoverability_map(priced)
    lines += [f"  {k:20} {fmt_gbp(v.low)} / {fmt_gbp(v.mid)} / {fmt_gbp(v.high)}" for k, v in sorted(rmap.items())] or ["  (none)"]
    counts: dict[str, int] = {}
    for a in priced:
        counts[a.decision] = counts.get(a.decision, 0) + 1
    byo: dict[str, int] = {}
    for r in results:
        o = getattr(r, "resolution", None)
        if o:
            byo[o.outcome] = byo.get(o.outcome, 0) + 1
    lines += ["", "Outcomes (every crash lands in one): " + ", ".join(f"{k}={v}" for k, v in sorted(byo.items()))]
    lines += ["", "Decisions: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
              "Synthetic data; careful-driver models A and B from the sim (UN R157 Annex 3); decision support only. See docs/verification.md."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--n", type=int, default=20)
    a.add_argument("--seed", type=int, default=7)
    a.add_argument("--dir", type=Path, default=None)
    a.add_argument("--single", action="store_true")
    a.add_argument("--min-net", type=float, default=0.0, help="policy: minimum net GBP to pursue (default 0)")
    a.add_argument("--ledger", type=Path, default=None, help="append every run to this JSONL and print what changed")
    args = a.parse_args(argv)
    if args.dir:
        cases = [load_bundle_file(p) for p in sorted(args.dir.glob("*.json"))]
    else:
        from insurance.synth_bundles import generate_cases
        cases = [c.bundle for c in generate_cases(args.n, args.seed)]
    results = run(cases, args.single, args.min_net, args.ledger)
    print(render(results))
    ch = [(r.verdict.case_id, c) for r in results for c in getattr(r, "changes", [])]
    if ch:
        print("\nChanged since the last run:\n" + "\n".join(f"  {cid}: {c}" for cid, c in ch))


if __name__ == "__main__":
    main()
