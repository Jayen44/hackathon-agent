"""Read-only link to Vakhtang's physics (`sim/`, `montecarlo/` on branch `sim`).

insurance/ no longer models driver physics itself: the careful-driver counterfactual comes from `montecarlo.estimate`
(UN R157 Annex 3 models A and B). We never edit that code. `vendor()` snapshots it from git into `.sim_src` (gitignored);
set SIM_SRC to point at a local checkout instead.

    python -m insurance.sim_link          # refresh the snapshot from origin/sim
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(os.environ.get("SIM_SRC", ROOT / ".sim_src"))
PATHS = ("sim", "montecarlo")


class SimUnavailable(RuntimeError):
    """The sim package could not be imported. The message says how to fix it."""


def vendor(ref: str = "origin/sim") -> Path:
    subprocess.run(["git", "fetch", "origin"], cwd=ROOT, check=False, capture_output=True)
    sha = subprocess.run(["git", "rev-parse", ref], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    tar = subprocess.run(["git", "archive", ref, *PATHS], cwd=ROOT, check=True, capture_output=True).stdout
    SRC.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        t.extractall(SRC, filter="data")
    (SRC / "SOURCE.json").write_text(json.dumps({"ref": ref, "sha": sha}))
    return SRC


def source_info() -> dict:
    p = SRC / "SOURCE.json"
    return json.loads(p.read_text()) if p.exists() else {"ref": None, "sha": None}


_estimate = None


def load_estimate():
    """Import `montecarlo.estimate.estimate` once; raise SimUnavailable with a fix-it message otherwise."""
    global _estimate
    if _estimate is not None:
        return _estimate
    if (SRC / "montecarlo").is_dir() and str(SRC) not in sys.path:
        sys.path.append(str(SRC))
    try:
        from montecarlo.estimate import estimate
    except Exception as e:  # noqa: BLE001 - any import problem means no physics
        raise SimUnavailable(f"the sim package is not available ({type(e).__name__}: {e}). "
                             "Run: python -m insurance.sim_link   (needs git access to origin/sim and numpy)") from e
    _estimate = estimate
    return estimate


def timeline_check(bundle: dict) -> dict | None:
    load_estimate()
    from montecarlo.evidence import timeline_check as tc
    return tc(bundle) if bundle.get("conflict") else None


if __name__ == "__main__":
    p = vendor()
    print(f"vendored {source_info()} into {p}")
