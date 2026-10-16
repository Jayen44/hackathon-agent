"""Managed Agents plumbing: agent setup (once), the event driver (every run), and the dry-run replay.

Follows the Managed Agents client patterns: agents are version-controlled files created once and
updated in place (IDs stored in ids.json); stream-first ordering; lossless reconnect (history fetch +
dedupe by event id); idle gate on stop_reason (requires_action keeps going, budget_reached stops);
`processed_at` recorded on every trace row; custom tool calls cross-posted from worker threads are
answered on the session stream.
"""
from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from fleet.tools import Desk, ToolInputError, result_text, tool_defs
from fleet.trace import TraceStore, clip, now

AGENTS_DIR = Path(__file__).resolve().parent / "agents"
LEAD = "Recovery portfolio lead"
WORKSPACE = "default"   # Console workspace for trace links; override with FLEET_WORKSPACE


# ----------------------------------------------------------------------------- setup (once)
def agent_configs() -> dict:
    roster = json.loads((AGENTS_DIR / "roster.json").read_text())
    out = {}
    for spec in roster["workers"] + [roster["orchestrator"]]:
        out[spec["key"]] = {"name": spec["name"], "model": spec["model"], "description": spec["description"],
                            "system": (AGENTS_DIR / spec["prompt"]).read_text(), "tools": tool_defs(spec["tools"]),
                            "metadata": {"project": "accel-fleet", "role": spec["key"]}}
    return {"environment": roster["environment"], "agents": out, "worker_keys": [w["key"] for w in roster["workers"]]}


def _hash(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:16]


def setup_agents(client, ids: dict) -> dict:
    """Create the environment and agents once; update in place when a config file changed."""
    cfgs = agent_configs()
    ids = dict(ids or {})
    env = cfgs["environment"]
    if not ids.get("environment_id"):
        found = [e for e in client.beta.environments.list() if getattr(e, "name", None) == env["name"]]
        e = found[0] if found else client.beta.environments.create(name=env["name"], config=env["config"])
        ids["environment_id"] = e.id
    agents = ids.setdefault("agents", {})
    for key in cfgs["worker_keys"] + ["orchestrator"]:
        cfg = dict(cfgs["agents"][key])
        if key == "orchestrator":
            cfg["multiagent"] = {"type": "coordinator",
                                 "agents": [{"type": "agent", "id": agents[k]["id"], "version": agents[k]["version"]}
                                            for k in cfgs["worker_keys"]]}
        h = _hash(cfg)
        cur = agents.get(key)
        if cur and cur.get("hash") == h:
            continue
        a = client.beta.agents.update(cur["id"], **cfg) if cur else client.beta.agents.create(**cfg)
        agents[key] = {"id": a.id, "version": a.version, "name": cfg["name"], "model": cfg["model"], "hash": h}
    ids["updated_at"] = now()
    return ids


# ----------------------------------------------------------------------------- event -> trace
def to_dict(ev) -> dict:
    if isinstance(ev, dict):
        return ev
    for m in ("to_dict", "model_dump"):
        if hasattr(ev, m):
            try:
                return getattr(ev, m)(mode="json") if m == "model_dump" else getattr(ev, m)()
            except TypeError:
                return getattr(ev, m)()
    return dict(vars(ev))


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return " ".join(b.get("text", "") for b in (content or []) if isinstance(b, dict) and b.get("type") == "text")


class Driver:
    """Turns session events into trace rows and answers custom tool calls (in a thread pool)."""

    def __init__(self, store: TraceStore, run_id: str, desk: Desk, send: Callable[[list[dict]], None], *,
                 dry_run: bool = False, workers: int = 6):
        self.store, self.run_id, self.desk, self.send, self.dry = store, run_id, desk, send, dry_run
        self.threads: dict[str, str] = {}
        self.seen: set[str] = set()
        self.answered: set[str] = set()
        self.pool = ThreadPoolExecutor(workers)
        self.inflight = 0
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                      "cache_creation_input_tokens": 0, "model_requests": 0, "list_cost_usd": None,
                      "debate_usd": 0.0, "by_agent": {}}
        self.tool_calls = 0

    def agent_of(self, ev: dict) -> str:
        tid = ev.get("session_thread_id")
        return self.threads.get(tid, LEAD) if tid else LEAD

    def row(self, ev: dict | None, **kw) -> dict:
        r = {"dry_run": self.dry, **kw}
        if ev is not None:
            r.update(event_id=ev.get("id"), processed_at=ev.get("processed_at"),
                     thread_id=ev.get("session_thread_id"))
        return self.store.append(self.run_id, r)

    def handle(self, ev, live: bool = True) -> str | None:
        """Record one event; returns 'idle_end' | 'requires_action' | 'budget' | 'terminated' | 'error' | None."""
        ev = to_dict(ev)
        eid, t = ev.get("id"), ev.get("type", "?")
        if eid and eid in self.seen:
            # a user.message echo arrives twice (queued, then processed): record the processed one too
            if not (t.startswith("user.") and ev.get("processed_at")):
                return None
        if eid:
            self.seen.add(eid)
        agent = self.agent_of(ev)
        if t == "session.thread_created":
            self.threads[ev.get("session_thread_id")] = ev.get("agent_name") or "worker"
            self.row(ev, agent=ev.get("agent_name"), type=t, summary=f"{ev.get('agent_name')} joined the team",
                     parent=LEAD)
        elif t == "agent.thread_message_sent":
            self.row(ev, agent=agent, type=t, to=ev.get("to_agent_name"),
                     summary=f"-> {ev.get('to_agent_name')}: {clip(_text(ev.get('content')), 400)}",
                     output=clip(_text(ev.get("content")), 4000))
        elif t == "agent.thread_message_received":
            self.row(ev, agent=ev.get("from_agent_name"), type=t, to=agent,
                     summary=f"{ev.get('from_agent_name')} reports: {clip(_text(ev.get('content')), 400)}",
                     output=clip(_text(ev.get("content")), 4000))
        elif t == "agent.message":
            txt = _text(ev.get("content"))
            self.row(ev, agent=agent, type=t, summary=clip(txt, 400), output=clip(txt, 4000))
        elif t == "agent.custom_tool_use":
            self.tool_calls += 1
            self.row(ev, agent=agent, type=t, tool=ev.get("name"), input=ev.get("input"),
                     summary=f"{agent} calls {ev.get('name')}({clip(ev.get('input'), 160)})")
            if eid not in self.answered and live:
                self.answered.add(eid)
                self.inflight += 1
                self.pool.submit(self._run_tool, ev, agent)
        elif t == "user.custom_tool_result":
            self.answered.add(ev.get("custom_tool_use_id"))
        elif t == "span.model_request_end":
            u = ev.get("model_usage") or {}
            self.usage["model_requests"] += 1
            for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                self.usage[k] += int(u.get(k) or 0)
            a = self.usage["by_agent"].setdefault(agent, {"input_tokens": 0, "output_tokens": 0, "requests": 0})
            a["input_tokens"] += int(u.get("input_tokens") or 0)
            a["output_tokens"] += int(u.get("output_tokens") or 0)
            a["requests"] += 1
            if self.usage["model_requests"] % 5 == 0:
                self.flush_meta()
        elif t == "session.usage":
            lc = ev.get("list_cost") or (ev.get("usage") or {}).get("list_cost") or {}
            if lc.get("amount") is not None:
                self.usage["list_cost_usd"] = int(lc["amount"]) / 100
            self.row(ev, agent="runner", type=t, summary=f"session list cost ${self.usage['list_cost_usd']}")
            self.flush_meta()
        elif t in ("session.status_idle", "session.thread_status_idle"):
            sr = (ev.get("stop_reason") or {}).get("type")
            self.row(ev, agent=agent if t.startswith("session.thread") else LEAD, type=t, stop_reason=sr,
                     summary=f"{ev.get('agent_name') or 'session'} idle ({sr})")
            if t == "session.status_idle":
                return {"requires_action": "requires_action", "budget_reached": "budget",
                        "end_turn": "idle_end"}.get(sr, "idle_end" if sr != "retries_exhausted" else "error")
        elif t == "session.status_terminated":
            self.row(ev, agent=LEAD, type=t, summary="session terminated")
            return "terminated"
        elif t == "session.error":
            self.row(ev, agent="runner", type=t, summary=clip(ev.get("error") or ev, 400))
        elif t in ("session.thread_status_running", "session.thread_status_terminated", "agent.thread_context_compacted",
                   "session.status_running", "session.status_rescheduled", "user.message", "session.updated"):
            self.row(ev, agent=ev.get("agent_name") or agent, type=t,
                     summary=clip(_text(ev.get("content")), 300) if t == "user.message" else t.split(".", 1)[1])
        return None

    def _run_tool(self, ev: dict, agent: str) -> None:
        name, args = ev.get("name"), ev.get("input") or {}
        t0 = time.monotonic()
        try:
            out, err = self.desk.execute(name, args), False
        except ToolInputError as e:
            out, err = {"error": str(e)}, True
        except Exception as e:  # noqa: BLE001 - report to the agent, keep the run alive
            out, err = {"error": f"{type(e).__name__}: {e}"}, True
        if isinstance(out, dict) and out.get("debate_usd"):
            self.usage["debate_usd"] = round(self.usage["debate_usd"] + out["debate_usd"], 4)
        dbt = (self.desk.pricing.get(args.get("claim_id"), {}) or {}).get("debate_trace") if name == "price_and_debate" else None
        for d in dbt or []:
            self.row(None, agent={"adjuster": "Adjuster", "defence_counsel": "Defence counsel",
                                  "adjuster_rebuttal": "Adjuster (rebuttal)", "orchestrator": "Debate referee"}
                     .get(d.get("agent"), d.get("agent")), type="debate." + str(d.get("step")), parent=ev.get("id"),
                     claim_id=d.get("claim_id"), summary=clip(d.get("detail"), 400), output=clip(d.get("detail"), 3000))
        self.row(None, agent=agent, type="tool_result", tool=name, parent=ev.get("id"), is_error=err,
                 claim_id=args.get("claim_id"), duration_s=round(time.monotonic() - t0, 2),
                 summary=f"{name} -> {clip(out, 300)}", output=clip(out, 6000))
        try:
            self.send([{"type": "user.custom_tool_result", "custom_tool_use_id": ev["id"],
                        "content": [{"type": "text", "text": result_text(out)}]}])
        except Exception as e:  # noqa: BLE001
            self.row(None, agent="runner", type="runner.error", summary=f"failed to send tool result: {e}")
        finally:
            self.inflight -= 1
            self.store.write_portfolio(self.run_id, {**self.desk.portfolio(), "findings": list(self.desk.findings.values())})

    def flush_meta(self, **extra) -> None:
        self.store.write_meta(self.run_id, {"usage": self.usage, "tool_calls": self.tool_calls,
                                            "agents": sorted(set(self.threads.values()) | {LEAD}), **extra})

    def wait_tools(self, timeout_s: float = 3600) -> None:
        t0 = time.monotonic()
        while self.inflight > 0 and time.monotonic() - t0 < timeout_s:
            time.sleep(0.2)


# ----------------------------------------------------------------------------- real session
KICKOFF = ("Start the portfolio run. {n} claims are queued (sources: insurance team synthetic bundles and real US "
           "traffic near-misses wrapped as synthetic claims). This run may take up to {k} claims. Work through them "
           "in triage order, delegating to Investigator, Reconstructor and Counterfactual analyst, and keep the "
           "portfolio summary up to date.")
NUDGE = ("Continue the portfolio run: {left} claims left in this run, open claims: {open}. Take the next claim "
         "(finish open ones first). If none are left, call update_portfolio once and stop.")


def run_session(client, store: TraceStore, run_id: str, desk: Desk, ids: dict, *, budget_usd: float,
                max_hours: float = 20.0, max_nudges: int = 400) -> dict:
    lead = ids["agents"]["orchestrator"]
    session = client.beta.sessions.create(
        agent={"type": "agent", "id": lead["id"], "version": lead["version"]},
        environment_id=ids["environment_id"], title=f"accel-fleet {run_id}",
        metadata={"run_id": run_id, "project": "accel-fleet"},
        budget={"type": "limit", "max_list_cost": {"amount": str(int(round(budget_usd * 100))), "currency": "USD"}})
    sid = session.id
    import os
    url = f"https://platform.claude.com/workspaces/{os.environ.get('FLEET_WORKSPACE', WORKSPACE)}/sessions/{sid}"
    store.write_meta(run_id, {"status": "running", "session_id": sid, "console_url": url})
    send = lambda evs: client.beta.sessions.events.send(sid, events=evs)  # noqa: E731
    drv = Driver(store, run_id, desk, send)
    drv.row(None, agent="runner", type="runner.session_created", summary=f"session {sid} created; budget ${budget_usd}",
            output={"console_url": url, "agent_versions": {k: v["version"] for k, v in ids["agents"].items()}})
    deadline = time.monotonic() + max_hours * 3600
    kicked, nudges, final, backoff = False, 0, None, 1.0

    def on_idle_end() -> str | None:
        nonlocal nudges
        drv.wait_tools()
        left, open_ = desk.remaining(), desk.open_claims()
        if (left or open_) and nudges < max_nudges and time.monotonic() < deadline:
            nudges += 1
            send([{"type": "user.message", "content": [{"type": "text", "text": NUDGE.format(left=left, open=open_ or "none")}]}])
            drv.row(None, agent="runner", type="runner.nudge", summary=f"nudge {nudges}: {left} left, open {open_}")
            return None
        return "done"

    while final is None:
        if time.monotonic() > deadline:
            send([{"type": "user.interrupt"}])
            final = "deadline"
            break
        try:
            with client.beta.sessions.events.stream(sid) as stream:      # stream first
                for ev in client.beta.sessions.events.list(sid):         # then history (lossless reconnect)
                    drv.handle(ev, live=True)
                if not kicked:
                    kicked = True
                    send([{"type": "user.message", "content": [{"type": "text", "text": KICKOFF.format(
                        n=len(desk.claims), k=desk.max_claims)}]}])
                else:
                    s = client.beta.sessions.retrieve(sid)
                    if s.status == "terminated":
                        final = "terminated"
                        break
                    sr = getattr(getattr(s, "stop_reason", None), "type", None)
                    if s.status == "idle" and sr not in ("requires_action",) and drv.inflight == 0:
                        if sr == "budget_reached":
                            final = "budget_reached"
                            break
                        final = on_idle_end()
                backoff = 1.0
                for ev in stream:
                    r = drv.handle(ev)
                    if r == "idle_end":
                        final = on_idle_end()
                    elif r in ("budget", "terminated", "error"):
                        final = {"budget": "budget_reached"}.get(r, r)
                    if final:
                        break
                    if time.monotonic() > deadline:
                        break
        except Exception as e:  # noqa: BLE001 - reconnect with consolidation
            drv.row(None, agent="runner", type="runner.reconnect", summary=f"stream dropped ({type(e).__name__}: {clip(str(e), 200)}); reconnecting")
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)
    drv.wait_tools(120)
    try:
        s = client.beta.sessions.retrieve(sid)
        lc = ((to_dict(s).get("usage") or {}).get("list_cost") or {}).get("amount")
        if lc is not None:
            drv.usage["list_cost_usd"] = int(lc) / 100
    except Exception:  # noqa: BLE001
        pass
    drv.row(None, agent="runner", type="runner.finished", summary=f"run finished: {final}; "
            f"{len(desk.findings)} findings; list cost ${drv.usage['list_cost_usd']}")
    drv.flush_meta(status="finished", finish_reason=final, finished_at=now())
    store.write_portfolio(run_id, {**desk.portfolio(), "findings": list(desk.findings.values())})
    store.maybe_commit(force=True)
    return {"session_id": sid, "finish_reason": final, "console_url": url, "usage": drv.usage}
