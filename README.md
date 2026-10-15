# Hackathon Agent

> One-line pitch: _what the agent does and for whom_ (edit me).

## What it does
- Runs continuously on a tick loop (`agent/loop.py`)
- Keeps state in SQLite (`agent/store.py`) so it survives restarts
- Uses deterministic code for the maths (`agent/model.py`) and an LLM only to explain (`agent/explain.py`)
- Shows results on a dashboard (`dashboard/app.py`)

## Quick start
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then add your keys
python -m agent.loop --fast # fake-clock replay (demo mode)
streamlit run dashboard/app.py
```

## Layout
| Path | Owner | Purpose |
|---|---|---|
| `agent/model.py` | Finance | Core calculations and rules |
| `agent/data.py` | Eng | Data fetchers / synthetic generators |
| `agent/loop.py` | Eng | Tick loop and fake clock |
| `agent/store.py` | Eng | SQLite persistence |
| `agent/explain.py` | Shared | LLM narration |
| `dashboard/app.py` | Eng | Streamlit UI |
| `docs/` | Finance | Assumptions, scenarios, demo script |
| `tests/` | Everyone | Tests for the model |

## Team
| Name | Role | GitHub |
|---|---|---|
| | | |

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow.

_Not financial advice. Demo uses synthetic or public data only._
