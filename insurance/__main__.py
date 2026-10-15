"""Usage: python -m insurance <bundle.json> [more.json ...] [--json] [--price [--legal-cost LOW,HIGH]]

--price also runs finance/ to price the recovery (GBP). Legal cost is TODO in finance/tables.py,
so pass --legal-cost (e.g. 2000,5000) to get a figure; otherwise the result is 'cannot_price'.
"""
import dataclasses
import json
import sys

from insurance.bridge import assess_bundle
from insurance.bundle import BundleError, load_bundle_file
from insurance.engine import decide
from insurance.report import render, render_recovery


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    price = "--price" in argv
    legal = None
    if "--legal-cost" in argv:
        i = argv.index("--legal-cost")
        lo, hi = argv[i + 1].split(",")
        legal = (float(lo), float(hi))
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
            r = assess_bundle(bundle, legal_cost_gbp=legal)
            print(json.dumps(dataclasses.asdict(r), indent=2, default=str) if as_json
                  else render(r.verdict) + "\n\n" + render_recovery(r))
        else:
            verdict = decide(bundle)
            print(json.dumps(dataclasses.asdict(verdict), indent=2) if as_json else render(verdict))
        print()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
