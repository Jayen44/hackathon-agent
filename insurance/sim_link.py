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


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True)


def vendor(ref: str = "origin/sim") -> Path:
    """Copy sim/ and montecarlo/ from `ref` (default origin/sim) into SRC. Fetches the branch explicitly first, because a
    clone may not have refs/remotes/origin/sim yet; errors say which git command failed and what it printed."""
    branch = ref.split("/", 1)[1] if "/" in ref else ref
    _git("fetch", "origin", f"{branch}:refs/remotes/origin/{branch}")
    rev = _git("rev-parse", "--verify", f"{ref}^{{commit}}")
    if rev.returncode != 0:
        raise SimUnavailable(f"cannot resolve {ref} in {ROOT}: {rev.stderr.decode(errors='replace').strip()}. "
                             f"Check `git remote -v` and `git fetch origin {branch}`, or set SIM_SRC to a local checkout.")
    sha = rev.stdout.decode().strip()
    tar = _git("archive", ref, *PATHS)
    if tar.returncode != 0:
        raise SimUnavailable(f"git archive {ref} failed: {tar.stderr.decode(errors='replace').strip()}")
    SRC.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as t:
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
