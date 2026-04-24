<#
.SYNOPSIS
  OASIS AI Agent Factory quickstart for Windows PowerShell.

.DESCRIPTION
  Usage (from a fresh PowerShell):
    iwr -useb https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install/quickstart.ps1 | iex

  Or:
    irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install/quickstart.ps1 | iex

  What it does:
    1. Checks prereqs (python, node, git) - offers winget commands if missing
    2. Clones CC90210/CEO-Agent into $HOME\bravo-repo (or updates if present)
    3. Runs install\install.ps1 (idempotent)
    4. Launches `bravo setup` (the interactive wizard)

  Never touches existing env files; never asks for admin.
#>

$ErrorActionPreference = 'Stop'

$RepoUrl = 'https://github.com/CC90210/CEO-Agent.git'
$RepoDir = $env:BRAVO_REPO_DIR
if (-not $RepoDir) { $RepoDir = Join-Path $env:USERPROFILE 'bravo-repo' }

# Make sure our output is UTF-8 when the terminal supports it.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# Banner - OASIS AI primary wordmark.
$banner = @'

╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║    ██████╗  █████╗ ███████╗██╗███████╗    █████╗ ██╗               ║
║   ██╔═══██╗██╔══██╗██╔════╝██║██╔════╝   ██╔══██╗██║               ║
║   ██║   ██║███████║███████╗██║███████╗   ███████║██║               ║
║   ██║   ██║██╔══██║╚════██║██║╚════██║   ██╔══██║██║               ║
║   ╚██████╔╝██║  ██║███████║██║███████║   ██║  ██║██║               ║
║    ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝╚══════╝   ╚═╝  ╚═╝╚═╝               ║
║                                                                    ║
║    Agent Factory · Business-in-a-Box                               ║
║    oasisai.work                                                    ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝
'@
Write-Host $banner -ForegroundColor Cyan
Write-Host "  OASIS AI setup - choose your agent, then configure it" -ForegroundColor White
Write-Host "  Repo: $RepoUrl" -ForegroundColor DarkGray
Write-Host "  Dest: $RepoDir" -ForegroundColor DarkGray
Write-Host ""

# Prereqs (kept in sync with install.ps1 + bootstrap.py)
Write-Host "==> Checking prerequisites" -ForegroundColor White
$missing = @()
foreach ($tool in @('python', 'node', 'npm', 'git')) {
    if (Get-Command $tool -ErrorAction SilentlyContinue) {
        Write-Host "    [+] $tool" -ForegroundColor Green
    } else {
        Write-Host "    [X] $tool" -ForegroundColor Red
        $missing += $tool
    }
}

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "Missing: $($missing -join ', ')" -ForegroundColor Red
    Write-Host "Install via winget:" -ForegroundColor Yellow
    foreach ($m in $missing) {
        switch ($m) {
            'python' { Write-Host "  winget install Python.Python.3.12" -ForegroundColor Yellow }
            'node'   { Write-Host "  winget install OpenJS.NodeJS.LTS"  -ForegroundColor Yellow }
            'git'    { Write-Host "  winget install Git.Git"            -ForegroundColor Yellow }
        }
    }
    exit 2
}
Write-Host ""

# Clone or update
if (Test-Path (Join-Path $RepoDir '.git')) {
    Write-Host "==> Updating existing repo at $RepoDir" -ForegroundColor White
    git -C $RepoDir pull --ff-only
} else {
    Write-Host "==> Cloning $RepoUrl into $RepoDir" -ForegroundColor White
    git clone --depth 10 $RepoUrl $RepoDir
}
Write-Host ""

# Install quietly. The user-facing product moment is the OASIS AI picker below,
# not an internal install banner before they choose an agent.
Write-Host "==> Preparing local Agent Factory" -ForegroundColor White
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoDir 'install\install.ps1') -SkipPathUpdate -Quiet
if ($LASTEXITCODE -ne 0) {
    throw "install.ps1 failed with exit code $LASTEXITCODE"
}
Write-Host "    [+] ready" -ForegroundColor Green
Write-Host ""

# Ensure ~/.bravo/bin is on PATH for THIS session before launching wizard
$binDir = Join-Path $env:USERPROFILE '.bravo\bin'
if ($env:PATH -notlike "*$binDir*") {
    $env:PATH = "$env:PATH;$binDir"
}

# Launch wizard
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host " Launching OASIS AI setup..." -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

python (Join-Path $RepoDir 'bravo_cli\main.py') setup
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "[+] Done." -ForegroundColor Green
Write-Host "   Open a new PowerShell window to pick up the PATH change."
Write-Host "   Then try: bravo doctor  |  bravo status" -ForegroundColor Cyan
