"""Portfolio run: price many crashes and print a ranked recoverability map in GBP.

    python -m insurance.portfolio --n 20 --seed 7            # synthetic UK crashes (insurance/synth_bundles.py)
    python -m insurance.portfolio --dir insurance/examples   # your own bundle files
    add --single to use one estimator (finance then holds every claim at pull_logs_first)

Two PLACEHOLDER human models bracket the uncertainty: a quick one (0.7/1.0/1.5 s) and a slower one (0.7/1.2/2.0 s).
They are NOT the R157 CCDM/FSM models; swap them in via `estimators` once sim/ has the real parameters.
"""
from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path

from finance.recovery import fmt_gbp, rank, recoverability_map
from insurance.bridge import BridgedAssessment, assess_bundle
from insurance.bundle import load_bundle_file
from insurance.resolution import resolve
from insurance.counterfactual import HumanParams, KinematicEstimator

PLACEHOLDER_QUICK = HumanParams()
PLACEHOLDER_SLOW = dataclasses.replace(HumanParams(), reaction_mode_s=1.2, reaction_high_s=2.0,
                                       label="placeholder slow human (not R157)")


def default_estimators(single: bool = False) -> dict:
    # n=400 keeps a 20-crash run to a few seconds; the CI passed to finance widens accordingly (Wilson on n)
    est = {"placeholder_quick_human": KinematicEstimator(PLACEHOLDER_QUICK, n=400)}
    if not single:
        est["placeholder_slow_human"] = KinematicEstimator(PLACEHOLDER_SLOW, n=400)
    return est


def run(cases: list[tuple], single: bool = False) -> list[BridgedAssessment]:
    """cases: (bundle, reproduced) pairs."""
    out = []
    for b, rep in cases:
        r = assess_bundle(b, estimators=default_estimators(single), reproduced=rep)
        r.resolution = resolve(r, b)   # outcome + next steps, see insurance/resolution.py
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
              "Synthetic data; placeholder human models; decision support only. See docs/verification.md."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--n", type=int, default=20)
    a.add_argument("--seed", type=int, default=7)
    a.add_argument("--dir", type=Path, default=None)
    a.add_argument("--single", action="store_true")
    args = a.parse_args(argv)
    if args.dir:
        cases = [(load_bundle_file(p), True) for p in sorted(args.dir.glob("*.json"))]
    else:
        from insurance.synth_bundles import generate_cases
        cases = [(c.bundle, c.reproduced) for c in generate_cases(args.n, args.seed)]
    print(render(run(cases, args.single)))


if __name__ == "__main__":
    main()
