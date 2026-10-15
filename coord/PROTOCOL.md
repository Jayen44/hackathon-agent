# Working together (Jayen = insurance, Antonio = finance). GitHub issues are the inbox; git is the truth.

- **Start:** read `coord/HANDOFF.md`, run `scripts/sync.ps1` (or `.sh`), read only open issues labelled `for:<you>`.
- **Own your folder.** Need a change elsewhere? Open an issue labelled `for:<them>`. The seam (`insurance/bridge.py`, `tests/test_bridge.py`) needs both OKs; its contract tests fail if the sides drift: fix the bridge, don't weaken the test.
- **Finish:** push, comment what changed + the test command, swap the `for:` label, close if done. Update `coord/HANDOFF.md` if the state changed.
- **Labels:** `for:antonio|jayen|vakhtang`, `area:insurance|finance`, `cross`, `chunk`, `blocked`.
- **Rules:** no guessed numbers or legal facts (unknown = TODO + visible refusal); every figure sourced; don't rename shared fields or codes without an issue.
- **Splitting work:** `work-splitter` agent proposes chunks; `gap-closer` agent fixes insurance gaps in a loop (max 5).

## Saving tokens
- `CLAUDE.md` stays tiny; detail lives in `docs/`, read on demand. Start a fresh session per chunk.
- Work from the issue; don't explore the repo. Run only the tests you need.
- Don't re-research: add to `docs/verification.md`. Use standard searches; avoid extended ones.
- No sub-agents for small edits. Put conclusions in comments, not transcripts.
- Don't read `docs/*.png` or `insurance/examples/*.json` (generated).
