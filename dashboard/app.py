import json

import pandas as pd
import streamlit as st

from agent import store

st.title("Hackathon Agent")
conn = store.connect()

rows = conn.execute("SELECT tick, kind, payload FROM events ORDER BY id").fetchall()
ticks = [(t, json.loads(p)) for t, k, p in rows if k == "tick"]
alerts = [(t, json.loads(p)) for t, k, p in rows if k == "alert"]

if ticks:
    df = pd.DataFrame({"tick": [t for t, _ in ticks], "score": [p["assessment"]["score"] for _, p in ticks]})
    st.line_chart(df.set_index("tick"))
else:
    st.info("No data yet. Run: python -m agent.loop --fast")

st.subheader("Alerts")
for t, p in reversed(alerts[-20:]):
    st.write(f"**Tick {t}**: {p['note']}")
