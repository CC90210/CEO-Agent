# OASIS AI — Multi-Agent Installer (Windows / PowerShell)
# Version: 6.2.0
#
# Usage:
#   irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.ps1 | iex
#
#   # Skip the picker:
#   $env:OASIS_PROFILE='atlas'; irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.ps1 | iex
#
# License: MIT - Copyright (c) 2026 OASIS AI Solutions

param(
    [switch]$Upgrade,
    [switch]$Uninstall,
    [switch]$SkipWizard,
    [switch]$AutoInstall,
    [switch]$NoAutoInstall,
    [string]$Profile
)

$ErrorActionPreference = 'Stop'
$ScriptVersion = '6.2.0'

# ── Agent registry ────────────────────────────────────────────────────────────
$Agents = [ordered]@{
    bravo  = @{ name='Bravo';  role='CEO';       repo='https://github.com/CC90210/CEO-Agent.git'; branch='main';   tagline='Autonomous CEO — strategy, clients, revenue, outreach' }
    atlas  = @{ name='Atlas';  role='CFO';       repo='https://github.com/CC90210/CFO-Agent.git'; branch='master'; tagline='Autonomous CFO — tax, treasury, FIRE, trading'         }
    maven  = @{ name='Maven';  role='CMO';       repo='https://github.com/CC90210/CMO-Agent.git'; branch='main';   tagline='Autonomous CMO — content, ads, brand, video pipeline'  }
    aura   = @{ name='Aura';   role='Lifestyle'; repo='https://github.com/CC90210/Aura-Home-Agent.git'; branch='main'; tagline='Lifestyle agent — home, habits, smart-home, voice'  }
    hermes = @{ name='Hermes'; role='Commerce';  repo='https://github.com/CC90210/hermes.git';    branch='main';   tagline='Commerce agent — POS, EDI, chargebacks, fulfillment'   }
}

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Write-Ok   { param($msg) Write-Host "  [+]  $msg" -ForegroundColor Green }
function Write-Fail { param($msg) Write-Host "  [x]  $msg" -ForegroundColor Red }
function Write-Warn { param($msg) Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Write-Info { param($msg) Write-Host "       $msg" -ForegroundColor DarkGray }
function Write-Step { param($msg) Write-Host "`n──  $msg" -ForegroundColor Cyan }

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
Write-Host "  installer v$ScriptVersion" -ForegroundColor DarkGray
Write-Host ""

# ── Agent selection ───────────────────────────────────────────────────────────
$Selected = $null
$envProfile = $env:OASIS_PROFILE
if ($Profile) { $Selected = $Profile.ToLower() }
elseif ($envProfile) { $Selected = $envProfile.ToLower() }

if ($Selected -and -not $Agents.Contains($Selected)) {
    Write-Warn "Unknown profile '$Selected' — choose from picker."
    $Selected = $null
}

if (-not $Selected) {
    Write-Host "  Choose an agent:" -ForegroundColor White
    Write-Host ""
    $idx = 1
    $slugs = @()
    foreach ($k in $Agents.Keys) {
        $a = $Agents[$k]
        Write-Host ("    {0}.  " -f $idx) -NoNewline -ForegroundColor DarkGray
        Write-Host $a.name -NoNewline -ForegroundColor Cyan
        Write-Host ("  ({0})  " -f $a.role) -NoNewline -ForegroundColor White
        Write-Host $a.tagline -ForegroundColor DarkGray
        $slugs += $k
        $idx++
    }
    Write-Host ""
    while (-not $Selected) {
        $reply = Read-Host "  Pick an agent (1-$($slugs.Count))"
        if ($reply -match '^\d+$') {
            $n = [int]$reply
            if ($n -ge 1 -and $n -le $slugs.Count) { $Selected = $slugs[$n - 1] }
        }
        if (-not $Selected) { Write-Host "  Enter a number 1-$($slugs.Count)" -ForegroundColor Red }
    }
}

$Agent = $Agents[$Selected]
$RepoUrl = $Agent.repo
$Branch = $Agent.branch
$AgentName = $Agent.name

Write-Host ""
Write-Host "  Installing: " -NoNewline -ForegroundColor White
Write-Host "$AgentName ($($Agent.role))" -ForegroundColor Cyan

# ── Paths ─────────────────────────────────────────────────────────────────────
$OasisHome = if ($env:OASIS_HOME) { $env:OASIS_HOME } else { Join-Path $env:USERPROFILE '.oasis' }
$AgentHome = Join-Path $OasisHome $Selected
$AgentRepo = Join-Path $AgentHome 'repo'
$AgentVenv = Join-Path $AgentHome 'venv'

$Mode = 'install'
if ($Upgrade)   { $Mode = 'upgrade' }
if ($Uninstall) { $Mode = 'uninstall' }

$AutoInstallMode = 'prompt'
if ($AutoInstall)   { $AutoInstallMode = 'yes' }
if ($NoAutoInstall) { $AutoInstallMode = 'no' }
if ($env:OASIS_AUTO_INSTALL    -in @('1','yes','true')) { $AutoInstallMode = 'yes' }
if ($env:OASIS_NO_AUTO_INSTALL -in @('1','yes','true')) { $AutoInstallMode = 'no' }

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

function Ask-YesNo($question, $defaultYes=$true) {
    if ($AutoInstallMode -eq 'yes') { return $true }
    if ($AutoInstallMode -eq 'no')  { return $false }
    $hint = if ($defaultYes) { '[Y/n]' } else { '[y/N]' }
    try { $reply = Read-Host "$question $hint" } catch { $reply = '' }
    if ([string]::IsNullOrWhiteSpace($reply)) { return $defaultYes }
    return $reply -match '^[Yy]'
}

# ── Uninstall ─────────────────────────────────────────────────────────────────
if ($Mode -eq 'uninstall') {
    Write-Step "Uninstall $AgentName"
    if (-not (Test-Path $AgentHome)) { Write-Warn "Nothing to uninstall at $AgentHome"; exit 0 }
    Write-Host "This will remove $AgentHome. Credentials remain elsewhere." -ForegroundColor Yellow
    if (-not (Ask-YesNo "Continue?" $false)) { Write-Host "Aborted."; exit 0 }
    Remove-Item -Recurse -Force $AgentHome -ErrorAction SilentlyContinue
    $userPath = [Environment]::GetEnvironmentVariable('Path','User') -replace [regex]::Escape((Join-Path $AgentHome 'bin') + ';'), ''
    [Environment]::SetEnvironmentVariable('Path', $userPath, 'User')
    Write-Ok "Uninstalled $AgentName. Open a new terminal to finalize."
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
    Write-Host "Missing: $($missing -join ', ')" -ForegroundColor Yellow
    if (-not (Test-Tool 'winget')) {
        Write-Warn "winget not available. Install manually:"
        Write-Host "  Python: https://python.org/downloads" -ForegroundColor DarkGray
        Write-Host "  Node:   https://nodejs.org" -ForegroundColor DarkGray
        Write-Host "  Git:    https://git-scm.com" -ForegroundColor DarkGray
        exit 2
    }
    $wingetMap = @{ python='Python.Python.3.12'; node='OpenJS.NodeJS.LTS'; npm='OpenJS.NodeJS.LTS'; git='Git.Git' }
    $wingetIds = @($missing | ForEach-Object { $wingetMap[$_] } | Sort-Object -Unique)
    Write-Host "Ready to install via winget:" -ForegroundColor Cyan
    foreach ($id in $wingetIds) { Write-Info "  $id" }
    if (-not (Ask-YesNo "Continue?" $true)) {
        Write-Warn "Skipped. Install manually and re-run."
        exit 2
    }
    foreach ($id in $wingetIds) {
        Write-Step "winget install $id"
        $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        & winget install --id $id --silent --accept-source-agreements --accept-package-agreements --scope user 2>&1 | ForEach-Object { Write-Info $_ }
        $ErrorActionPreference = $prev
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

# ── Clone / upgrade ───────────────────────────────────────────────────────────
Write-Step "$($Mode.Substring(0,1).ToUpper())$($Mode.Substring(1)) $AgentName"

if ($Mode -eq 'upgrade' -and (Test-Path (Join-Path $AgentRepo '.git'))) {
    $dirty = (& git -C $AgentRepo status --porcelain 2>$null | Out-String).Trim()
    if ($dirty) {
        Write-Warn "Local changes - stashing"
        Invoke-GitSilent @('-C', $AgentRepo, 'stash', 'push', '-u', '-m', "auto-stash $(Get-Date -UFormat %s)") | Out-Null
    }
    if ((Invoke-GitSilent @('-C', $AgentRepo, 'fetch', '--depth', '50', 'origin', $Branch)) -eq 0) {
        Invoke-GitSilent @('-C', $AgentRepo, 'reset', '--hard', "origin/$Branch") | Out-Null
        Write-Ok "$AgentName updated"
    } else { Write-Warn "Fetch failed (offline?) - using local commits" }
} elseif (Test-Path (Join-Path $AgentRepo '.git')) {
    Write-Warn "Existing $AgentName install at $AgentRepo"
    $reply = ''
    try { $reply = Read-Host "Options: [u]pgrade  [o]verwrite  [c]ancel  (default: cancel)" } catch {}
    switch -Regex ($reply) {
        '^[Uu]' {
            Invoke-GitSilent @('-C', $AgentRepo, 'fetch', '--depth', '50', 'origin', $Branch) | Out-Null
            Invoke-GitSilent @('-C', $AgentRepo, 'reset', '--hard', "origin/$Branch") | Out-Null
            Write-Ok "Upgraded"
        }
        '^[Oo]' {
            Remove-Item -Recurse -Force $AgentRepo -ErrorAction SilentlyContinue
            if ((Invoke-GitSilent @('clone', '--depth', '10', '--branch', $Branch, $RepoUrl, $AgentRepo)) -ne 0) { throw "git clone failed" }
            Write-Ok "Cloned fresh"
        }
        default { Write-Info "Cancelled. Re-run with -Upgrade to update in place."; exit 0 }
    }
} else {
    if (Test-Path $AgentRepo) { Remove-Item -Recurse -Force $AgentRepo }
    New-Item -ItemType Directory -Force -Path (Split-Path $AgentRepo) | Out-Null
    Write-Info "Cloning $RepoUrl ($Branch) -> $AgentRepo"
    if ((Invoke-GitSilent @('clone', '--depth', '10', '--branch', $Branch, $RepoUrl, $AgentRepo)) -ne 0) { throw "git clone failed" }
    Write-Ok "Cloned"
}

# ── Python venv + deps ────────────────────────────────────────────────────────
Write-Step "Installing Python dependencies"
Set-Location $AgentRepo

if (-not (Test-Path (Join-Path $AgentVenv 'Scripts\python.exe'))) {
    Write-Info "Creating virtualenv at $AgentVenv"
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $pythonResolved.Exe @($pythonResolved.Args) '-m' 'venv' $AgentVenv 2>&1 | Out-Null
    $ErrorActionPreference = $prev
}
$venvPy = Join-Path $AgentVenv 'Scripts\python.exe'
$reqFile = Join-Path $AgentRepo 'requirements.txt'
if (Test-Path $reqFile) {
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $venvPy '-m' 'pip' 'install' '--quiet' '--upgrade' 'pip' 2>&1 | Out-Null
    & $venvPy '-m' 'pip' 'install' '--quiet' '-r' $reqFile 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Ok "Python deps installed" } else { Write-Fail "pip install failed"; exit 1 }
    $ErrorActionPreference = $prev
} else { Write-Warn "requirements.txt not found - skipping" }

# ── Node deps ─────────────────────────────────────────────────────────────────
Write-Step "Installing Node.js dependencies"
if (Test-Path (Join-Path $AgentRepo 'package.json')) {
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & npm install --prefix $AgentRepo --silent 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Ok "Node deps installed" } else { Write-Fail "npm install failed"; exit 1 }
    $ErrorActionPreference = $prev
} else { Write-Warn "package.json not found - skipping" }

# ── PATH shim ─────────────────────────────────────────────────────────────────
Write-Step "Adding $Selected to PATH"
$binDir = Join-Path $AgentHome 'bin'
New-Item -ItemType Directory -Force -Path $binDir | Out-Null

# Each agent's CLI lives at <repo>/<slug>_cli/main.py if that pattern exists,
# otherwise fall back to scripts/setup_wizard.py
$cliCandidates = @(
    (Join-Path $AgentRepo "$($Selected)_cli\main.py"),
    (Join-Path $AgentRepo "bravo_cli\main.py"),
    (Join-Path $AgentRepo "scripts\setup_wizard.py")
)
$cliPath = $null
foreach ($c in $cliCandidates) { if (Test-Path $c) { $cliPath = $c; break } }
if (-not $cliPath) { $cliPath = Join-Path $AgentRepo 'scripts\setup_wizard.py' }

$shimCmd = Join-Path $binDir "$Selected.cmd"
@"
@echo off
"$venvPy" "$cliPath" %*
"@ | Set-Content -Path $shimCmd -Encoding ASCII
Write-Ok "Wrote $shimCmd"

$currentUser = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($currentUser -notlike "*$binDir*") {
    [Environment]::SetEnvironmentVariable('Path', "$currentUser;$binDir", 'User')
    Write-Info "Added $binDir to user PATH (takes effect in new terminal)"
}

# ── Setup wizard ──────────────────────────────────────────────────────────────
if (-not $SkipWizard) {
    Write-Step "$AgentName setup wizard"
    if (Test-Path $cliPath) {
        $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        if ($cliPath -match 'bravo_cli\\main\.py$|.*_cli\\main\.py$') {
            & $venvPy $cliPath 'setup'
        } else {
            & $venvPy $cliPath
        }
        $ErrorActionPreference = $prev
    } else { Write-Warn "Wizard not found - cd $AgentRepo and run python scripts/setup_wizard.py" }
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  $AgentName is alive." -ForegroundColor White
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Open a new PowerShell, then:" -ForegroundColor White
Write-Host "    $Selected doctor" -ForegroundColor Cyan -NoNewline; Write-Host "    -- health check"
Write-Host "    $Selected status" -ForegroundColor Cyan -NoNewline; Write-Host "    -- live summary"
Write-Host "    $Selected setup"  -ForegroundColor Cyan -NoNewline; Write-Host "     -- re-run wizard"
Write-Host ""
Write-Host "  Install another agent:" -ForegroundColor White
Write-Host "    irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.ps1 | iex" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Support: https://oasisai.work" -ForegroundColor DarkGray
Write-Host ""
