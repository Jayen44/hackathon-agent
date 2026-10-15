# Contributing (5-hour hackathon rules)

1. **Never commit to `main` directly.** Branch: `feat/<name>-<thing>`.
2. **Small PRs, merged fast.** Aim for under 30 minutes open. One reviewer, any teammate.
3. **Pull before you push.** `git pull --rebase origin main`.
4. **Secrets stay out of git.** Use `.env` (ignored). Never paste keys in code or chat.
5. **Agree interfaces first.** Change function signatures in `agent/` only after telling the team.
6. **Finance owns `docs/assumptions.md`.** Engineers read it before coding model logic.
7. **Freeze at T-30 min.** After that, only bug fixes and demo prep.

## Commit style
`feat: add break-even calc`, `fix: handle empty ledger`, `docs: add scenario 2`

## Merge conflicts
Ask in chat before resolving someone else's file. Keep `model.py` edits to finance and `loop.py` edits to engineers where possible.
