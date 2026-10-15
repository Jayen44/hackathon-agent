# finance/: owner Antonio (insurance branch)

Read the root CLAUDE.md first (on `sim` until merged). This file adds rules for `finance/` only.

## What is here
- `recovery.py`: culpability and money. `assess(ClaimFacts, [AvoidanceResult]) -> RecoveryAssessment` gives the AV share of fault, expected recovery in GBP (low / central / high) and a decision: `pursue`, `dont_pursue`, `pull_logs_first`, `not_av_recovery`, `cannot_price`. `weakest_assumption()` feeds Defence counsel. `rank()` and `recoverability_map()` feed the orchestrator and UI.
- `tables.py`: claim value by SGO injury severity, and legal cost from CPR PD 45 fixed recoverable costs (band 2 settled pre-issue to band 4 one-day trial; fast track <= £25k, intermediate <= £100k). Every figure has a source and a status (`statutory` / `secondary` / `TODO`).
- UK foundation lives in `ukcrash/` (STATS19 profile + synthetic demo crashes); see its docstrings.

## The calculation
```
P(avoid)          = bracket over careful_a and careful_b (lowest CI end, mean, highest CI end)
AV share of fault = P(avoid) x (1 - third-party share)          AV Act 2024 standard; 1945 Act
expected recovery = AV share x claim value - legal cost          AEVA 2018 s.2 pays, s.5 recovers
pursue            only if the WORST case clears the threshold and no gate is open
dont_pursue       if even the BEST case does not clear it
pull_logs_first   otherwise: gates (engagement not verified, ODD not "Yes", not reproduced,
                  one model only) or a range that straddles the threshold
```
No tuned weights: every input is a physical result, an SGO fact or a sourced GBP figure.

## Rules
- Never put a GBP figure in `tables.py` without a source. Unknown means `None` + `TODO`; the engine then returns `cannot_price` rather than guessing.
- An insurer's actual paid amount (`paid_claim_gbp`) always beats the table.
- Severity, engagement and ODD strings are the exact SGO drop-down values (NHTSA SGO-2021-01 Data Element Definitions, fields 22, 73, 113).
- Every number is an `Interval`. Every assessment carries `DISCLAIMER`.
- Keep it pure: no I/O, no LLM calls. Run `python -m pytest -q` before every commit.

## Open TODOs for the finance owner
1. Judicial College Guidelines 18th ed. (April 2026) brackets for Moderate / Serious / Fatality.
2. Legal cost above £100k (multi-track: no fixed costs, needs a budget estimate).
3. Verify the FCA 2025 average motor claim (GBP 3,858) against the FCA release.
4. `eval/labels.csv`: 20 hand-labelled SGO crashes (preventable? pursue?).

## Finding
With PD 45 costs, a minor-injury claim (about £4-5k) never clears its own trial cost: single small claims land on `pull_logs_first` at best. The recovery money is in serious and fatal claims (TODO 1) or in bundling small claims. Say this in the pitch.

## Judged on (see `docs/hackathon-marking-rubric.png`)
| Criterion | Weight | What finance/ contributes |
|---|---|---|
| Real output | 20% | Every claim ends in a GBP range and a decision |
| Business viability | 20% | Recovery value per claim = what the insurer gets back |
| Agent design | 15% | Adjuster uses `assess`, Defence counsel attacks with `weakest_assumption` |
| Demo and pitch | 15% | "Claim X: pursue, £a to £b" plus the defence-counsel flip |
| Demo clarity | 15% | Three numbers per claim: P(avoid), AV share, GBP |
| Responsible design | 15% | Ranges not points, refuses to price unsourced claims, disclaimer, logs gate |
