"""Snapshot the REAL sim's output for every example bundle into tests/data/sim_snapshots.json.

    python scripts/snapshot_sim.py            # needs the sim (python -m insurance.sim_link) and a few minutes

Offline tests use these golden results instead of calling the sim (see tests/conftest.py); one slow test checks that the
snapshots still match the live sim. Re-run after changing the examples or updating the sim snapshot.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from insurance import sim_link  # noqa: E402
from insurance.bundle import load_bundle_file  # noqa: E402
from insurance.sim_estimator import run_sim  # noqa: E402

N = 300
out = {"_meta": {"n": N, "sim": sim_link.source_info()}, "cases": {}}
for p in sorted((ROOT / "insurance" / "examples").glob("*.json")):
    b = load_bundle_file(p)
    if b.conflict is None or not b.outcome.collided:
        continue
    r = run_sim(b, n=N)
    out["cases"][b.case_id] = {
        "reproduced": r.reproduced, "tier": r.tier, "timeline": r.timeline,
        "drivers": {k: {"p_avoid": e.result.p_avoid, "avoids_at_p50": e.result.avoids_at_p50,
                        "median_impact_speed_mps": e.result.median_impact_speed_mps, "n_samples": e.result.n_samples,
                        "model": e.result.model, "notes": e.result.notes} for k, e in r.estimators.items()}}
    print(b.case_id, {k: round(v["p_avoid"], 2) for k, v in out["cases"][b.case_id]["drivers"].items()}, r.reproduced,
          flush=True)
dest = ROOT / "tests" / "data"
dest.mkdir(exist_ok=True)
(dest / "sim_snapshots.json").write_text(json.dumps(out, indent=1))
print("wrote", dest / "sim_snapshots.json")
