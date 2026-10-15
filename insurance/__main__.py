"""Usage: python -m insurance <bundle.json> [more.json ...] [--json] [--price [--legal-cost LOW,HIGH]]

--single uses one careful-driver model; --min-net GBP sets the pursue threshold;
--ledger FILE logs the run and prints what changed since the last one.
--price also runs finance/ to price the recovery (GBP). Legal cost comes from finance/tables.py
(CPR PD 45, claims up to GBP 100k); pass --legal-cost (e.g. 2000,5000) to override it, or for
larger claims where the table is still TODO (otherwise the result is 'cannot_price').
"""
import dataclasses
import json
import sys

from insurance.bridge import assess_bundle
from insurance.bundle import BundleError, load_bundle_file
from insurance.engine import decide
from insurance.report import render, render_recovery
from insurance.resolution import render_resolution, resolve


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    price = "--price" in argv
    single = "--single" in argv
    legal = None
    if "--legal-cost" in argv:
        i = argv.index("--legal-cost")
        lo, hi = argv[i + 1].split(",")
        legal = (float(lo), float(hi))
        del argv[i:i + 2]
    min_net = 0.0
    if "--min-net" in argv:
        i = argv.index("--min-net")
        min_net = float(argv[i + 1])
        del argv[i:i + 2]
    ledger = None
    if "--ledger" in argv:
        i = argv.index("--ledger")
        ledger = argv[i + 1]
        del argv[i:i + 2]
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print(__doc__)
        return 2
    rc = 0
    for p in paths:
        try:
            bundle = load_bundle_file(p)
        except BundleError as e:
            print(f"{p}: invalid bundle: {e}")
            rc = 1
            continue
        if price:
            from insurance.portfolio import sim_inputs
            est, sim_rep = sim_inputs(bundle, single=single)
            r = assess_bundle(bundle, legal_cost_gbp=legal, min_net_gbp=min_net, estimators=est, reproduced=sim_rep)
            x = resolve(r, bundle)
            print(json.dumps(dataclasses.asdict(r), indent=2, default=str) if as_json
                  else render(r.verdict) + "\n\n" + render_recovery(r)
                  + "\n\n" + render_resolution(x))
            if ledger and not as_json:
                from insurance import ledger as L
                for c in L.changes(ledger, r, x):
                    print("changed since last run: " + c)
                L.record(ledger, r, x)
        else:
            verdict = decide(bundle)
            print(json.dumps(dataclasses.asdict(verdict), indent=2) if as_json else render(verdict))
        print()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
