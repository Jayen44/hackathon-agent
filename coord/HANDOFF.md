# Handoff: current state (update this, don't re-explain history)

**Branch** `insurance` · tests: `pytest -q` (136 pass, 1 skipped until `sim/` is merged) · repo is private (Jayen44, antoniohede-ai, termvato).

## What exists
- `insurance/`: crash-bundle JSON (`bundle.py`), integrity checks, liability engine (`engine.py`, decision paths have `Step.code`), counterfactual estimators (`counterfactual.py`: closed form + numeric for lead-braking/cut-in), AEVA s.3(2)/s.4 rules, `bridge.py` -> `finance.recovery.assess` (sends UK codes), `synth_bundles.py`, `portfolio.py`, `gaps.py`.
- 20 example bundles in `insurance/examples` (regenerate with `scripts/make_examples.py`).
- Verified/validated: `docs/verification.md`, `docs/validation.md`.

## Commands
```
pytest -q                                      python -m insurance.gaps [--mine]
python -m insurance <bundle.json> [--price]    python -m insurance.portfolio --n 20 --seed 7
scripts/sync.ps1 | scripts/sync.sh             python scripts/sensitivity.py
```

## Open work (GitHub issues are the inbox)
| # | Owner | What |
|---|---|---|
| 4 | Antonio | finish claim-value gaps (JCG) |
| 5 | Antonio | `eval/labels.csv`, 20 labelled crashes |
| 6 / 8 | Antonio / Jayen | seam: two estimators + real `reproduced` flag (needs OK in #6) |
| 17 | Vakhtang | sim is source of truth: answer 4 questions (bundle decel/cut-in fields, mu in braking, perception trigger, None p5/p95). After `sim/` merge, Jayen deletes duplicated physics in `sim_adapter.py` |
| 14 | Vakhtang | R157 Annex 3 parameters (blocks real driver models) |
| 15 | Antonio | drop legacy SGO tables now that the bridge sends UK codes |

## Recent
- #11 closed: reaction range stays 0.7/1.0/1.5 s (evidence in `docs/validation.md`). Engine accepts `avoids_at_p5/p95 = None`.
- Antonio added `agents/` (adjuster/defence/rebuttal debate over finance tools; reads the seam). `coord/drafts/labels_synthetic_draft.csv` offered for #5.
- Waiting on Antonio's approve on #6 (nudged twice). No insurer UI exists yet on any branch (Streamlit scaffold on main; Sim Lab on sim).

## Known limits
Human-driver model is a placeholder (optimistic reaction times, no swerving); friction values are unsourced physics; all crashes synthetic; recovery maths ignores cost-shifting and delay (see `docs/validation.md`).

## Token tips
Start a fresh session per chunk (`/clear`), use this file instead of history, run only the tests you need, avoid extended web searches, don't read `docs/*.png` or `insurance/examples/*.json`.
