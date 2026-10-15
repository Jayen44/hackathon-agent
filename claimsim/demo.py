"""Run the illustrative claim and print a readable summary.

    python -m claimsim.demo [--n 10000] [--seed 42] [--json]

ILLUSTRATIVE ONLY: synthetic inputs and uncalibrated synthetic assumptions; not a forecast.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from claimsim.agent_tools import simulate_claim_cost

EXAMPLE = Path(__file__).with_name("examples") / "illustrative_claim.json"


def gbp(x: float) -> str:
    return f"£{x:,.0f}"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--n", type=int, default=10_000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    out = simulate_claim_cost(json.loads(EXAMPLE.read_text()), n_simulations=a.n, seed=a.seed)
    if a.json:
        print(json.dumps(out, indent=1))
        return
    print(f"Claim {out['claim_id']}  |  {out['config']['n_simulations']:,} simulations, seed {out['config']['seed']}  |  "
          f"{out['model_version']}, assumptions {out['assumptions_version']}\n")
    for w in out["warnings"]:
        print(f"  ! {w}")
    print(f"\n{'scenario (conditional)':<28}{'gross':>9}{'payment':>10}{'expenses':>10}{'recovered':>11}"
          f"{'NET mean':>10}{'p50':>9}{'p90':>9}{'p95':>9}{'P(>25k)':>9}")
    for name, s in out["scenarios"].items():
        q = s["net_exposure_percentiles"]
        print(f"{name:<28}{gbp(s['expected_gross_loss']):>9}{gbp(s['expected_insurer_payment']):>10}"
              f"{gbp(s['expected_legal_and_handling']):>10}{gbp(s['expected_recoveries']):>11}"
              f"{gbp(s['expected_net_exposure']):>10}{gbp(q['p50']):>9}{gbp(q['p90']):>9}{gbp(q['p95']):>9}"
              f"{s['prob_net_exposure_exceeds']['25,000']:>9.1%}")
    print("\n" + (out.get("conditional_only") or "Probability-weighted results available."))
    first = next(iter(out["sensitivity"]))
    key = "B_insured_50pct_liable" if "B_insured_50pct_liable" in out["sensitivity"] else first
    print(f"\nWhat drives scenario {key} (one-way, expected net exposure low -> high):")
    for r in out["sensitivity"][key]["one_way"]:
        print(f"  {r['driver']:<22}{gbp(r['expected_low']):>9} -> {gbp(r['expected_high']):<9} "
              f"swing {gbp(r['swing_expected']):>8}   evidence: {r['evidence_to_collect']}")
    print("\nMissing information:")
    for m in out["missing_information"]:
        print(f"  - {m['item']}: {m['why_it_matters']} (resolve with: {m['evidence_that_would_resolve_it']})")
    hr = out["human_review"]
    print(f"\nHuman review: {'REQUIRED' if hr['required'] else 'not triggered'}. {hr['note']}")
    for r in hr["reasons"]:
        print(f"  - {r}")


if __name__ == "__main__":
    main()
