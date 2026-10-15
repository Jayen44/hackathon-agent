"""Optional Modal fan-out for counterfactual.compare(). CPU only.

Usage from code:
    from montecarlo.modal_fanout import app, modal_map
    with app.run():
        res = compare(ranges, drivers, n=20000, seed=0, map_fn=modal_map)

Results are identical to local runs for the same seed: uniforms are drawn
locally from the seed, chunks are evaluated remotely by the same pure
evaluate_chunk(), and results come back in order.

Verify (small n, cheap):  .venv/bin/modal run -m montecarlo.modal_fanout --n 200
"""
from __future__ import annotations

import modal

app = modal.App("accel-montecarlo")

image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install("numpy")
         .add_local_python_source("sim", "montecarlo"))


@app.function(image=image, cpu=1.0, memory=512, timeout=600)
def eval_chunk_remote(ranges, factories, u):
    from montecarlo.counterfactual import evaluate_chunk
    return evaluate_chunk(ranges, factories, u)


def modal_map(ranges, factories, chunks):
    """map_fn for counterfactual.compare(): one Modal call per chunk, order preserved."""
    return eval_chunk_remote.starmap([(ranges, factories, c) for c in chunks], order_outputs=True)


@app.local_entrypoint()
def main(n: int = 200, seed: int = 0):
    """Local vs Modal equality check on the test-fixture scenario and drivers (NOT R157 values)."""
    import time

    from montecarlo.counterfactual import compare
    from tests.test_montecarlo import cut_in_ranges, fixture_drivers

    ranges, drivers = cut_in_ranges(), fixture_drivers()
    t0 = time.perf_counter()
    local = compare(ranges, drivers, n, seed, keep_outcomes=True, chunk=50)
    t1 = time.perf_counter()
    remote = compare(ranges, drivers, n, seed, keep_outcomes=True, chunk=50, map_fn=modal_map)
    t2 = time.perf_counter()
    same = local == remote
    print(f"local  {t1 - t0:.2f}s  {local['drivers']}")
    print(f"modal  {t2 - t1:.2f}s  {remote['drivers']}")
    print(f"identical: {same}")
    if not same:
        raise SystemExit("Modal results differ from local")
