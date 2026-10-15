# finance/: owner Antonio (insurance branch)

Read the root CLAUDE.md first (on `sim` until merged). This file adds rules for `finance/` only.

## What is here
- `recovery.py`: culpability and money. `assess(ClaimFacts, [AvoidanceResult]) -> RecoveryAssessment` gives the AV share of fault, expected recovery in GBP (low / central / high) and a decision: `pursue`, `dont_pursue`, `pull_logs_first`, `not_av_recovery`, `cannot_price`. `weakest_assumption()` feeds Defence counsel. `rank()` and `recoverability_map()` feed the orchestrator and UI.
- `tables.py`: claim value by UK injury severity (STATS19: Fatal / Serious / Slight / Damage only; legacy SGO keys kept until the bridge switches), and legal cost from CPR PD 45 fixed recoverable costs (band 2 settled pre-issue to band 4 one-day trial; fast track <= £25k, intermediate <= £100k). Every figure has a source and a status (`statutory` / `secondary` / `TODO`).
- UK foundation lives in `ukcrash/` (STATS19 profile + synthetic demo crashes); see its docstrings.

## The calculation
```
P(avoid)          = bracket over careful_a and careful_b (lowest CI end, mean, highest CI end)
AV share of fault = P(avoid) x (1 - injured party's contrib. negligence)   AV Act 2024; AEVA s.3(1)
                    (applied to table values only: a paid amount is already net of it)
expected recovery = AV share x claim value - legal cost          AEVA 2018 s.2 pays, s.5 recovers
pursue            only if the WORST case clears the threshold and no gate is open
dont_pursue       if even the BEST case does not clear it
pull_logs_first   otherwise: gates (engagement not verified, ODD not inside, not reproduced,
                  one model only, contributory negligence not assessed) or a range that straddles
not_av_recovery   self-driving not engaged, or AEVA s.4 software breach (recover from the insured)
```
No tuned weights: every input is a physical result, a fact from the vehicle data or claim file, or a sourced GBP figure.

## Rules
- Never put a GBP figure in `tables.py` without a source. Unknown means `None` + `TODO`; the engine then returns `cannot_price` rather than guessing.
- An insurer's actual paid amount (`paid_claim_gbp`) always beats the table.
- UK data only. Codes: `ENGAGEMENT`, `ODD`, `SOFTWARE` in `recovery.py`; severity keys in `tables.CLAIM_VALUE_BY_UK_SEVERITY`. US SGO strings are accepted as legacy input only, until `insurance/bridge.py` sends UK codes.
- Every number is an `Interval`. Every assessment carries `DISCLAIMER`.
- Keep it pure: no I/O, no LLM calls. Run `python -m pytest -q` before every commit.

## Open TODOs for the finance owner
1. Check the Serious/Fatal figures against the book (read via law firms). Serious and fatal values are general damages only: the insurer's paid amount is far better when available.
2. Legal cost above £100k (multi-track: no fixed costs, needs a budget estimate).
3. Verify the FCA 2025 average motor claim (GBP 3,858) against the FCA release.
4. `eval/labels.csv`: 20 hand-labelled UK crashes (synthetic, STATS19-based; no public UK AV crash reports exist).

## Finding
With PD 45 costs, a minor-injury claim (about £4-5k) never clears its own trial cost: single small claims land on `pull_logs_first` at best. The recovery money is in serious and fatal claims or in bundling small claims. Say this in the pitch.

## Judged on (see `docs/hackathon-marking-rubric.png`)
| Criterion | Weight | What finance/ contributes |
|---|---|---|
| Real output | 20% | Every claim ends in a GBP range and a decision |
| Business viability | 20% | Recovery value per claim = what the insurer gets back |
| Agent design | 15% | Adjuster uses `assess`, Defence counsel attacks with `weakest_assumption` |
| Demo and pitch | 15% | "Claim X: pursue, £a to £b" plus the defence-counsel flip |
| Demo clarity | 15% | Three numbers per claim: P(avoid), AV share, GBP |
| Responsible design | 15% | Ranges not points, refuses to price unsourced claims, disclaimer, logs gate |

## Cost edge cases (Jayen, Oct 2026)
- `validate_facts` rejects paid amount <= 0/NaN, legal cost override not 0 < low <= high, bad contributory negligence. The bridge turns these into "unpriced" instead of crashing a portfolio run.
- Legal cost is a step function at the £25k/£100k track limits (real CPR behaviour, not a bug). Claims within 10% of a limit get a reason saying the decision may flip.
- Still open: multi-track (> £100k) cost, so every table-priced Serious claim is `cannot_price` unless `paid_claim_gbp` or `legal_cost_gbp` is supplied. Needs a sourced budget estimate.
- Still modelled out: cost-shifting if the insurer loses, delay, settlement discount, cost of pulling logs.
