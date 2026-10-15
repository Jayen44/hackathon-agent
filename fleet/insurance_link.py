"""Read-only link to the insurance team's code (origin/insurance: insurance/, finance/, agents/, ukcrash/).

We never edit their code. `vendor()` snapshots it from git into fleet/.insurance_src (gitignored) so
it can be imported locally and shipped in the Modal image. If it is missing or fails to import,
every caller gets a clear "pricing unavailable" result instead of a crash.

    python -m fleet.insurance_link        # refresh the snapshot from origin/insurance
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("FLEET_INSURANCE_SRC", HERE / ".insurance_src"))
PATHS = ("insurance", "finance", "agents", "ukcrash")
DISCLAIMER = ("Triage evidence for a human claims handler, not a liability ruling or legal advice. "
              "Simulation-based, with stated assumptions and a sim-to-real gap.")


def vendor(ref: str = "origin/insurance") -> Path:
    repo = HERE.parent
    subprocess.run(["git", "fetch", "origin"], cwd=repo, check=False, capture_output=True)
    sha = subprocess.run(["git", "rev-parse", ref], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
    tar = subprocess.run(["git", "archive", ref, *PATHS], cwd=repo, check=True, capture_output=True).stdout
    SRC.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        t.extractall(SRC, filter="data")
    (SRC / "SOURCE.json").write_text(json.dumps({"ref": ref, "sha": sha}))
    return SRC


_mods: dict | None = None
_err: str | None = None


def load() -> dict | None:
    """Import the insurance modules once. None (and `error()`) when unavailable."""
    global _mods, _err
    if _mods is not None or _err is not None:
        return _mods
    if not (SRC / "insurance").is_dir():
        _err = f"insurance code not found at {SRC} (run: python -m fleet.insurance_link)"
        return None
    if str(SRC) not in sys.path:
        sys.path.append(str(SRC))   # appended: our own sim/ and montecarlo/ always win
    try:
        from agents import debate
        from agents import llm
        from finance import recovery, tables
        from insurance import bridge, bundle, counterfactual
        _mods = dict(debate=debate, llm=llm, recovery=recovery, tables=tables, bridge=bridge, bundle=bundle,
                     counterfactual=counterfactual)
    except Exception as e:  # noqa: BLE001 - any import problem = pricing unavailable
        _err = f"insurance code failed to import: {type(e).__name__}: {e}"
    return _mods


def error() -> str | None:
    load()
    return _err


def source_info() -> dict:
    p = SRC / "SOURCE.json"
    return json.loads(p.read_text()) if p.exists() else {"ref": None, "sha": None}


# ----------------------------------------------------------------------------- claim sources
def example_bundles() -> list[dict]:
    d = SRC / "insurance" / "examples"
    return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))] if d.is_dir() else []


def synthetic_bundles(n: int, seed: int = 7) -> list[dict]:
    """The insurance team's synthetic UK portfolio generator (insurance/synth_bundles.py), as dicts."""
    if load() is None:
        return []
    import random

    from insurance.synth_bundles import to_bundle_dict
    from ukcrash.synthetic import generate
    rng = random.Random(f"bundles-{seed}")
    return [to_bundle_dict(sc, rng) for sc in generate(n, seed)]


def claim_value_mid(severity: str | None, paid: float | None) -> float | None:
    """Mid of the finance team's claim value range (for triage ranking only)."""
    if paid:
        return float(paid)
    m = load()
    if m is None or not severity:
        return None
    try:
        r = m["tables"].claim_value_for_severity(severity)
        lo, hi = getattr(r, "low", None), getattr(r, "high", None)
        return None if lo is None or hi is None else (lo + hi) / 2
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------------- pricing + debate
class _Fixed:
    """insurance Estimator protocol returning a result computed by our montecarlo.estimate."""

    def __init__(self, cf):
        self.cf = cf

    def estimate(self, _conflict):
        return self.cf


def quick_price(bundle: dict, sim: dict) -> dict | None:
    """Engine pricing without the debate (for the cheap triage pass). None if unavailable."""
    m = load()
    if m is None:
        return None
    try:
        b = m["bundle"].load_bundle(bundle)
        est = {k: _Fixed(m["counterfactual"].CounterfactualResult(
            p_avoid=d["p_avoid"], avoids_at_p5=None, avoids_at_p50=bool(d["avoids_at_p50"]), avoids_at_p95=None,
            median_impact_speed_mps=float(d["median_impact_speed_mps"]), n_samples=int(d["n_samples"]),
            model=d["model"])) for k, d in sim["drivers"].items()}
        r = m["bridge"].assess_bundle(b, estimators=est, reproduced=False).recovery
    except Exception as e:  # noqa: BLE001
        return {"decision": "error", "expected_recovery_mid": None, "reason": str(e)[:200]}
    if r is None:
        return {"decision": "not_priced", "expected_recovery_mid": None}
    ev = r.expected_recovery
    return {"decision": r.decision, "expected_recovery_mid": None if ev is None else ev.mid,
            "reason": None if ev else "; ".join(r.reasons)[:200]}


def price_and_debate(bundle: dict, sim: dict, reproduced: bool, debate_client=None) -> dict:
    """insurance.bridge.assess_bundle + agents.debate.run_debate on our counterfactual result.

    debate_client=None runs their scripted (offline) adjuster/defence; an Anthropic client runs
    their Claude adjuster, defence counsel and rebuttal. All GBP figures come from finance/.
    """
    m = load()
    if m is None:
        return {"available": False, "reason": f"pricing unavailable: {_err}", "disclaimer": DISCLAIMER}
    bridge, cfm, debate, recovery = m["bridge"], m["counterfactual"], m["debate"], m["recovery"]
    try:
        b = m["bundle"].load_bundle(bundle)
    except Exception as e:  # noqa: BLE001
        return {"available": True, "priced": False, "reason": f"bundle rejected by insurance schema: {e}",
                "disclaimer": DISCLAIMER}
    est = {}
    for name, d in sim["drivers"].items():
        est[name] = _Fixed(cfm.CounterfactualResult(
            p_avoid=d["p_avoid"], avoids_at_p5=d.get("avoids_at_p5"), avoids_at_p50=bool(d["avoids_at_p50"]),
            avoids_at_p95=d.get("avoids_at_p95"), median_impact_speed_mps=float(d["median_impact_speed_mps"]),
            n_samples=int(d["n_samples"]), model=d["model"], notes=list(d.get("notes", []))))
    ba = bridge.assess_bundle(b, estimators=est, reproduced=reproduced)
    v = ba.verdict
    out = {"available": True, "source": source_info(),
           "liability": {"liable": v.liable, "confidence": v.confidence, "summary": v.summary,
                         "evidence_missing": list(v.evidence_missing)},
           "notes": list(ba.notes), "disclaimer": DISCLAIMER}
    if ba.recovery is None:
        return {**out, "priced": False, "reason": ba.notes[0] if ba.notes else "not priced"}
    rec = ba.recovery
    out.update(priced=rec.expected_recovery is not None, original=debate.summary(rec))
    if rec.expected_recovery is None:
        return {**out, "decision": rec.decision, "reason": "; ".join(rec.reasons)}
    # sim CIs are passed as-is (ours are Wilson CI90 on the same n)
    avoidance = [recovery.AvoidanceResult(model=k, p_avoid=d["p_avoid"], ci90=tuple(d["ci90"]))
                 for k, d in sim["drivers"].items()]
    case_file = {"provenance": {"synthetic": bundle.get("synthetic"), "source_label": bundle.get("_fleet_source"),
                                "reproduced_source": "sim reconstructor check (fleet)" if reproduced
                                else "not reproduced by the reconstructor",
                                "driver_models": [d["model"] for d in sim["drivers"].values()]},
                 "liability_verdict": out["liability"],
                 "sim": {"evidence_tier": sim.get("evidence_tier"), "data_sufficiency": sim.get("data_sufficiency"),
                         "top_sensitivity": sim.get("top_sensitivity"), "assumptions": sim.get("assumptions")}}
    claim = debate.Claim(bridge.claim_facts(b, reproduced), avoidance, case_file=case_file)
    try:
        d = debate.run_debate(claim, client=debate_client)
    except Exception as e:  # noqa: BLE001 - LLM debate failure falls back to the scripted one
        if debate_client is None:
            raise
        d = debate.run_debate(claim, client=None)
        out["notes"].append(f"Claude debate failed ({type(e).__name__}); scripted debate used")
    usage = [t["detail"] for t in d.trace if t.get("step") == "usage"]
    out.update(decision=d.final["decision"], final=d.final, adjuster=d.adjuster, challenge=d.challenge,
               challenged=d.challenged, rebuttal=d.rebuttal, contested=d.contested, debate_mode=d.mode,
               debate_trace=[t for t in d.trace if t.get("step") != "usage"],
               debate_usd=round(debate._cost(d), 4) if usage else 0.0)
    return out


def _main() -> None:
    p = vendor()
    print(f"vendored {source_info()} into {p}; import ok: {load() is not None} {error() or ''}")


if __name__ == "__main__":
    _main()
