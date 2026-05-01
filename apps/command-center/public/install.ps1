# OASIS AI install - stable URL, repo-visibility-proof.
#
#   irm https://agent-dashboard-cc90210.vercel.app/install.ps1 | iex
#   $env:OASIS_PROFILE='hermes'; irm https://agent-dashboard-cc90210.vercel.app/install.ps1 | iex
#
# This URL is the canonical install entry point. The underlying GitHub
# repo (CC90210/CEO-Agent) may flip visibility - this script always fetches
# the latest install/quickstart.ps1, transparently bridging public->gh-auth
# if the public path 404s.

$ErrorActionPreference = 'Stop'
$Repo = 'CC90210/CEO-Agent'
$File = 'install/quickstart.ps1'
$RawUrl = "https://raw.githubusercontent.com/$Repo/main/$File"

Write-Host "==> OASIS AI install" -ForegroundColor Cyan
Write-Host "    repo: https://github.com/$Repo" -ForegroundColor DarkGray
Write-Host ""

# Try the public path first - the simplest and most common case.
try {
    $script = (Invoke-RestMethod -Uri $RawUrl -ErrorAction Stop)
    Invoke-Expression $script
    exit $LASTEXITCODE
} catch {
    Write-Host "Public URL returned an error (repo may be private)." -ForegroundColor Yellow
    Write-Host "Falling back to authenticated GitHub CLI..." -ForegroundColor Yellow
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "GitHub CLI not installed. Install it first:" -ForegroundColor Red
    Write-Host "  winget install GitHub.cli" -ForegroundColor Yellow
    Write-Host "Then re-run: irm https://agent-dashboard-cc90210.vercel.app/install.ps1 | iex" -ForegroundColor Yellow
    exit 1
}

& gh auth status -h github.com *> $null
if ($LASTEXITCODE -ne 0) {
    & gh auth login -h github.com
}

$contentB64 = (& gh api "repos/$Repo/contents/$File" --jq .content) -join ''
$script = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($contentB64))
Invoke-Expression $script
