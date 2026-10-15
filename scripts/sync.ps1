# Keep this clone in sync with the team: fetch, rebase, test, show your inbox.
# Usage: .\scripts\sync.ps1 [-Branch insurance] [-Me jayen|antonio]
param([string]$Branch = "insurance", [string]$Me = "")

$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)

git fetch origin 2>&1 | Out-Null
$current = git branch --show-current
if ($current -ne $Branch) { Write-Host "You are on '$current', not '$Branch'. Run: git switch $Branch" -ForegroundColor Yellow }

$behind = git log --format="%h %an: %s" "HEAD..origin/$Branch" 2>$null
if ($behind) { Write-Host "`nNew on origin/${Branch}:" -ForegroundColor Cyan; $behind }
else { Write-Host "`nNothing new on origin/$Branch." }

if (git status --porcelain) { Write-Host "`nYou have uncommitted changes; commit or stash before rebasing." -ForegroundColor Yellow }
else {
    git pull --rebase origin $Branch 2>&1 | Select-Object -Last 2
}

Write-Host "`nRunning tests..." -ForegroundColor Cyan
python -m pytest -q 2>&1 | Select-Object -Last 5
Write-Host "If tests/test_bridge.py fails: the seam drifted. Read coord/PROTOCOL.md and comment on the issue." -ForegroundColor DarkGray

if (Get-Command gh -ErrorAction SilentlyContinue) {
    if (-not $Me) { $Me = if ((git config user.email) -match "antonio") { "antonio" } else { "jayen" } }
    Write-Host "`nOpen issues for:$Me" -ForegroundColor Cyan
    gh issue list --label "for:$Me" --state open
    Write-Host "`nOpen unowned chunks" -ForegroundColor Cyan
    gh issue list --label chunk --state open --limit 10
} else { Write-Host "`n(gh not installed: check the Issues tab on GitHub instead)" }
