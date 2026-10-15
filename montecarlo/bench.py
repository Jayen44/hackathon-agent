"""Local throughput benchmark: .venv/bin/python -m montecarlo.bench [n]

Uses the TEST FIXTURE scenarios and drivers from tests/ (not R157 values,
not a real crash). Prints sim runs/sec for one driver and for the paired A/B run.
"""
from __future__ import annotations

import sys
import time

from montecarlo.counterfactual import compare, p_avoid
from tests.test_montecarlo import cut_in_ranges, fixture_drivers, lead_brake_ranges


def bench(n: int = 1000) -> None:
    drivers = fixture_drivers()
    for label, r in (("cut_in", cut_in_ranges()), ("lead_brake", lead_brake_ranges())):
        t0 = time.perf_counter()
        one = p_avoid(r, drivers["fixture_A"], n=n, seed=0)
        t1 = time.perf_counter()
        both = compare(r, drivers, n=n, seed=0)
        t2 = time.perf_counter()
        print(f"{label:10s} single driver: {n / (t1 - t0):7.0f} runs/s  (n={n}, p={one['p']:.3f})")
        print(f"{label:10s} paired A+B:    {2 * n / (t2 - t1):7.0f} runs/s  "
              f"({n / (t2 - t1):.0f} samples/s)")
        del both


if __name__ == "__main__":
    bench(int(sys.argv[1]) if len(sys.argv) > 1 else 1000)
