"""accel-fleet: a long-running Managed Agents team that works a queue of AV crash claims.

Local:
    python -m fleet.runner --dry-run --claims 3                 # scripted events, real tools, local trace
    python -m fleet.runner --claims 3 --budget-usd 3            # real session (needs ANTHROPIC_API_KEY)
    python -m fleet.runner --serve                              # read API on http://127.0.0.1:8090

Modal (app `accel-fleet`, trace on volume `accel-fleet`):
    modal deploy fleet/runner.py                                # read API + functions
    modal run fleet/runner.py::setup                            # create/update agents once (stores IDs)
    modal run fleet/runner.py::dry --claims 5                   # DRY RUN on Modal
    modal run fleet/runner.py::start --claims 40 --budget-usd 30   # the long run (detaches)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import uuid
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
APP = "accel-fleet"
VOL_PATH = "/fleet"
IDS_FILE = "agents/ids.json"

app = modal.App(APP)
vol = modal.Volume.from_name(APP, create_if_missing=True)
data_vol = modal.Volume.from_name("accel-data", create_if_missing=True)
image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install("numpy", "pandas", "requests", "python-dotenv", "anthropic>=1.14", "fastapi[standard]")
         .add_local_python_source("sim", "montecarlo")
         .add_local_dir(HERE, "/root/fleet", ignore=["**/__pycache__/**", ".runs/**", "**/*.pyc"]))


def anthropic_secret() -> modal.Secret:
    return modal.Secret.from_name("anthropic", required_keys=["ANTHROPIC_API_KEY"])


# ----------------------------------------------------------------------------- shared run logic
def new_run_id(dry: bool) -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S") + ("-dry-" if dry else "-") + uuid.uuid4().hex[:4]


def build_desk(cfg: dict, store, run_id: str, map_fn=None, triage_map=None):
    from fleet import claims, insurance_link, sim_ops
    from fleet.tools import Desk
    from fleet.trace import now

    q = claims.load_queue(n_synthetic=cfg["n_synthetic"], n_tgsim=cfg["n_tgsim"])
    store.append(run_id, {"agent": "runner", "type": "runner.queue", "dry_run": cfg["dry_run"],
                          "summary": f"{len(q)} claims queued: " + ", ".join(
                              f"{s}={sum(b['_fleet_source'] == s for b in q)}" for s in sorted({b['_fleet_source'] for b in q})),
                          "output": {"insurance_source": insurance_link.source_info(),
                                     "pricing_available": insurance_link.load() is not None,
                                     "pricing_error": insurance_link.error()}})
    # cheap first pass over every claim (small-n Monte Carlo), fanned out on Modal when available
    tri = list(triage_map(q)) if triage_map else [sim_ops.triage_one(b, n=cfg["triage_n"]) for b in q]
    triage = {t["claim_id"]: t for t in tri}
    top = sorted(tri, key=lambda t: -(t.get("value_gbp") or 0))[:5]
    store.append(run_id, {"agent": "Recovery portfolio lead", "type": "runner.triage", "dry_run": cfg["dry_run"], "ts": now(),
                          "summary": f"first pass over {len(tri)} claims (n={cfg['triage_n']} each); top: " + ", ".join(
                              f"{t['claim_id']} GBP {t.get('value_gbp'):,.0f}" for t in top),
                          "output": tri})

    debate_client = None
    if cfg.get("debate") == "claude" and not cfg["dry_run"]:
        debate_client = insurance_link.load() and insurance_link.load()["llm"].make_client()
    spent = {"usd": 0.0}

    def price(bundle, sim, reproduced):
        client = debate_client if spent["usd"] < cfg["debate_budget_usd"] else None
        out = insurance_link.price_and_debate(bundle, sim, reproduced, debate_client=client or None)
        spent["usd"] += out.get("debate_usd", 0.0) or 0.0
        if debate_client and client is None:
            out.setdefault("notes", []).append("debate budget reached: scripted debate used")
        return out

    est = sim_ops.make_estimate(map_fn=map_fn, sensitivity=cfg["sensitivity"])
    return Desk(q, estimate_fn=est, reproduce_fn=sim_ops.reproduce, price_fn=price, max_claims=cfg["claims"],
                n_samples=cfg["n"], triage=triage)


def execute_run(cfg: dict, store, run_id: str, *, ids: dict | None = None, map_fn=None, triage_map=None) -> dict:
    store.create_run(run_id, {"config": cfg, "dry_run": cfg["dry_run"],
                              "label": "DRY RUN (scripted agents, real tools)" if cfg["dry_run"] else "LIVE Managed Agents run",
                              "status": "triage"})
    try:
        desk = build_desk(cfg, store, run_id, map_fn=map_fn, triage_map=triage_map)
        store.write_portfolio(run_id, {**desk.portfolio(), "findings": []})
        if cfg["dry_run"]:
            from fleet.dryrun import Script
            store.write_meta(run_id, {"status": "running"})
            res = Script(store, run_id, desk, pace_s=cfg["pace_s"]).run(cfg["claims"])
            store.write_portfolio(run_id, {**desk.portfolio(), "findings": list(desk.findings.values())})
            store.write_meta(run_id, {"status": "finished", "finish_reason": "dry_run_complete", **res})
        else:
            import anthropic

            from fleet.session import run_session
            client = anthropic.Anthropic(max_retries=5)
            res = run_session(client, store, run_id, desk, ids, budget_usd=cfg["budget_usd"], max_hours=cfg["max_hours"])
        store.maybe_commit(force=True)
        return {"run_id": run_id, **res}
    except Exception as e:
        store.append(run_id, {"agent": "runner", "type": "runner.failed", "summary": f"{type(e).__name__}: {e}"})
        store.write_meta(run_id, {"status": "failed", "error": f"{type(e).__name__}: {e}"})
        store.maybe_commit(force=True)
        raise


def default_cfg(**kw) -> dict:
    cfg = {"claims": 20, "budget_usd": 25.0, "max_hours": 20.0, "n": 1000, "triage_n": 60, "n_synthetic": 30,
           "n_tgsim": 30, "sensitivity": True, "debate": "claude", "debate_budget_usd": 5.0, "dry_run": False,
           "pace_s": 0.0}
    cfg.update({k: v for k, v in kw.items() if v is not None})
    return cfg


def missing_key_message() -> str:
    return ("No Anthropic API key. Ask the human to run (they type the key themselves):\n"
            "    modal secret create anthropic ANTHROPIC_API_KEY=...\n"
            "Local runs read ANTHROPIC_API_KEY from the environment.")


# ----------------------------------------------------------------------------- Modal functions
@app.function(image=image, cpu=1.0, memory=512, timeout=600)
def eval_chunk(ranges, factories, u):
    from montecarlo.counterfactual import evaluate_chunk
    return evaluate_chunk(ranges, factories, u)


def _modal_map(ranges, factories, chunks):
    return list(eval_chunk.starmap([(ranges, factories, c) for c in chunks], order_outputs=True))


@app.function(image=image, cpu=1.0, memory=512, timeout=600)
def triage_remote(bundle: dict, n: int) -> dict:
    from fleet import sim_ops
    return sim_ops.triage_one(bundle, n=n)


def _store():
    from fleet.trace import TraceStore
    return TraceStore(VOL_PATH, commit=vol.commit)


def _ids() -> dict:
    p = Path(VOL_PATH) / IDS_FILE
    return json.loads(p.read_text()) if p.exists() else {}


@app.function(image=image, volumes={VOL_PATH: vol}, secrets=[anthropic_secret()], timeout=600)
def setup_agents_remote() -> dict:
    import anthropic

    from fleet.session import setup_agents
    vol.reload()
    ids = setup_agents(anthropic.Anthropic(), _ids())
    p = Path(VOL_PATH) / IDS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ids, indent=1))
    vol.commit()
    return ids


def _run_on_modal(cfg: dict, run_id: str) -> dict:
    vol.reload()
    tn = cfg["triage_n"]
    return execute_run(cfg, _store(), run_id, ids=_ids(), map_fn=_modal_map,
                       triage_map=lambda q: triage_remote.map(q, kwargs={"n": tn}, order_outputs=True))


@app.function(image=image, volumes={VOL_PATH: vol, "/data": data_vol}, secrets=[anthropic_secret()],
              timeout=24 * 3600, cpu=1.0, memory=2048)
def run_fleet(cfg: dict, run_id: str) -> dict:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(missing_key_message())
    if not _ids().get("agents"):
        raise RuntimeError("agents not set up: run `modal run fleet/runner.py::setup` first")
    return _run_on_modal(cfg, run_id)


@app.function(image=image, volumes={VOL_PATH: vol, "/data": data_vol}, timeout=6 * 3600, cpu=1.0, memory=2048)
def dry_run_fleet(cfg: dict, run_id: str) -> dict:
    return _run_on_modal(cfg, run_id)


@app.function(image=image, volumes={VOL_PATH: vol}, timeout=600, min_containers=0)
@modal.concurrent(max_inputs=32)
@modal.asgi_app()
def web():
    return make_api(_store(), reload=vol.reload)


def make_api(store, reload=None):
    import time

    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware

    api = FastAPI(title="accel-fleet trace API")
    api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
    last = {"t": 0.0}

    def fresh():
        if reload and time.monotonic() - last["t"] > 1.5:
            last["t"] = time.monotonic()
            try:
                reload()
            except Exception:  # noqa: BLE001 - serve slightly stale data rather than fail
                pass

    @api.get("/api/runs")
    def runs():
        fresh()
        return {"runs": store.runs()}

    @api.get("/api/runs/{run_id}")
    def run(run_id: str):
        fresh()
        m = store.meta(run_id)
        if m is None:
            raise HTTPException(404, "unknown run")
        return m

    @api.get("/api/runs/{run_id}/trace")
    def trace(run_id: str, since: int = 0, limit: int = 500):
        fresh()
        if store.meta(run_id) is None:
            raise HTTPException(404, "unknown run")
        ev = store.trace(run_id, since=since, limit=min(limit, 2000))
        return {"run_id": run_id, "since": since, "next": since + len(ev), "events": ev}

    @api.get("/api/runs/{run_id}/portfolio")
    def portfolio(run_id: str):
        fresh()
        p = store.portfolio(run_id)
        if p is None:
            raise HTTPException(404, "no portfolio yet")
        return p

    @api.get("/")
    def root():
        return {"app": APP, "endpoints": ["/api/runs", "/api/runs/{id}", "/api/runs/{id}/trace?since=0",
                                          "/api/runs/{id}/portfolio"]}
    return api


# ----------------------------------------------------------------------------- Modal entrypoints
@app.local_entrypoint()
def setup():
    ids = setup_agents_remote.remote()
    (HERE / "agents" / "ids.json").write_text(json.dumps(ids, indent=1) + "\n")
    print(json.dumps({k: {"id": v["id"], "version": v["version"]} for k, v in ids["agents"].items()}, indent=1))
    print("environment:", ids["environment_id"], "-> saved fleet/agents/ids.json")


@app.local_entrypoint()
def dry(claims: int = 5, pace: float = 0.3, n: int = 400, sensitivity: bool = True):
    cfg = default_cfg(claims=claims, pace_s=pace, n=n, sensitivity=sensitivity, dry_run=True)
    rid = new_run_id(True)
    fc = modal.Function.from_name(APP, "dry_run_fleet").spawn(cfg, rid)
    print(f"DRY RUN {rid} spawned ({fc.object_id})")


@app.local_entrypoint()
def start(claims: int = 20, budget_usd: float = 25.0, max_hours: float = 20.0, n: int = 1000,
          debate: str = "claude", debate_budget_usd: float = 5.0):
    cfg = default_cfg(claims=claims, budget_usd=budget_usd, max_hours=max_hours, n=n, debate=debate,
                      debate_budget_usd=debate_budget_usd)
    rid = new_run_id(False)
    fc = modal.Function.from_name(APP, "run_fleet").spawn(cfg, rid)
    print(f"LIVE run {rid} spawned ({fc.object_id}); budget ${budget_usd}, max {claims} claims")


# ----------------------------------------------------------------------------- local CLI
def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--serve", action="store_true")
    p.add_argument("--setup", action="store_true", help="create/update agents with the local key")
    p.add_argument("--claims", type=int, default=3)
    p.add_argument("--budget-usd", type=float, default=3.0)
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--triage-n", type=int, default=20)
    p.add_argument("--no-sensitivity", action="store_true")
    p.add_argument("--debate", choices=["claude", "offline"], default="offline")
    p.add_argument("--pace", type=float, default=0.0)
    p.add_argument("--store", default=str(HERE / ".runs"))
    p.add_argument("--modal-fanout", action="store_true", help="Monte Carlo chunks on deployed accel-fleet")
    a = p.parse_args(argv)

    from fleet.trace import TraceStore
    store = TraceStore(a.store)
    if a.serve:
        import uvicorn
        uvicorn.run(make_api(store), host="127.0.0.1", port=8090)
        return
    ids_path = HERE / "agents" / "ids.json"
    if a.setup or not a.dry_run:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit(missing_key_message())
    if a.setup:
        import anthropic

        from fleet.session import setup_agents
        ids = setup_agents(anthropic.Anthropic(), json.loads(ids_path.read_text()) if ids_path.exists() else {})
        ids_path.write_text(json.dumps(ids, indent=1) + "\n")
        print(json.dumps(ids, indent=1))
        return
    map_fn = None
    if a.modal_fanout:
        f = modal.Function.from_name(APP, "eval_chunk")
        map_fn = lambda r, fa, chunks: list(f.starmap([(r, fa, c) for c in chunks], order_outputs=True))  # noqa: E731
    cfg = default_cfg(claims=a.claims, budget_usd=a.budget_usd, n=a.n, triage_n=a.triage_n,
                      sensitivity=not a.no_sensitivity, debate=a.debate, dry_run=a.dry_run, pace_s=a.pace)
    ids = json.loads(ids_path.read_text()) if ids_path.exists() else None
    if not a.dry_run and not (ids and ids.get("agents")):
        sys.exit("agents not set up: run `python -m fleet.runner --setup` or `modal run fleet/runner.py::setup`")
    rid = new_run_id(a.dry_run)
    print(f"run {rid} -> {store.run_dir(rid)}")
    res = execute_run(cfg, store, rid, ids=ids, map_fn=map_fn)
    print(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: v for k, v in (store.portfolio(rid) or {}).items() if k != "findings"}, indent=1))


if __name__ == "__main__":
    main()
