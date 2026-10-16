"""DRY RUN: a scripted Managed Agents event sequence pushed through the real Driver, tools and trace store.

No Claude calls. Tool calls are executed for real (sim, montecarlo, insurance pricing), so the
numbers in the trace are real; only the agents' words are scripted. Every row is marked dry_run=true.
"""
from __future__ import annotations

import itertools
import threading
import time

from fleet.session import LEAD, Driver
from fleet.tools import Desk
from fleet.trace import TraceStore, now

WORKERS = {"inv": "Investigator", "rec": "Reconstructor", "cf": "Counterfactual analyst"}


class Script:
    def __init__(self, store: TraceStore, run_id: str, desk: Desk, pace_s: float = 0.0):
        self.results: dict[str, dict] = {}
        self.cv = threading.Condition()
        self.drv = Driver(store, run_id, desk, self._sink, dry_run=True)
        self.desk, self.pace = desk, pace_s
        self.ids = itertools.count(1)

    def _sink(self, events: list[dict]) -> None:
        import json
        for e in events:
            if e["type"] == "user.custom_tool_result":
                with self.cv:
                    self.results[e["custom_tool_use_id"]] = json.loads(e["content"][0]["text"])
                    self.cv.notify_all()
            self.emit(dict(e, id=f"dry_{next(self.ids)}"))

    def emit(self, ev: dict) -> None:
        ev.setdefault("id", f"dry_{next(self.ids)}")
        ev.setdefault("processed_at", now())
        self.drv.handle(ev)
        if self.pace:
            time.sleep(self.pace)

    def say(self, text: str, thread: str | None = None) -> None:
        self.emit({"type": "agent.message", "session_thread_id": thread,
                   "content": [{"type": "text", "text": "[DRY RUN] " + text}]})

    def tool(self, name: str, args: dict, thread: str | None = None) -> dict:
        eid = f"dry_{next(self.ids)}"
        self.emit({"id": eid, "type": "agent.custom_tool_use", "name": name, "input": args, "session_thread_id": thread})
        with self.cv:
            self.cv.wait_for(lambda: eid in self.results, timeout=3600)
        return self.results.get(eid, {"error": "timeout"})

    def send_to(self, key: str, text: str) -> None:
        self.emit({"type": "agent.thread_message_sent", "to_session_thread_id": key, "to_agent_name": WORKERS[key],
                   "content": [{"type": "text", "text": "[DRY RUN] " + text}]})

    def report(self, key: str, text: str) -> None:
        self.emit({"type": "agent.thread_message_received", "from_session_thread_id": key,
                   "from_agent_name": WORKERS[key], "content": [{"type": "text", "text": "[DRY RUN] " + text}]})

    # ------------------------------------------------------------------ one claim
    def claim(self, card: dict) -> None:
        cid = card["claim_id"]
        self.send_to("inv", f"Investigate claim {cid}: facts, evidence tier, unknowns, red flags.")
        self.send_to("rec", f"Check the sim reproduces claim {cid}; revise ranges if needed (max 5 attempts).")
        self.emit({"type": "session.thread_status_running", "session_thread_id": "inv", "agent_name": WORKERS["inv"]})
        b = self.tool("get_claim_bundle", {"claim_id": cid}, "inv")
        c = (b.get("untrusted_claim_data") or {}).get("conflict", {})
        o = (b.get("untrusted_claim_data") or {}).get("outcome", {})
        self.report("inv", f"{cid}: {c.get('kind')} at {c.get('ego_speed_mps')} m/s, gap {c.get('gap_m')} m, hazard "
                           f"{c.get('hazard_speed_mps')} m/s; outcome collided={o.get('collided')}, injury "
                           f"{o.get('injury_severity')}. Source: {b.get('source_label')}. Unknowns: exact AV braking onset.")
        self.emit({"type": "session.thread_status_idle", "session_thread_id": "inv", "agent_name": WORKERS["inv"],
                   "stop_reason": {"type": "end_turn"}})
        r = self.tool("check_reproduction", {"claim_id": cid, "range_overrides": None}, "rec")
        if not r.get("reproduced_flag") and c.get("gap_m"):
            g = float(c["gap_m"])
            r = self.tool("check_reproduction", {"claim_id": cid, "range_overrides": [
                {"param": "gap", "lo": round(g * 0.7, 1), "hi": round(g * 1.3, 1),
                 "reason": "report gap is an estimate; +/-30% around the reported value"}]}, "rec")
        if "error" in r:
            r = {"reproduced_flag": False, "attempt": len(self.desk.repro.get(cid, [])), "rate": None, "ci90": None}
        self.report("rec", f"{cid}: reproduced={r.get('reproduced_flag')} (rate {r.get('rate')}, CI90 {r.get('ci90')}) "
                           f"after {r.get('attempt')} attempt(s)."
                    + ("" if r.get("reproduced_flag") else " Low confidence reconstruction."))
        self.send_to("cf", f"Run the counterfactual for {cid} at its evidence tier and one tier up.")
        s = self.tool("estimate_counterfactual", {"claim_id": cid, "tier": None}, "cf")
        tier = s.get("evidence_tier") or 0
        txt = self._cf_text(s)
        if tier < 2:
            s2 = self.tool("estimate_counterfactual", {"claim_id": cid, "tier": tier + 1}, "cf")
            txt += f" | at tier {tier + 1}: " + self._cf_text(s2)
            s = self.tool("estimate_counterfactual", {"claim_id": cid, "tier": None}, "cf")   # price on actual evidence
        self.report("cf", f"{cid} tier {tier}: {txt}")
        p = self.tool("price_and_debate", {"claim_id": cid})
        dec = p.get("decision") or ("not_priced" if p.get("available") else "get_more_evidence")
        if dec not in ("pursue", "dont_pursue", "pull_logs_first", "get_more_evidence", "not_priced"):
            dec = "not_priced"
        ev = (p.get("final") or {}).get("expected_recovery") if isinstance(p.get("final"), dict) else None
        money = f"expected recovery GBP {ev['low']:,.0f} to {ev['high']:,.0f}" if ev else (p.get("reason") or "not priced")
        reqs = [] if dec in ("pursue", "dont_pursue") else [{"item": "full AV logs (decision log + control inputs)",
                                                              "why": "narrows P(avoid) CI and confirms engagement"}]
        self.tool("record_finding", {"claim_id": cid, "decision": dec, "evidence_requests": reqs,
                                     "summary": f"{card.get('crash_type')} claim; {money}."})

    @staticmethod
    def _cf_text(s: dict) -> str:
        d = s.get("careful_drivers", {})
        return "; ".join(f"{k} P(avoid) {v['p_avoid']} CI90 {v['ci90']}" for k, v in d.items()) + \
            f"; A-B spread {s.get('a_b_spread')}"

    def run(self, max_claims: int) -> dict:
        self.emit({"type": "user.message", "content": [{"type": "text", "text": "[DRY RUN] Start the portfolio run."}]})
        self.emit({"type": "session.status_running"})
        for k, name in WORKERS.items():
            self.emit({"type": "session.thread_created", "session_thread_id": k, "agent_name": name})
        done = 0
        self.tool("list_queue", {"limit": 5})
        while True:
            card = self.tool("get_next_claim", {"claim_id": None})
            if card.get("done"):
                break
            self.say(f"Taking {card['claim_id']} ({card.get('source_label')}), triage value GBP "
                     f"{card.get('triage_value_gbp')}.")
            self.claim(card)
            done += 1
            if done % 3 == 0:
                self.tool("update_portfolio", {"note": f"{done} claims done (dry run)."})
            if done >= max_claims:
                break
        self.tool("update_portfolio", {"note": "Dry run complete."})
        self.emit({"type": "session.status_idle", "stop_reason": {"type": "end_turn"}})
        self.drv.wait_tools()
        return {"claims": done}
