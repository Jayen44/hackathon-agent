# CLAUDE.md: driverless-car crash liability and recovery (`insurance` branch)

Given the evidence from a driverless-car crash, decide who pays (human driver vs tech company) and price what the
victim's insurer can recover. Benchmark: would a careful and competent human driver have avoided it?
Decision support only; all demo data is synthetic. Keep this file short: it is loaded every session.

## Map
| Path | Owner | What |
|---|---|---|
| `insurance/` | Jayen | `bundle.py` crash-bundle JSON format, `integrity.py`, `engine.py` (`decide`), `counterfactual.py`, `sim_adapter.py`, `report.py` |
| `insurance/bridge.py` | Jayen + Antonio | the seam: bundle -> `finance.recovery.assess` |
| `finance/` | Antonio | `recovery.py` (GBP + pursue/don't), `tables.py` (sourced claim values); read `finance/CLAUDE.md` |
| `sim/` | Vakhtang | simulator on the `sim` branch (R157 driver models); read `sim/CLAUDE.md` there |
| `coord/PROTOCOL.md` | all | how we split and hand over work (GitHub issues are the inbox) |

## Commands
```
pytest -q                                   # all tests (add -x, or a single file, while iterating)
python -m insurance insurance/examples/01_av_late_detection.json [--price --legal-cost 2000,5000]
python -m insurance.portfolio --n 20 --seed 7   # price 20 synthetic UK crashes, ranked in GBP
python -m insurance.gaps [--mine --json]        # what is still missing (free, deterministic)
python scripts/make_examples.py                 # regenerate insurance/examples (edit the script, not the JSON)
python scripts/sensitivity.py                   # how far human-model assumptions move the verdict
scripts/sync.ps1   (or scripts/sync.sh)         # fetch, rebase, test, list your issues
```
To fill gaps iteratively use the `gap-closer` agent (`.claude/agents/gap-closer.md`): audit, fix the top gap, test, repeat (max 5).

## Read on demand (do NOT preload)
- Crash data checklist, competent-driver test, liability table and decision flow: `docs/liability-spec.md`
- What has been fact-checked and what hasn't: `docs/verification.md`
- Whether the formulae and assumptions hold, and how sensitive verdicts are: `docs/validation.md`
- Finance assumptions and open TODOs: `docs/assumptions.md`

## Rules
- Start of session: run the sync script, read ONLY the open issues labelled `for:<you>`. Each issue lists the files, interface and test command, so work from it instead of exploring the repo.
- Stay on the `insurance` branch (or a short branch off it). Small commits; `git pull --rebase origin insurance` before pushing; `pytest -q` before every push.
- Never edit the other owner's folder; open an issue labelled `for:<them>`. The seam (`bridge.py`, `tests/test_bridge.py`) needs both owners' OK.
- Contract tests in `tests/test_bridge.py` fail if finance and insurance drift. Fix the bridge, don't weaken the test.
- No guessed numbers or legal facts. Unknown = TODO + visible refusal. Every figure needs a source; mark claims Verified / Knowledge / Design.
- Thresholds in `engine.Policy` and the human model in `counterfactual.HumanParams` are illustrative placeholders, not R157.
- Token care: see `coord/PROTOCOL.md` section "Saving tokens".
