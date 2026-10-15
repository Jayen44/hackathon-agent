# Handoff: current state (update this, don't re-explain history)

**Branch** `insurance` · tests: `pytest -q` (~207 pass, 1 skipped until `sim/` is merged) · repo is private (Jayen44, antoniohede-ai, termvato).

## What exists
- `insurance/`: crash-bundle JSON (`bundle.py`, incl. optional `legal` block), integrity checks, liability engine (`engine.py`, decision paths have `Step.code`), counterfactual estimators (`counterfactual.py`), AEVA s.3(2)/s.4 rules, `bridge.py` -> `finance.recovery.assess` (UK codes), `legal.py` (regime, recovery route, limitation deadlines, `p_liable_to_victim`), `resolution.py` (every crash -> one of 8 outcomes + next steps, reads `assess().codes` not prose), `synth_bundles.py`, `portfolio.py`, `gaps.py`.
- 22 example bundles in `insurance/examples` (regenerate with `scripts/make_examples.py`; timelines and impact speeds computed by `settle()`; 21 and 22 are clean Pursue demos; legal block is a synthetic post-commencement scenario).
- Verified/validated: `docs/verification.md`, `docs/validation.md`. Pitch dos/don'ts and legal to-do: `docs/legal-basis.md` (summary of Vakhtang's `sim/LEGAL_BASIS.md`).

## Commands
```
pytest -q                                      python -m insurance.gaps [--mine]
python -m insurance <bundle.json> [--price]    python -m insurance.portfolio --n 20 --seed 7   (or --dir insurance/examples)
scripts/sync.ps1 | scripts/sync.sh             python scripts/sensitivity.py
```
`--price` on one bundle uses one estimator and `reproduced=False`, so it stops at `pull_logs_first`; the portfolio run uses two estimators and reaches `pursue`.

## Open work (GitHub issues are the inbox)
| # | Owner | What |
|---|---|---|
| 22 | Jayen | done: seam test OK'd, `LITIGATION_DOWNSIDE` / `MODELS_DISAGREE` mapped in `resolution.py` (a test fails if finance adds a code with no step); close once Antonio confirms |
| 6 / 8 | Antonio / Jayen | seam: two estimators + real `reproduced` flag (needs OK in #6) |
| 17 | Vakhtang | sim is source of truth. After `sim/` merge, Jayen deletes duplicated physics in `sim_adapter.py` |
| 14 | Vakhtang | R157 Annex 3 parameters (said done on `sim`; confirm and close) |
| 24 | Vakhtang | R157 scope tags + typical-driver sensitivity; Jayen reads the tags in the bridge once `estimate()` returns them |
| 23 | Antonio | claim-value scope (AEVA s.2(3), CPA exclusions) |
| 4 / 5 / 15 | Antonio | JCG gaps; `eval/labels.csv` (pursue agreement 11 to 15/20, who_pays 16/20); drop legacy SGO tables |
| 20 / 21 | Jayen | answered (examples fixed, resolution uses codes); close once Vakhtang / Antonio confirm |

## Recent
- Legal regime built (see `docs/legal-basis.md` section 3): `regime` / `recovery_route`, limitation clocks (first resolution step, URGENT under 90 days), `p_liable_to_victim` scaling in the bridge (unset = flagged "not assessed"), updated `engine.DISCLAIMER`, preservation-letter / CPR 31.16 wording.
- Finance (Antonio): input validation, track-limit warning, opt-in `cost_shift_risk`, `RecoveryAssessment.codes` (add a code when you add a gate), central legal cost = band 2 issued-and-settled, pursue now decided on the central case with a stated litigation downside (#22). Bridge returns "unpriced" on bad inputs instead of raising.
- Process: `finance/` is Antonio's. Open a `for:antonio` issue before editing it.
- Antonio's `agents/` debate and dashboard page exist; no insurer UI beyond that on any branch.

## Known limits
Legal regime: AEVA s.2/s.5 does not cover today's supervised pilots (no listed vehicles); the engine prices the s.5 route as a proxy. `p_liable_to_victim` has no sourced value yet, so avoidance is treated as the whole liability case unless set. Multi-track (> £100k) legal cost is unsourced, so table-priced Serious claims are `cannot_price` unless `paid_claim_gbp` or `legal_cost_gbp` is given. Human-driver model is a placeholder (optimistic reaction times, no swerving); friction values are unsourced physics; all crashes synthetic; example timelines use a simple brake x mu x g model, not the `sim` physics; recovery maths ignores settlement and delay (see `docs/validation.md`).

## Token tips
Start a fresh session per chunk (`/clear`), use this file instead of history, run only the tests you need, avoid extended web searches, don't read `docs/*.png` or `insurance/examples/*.json`.
