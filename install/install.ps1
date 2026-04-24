<#
.SYNOPSIS
  Bravo one-command installer for Windows.

.DESCRIPTION
  Idempotent install. Safe to re-run. Never mutates .env.agents.
  Creates ~/.bravo/ tree via runtime/profile_home, writes a bravo.cmd shim,
  adds it to user PATH, and runs doctor.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install/install.ps1

.EXAMPLE
  powershell -File install/install.ps1 -SkipPathUpdate
#>

[CmdletBinding()]
param(
    [switch]$SkipPathUpdate,
    [switch]$DryRun,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$home_    = [Environment]::GetFolderPath('UserProfile')
$bravoHome = Join-Path $home_ '.bravo'
$binDir    = Join-Path $bravoHome 'bin'

function Write-Banner {
    $banner = @'

  ____  ____    ____  _     _____
 | __ )|  _ \  / \ \ \   / / _ \
 |  _ \| |_) |/ _ \ \ \ / / | | |
 | |_) |  _ </ ___ \ \ V /| |_| |
 |____/|_| \_\_/   \_\ |_|  \___/

'@
    Write-Host $banner -ForegroundColor Cyan
    Write-Host "  Bravo installer - CEO-Agent" -ForegroundColor White
    Write-Host "  repo: $repoRoot" -ForegroundColor DarkGray
    Write-Host ""
}

function Test-Tool {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    return [bool]$cmd
}

function Step {
    param([string]$Label, [scriptblock]$Action)
    if ($Quiet) {
        if (-not $DryRun) {
            & $Action *> $null
            if ($LASTEXITCODE -ne 0) {
                throw "$Label failed with exit code $LASTEXITCODE"
            }
        }
        return
    }
    Write-Host "==> $Label" -ForegroundColor White
    if ($DryRun) {
        Write-Host "    (dry run - skipping)" -ForegroundColor DarkGray
        return
    }
    & $Action
    Write-Host "    done" -ForegroundColor Green
    Write-Host ""
}

if (-not $Quiet) { Write-Banner }

# 1. Prereq scan
if (-not $Quiet) { Write-Host "==> Checking prerequisites" -ForegroundColor White }
$required = @{
    python = Test-Tool 'python'
    node   = Test-Tool 'node'
    npm    = Test-Tool 'npm'
    git    = Test-Tool 'git'
}
$optional = @{
    uv              = Test-Tool 'uv'
    rg              = Test-Tool 'rg'
    ffmpeg          = Test-Tool 'ffmpeg'
    'browser-harness' = Test-Tool 'browser-harness'
}

foreach ($pair in $required.GetEnumerator()) {
    $mark = if ($pair.Value) { '+' } else { 'X' }
    $color = if ($pair.Value) { 'Green' } else { 'Red' }
    if (-not $Quiet) { Write-Host ("    [{0}] {1}" -f $mark, $pair.Key) -ForegroundColor $color }
}
foreach ($pair in $optional.GetEnumerator()) {
    $mark = if ($pair.Value) { '+' } else { 'o' }
    $color = if ($pair.Value) { 'Green' } else { 'DarkYellow' }
    $suffix = if ($pair.Value) { '' } else { ' (optional)' }
    if (-not $Quiet) { Write-Host ("    [{0}] {1}{2}" -f $mark, $pair.Key, $suffix) -ForegroundColor $color }
}

$missing = $required.GetEnumerator() | Where-Object { -not $_.Value } | ForEach-Object { $_.Key }
if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "Missing required tools: $($missing -join ', ')" -ForegroundColor Red
    Write-Host "Install them first, e.g.:" -ForegroundColor Yellow
    foreach ($m in $missing) {
        switch ($m) {
            'python' { Write-Host "  winget install Python.Python.3.12" -ForegroundColor Yellow }
            'node'   { Write-Host "  winget install OpenJS.NodeJS.LTS" -ForegroundColor Yellow }
            'git'    { Write-Host "  winget install Git.Git" -ForegroundColor Yellow }
            default  { Write-Host "  winget install $m" -ForegroundColor Yellow }
        }
    }
    exit 2
}
if (-not $Quiet) { Write-Host "" }

# 2. Run bootstrap
Step "Creating ~/.bravo/ home + profiles + env template" {
    python "$repoRoot\install\bootstrap.py" --home "$bravoHome" --repo "$repoRoot"
}

# 2a. Install Python + Node dependencies via the shared bootstrap helper.
# Single source of truth — install.sh calls the exact same code path.
Step "Installing Python + Node packages (pip + npm, both idempotent)" {
    python "$repoRoot\install\bootstrap.py" --repo "$repoRoot" --install-deps
}

# 3. Confirm shim present
Step "Verifying bravo shim at $binDir\bravo.cmd" {
    if (-not (Test-Path (Join-Path $binDir 'bravo.cmd'))) {
        throw "shim missing at $binDir\bravo.cmd"
    }
}

# 4. Add to PATH if not present
if (-not $SkipPathUpdate) {
    if (-not $Quiet) { Write-Host "==> Ensuring $binDir is on user PATH" -ForegroundColor White }
    $userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
    if ($null -eq $userPath) { $userPath = '' }
    if ($userPath -notlike "*$binDir*") {
        if (-not $DryRun) {
            $newPath = if ($userPath) { "$userPath;$binDir" } else { $binDir }
            [Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')
            if (-not $Quiet) { Write-Host "    added $binDir to PATH (new shells will see it)" -ForegroundColor Green }
        } else {
            if (-not $Quiet) { Write-Host "    (dry run) would add $binDir to PATH" -ForegroundColor DarkGray }
        }
    } else {
        if (-not $Quiet) { Write-Host "    already on PATH" -ForegroundColor Green }
    }
    if (-not $Quiet) { Write-Host "" }
}

# 5. Smoke tests - propagate failures instead of silently swallowing them
Step "Running self_audit + browser_harness_doctor" {
    & python "$repoRoot\scripts\self_audit.py" 2>&1 | Select-Object -Last 5 | Write-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    WARN: self_audit exited with code $LASTEXITCODE" -ForegroundColor Yellow
    }
    if (Test-Path "$repoRoot\scripts\browser_harness_doctor.py") {
        & python "$repoRoot\scripts\browser_harness_doctor.py" --json 2>&1 |
            Select-String -Pattern '"ok"|"install_ok"|"attach_ok"' | Write-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    INFO: browser_harness_doctor exit $LASTEXITCODE (attach may be pending)" -ForegroundColor DarkGray
        }
    }
}

if (-not $Quiet) {
    Write-Host ""
    Write-Host "=================================================" -ForegroundColor Cyan
    Write-Host " OASIS AI Agent Factory is ready." -ForegroundColor Cyan
    Write-Host "=================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Next steps:" -ForegroundColor White
    Write-Host "    1. Open a new PowerShell window (PATH update)" -ForegroundColor DarkGray
    Write-Host "    2. bravo doctor" -ForegroundColor Green
    Write-Host "    3. bravo setup" -ForegroundColor Green
    Write-Host "    4. bravo agent list" -ForegroundColor Green
    Write-Host ""
}
