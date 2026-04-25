<#
.SYNOPSIS
  OASIS AI Agent Factory quickstart for Windows PowerShell.

.DESCRIPTION
  Usage (from a fresh PowerShell):
    irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install/quickstart.ps1 | iex

  What it does:
    1. Detects missing prereqs (python, node, npm, git).
    2. AUTO-INSTALLS them via winget (after one consent prompt).
       Override with -NoAutoInstall (or $env:OASIS_NO_AUTO_INSTALL='1')
       to keep the old "tell me what's missing" behavior.
       Override with -AutoInstall (or $env:OASIS_AUTO_INSTALL='1') to
       skip the consent prompt entirely (CI / scripted installs).
    3. Clones CC90210/CEO-Agent into $HOME\bravo-repo (or updates it).
    4. Prepares the local Agent Factory launcher (idempotent).
    5. Launches `bravo setup` (the interactive wizard).

  Never touches existing env files. Admin elevation is requested only if
  winget itself requires it; most LTS installs don't.

  When piped through iex (the typical case), positional flags get lost,
  so use the env-var overrides if you need non-interactive behavior:
    $env:OASIS_AUTO_INSTALL='1'; irm <url> | iex
#>

param(
    [switch]$AutoInstall,
    [switch]$NoAutoInstall,
    # Pre-select an agent profile and skip the picker. Used by per-agent
    # quickstart shims (CFO-Agent, CMO-Agent, Aura, Hermes) so users land
    # directly in their wizard. When piped through iex, positional flags
    # are lost, so `$env:OASIS_PROFILE = 'atlas'` is the documented escape
    # hatch — the shim sets it before invoking irm|iex.
    [string]$Profile = ''
)

$ErrorActionPreference = 'Stop'

$RepoUrl = 'https://github.com/CC90210/CEO-Agent.git'
$RepoDir = $env:BRAVO_REPO_DIR
if (-not $RepoDir) { $RepoDir = Join-Path $env:USERPROFILE 'bravo-repo' }

# prompt | yes | no
$AutoInstallMode = 'prompt'
if ($AutoInstall)   { $AutoInstallMode = 'yes' }
if ($NoAutoInstall) { $AutoInstallMode = 'no' }
if ($env:OASIS_AUTO_INSTALL    -in @('1','yes','true')) { $AutoInstallMode = 'yes' }
if ($env:OASIS_NO_AUTO_INSTALL -in @('1','yes','true')) { $AutoInstallMode = 'no'  }
if (-not $Profile -and $env:OASIS_PROFILE) { $Profile = $env:OASIS_PROFILE }

# UTF-8 output where the terminal supports it
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

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

function Test-Tool($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

# Find a real Python 3.10+ interpreter and return its path. Codex P1:
#   - Get-Command python may return the Microsoft Store stub
#     (C:\Users\<u>\AppData\Local\Microsoft\WindowsApps\python.exe) which
#     opens the Store rather than running Python.
#   - The default winget package puts python3.12 on PATH but not always
#     a bare `python`.
# Strategy: probe py -3.12 / py -3.11 / py -3.10 (the launcher), then
# python3.12 / python3.11 / python3.10 / python3, then `python`. For
# each, run --version and accept only 3.10+. Reject the Store stub by
# checking the resolved path.
function Resolve-Python310Plus {
    $candidates = @(
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
        # Reject the Microsoft Store stub explicitly.
        if ($cmd.Source -and $cmd.Source -match 'WindowsApps\\python.*\.exe$') {
            continue
        }
        try {
            $args = $c.args + @('-c', 'import sys; print("%d.%d" % sys.version_info[:2])')
            $ver  = (& $c.exe @args 2>$null).Trim()
            if ($ver -match '^3\.(1[0-9]|[2-9][0-9])$') {
                # Return both the executable and its launcher args so
                # callers can invoke `& $exe @launcherArgs script ...`.
                return [pscustomobject]@{
                    Exe          = $c.exe
                    LauncherArgs = $c.args
                    Source       = $cmd.Source
                    Version      = $ver
                }
            }
        } catch {}
    }
    return $null
}

function Get-WingetId($tool) {
    switch ($tool) {
        'python' { return 'Python.Python.3.12' }
        'node'   { return 'OpenJS.NodeJS.LTS' }
        'npm'    { return 'OpenJS.NodeJS.LTS' }   # ships with node
        'git'    { return 'Git.Git' }
        default  { return $null }
    }
}

function Ask-YesNo($question, $defaultYes = $true) {
    if ($AutoInstallMode -eq 'yes') { return $true }
    if ($AutoInstallMode -eq 'no')  { return $false }
    $hint = if ($defaultYes) { '[Y/n]' } else { '[y/N]' }
    # Prefer a real Read-Host. When the script is run via `irm | iex`,
    # Read-Host still works in an interactive session — it's only broken
    # in fully headless contexts, where the env-var override is the path.
    try {
        $reply = Read-Host "$question $hint"
    } catch {
        $reply = ''
    }
    if ([string]::IsNullOrWhiteSpace($reply)) { return $defaultYes }
    return $reply -match '^[Yy]'
}

# Prereqs
Write-Host "==> Checking prerequisites" -ForegroundColor White
$tools = @('python', 'node', 'npm', 'git')
$missing = @()
$pythonResolved = $null
foreach ($tool in $tools) {
    if ($tool -eq 'python') {
        $pythonResolved = Resolve-Python310Plus
        if ($pythonResolved) {
            Write-Host "    [+] python ($($pythonResolved.Version) via $($pythonResolved.Exe))" -ForegroundColor Green
        } else {
            Write-Host "    [X] python (need 3.10+)" -ForegroundColor Red
            $missing += $tool
        }
        continue
    }
    if (Test-Tool $tool) {
        Write-Host "    [+] $tool" -ForegroundColor Green
    } else {
        Write-Host "    [X] $tool" -ForegroundColor Red
        $missing += $tool
    }
}

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "Missing: $($missing -join ', ')" -ForegroundColor Yellow
    Write-Host ""

    $hasWinget = Test-Tool 'winget'
    if (-not $hasWinget) {
        Write-Host "winget is not installed on this machine." -ForegroundColor Red
        Write-Host "Install 'App Installer' from the Microsoft Store, then re-run." -ForegroundColor Yellow
        Write-Host "  https://apps.microsoft.com/detail/9NBLGGH4NNS1" -ForegroundColor DarkGray
        exit 2
    }

    # Compute distinct winget IDs (npm + node both map to OpenJS.NodeJS.LTS).
    $wingetIds = @()
    foreach ($m in $missing) {
        $id = Get-WingetId $m
        if ($id -and -not ($wingetIds -contains $id)) {
            $wingetIds += $id
        }
    }

    Write-Host "Ready to install via winget:" -ForegroundColor Cyan
    foreach ($id in $wingetIds) { Write-Host "    $id" -ForegroundColor White }
    Write-Host "  (silent install, current-user scope)" -ForegroundColor DarkGray
    Write-Host ""

    if (-not (Ask-YesNo "Continue?" $true)) {
        Write-Host ""
        Write-Host "Skipped auto-install. Run these manually and re-run quickstart:" -ForegroundColor Yellow
        foreach ($id in $wingetIds) {
            Write-Host "  winget install --id $id --silent --accept-source-agreements --accept-package-agreements" -ForegroundColor Yellow
        }
        exit 2
    }

    foreach ($id in $wingetIds) {
        Write-Host "==> winget install $id" -ForegroundColor White
        # --scope user keeps us out of admin elevation when the package supports it.
        & winget install --id $id --silent --accept-source-agreements --accept-package-agreements --scope user 2>&1 |
            ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
        # winget exit codes: 0 OK; 0x8A150011 already installed; sometimes
        # non-zero when --scope user falls back to machine. We re-check the
        # actual binary below rather than trusting the return code.
    }

    # winget installs typically don't refresh the current process PATH.
    # Pull the latest System + User PATH so our re-check sees the new bins.
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:PATH    = "$machinePath;$userPath"

    Write-Host ""
    Write-Host "==> Re-checking prerequisites after install" -ForegroundColor White
    $stillMissing = @()
    foreach ($tool in $missing) {
        if ($tool -eq 'python') {
            $pythonResolved = Resolve-Python310Plus
            if ($pythonResolved) {
                Write-Host "    [+] python ($($pythonResolved.Version) via $($pythonResolved.Exe))" -ForegroundColor Green
            } else {
                Write-Host "    [X] python" -ForegroundColor Red
                $stillMissing += $tool
            }
            continue
        }
        if (Test-Tool $tool) {
            Write-Host "    [+] $tool" -ForegroundColor Green
        } else {
            Write-Host "    [X] $tool" -ForegroundColor Red
            $stillMissing += $tool
        }
    }

    if ($stillMissing.Count -gt 0) {
        Write-Host ""
        Write-Host "Still missing after install: $($stillMissing -join ', ')" -ForegroundColor Red
        Write-Host "Open a new PowerShell window so PATH updates apply, then re-run." -ForegroundColor Yellow
        exit 1
    }
}
Write-Host ""

# Clone or update (atomic — Codex P2: a previous failed clone may leave
# a partial directory without a .git/, which would crash the next run).
if (Test-Path (Join-Path $RepoDir '.git')) {
    Write-Host "==> Updating existing repo at $RepoDir" -ForegroundColor White
    git -C $RepoDir pull --ff-only
} elseif ((Test-Path $RepoDir) -and -not (Get-ChildItem -Force $RepoDir -ErrorAction SilentlyContinue)) {
    Write-Host "==> Cloning $RepoUrl into $RepoDir (empty dir)" -ForegroundColor White
    Remove-Item -Path $RepoDir -Force -ErrorAction SilentlyContinue
    git clone --depth 10 $RepoUrl $RepoDir
} elseif (Test-Path $RepoDir) {
    Write-Host "==> $RepoDir exists but is not a clean git clone — repairing via atomic swap." -ForegroundColor Yellow
    $tmpClone = "$RepoDir.partial.$([guid]::NewGuid().ToString('N').Substring(0,8))"
    git clone --depth 10 $RepoUrl $tmpClone
    if ($LASTEXITCODE -ne 0) { throw "clone into temp dir failed" }
    $backup = "$RepoDir.broken.$([int][double]::Parse((Get-Date -UFormat %s)))"
    Move-Item -Path $RepoDir -Destination $backup -Force
    Move-Item -Path $tmpClone -Destination $RepoDir -Force
    Write-Host "    old contents preserved at $backup (delete when ready)" -ForegroundColor DarkGray
} else {
    Write-Host "==> Cloning $RepoUrl into $RepoDir" -ForegroundColor White
    git clone --depth 10 $RepoUrl $RepoDir
}
Write-Host ""

# Local prep
Write-Host "==> Preparing local Agent Factory" -ForegroundColor White
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoDir 'install\install.ps1') -SkipPathUpdate -Quiet -SkipDependencyInstall -SkipSmokeTests
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

# Use the resolved Python 3.10+ interpreter from the prereq check, not
# whatever `python` happens to point at in the current PATH (could be a
# Store stub or the wrong version). Resolve a fresh one if we somehow
# lost the reference.
if (-not $pythonResolved) { $pythonResolved = Resolve-Python310Plus }
if (-not $pythonResolved) {
    Write-Host "[X] No working Python 3.10+ found after install. Open a new shell and re-run." -ForegroundColor Red
    exit 1
}
$wizardScript = Join-Path $RepoDir 'bravo_cli\main.py'
if ($Profile) {
    & $pythonResolved.Exe @($pythonResolved.LauncherArgs) $wizardScript 'setup' '--profile' $Profile
} else {
    & $pythonResolved.Exe @($pythonResolved.LauncherArgs) $wizardScript 'setup'
}
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "[+] Done." -ForegroundColor Green
Write-Host "   Open a new PowerShell window to pick up the PATH change."
Write-Host "   Then try: bravo doctor  |  bravo status" -ForegroundColor Cyan
