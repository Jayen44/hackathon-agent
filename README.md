# Hackathon Agent

> One-line pitch: _what the agent does and for whom_ (edit me).
> https://claude.ai/share/569e9601-3ace-4468-8e32-29f57d52d62c
> 
## What it does
- Runs continuously on a tick loop (`agent/loop.py`)
- Keeps state in SQLite (`agent/store.py`) so it survives restarts
- Uses deterministic code for the maths (`agent/model.py`) and an LLM only to explain (`agent/explain.py`)
- Shows results on a dashboard (`dashboard/app.py`)

## Quick start
```bash
git clone https://github.com/Jayen44/hackathon-agent.git
cd hackathon-agent
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
| Jayen | Owner | [@Jayen44](https://github.com/Jayen44) |
| Antonio | Finance | [@antoniohede-ai](https://github.com/antoniohede-ai) |
| Termvato | Robotics | [@termvato](https://github.com/termvato) |

Private repo: access is limited to the three people above.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow.

_Not financial advice. Demo uses synthetic or public data only._
