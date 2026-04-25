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
    [switch]$NoAutoInstall
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
foreach ($tool in $tools) {
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

# Clone or update
if (Test-Path (Join-Path $RepoDir '.git')) {
    Write-Host "==> Updating existing repo at $RepoDir" -ForegroundColor White
    git -C $RepoDir pull --ff-only
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

python (Join-Path $RepoDir 'bravo_cli\main.py') setup
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "[+] Done." -ForegroundColor Green
Write-Host "   Open a new PowerShell window to pick up the PATH change."
Write-Host "   Then try: bravo doctor  |  bravo status" -ForegroundColor Cyan
