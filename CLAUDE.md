# Driverless-car crash liability + recovery (`insurance` branch)
Decide who pays (human vs tech company) and price the insurer's recovery. Synthetic/UK data; decision support only.

**Resume here:** read `coord/HANDOFF.md` (state, open issues, commands). Don't read other docs unless needed.

| Path | Owner |
|---|---|
| `insurance/` (`bridge.py` = shared seam) | Jayen |
| `finance/` (see its CLAUDE.md) | Antonio |
| `sim/` (on `sim` branch) | Vakhtang |

Rules: work from your `for:<you>` GitHub issue; don't edit another owner's folder (open an issue); `pytest -q` before push; `git pull --rebase origin insurance`; no guessed numbers (unknown = TODO); trim command output.
Docs, read only on demand: `docs/liability-spec.md`, `docs/verification.md`, `docs/validation.md`, `coord/PROTOCOL.md`, `docs/legal-basis.md` (pitch dos/don'ts, regime caveat).
