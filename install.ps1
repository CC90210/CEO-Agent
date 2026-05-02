# OASIS AI — One-Line Installer (Windows / PowerShell)
# Version: 6.3.0
#
# This is a thin bootstrap. It clones the OASIS wizard, installs deps,
# then HANDS OFF to the real wizard (bravo_cli) which has the full UX:
# big figlet agent picker, identity questions, and per-agent repo cloning.
#
# Usage:
#   irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.ps1 | iex
#
# License: MIT - Copyright (c) 2026 OASIS AI Solutions

param(
    [switch]$Upgrade,
    [switch]$Uninstall,
    [switch]$SkipWizard,
    [switch]$AutoInstall,
    [switch]$NoAutoInstall,
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'
$ScriptVersion = '6.3.0'
$BootstrapRepo = 'https://github.com/CC90210/CEO-Agent.git'
$BootstrapBranch = 'main'

$OasisHome = if ($env:OASIS_HOME) { $env:OASIS_HOME } else { Join-Path $env:USERPROFILE '.oasis' }
$WizardHome = Join-Path $OasisHome 'wizard'
$WizardRepo = Join-Path $WizardHome 'repo'
$WizardVenv = Join-Path $WizardHome 'venv'

$Mode = 'install'
if ($Upgrade)   { $Mode = 'upgrade' }
if ($Uninstall) { $Mode = 'uninstall' }

$AutoInstallMode = 'prompt'
if ($AutoInstall)   { $AutoInstallMode = 'yes' }
if ($NoAutoInstall) { $AutoInstallMode = 'no' }
if ($Yes)           { $AutoInstallMode = 'yes' }
if ($env:OASIS_AUTO_INSTALL    -in @('1','yes','true')) { $AutoInstallMode = 'yes' }
if ($env:OASIS_NO_AUTO_INSTALL -in @('1','yes','true')) { $AutoInstallMode = 'no' }

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Write-Ok   { param($msg) Write-Host "  [+]  $msg" -ForegroundColor Green }
function Write-Fail { param($msg) Write-Host "  [x]  $msg" -ForegroundColor Red }
function Write-Warn { param($msg) Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Write-Info { param($msg) Write-Host "       $msg" -ForegroundColor DarkGray }
function Write-Step { param($msg) Write-Host "`n──  $msg" -ForegroundColor Cyan }

function Confirm-YesNo($question, $defaultYes=$true) {
    if ($AutoInstallMode -eq 'yes') { return $true }
    if ($AutoInstallMode -eq 'no')  { return $false }
    $hint = if ($defaultYes) { '[Y/n]' } else { '[y/N]' }
    try { $reply = Read-Host "$question $hint" } catch { $reply = '' }
    if ([string]::IsNullOrWhiteSpace($reply)) { return $defaultYes }
    return $reply -match '^[Yy]'
}

# ── OASIS banner ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "   ██████╗  █████╗ ███████╗██╗███████╗      █████╗ ██╗" -ForegroundColor Cyan
Write-Host "  ██╔═══██╗██╔══██╗██╔════╝██║██╔════╝     ██╔══██╗██║" -ForegroundColor Cyan
Write-Host "  ██║   ██║███████║███████╗██║███████╗     ███████║██║" -ForegroundColor Cyan
Write-Host "  ██║   ██║██╔══██║╚════██║██║╚════██║     ██╔══██║██║" -ForegroundColor Cyan
Write-Host "  ╚██████╔╝██║  ██║███████║██║███████║     ██║  ██║██║" -ForegroundColor Cyan
Write-Host "   ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝╚══════╝     ╚═╝  ╚═╝╚═╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Autonomous AI C-Suite  ·  oasisai.work" -ForegroundColor White
Write-Host "  bootstrap v$ScriptVersion" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  After dependencies install, the wizard will let you pick:" -ForegroundColor White
Write-Host "    Bravo (CEO)  ·  Atlas (CFO)  ·  Maven (CMO)  ·  Aura  ·  Hermes" -ForegroundColor DarkGray
Write-Host ""

if (-not (Confirm-YesNo "Continue with installation?" $true)) {
    Write-Warn "Aborted."
    exit 0
}

function Test-Tool($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

function Resolve-Python310Plus {
    $candidates = @(
        @{ exe='py';         args=@('-3.13') },
        @{ exe='py';         args=@('-3.12') },
        @{ exe='py';         args=@('-3.11') },
        @{ exe='py';         args=@('-3.10') },
        @{ exe='python3.12'; args=@() },
        @{ exe='python3.11'; args=@() },
        @{ exe='python3.10'; args=@() },
        @{ exe='python3';    args=@() },
        @{ exe='python';     args=@() }
    )
    foreach ($c in $candidates) {
        $cmd = Get-Command $c.exe -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        if ($cmd.Source -and $cmd.Source -match 'WindowsApps\\python.*\.exe$') { continue }
        $pyArgs = @() + $c.args + @('-c', "import sys; print(sys.version_info.major, sys.version_info.minor, sep='.')")
        $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        try {
            $ver = (& $c.exe @pyArgs 2>$null | Out-String).Trim()
            if ($ver -match '^3\.(1[0-9]|[2-9][0-9])$') { return [pscustomobject]@{ Exe=$c.exe; Args=$c.args; Version=$ver } }
        } catch {} finally { $ErrorActionPreference = $prev }
    }
    foreach ($v in @('313','312','311','310')) {
        foreach ($p in @("$env:LOCALAPPDATA\Programs\Python\Python$v\python.exe", "$env:ProgramFiles\Python$v\python.exe")) {
            if (-not (Test-Path $p)) { continue }
            $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
            try {
                $ver = (& $p '-c' "import sys; print(sys.version_info.major, sys.version_info.minor, sep='.')" 2>$null | Out-String).Trim()
                if ($ver -match '^3\.(1[0-9]|[2-9][0-9])$') { return [pscustomobject]@{ Exe=$p; Args=@(); Version=$ver } }
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

# ── Uninstall ─────────────────────────────────────────────────────────────────
if ($Mode -eq 'uninstall') {
    Write-Step "Uninstall OASIS"
    if (-not (Test-Path $OasisHome)) { Write-Warn "Nothing to uninstall at $OasisHome"; exit 0 }
    Write-Host "This will remove $OasisHome (every installed agent)." -ForegroundColor Yellow
    if (-not (Confirm-YesNo "Continue?" $false)) { Write-Host "Aborted."; exit 0 }
    Remove-Item -Recurse -Force $OasisHome -ErrorAction SilentlyContinue
    Write-Ok "Uninstalled. Open a new terminal to finalize."
    exit 0
}

# ── Prerequisites ─────────────────────────────────────────────────────────────
Write-Step "Checking prerequisites"
Sync-PathFromRegistry

$missing = @()
$pythonResolved = Resolve-Python310Plus
if ($pythonResolved) { Write-Ok "python ($($pythonResolved.Version))" }
else { Write-Fail "python (need 3.10+)"; $missing += 'python' }
foreach ($tool in @('node', 'npm', 'git')) {
    if (Test-Tool $tool) { Write-Ok $tool } else { Write-Fail $tool; $missing += $tool }
}

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Warn "Missing: $($missing -join ', ')"
    if (-not (Test-Tool 'winget')) {
        Write-Warn "winget not available. Install manually:"
        Write-Info "  Python: https://python.org/downloads"
        Write-Info "  Node:   https://nodejs.org"
        Write-Info "  Git:    https://git-scm.com"
        exit 2
    }
    $wingetMap = @{ python='Python.Python.3.12'; node='OpenJS.NodeJS.LTS'; npm='OpenJS.NodeJS.LTS'; git='Git.Git' }
    $wingetIds = @($missing | ForEach-Object { $wingetMap[$_] } | Sort-Object -Unique)
    Write-Host "  Will install via winget:" -ForegroundColor Cyan
    foreach ($id in $wingetIds) { Write-Info "  $id" }
    if (-not (Confirm-YesNo "Install missing prerequisites now?" $true)) { Write-Warn "Aborted."; exit 2 }
    foreach ($id in $wingetIds) {
        Write-Step "winget install $id"
        & winget install --id $id --silent --accept-source-agreements --accept-package-agreements --scope user 2>&1 | ForEach-Object { Write-Info $_ }
    }
    Sync-PathFromRegistry
    Write-Step "Re-checking after install"
    $stillMissing = @()
    foreach ($t in $missing) {
        if ($t -eq 'python') {
            $pythonResolved = Resolve-Python310Plus
            if ($pythonResolved) { Write-Ok "python ($($pythonResolved.Version))" } else { Write-Fail "python"; $stillMissing += $t }
        } elseif (Test-Tool $t) { Write-Ok $t } else { Write-Fail $t; $stillMissing += $t }
    }
    if ($stillMissing.Count -gt 0) {
        Write-Warn "PATH didn't refresh in this window. Open a new PowerShell and re-run."
        exit 1
    }
}

# ── Detect existing OASIS clone (skip redundant download) ────────────────────
function Find-ExistingOasisRepo {
    $candidates = @()
    # Already inside an OASIS repo? (script run from a clone)
    $here = Get-Location
    if ((Test-Path (Join-Path $here 'bravo_cli\main.py')) -and (Test-Path (Join-Path $here 'requirements.txt'))) {
        $candidates += $here.Path
    }
    # Common sibling locations
    foreach ($p in @(
        (Join-Path $env:USERPROFILE 'Business-Empire-Agent'),
        (Join-Path $env:USERPROFILE 'CEO-Agent'),
        (Join-Path $env:USERPROFILE 'Documents\Business-Empire-Agent'),
        (Join-Path $env:USERPROFILE 'Documents\CEO-Agent'),
        'C:\Users\User\Business-Empire-Agent'
    )) {
        if ((Test-Path (Join-Path $p 'bravo_cli\main.py')) -and (Test-Path (Join-Path $p 'requirements.txt'))) {
            $candidates += $p
        }
    }
    # Verify it's actually an OASIS-family repo via git remote
    foreach ($c in $candidates) {
        $remote = & git -C $c config --get remote.origin.url 2>$null
        if ($remote -match 'CC90210/(CEO|CFO|CMO)-Agent|Business-Empire-Agent') {
            return $c
        }
    }
    return $null
}

Write-Step "Fetching OASIS wizard"
$ExistingRepo = Find-ExistingOasisRepo
if ($ExistingRepo) {
    Write-Ok "Found existing OASIS clone: $ExistingRepo"
    Write-Info "Will use this instead of cloning a duplicate."
    if (Confirm-YesNo "Use existing clone at $ExistingRepo?" $true) {
        $WizardRepo = $ExistingRepo
        $WizardHome = Split-Path $WizardRepo
        # Place venv adjacent to the existing repo, NOT in ~/.oasis/wizard
        $WizardVenv = Join-Path $WizardHome '.venv'
        if (-not (Test-Path $WizardVenv)) { $WizardVenv = Join-Path $WizardRepo '.venv' }
    } else {
        Write-Info "User declined — falling through to fresh clone path."
        $ExistingRepo = $null
    }
}

if (-not $ExistingRepo) {
    if ((Test-Path (Join-Path $WizardRepo '.git')) -and $Mode -ne 'upgrade') {
        Write-Warn "Wizard already installed at $WizardRepo"
        $reply = ''
        try { $reply = Read-Host "  [u]pgrade  [r]un wizard now  [c]ancel  (default: run)" } catch {}
        switch -Regex ($reply) {
            '^[Uu]' {
                Invoke-GitSilent @('-C', $WizardRepo, 'fetch', '--depth', '50', 'origin', $BootstrapBranch) | Out-Null
                Invoke-GitSilent @('-C', $WizardRepo, 'reset', '--hard', "origin/$BootstrapBranch") | Out-Null
                Write-Ok "Updated"
            }
            '^[Cc]' { Write-Info "Cancelled."; exit 0 }
            default { Write-Info "Skipping clone — using existing wizard." }
        }
    } elseif ($Mode -eq 'upgrade' -and (Test-Path (Join-Path $WizardRepo '.git'))) {
        Invoke-GitSilent @('-C', $WizardRepo, 'fetch', '--depth', '50', 'origin', $BootstrapBranch) | Out-Null
        Invoke-GitSilent @('-C', $WizardRepo, 'reset', '--hard', "origin/$BootstrapBranch") | Out-Null
        Write-Ok "Wizard updated"
    } else {
        if (Test-Path $WizardRepo) { Remove-Item -Recurse -Force $WizardRepo }
        New-Item -ItemType Directory -Force -Path (Split-Path $WizardRepo) | Out-Null
        Write-Info "Cloning $BootstrapRepo -> $WizardRepo (about 5 seconds)"
        if ((Invoke-GitSilent @('clone', '--depth', '10', '--branch', $BootstrapBranch, $BootstrapRepo, $WizardRepo)) -ne 0) { throw "git clone failed" }
        Write-Ok "Cloned"
    }
}

# ── Python venv + deps ────────────────────────────────────────────────────────
$venvPy = Join-Path $WizardVenv 'Scripts\python.exe'
$venvExists = Test-Path $venvPy

if ($venvExists) {
    Write-Step "Python virtualenv (already present, reusing)"
    Write-Ok "venv at $WizardVenv"
} else {
    Write-Step "Python virtualenv"
    Write-Info "Creating virtualenv at $WizardVenv (about 15-30 seconds)..."
    if (-not (Confirm-YesNo "Continue?" $true)) { Write-Warn "Aborted before venv create."; exit 0 }
    Set-Location $WizardRepo
    & $pythonResolved.Exe @($pythonResolved.Args) '-m' 'venv' $WizardVenv
    if (-not (Test-Path $venvPy)) { Write-Fail "venv creation failed"; exit 1 }
    Write-Ok "venv created"
}

$reqFile = Join-Path $WizardRepo 'requirements.txt'
if (Test-Path $reqFile) {
    Write-Step "Python dependencies"
    Write-Info "pip install -r requirements.txt — about 2-4 minutes total."
    Write-Info "Phases: (1) Collecting (~30s) -> (2) Downloading (~1min) -> (3) Installing wheels (~1-2min, SILENT)"
    Write-Warn "When you see 'Installing collected packages: ...' that's phase 3."
    Write-Warn "It produces NO output for 1-2 minutes. DO NOT abort. Wait for the [+] line."
    if (-not (Confirm-YesNo "Continue?" $true)) { Write-Warn "Aborted before pip install."; exit 0 }
    Write-Host ""
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $venvPy '-m' 'pip' 'install' '--upgrade' 'pip' 2>&1 | ForEach-Object { Write-Host "       $_" -ForegroundColor DarkGray }
    & $venvPy '-m' 'pip' 'install' '-r' $reqFile 2>&1 | ForEach-Object { Write-Host "       $_" -ForegroundColor DarkGray }
    $pipExit = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($pipExit -ne 0) { Write-Fail "pip install failed (exit $pipExit)"; exit 1 }
    Write-Ok "Python deps installed"
} else { Write-Warn "requirements.txt not found - skipping" }

# ── Node deps ─────────────────────────────────────────────────────────────────
$pkgJson = Join-Path $WizardRepo 'package.json'
if (Test-Path $pkgJson) {
    Write-Step "Node.js dependencies"
    Write-Info "npm install — this can take 1-3 minutes."
    Write-Info "(npm prints 'deprecated' WARNINGS for old transitive deps. Those are not errors. Ignore them.)"
    if (-not (Confirm-YesNo "Continue?" $true)) { Write-Warn "Skipping npm install."; }
    else {
        Write-Host ""
        # Suppress PowerShell's NativeCommandError-from-stderr behavior — npm
        # uses stderr for ordinary deprecation warnings which are NOT errors.
        $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        & npm install --prefix $WizardRepo --no-fund --no-audit 2>&1 | ForEach-Object { Write-Host "       $_" -ForegroundColor DarkGray }
        $npmExit = $LASTEXITCODE
        $ErrorActionPreference = $prev
        if ($npmExit -eq 0) { Write-Ok "Node deps installed" }
        else { Write-Warn "npm exited $npmExit — usually a deprecation warning, not a real failure. Wizard should still work." }
    }
}

# ── PATH shim ─────────────────────────────────────────────────────────────────
Write-Step "Adding 'oasis' command to PATH"
$binDir = Join-Path $OasisHome 'bin'
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
$wizardEntry = Join-Path $WizardRepo 'bravo_cli\main.py'

$shimCmd = Join-Path $binDir 'oasis.cmd'
@"
@echo off
"$venvPy" "$wizardEntry" %*
"@ | Set-Content -Path $shimCmd -Encoding ASCII

# Backwards-compat: 'bravo' alias
$bravoCmd = Join-Path $binDir 'bravo.cmd'
@"
@echo off
"$venvPy" "$wizardEntry" %*
"@ | Set-Content -Path $bravoCmd -Encoding ASCII

Write-Ok "Wrote $shimCmd (and 'bravo' alias)"

$currentUser = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($currentUser -notlike "*$binDir*") {
    [Environment]::SetEnvironmentVariable('Path', "$currentUser;$binDir", 'User')
    Write-Info "Added $binDir to user PATH (open a new terminal to use 'oasis' globally)"
}

# ── Hand off to the wizard ────────────────────────────────────────────────────
if (-not $SkipWizard) {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  Bootstrap complete. Launching wizard..." -ForegroundColor White
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Set-Location $WizardRepo
    & $venvPy $wizardEntry 'setup'
}
