"""Usage: python -m insurance <bundle.json> [more.json ...] [--json]"""
import dataclasses
import json
import sys

from insurance.bundle import BundleError, load_bundle_file
from insurance.engine import decide
from insurance.report import render


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print(__doc__)
        return 2
    rc = 0
    for p in paths:
        try:
            verdict = decide(load_bundle_file(p))
        except BundleError as e:
            print(f"{p}: invalid bundle: {e}")
            rc = 1
            continue
        print(json.dumps(dataclasses.asdict(verdict), indent=2) if as_json else render(verdict))
        print()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
