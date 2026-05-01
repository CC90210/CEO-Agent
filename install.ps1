# Bravo — Autonomous AI Business Agent
# One-command installer for Windows (PowerShell)
# Version: 6.0.0
#
# Usage:
#   irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.ps1 | iex
#
#   # Upgrade existing install:
#   bravo_install_path\install.ps1 -Upgrade
#
#   # Uninstall:
#   bravo_install_path\install.ps1 -Uninstall
#
#   # Skip auto-install of missing prereqs:
#   install.ps1 -NoAutoInstall
#
#   # Non-interactive (CI):
#   $env:OASIS_AUTO_INSTALL='1'; irm ... | iex
#
# License: MIT - Copyright (c) 2026 Conaugh McKenna / OASIS AI Solutions

# Uses only single-line # comments (no <# ... #> blocks) to survive irm|iex
param(
    [switch]$Upgrade,
    [switch]$Uninstall,
    [switch]$SkipWizard,
    [switch]$AutoInstall,
    [switch]$NoAutoInstall
)

$ErrorActionPreference = 'Stop'
$ScriptVersion = '6.0.0'
$RepoUrl = 'https://github.com/CC90210/CEO-Agent.git'
$BravoHome = if ($env:BRAVO_HOME) { $env:BRAVO_HOME } else { Join-Path $env:USERPROFILE '.bravo' }
$BravoRepo = Join-Path $BravoHome 'repo'
$BravoVersion = if ($env:BRAVO_VERSION) { $env:BRAVO_VERSION } else { '' }

$Mode = 'install'
if ($Upgrade)   { $Mode = 'upgrade' }
if ($Uninstall) { $Mode = 'uninstall' }

$AutoInstallMode = 'prompt'
if ($AutoInstall)   { $AutoInstallMode = 'yes' }
if ($NoAutoInstall) { $AutoInstallMode = 'no' }
if ($env:OASIS_AUTO_INSTALL    -in @('1','yes','true')) { $AutoInstallMode = 'yes' }
if ($env:OASIS_NO_AUTO_INSTALL -in @('1','yes','true')) { $AutoInstallMode = 'no' }

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# Banner
Write-Host ""
Write-Host "  ██████╗ ██████╗  █████╗ ██╗   ██╗ ██████╗ " -ForegroundColor Cyan
Write-Host "  ██╔══██╗██╔══██╗██╔══██╗██║   ██║██╔═══██╗" -ForegroundColor Cyan
Write-Host "  ██████╔╝██████╔╝███████║██║   ██║██║   ██║" -ForegroundColor Cyan
Write-Host "  ██╔══██╗██╔══██╗██╔══██║╚██╗ ██╔╝██║   ██║" -ForegroundColor Cyan
Write-Host "  ██████╔╝██║  ██║██║  ██║ ╚████╔╝ ╚██████╔╝" -ForegroundColor Cyan
Write-Host "  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝   ╚═════╝ " -ForegroundColor Cyan
Write-Host ""
Write-Host "  Autonomous AI Business Agent  ·  oasisai.work" -ForegroundColor White
Write-Host "  installer v$ScriptVersion" -ForegroundColor DarkGray
Write-Host ""

function Write-Ok   { param($msg) Write-Host "  [+]  $msg" -ForegroundColor Green }
function Write-Fail { param($msg) Write-Host "  [x]  $msg" -ForegroundColor Red }
function Write-Warn { param($msg) Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Write-Info { param($msg) Write-Host "       $msg" -ForegroundColor DarkGray }
function Write-Step { param($msg) Write-Host "`n──  $msg" -ForegroundColor Cyan }

function Test-Tool($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Resolve-Python310Plus {
    # Probe by name, then absolute fallback — handles winget PATH-not-refreshed case
    $candidates = @(
        @{ exe = 'py';         args = @('-3.13') },
        @{ exe = 'py';         args = @('-3.12') },
        @{ exe = 'py';         args = @('-3.11') },
        @{ exe = 'py';         args = @('-3.10') },
        @{ exe = 'python3.12'; args = @() },
        @{ exe = 'python3.11'; args = @() },
        @{ exe = 'python3.10'; args = @() },
        @{ exe = 'python3';    args = @() },
        @{ exe = 'python';     args = @() }
    )
    foreach ($c in $candidates) {
        $cmd = Get-Command $c.exe -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        if ($cmd.Source -and $cmd.Source -match 'WindowsApps\\python.*\.exe$') { continue }
        $pyArgs = @() + $c.args + @('-c', "import sys; print(sys.version_info.major, sys.version_info.minor, sep='.')")
        $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        try {
            $ver = (& $c.exe @pyArgs 2>$null | Out-String).Trim()
            if ($ver -match '^3\.(1[0-9]|[2-9][0-9])$') {
                return [pscustomobject]@{ Exe = $c.exe; Args = $c.args; Version = $ver }
            }
        } catch {} finally { $ErrorActionPreference = $prev }
    }
    # Absolute fallback for winget installs not yet on PATH
    foreach ($v in @('313','312','311','310')) {
        $paths = @(
            "$env:LOCALAPPDATA\Programs\Python\Python$v\python.exe",
            "$env:ProgramFiles\Python$v\python.exe"
        )
        foreach ($p in $paths) {
            if (-not (Test-Path $p)) { continue }
            $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
            try {
                $ver = (& $p '-c' "import sys; print(sys.version_info.major, sys.version_info.minor, sep='.')" 2>$null | Out-String).Trim()
                if ($ver -match '^3\.(1[0-9]|[2-9][0-9])$') {
                    return [pscustomobject]@{ Exe = $p; Args = @(); Version = $ver }
                }
            } catch {} finally { $ErrorActionPreference = $prev }
        }
    }
    return $null
}

function Sync-PathFromRegistry {
    try { $m = [Environment]::GetEnvironmentVariable('Path','Machine') } catch { $m = '' }
    try { $u = [Environment]::GetEnvironmentVariable('Path','User') } catch { $u = '' }
    if ($m -or $u) { $env:PATH = "$m;$u" }
}

function Invoke-GitSilent {
    param([string[]]$GitArgs)
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { & git @GitArgs 2>&1 | Out-Null; return $LASTEXITCODE }
    finally { $ErrorActionPreference = $prev }
}

function Ask-YesNo($question, $defaultYes = $true) {
    if ($AutoInstallMode -eq 'yes') { return $true }
    if ($AutoInstallMode -eq 'no')  { return $false }
    $hint = if ($defaultYes) { '[Y/n]' } else { '[y/N]' }
    try { $reply = Read-Host "$question $hint" } catch { $reply = '' }
    if ([string]::IsNullOrWhiteSpace($reply)) { return $defaultYes }
    return $reply -match '^[Yy]'
}

# ── Uninstall ─────────────────────────────────────────────────────────────────
if ($Mode -eq 'uninstall') {
    Write-Step "Uninstall"
    if (-not (Test-Path $BravoHome)) { Write-Warn "Nothing to uninstall at $BravoHome"; exit 0 }
    Write-Host "This will remove $BravoHome. Your credentials will NOT be deleted." -ForegroundColor Yellow
    if (-not (Ask-YesNo "Continue?" $false)) { Write-Host "Aborted."; exit 0 }
    Remove-Item -Recurse -Force $BravoHome -ErrorAction SilentlyContinue
    # Clean PATH
    $userPath = [Environment]::GetEnvironmentVariable('Path','User') -replace [regex]::Escape((Join-Path $BravoHome 'bin') + ';'), ''
    [Environment]::SetEnvironmentVariable('Path', $userPath, 'User')
    Write-Ok "Uninstalled. Open a new terminal to finalize."
    exit 0
}

# ── Prerequisites ─────────────────────────────────────────────────────────────
Write-Step "Checking prerequisites"
Sync-PathFromRegistry

$missing = @()
$pythonResolved = $null

$pythonResolved = Resolve-Python310Plus
if ($pythonResolved) {
    Write-Ok "python ($($pythonResolved.Version))"
} else {
    Write-Fail "python (need 3.10+)"
    $missing += 'python'
}

foreach ($tool in @('node', 'npm', 'git')) {
    if (Test-Tool $tool) { Write-Ok $tool }
    else { Write-Fail $tool; $missing += $tool }
}

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "Missing: $($missing -join ', ')" -ForegroundColor Yellow
    Write-Host ""

    $hasWinget = Test-Tool 'winget'
    if (-not $hasWinget) {
        Write-Warn "winget not available. Install manually:"
        Write-Host "  Python: https://python.org/downloads" -ForegroundColor DarkGray
        Write-Host "  Node:   https://nodejs.org" -ForegroundColor DarkGray
        Write-Host "  Git:    https://git-scm.com" -ForegroundColor DarkGray
        Write-Host "  Or install 'App Installer' from the Microsoft Store for winget:" -ForegroundColor DarkGray
        Write-Host "  https://apps.microsoft.com/detail/9NBLGGH4NNS1" -ForegroundColor DarkGray
        exit 2
    }

    $wingetMap = @{ python = 'Python.Python.3.12'; node = 'OpenJS.NodeJS.LTS'; npm = 'OpenJS.NodeJS.LTS'; git = 'Git.Git' }
    $wingetIds = @($missing | ForEach-Object { $wingetMap[$_] } | Sort-Object -Unique)

    Write-Host "Ready to install via winget:" -ForegroundColor Cyan
    foreach ($id in $wingetIds) { Write-Info "  $id" }
    Write-Host ""

    if (-not (Ask-YesNo "Continue?" $true)) {
        Write-Warn "Skipped. Install manually and re-run."
        foreach ($id in $wingetIds) {
            Write-Host "  winget install --id $id --silent --accept-source-agreements --accept-package-agreements" -ForegroundColor Yellow
        }
        exit 2
    }

    foreach ($id in $wingetIds) {
        Write-Step "winget install $id"
        $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        & winget install --id $id --silent --accept-source-agreements --accept-package-agreements --scope user 2>&1 |
            ForEach-Object { Write-Info $_ }
        $ErrorActionPreference = $prev
    }

    Sync-PathFromRegistry
    Write-Step "Re-checking after install"
    $stillMissing = @()
    foreach ($t in $missing) {
        if ($t -eq 'python') {
            $pythonResolved = Resolve-Python310Plus
            if ($pythonResolved) { Write-Ok "python ($($pythonResolved.Version))" }
            else { Write-Fail "python"; $stillMissing += $t }
        } elseif (Test-Tool $t) { Write-Ok $t }
        else { Write-Fail $t; $stillMissing += $t }
    }

    if ($stillMissing.Count -gt 0) {
        Write-Warn "PATH didn't refresh in this window. Open a new PowerShell and re-run."
        Write-Host "  Still missing: $($stillMissing -join ', ')" -ForegroundColor DarkGray
        exit 1
    }
}

# ── Clone / upgrade ───────────────────────────────────────────────────────────
Write-Step "$($Mode.Substring(0,1).ToUpper())$($Mode.Substring(1)) Bravo"

if ($Mode -eq 'upgrade' -and (Test-Path (Join-Path $BravoRepo '.git'))) {
    Write-Info "Pulling latest from origin/main..."
    $dirty = (& git -C $BravoRepo status --porcelain 2>$null | Out-String).Trim()
    if ($dirty) {
        Write-Warn "Local changes - stashing"
        Invoke-GitSilent @('-C', $BravoRepo, 'stash', 'push', '-u', '-m', "auto-stash $(Get-Date -UFormat %s)") | Out-Null
    }
    if ((Invoke-GitSilent @('-C', $BravoRepo, 'fetch', '--depth', '50', 'origin', 'main')) -eq 0) {
        Invoke-GitSilent @('-C', $BravoRepo, 'reset', '--hard', 'origin/main') | Out-Null
        Write-Ok "Repo updated"
    } else { Write-Warn "Fetch failed (offline?) - using local commits" }
} elseif (Test-Path (Join-Path $BravoRepo '.git')) {
    Write-Warn "Existing install found at $BravoRepo"
    $reply = ''
    try { $reply = Read-Host "Options: [u]pgrade  [o]verwrite  [c]ancel  (default: cancel)" } catch {}
    switch -Regex ($reply) {
        '^[Uu]' {
            Invoke-GitSilent @('-C', $BravoRepo, 'fetch', '--depth', '50', 'origin', 'main') | Out-Null
            Invoke-GitSilent @('-C', $BravoRepo, 'reset', '--hard', 'origin/main') | Out-Null
            Write-Ok "Upgraded"
        }
        '^[Oo]' {
            Remove-Item -Recurse -Force $BravoRepo -ErrorAction SilentlyContinue
            $gitArgs = @('clone', '--depth', '10', $RepoUrl, $BravoRepo)
            if ($BravoVersion) { $gitArgs = @('clone', '--depth', '10', '--branch', $BravoVersion, $RepoUrl, $BravoRepo) }
            if ((Invoke-GitSilent $gitArgs) -ne 0) { throw "git clone failed" }
            Write-Ok "Cloned fresh"
        }
        default { Write-Info "Cancelled. Re-run with -Upgrade to update in place."; exit 0 }
    }
} elseif (Test-Path $BravoRepo) {
    Write-Warn "$BravoRepo exists but is not a git repo - removing and re-cloning"
    Remove-Item -Recurse -Force $BravoRepo
    $gitArgs = @('clone', '--depth', '10', $RepoUrl, $BravoRepo)
    if ($BravoVersion) { $gitArgs = @('clone', '--depth', '10', '--branch', $BravoVersion, $RepoUrl, $BravoRepo) }
    if ((Invoke-GitSilent $gitArgs) -ne 0) { throw "git clone failed" }
    Write-Ok "Cloned"
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path $BravoRepo) | Out-Null
    Write-Info "Cloning $RepoUrl -> $BravoRepo"
    $gitArgs = @('clone', '--depth', '10', $RepoUrl, $BravoRepo)
    if ($BravoVersion) { $gitArgs = @('clone', '--depth', '10', '--branch', $BravoVersion, $RepoUrl, $BravoRepo) }
    if ((Invoke-GitSilent $gitArgs) -ne 0) { throw "git clone failed" }
    Write-Ok "Cloned"
}

# ── Python venv + deps ────────────────────────────────────────────────────────
Write-Step "Installing Python dependencies"
Set-Location $BravoRepo

$venvDir = Join-Path $BravoHome 'venv'
if (-not (Test-Path (Join-Path $venvDir 'Scripts\python.exe'))) {
    Write-Info "Creating virtualenv at $venvDir"
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $pythonResolved.Exe @($pythonResolved.Args) '-m' 'venv' $venvDir 2>&1 | Out-Null
    $ErrorActionPreference = $prev
}

$venvPy = Join-Path $venvDir 'Scripts\python.exe'
$reqFile = Join-Path $BravoRepo 'requirements.txt'

if (Test-Path $reqFile) {
    Write-Info "pip install -r requirements.txt"
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $venvPy '-m' 'pip' 'install' '--quiet' '--upgrade' 'pip' 2>&1 | Out-Null
    & $venvPy '-m' 'pip' 'install' '--quiet' '-r' $reqFile 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Ok "Python deps installed" }
    else { Write-Fail "pip install failed — check output above"; exit 1 }
    $ErrorActionPreference = $prev
} else { Write-Warn "requirements.txt not found — skipping" }

# ── Node deps ─────────────────────────────────────────────────────────────────
Write-Step "Installing Node.js dependencies"
$pkgJson = Join-Path $BravoRepo 'package.json'
if (Test-Path $pkgJson) {
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & npm install --prefix $BravoRepo --silent 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Ok "Node deps installed" }
    else { Write-Fail "npm install failed"; exit 1 }
    $ErrorActionPreference = $prev
} else { Write-Warn "package.json not found — skipping" }

# ── PATH shim ─────────────────────────────────────────────────────────────────
Write-Step "Adding bravo to PATH"
$binDir = Join-Path $BravoHome 'bin'
New-Item -ItemType Directory -Force -Path $binDir | Out-Null

$shimCmd = Join-Path $binDir 'bravo.cmd'
@"
@echo off
"$venvPy" "$BravoRepo\bravo_cli\main.py" %*
"@ | Set-Content -Path $shimCmd -Encoding ASCII

$shimPs = Join-Path $binDir 'bravo.ps1'
@"
`$venvPy = "$venvPy"
`$cli = "$BravoRepo\bravo_cli\main.py"
& `$venvPy `$cli @args
"@ | Set-Content -Path $shimPs -Encoding UTF8

Write-Ok "Wrote $shimCmd"

$currentUser = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($currentUser -notlike "*$binDir*") {
    [Environment]::SetEnvironmentVariable('Path', "$currentUser;$binDir", 'User')
    Write-Info "Added $binDir to user PATH (takes effect in new terminal)"
} else {
    Write-Info "PATH entry already present"
}

# ── Setup wizard ──────────────────────────────────────────────────────────────
if (-not $SkipWizard) {
    Write-Step "Setup wizard"
    $wizardScript = Join-Path $BravoRepo 'bravo_cli\main.py'
    if (Test-Path $wizardScript) {
        $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        & $venvPy $wizardScript 'setup'
        $ErrorActionPreference = $prev
    } else { Write-Warn "Wizard not found — run manually: bravo setup" }
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Bravo is alive." -ForegroundColor White
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "    Open a new PowerShell window (PATH update takes effect)"
Write-Host ""
Write-Host "    bravo doctor" -ForegroundColor Cyan -NoNewline; Write-Host "    -- full health check"
Write-Host "    bravo status" -ForegroundColor Cyan -NoNewline; Write-Host "    -- live operational summary"
Write-Host "    bravo setup"  -ForegroundColor Cyan -NoNewline; Write-Host "     -- re-run credential wizard"
Write-Host ""
Write-Host "  Support: https://oasisai.work" -ForegroundColor DarkGray
Write-Host ""
