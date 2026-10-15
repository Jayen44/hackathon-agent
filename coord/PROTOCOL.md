# How the two sessions work together (Jayen's insurance side and Antonio's finance side)

Each of us runs our own Claude Code session. Sessions can't message each other directly, so they talk
through the repo. **GitHub issues are the message bus and the task board.** Git is the source of truth.

## Who owns what
| Area | Owner | Files |
|---|---|---|
| Evidence, liability decision, counterfactual | Jayen | `insurance/` (except `bridge.py`), `tests/test_insurance*.py` |
| Culpability, claim values, recovery GBP | Antonio | `finance/`, `docs/assumptions.md`, `tests/test_finance.py` |
| **The seam** | both | `insurance/bridge.py`, `tests/test_bridge.py` |
| Simulator | Vakhtang | `sim/` (on the `sim` branch) |

Never edit the other owner's files. If you need a change there, open an issue labelled `for:<them>`.
Changes to the seam need the other person's OK in the issue or PR first.

## Labels
`for:antonio` / `for:jayen` (whose turn it is) · `area:insurance` / `area:finance` / `cross` · `blocked` · `chunk`

## Start of every session (human or Claude)
1. Run `scripts/sync.ps1` (Windows) or `scripts/sync.sh`. It fetches, rebases, runs the tests and lists your open issues.
2. Read the open issues labelled `for:<you>`. They are your inbox.
3. Pick ONE `chunk` issue, say so in a comment ("taking this"), and work on it.

## Doing a chunk
- Work on the `insurance` branch (or a short branch off it). Small commits, `git pull --rebase` before every push.
- Run `pytest` before every push. `tests/test_bridge.py` contains **contract tests**: if one fails after you pull,
  the other side changed something the seam depends on. Fix the bridge, don't weaken the test, and tell the other owner.
- When finished: push, comment on the issue with what changed and how to verify, remove your `for:` label, add the
  other person's label if they need to react, and close the issue if nothing is left.

## Handing something over
Comment on the issue with: **what you changed, what you need from them, how to test it (a command)**, then label it `for:<them>`.

## Splitting new work
Ask the `work-splitter` agent (`.claude/agents/work-splitter.md`). It reads both sides' code and CLAUDE.md files and
proposes chunks with an owner, an interface and an acceptance test. Review its proposal before it files issues.

## Rules that keep us in sync
- No guessed numbers. Unknown means TODO and a visible refusal (finance's rule, applies to both sides).
- Real figures need a source in the code comment or table.
- Don't change a shared dataclass field name or a string finance compares against ("Verified Engaged", etc.) without an issue.
- Disagreement goes in the issue thread, not in a silent override.
