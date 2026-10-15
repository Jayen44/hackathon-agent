"""Tests never call the real sim by default (it needs a git snapshot and ~3 s per claim).

`run_sim` is replaced by golden results recorded from the REAL sim (tests/data/sim_snapshots.json, made by
scripts/snapshot_sim.py). Bundles not in the snapshot (synthetic portfolios) get a deterministic TEST DOUBLE: it is not
physics, only a stable stand-in so structural tests (every crash resolves, rendering, ledger) have something to price.
Mark a test `@pytest.mark.live_sim` to run it against the real sim; it skips when the sim is unavailable.
"""
import hashlib
import json
from pathlib import Path

import pytest

from insurance.counterfactual import FixedEstimator
from insurance.sim_estimator import SimRun, result_from_sim

SNAP = Path(__file__).resolve().parent / "data" / "sim_snapshots.json"


def pytest_configure(config):
    config.addinivalue_line("markers", "live_sim: runs the real sim (slow; skipped if the sim is unavailable)")


def _snapshot() -> dict:
    return json.loads(SNAP.read_text(encoding="utf-8"))["cases"] if SNAP.exists() else {}


def _double(case_id: str) -> dict:
    h = int(hashlib.sha256(case_id.encode()).hexdigest(), 16)
    p_a = (0.0, 0.5, 1.0)[h % 3]
    p_b = min(1.0, p_a + (0.0, 0.0, 0.4)[(h // 3) % 3]) if p_a < 1.0 else 1.0
    mk = lambda p, m: {"p_avoid": p, "avoids_at_p50": p >= 0.5, "median_impact_speed_mps": 0.0 if p >= 0.5 else 8.0,  # noqa: E731
                       "n_samples": 300, "model": f"TEST DOUBLE {m} (not physics)", "notes": []}
    return {"reproduced": bool((h // 9) % 2), "tier": 2, "timeline": {"consistent": True},
            "drivers": {"careful_a": mk(p_a, "A"), "careful_b": mk(p_b, "B")}}


@pytest.fixture(autouse=True)
def fake_sim(monkeypatch, request):
    if request.node.get_closest_marker("live_sim"):
        return
    snaps = _snapshot()

    def fake(b, n=300, tier=None, sensitivity=False):
        s = snaps.get(b.case_id) or _double(b.case_id)
        return SimRun(case_id=b.case_id, tier=s.get("tier", 2),
                      estimators={k: FixedEstimator(result_from_sim(d)) for k, d in s["drivers"].items()},
                      reproduced=s.get("reproduced"), timeline=s.get("timeline"), source={"ref": "snapshot"})

    monkeypatch.setattr("insurance.sim_estimator.run_sim", fake)
