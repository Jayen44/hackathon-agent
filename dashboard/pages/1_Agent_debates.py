"""Agent debates: adjuster -> defence counsel -> rebuttal, per claim (owner: Antonio, agents/).

Reads the `debate` and `agent_step` events that `python -m agents.debate --db agent_state.db` writes.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent import store  # noqa: E402
from finance.recovery import fmt_gbp  # noqa: E402

st.title("Agent debates")
st.caption("The system challenges its own results: the adjuster prices each claim, defence counsel argues for the "
           "AV company, the adjuster answers. Every £ figure is recomputed by the finance engine. "
           "Synthetic UK data; triage evidence for a claims handler, not legal advice.")

conn = store.connect()
rows = conn.execute("SELECT tick, kind, payload FROM events WHERE kind IN ('debate', 'agent_step') ORDER BY id").fetchall()
debates = [json.loads(p) for _, k, p in rows if k == "debate"]
steps = [json.loads(p) for _, k, p in rows if k == "agent_step"]

if not debates:
    st.info("No debates yet. Run: python -m agents.debate --n 20 --seed 7 --max-claims 5 --db agent_state.db")
    st.stop()


def mid(x):
    e = x.get("expected_recovery")
    return e["mid"] if e else None


def rng(x):
    e = x.get("expected_recovery")
    return f"{fmt_gbp(e['low'])} to {fmt_gbp(e['high'])}" if e else "n/a"


c1, c2, c3, c4 = st.columns(4)
c1.metric("Claims debated", len(debates))
c2.metric("Decision changed by the challenge", sum(d["final"]["decision"] != d["original"]["decision"] for d in debates))
c3.metric("Contested (human review)", sum(d["contested"] for d in debates))
c4.metric("API cost", f"${sum(d.get('cost_usd', 0) for d in debates):.2f}")

table = pd.DataFrame([{
    "claim": d["claim_id"],
    "mode": d["mode"],
    "adjuster": d["original"]["decision"],
    "central £ (before)": mid(d["original"]),
    "defence attack": d["challenge"]["assumption"],
    "rebuttal": d["rebuttal"]["verdict"],
    "final": d["final"]["decision"],
    "central £ (final)": mid(d["final"]),
    "contested": "yes" if d["contested"] else "",
} for d in debates])
st.dataframe(table, hide_index=True, width="stretch")

st.subheader("Recoverable after challenge, by crash type (central £, claims still worth pursuing or investigating)")
live = [d for d in debates if d["final"]["decision"] in ("pursue", "pull_logs_first") and mid(d["final"]) is not None]
if live:
    by_type = pd.DataFrame([{"crash type": d["final"]["crash_type"], "central £": max(0.0, mid(d["final"]))}
                            for d in live]).groupby("crash type").sum()
    st.bar_chart(by_type)
else:
    st.write("None: every debated claim ended at don't pursue, or was not priced.")

st.subheader("The debates")
for d in debates:
    flag = "  ·  CONTESTED" if d["contested"] else ""
    with st.expander(f"{d['claim_id']}: {d['original']['decision']} → {d['final']['decision']}{flag}"):
        h = d.get("handler_summary") or {}
        if h:
            st.markdown(f"### {h['bottom_line']}")
            (st.warning if d["contested"] else st.success)(h["status"])
            st.markdown(f"**What happened:** {h['what_happened']}")
            if h["why"]:
                st.markdown("**Why:**\n" + "\n".join(f"- {x}" for x in h["why"]))
            st.markdown(f"**What the challenge changed:** {h['what_the_challenge_changed']}")
            st.markdown(f"**Defence counsel got right:** {h['conceded']}  \n**Still stands:** {h['maintained']}")
            if h["checks_for_you"]:
                st.markdown("**Checks for you:**\n" + "\n".join(f"- [ ] {x}" for x in h["checks_for_you"]))
            st.caption(" ".join(h["caveats"]))
            st.divider()
            st.markdown("**The full debate**")
        cf = d.get("case_file", {})
        v = cf.get("liability_verdict", {})
        if v:
            st.markdown(f"**Liability engine:** {v.get('liable')} ({v.get('confidence')}). {v.get('summary', '')}")
            for x in v.get("findings", []):
                st.markdown(f"- {x}")
            if v.get("evidence_missing"):
                st.markdown("Missing evidence: " + ", ".join(v["evidence_missing"]))
        st.markdown(f"**Adjuster** ({rng(d['original'])}): {d['adjuster']['recommendation']}")
        st.markdown(f"**Defence counsel**: *{d['challenge']['assumption']}*. {d['challenge']['argument']}  \n"
                    f"→ re-priced: {d['challenged']['decision']}, {rng(d['challenged'])}")
        st.markdown(f"**Adjuster's rebuttal** ({d['rebuttal']['verdict']}): {d['rebuttal']['reasoning']}")
        st.markdown(f"**Final** ({rng(d['final'])}): {d['final']['decision']}")
        for x in d["final"]["reasons"]:
            st.markdown(f"- {x}")
        trail = [s for s in steps if s["claim_id"] == d["claim_id"] and s["step"] != "usage"]
        if trail:
            st.markdown("**Agent trace**")
            st.dataframe(pd.DataFrame([{"agent": s["agent"], "step": s["step"],
                                        "detail": json.dumps(s["detail"], default=str)[:300]} for s in trail]),
                         hide_index=True, width="stretch")
