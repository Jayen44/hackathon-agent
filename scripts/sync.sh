#!/usr/bin/env bash
# Keep this clone in sync with the team: fetch, rebase, test, show your inbox.
# Usage: scripts/sync.sh [branch] [jayen|antonio]
set -u
BRANCH="${1:-insurance}"
ME="${2:-}"
cd "$(dirname "$0")/.."

git fetch origin >/dev/null 2>&1
current="$(git branch --show-current)"
[ "$current" != "$BRANCH" ] && echo "You are on '$current', not '$BRANCH'. Run: git switch $BRANCH"

new="$(git log --format='%h %an: %s' "HEAD..origin/$BRANCH" 2>/dev/null)"
if [ -n "$new" ]; then echo; echo "New on origin/$BRANCH:"; echo "$new"; else echo "Nothing new on origin/$BRANCH."; fi

if [ -n "$(git status --porcelain)" ]; then
  echo "You have uncommitted changes; commit or stash before rebasing."
else
  git pull --rebase origin "$BRANCH" 2>&1 | tail -2
fi

echo; echo "Running tests..."
python -m pytest -q 2>&1 | tail -5
echo "If tests/test_bridge.py fails: the seam drifted. Read coord/PROTOCOL.md and comment on the issue."

if command -v gh >/dev/null 2>&1; then
  if [ -z "$ME" ]; then case "$(git config user.email)" in *antonio*) ME=antonio;; *) ME=jayen;; esac; fi
  echo; echo "Open issues for:$ME"; gh issue list --label "for:$ME" --state open
  echo; echo "Open chunks"; gh issue list --label chunk --state open --limit 10
else
  echo; echo "(gh not installed: check the Issues tab on GitHub instead)"
fi
