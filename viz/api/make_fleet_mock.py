"""Mock fixture for the dashboard's Agent run page until the fleet read API (Modal app `accel-fleet`) is live.

    .venv/bin/python viz/api/make_fleet_mock.py [API_BASE]

Every number in the fixture comes from REAL assessments stored by the claims API (our sim + the insurance
engine + Antonio's scripted debate) for the example bundles. Only the TIMING is simulated (events spaced
out so the page can replay them "live"); the fixture says so in `mock_note`. The recoverability map uses the
same rule as finance.recovery.recoverability_map (pursue + pull_logs_first, negative ends clipped at 0).

Writes viz/dashboard/public/mock-fleet/runs.json, runs/mock-run/trace.json, runs/mock-run/portfolio.json.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

API = (sys.argv[1] if len(sys.argv) > 1 else "https://termvato--accel-claims-api-web.us-east.modal.run").rstrip("/")
OUT = Path(__file__).resolve().parent.parent / "dashboard" / "public" / "mock-fleet"
RUN = "mock-run"
STEP_S = 1.5   # simulated spacing between events


def get(path: str):
    with urllib.request.urlopen(API + path, timeout=60) as r:
        return json.loads(r.read())


def pct(x):
    return f"{100 * x:.1f}%" if 0 < x < 0.01 or 0.99 < x < 1 else f"{100 * x:.0f}%"


def gbp(x):
    return ("-" if x < 0 else "") + f"£{abs(x):,.0f}"


def main() -> None:
    rows = [r for r in get("/api/claims") if r.get("decision")]
    claims = []
    for r in rows:
        try:
            claims.append(get(f"/api/claims/{r['claim_id']}"))
        except Exception as e:  # noqa: BLE001
            print("skip", r["claim_id"], e)
    events, t = [], 0.0

    def ev(agent, typ, summary, parent=None, claim=None, tool=None, inp=None, out=None):
        nonlocal t
        t += STEP_S
        e = {"id": len(events) + 1, "t_offset_s": round(t, 1), "agent": agent, "type": typ, "summary": summary,
             "tool": tool, "input_summary": inp, "output_summary": out, "parent": parent, "claim_id": claim}
        events.append(e)
        return e["id"]

    root = ev("portfolio_lead", "plan", f"Loaded {len(claims)} crash bundles; cheap first pass, then deep investigation",
              out=f"{len(claims)} claims queued")
    for c in claims:
        cid, s = c["claim_id"], c.get("sim")
        d = ev("portfolio_lead", "handoff", f"Dispatch {cid} to Investigator", parent=root, claim=cid)
        ds = (c.get("data_sufficiency") or {})
        i = ev("investigator", "scenario", f"{cid}: {c.get('crash_type') or 'no conflict'}, evidence tier {c['evidence_tier']}",
               parent=d, claim=cid, tool="montecarlo.evidence.ranges_from_bundle", inp="crash bundle (untrusted data)",
               out=(f"data sufficiency {ds.get('score')}; priors: {', '.join(ds.get('prior') or []) or 'none'}"
                    if ds else "no reconstructed conflict"))
        if s:
            rep = s.get("reproduction") or {}
            r = ev("reconstructor", "reproduce", f"{cid}: AV replay vs reported outcome", parent=i, claim=cid,
                   tool="montecarlo.counterfactual.reproduce_rate",
                   out=f"{'reproduced' if rep.get('reproduced_flag') else 'not reproduced'} ({pct(rep.get('rate', 0))} of {rep.get('n')} runs)")
            a, b = s["drivers"]["careful_a"], s["drivers"]["careful_b"]
            cf = ev("counterfactual_analyst", "monte_carlo", f"{cid}: careful drivers A and B", parent=r, claim=cid,
                    tool="montecarlo.estimate", inp=f"{a['n_samples']} samples per model",
                    out=f"P(avoid) A {pct(a['p_avoid'])} (CI {pct(a['ci90'][0])}-{pct(a['ci90'][1])}), "
                        f"B {pct(b['p_avoid'])} (CI {pct(b['ci90'][0])}-{pct(b['ci90'][1])})")
        else:
            cf = i
        er = c.get("expected_recovery_gbp")
        adj = ev("adjuster", "price", f"{cid}: {c['decision_label']}", parent=cf, claim=cid,
                 tool="insurance.bridge.assess_bundle",
                 out=(f"expected recovery {gbp(er['low'])} to {gbp(er['high'])}" if er else f"not priced: {c['gbp'].get('reason')}"))
        db = c.get("debate") or {}
        if db.get("available"):
            dc = ev("defence_counsel", "challenge", f"{cid}: attacks {db['challenge']['assumption']}", parent=adj, claim=cid,
                    tool="finance.recovery.weakest_assumption", out=db["challenge"]["argument"])
            ev("adjuster", "rebuttal", f"{cid}: {db['rebuttal']['verdict'].replace('_', ' ')}", parent=dc, claim=cid,
               out=db["rebuttal"]["reasoning"])
    ev("portfolio_lead", "rank", "Ranked claims by expected recovery; recoverability map updated", parent=root)

    by_type: dict[str, list[float]] = {}
    decisions: dict[str, int] = {}
    table = []
    for c in claims:
        decisions[c["decision"]] = decisions.get(c["decision"], 0) + 1
        er = c.get("expected_recovery_gbp")
        table.append({"claim_id": c["claim_id"], "crash_type": c.get("crash_type"), "decision": c["decision"],
                      "decision_label": c["decision_label"], "expected_recovery": er,
                      "counts_toward_map": bool(er) and c["engine_decision"] in ("pursue", "pull_logs_first")})
        if er and c["engine_decision"] in ("pursue", "pull_logs_first"):
            acc = by_type.setdefault(c.get("crash_type") or "other", [0.0, 0.0, 0.0])
            for k, x in enumerate((er["low"], er["mid"], er["high"])):
                acc[k] += max(0.0, x)
    portfolio = {
        "run_id": RUN, "claims_total": len(claims), "claims_processed": len(claims),
        "recoverable_by_crash_type": {k: {"low": v[0], "mid": v[1], "high": v[2]} for k, v in by_type.items()},
        "decisions": decisions, "claims": table,
        "mock_note": "Mock fixture: numbers are real stored assessments of synthetic example claims; timing is simulated.",
    }
    (OUT / "runs" / RUN).mkdir(parents=True, exist_ok=True)
    (OUT / "runs.json").write_text(json.dumps([{"id": RUN, "status": "replay", "claims_total": len(claims),
                                                 "label": "Mock replay of stored example assessments"}], indent=1))
    (OUT / "runs" / RUN / "trace.json").write_text(json.dumps({"events": events}, indent=1))
    (OUT / "runs" / RUN / "portfolio.json").write_text(json.dumps(portfolio, indent=1))
    print(f"wrote {len(events)} events, {len(claims)} claims to {OUT}")


if __name__ == "__main__":
    main()
