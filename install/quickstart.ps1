# OASIS AI Agent Factory quickstart for Windows PowerShell.
#
# Usage (from a fresh PowerShell):
#   if (-not (Get-Command gh -EA SilentlyContinue)) { throw "GitHub CLI required: winget install GitHub.cli" }; gh auth status -h github.com *> $null; if ($LASTEXITCODE -ne 0) { gh auth login -h github.com }; $c=(gh api repos/CC90210/CEO-Agent/contents/install/quickstart.ps1 --jq .content) -join ''; iex ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($c)))
#
# What it does:
#   1. Detects missing prereqs (python, node, npm, git).
#   2. Auto-installs them via winget after one consent prompt.
#   3. Clones CEO-Agent into ~/bravo-repo (or updates it).
#   4. Prepares the local Agent Factory launcher.
#   5. Launches the interactive setup wizard.
#
# Overrides:
#   $env:OASIS_AUTO_INSTALL    = '1'   # skip consent prompt (CI use)
#   $env:OASIS_NO_AUTO_INSTALL = '1'   # keep old detect-only behavior
#   $env:OASIS_PROFILE         = 'atlas' | 'maven' | etc  # skip picker
#   $env:BRAVO_REPO_DIR        = 'C:\path\to\dir'         # clone target
#
# NOTE: this file uses ONLY single-line # comments. Multi-line <# ... #>
# block comments can break under irm|iex if any byte (BOM, whitespace)
# precedes the opener. Per-line # comments are robust against that
# entire class of prefix-corruption bug.

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

$RepoFullName = 'CC90210/CEO-Agent'
$RepoUrl = "https://github.com/$RepoFullName.git"
$QuickstartRawUrl = "https://raw.githubusercontent.com/$RepoFullName/main/install/quickstart.ps1"
$QuickstartApiPath = "repos/$RepoFullName/contents/install/quickstart.ps1"
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

function Test-GhReady {
    if (-not (Test-Tool 'gh')) { return $false }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & gh auth status -h github.com *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Get-QuickstartReinvokeCommand {
    return ('$env:OASIS_AUTO_INSTALL=''1''; if (Get-Command gh -ErrorAction SilentlyContinue) {{ gh auth status -h github.com *> $null; if ($LASTEXITCODE -eq 0) {{ $c=(gh api {0} --jq .content) -join [string]::Empty; iex ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($c))); exit $LASTEXITCODE }} }}; irm {1} | iex' -f $QuickstartApiPath, $QuickstartRawUrl)
}

# Find a real Python 3.10+ interpreter. Robust against:
#   - Microsoft Store stub (~\AppData\Local\Microsoft\WindowsApps\python.exe)
#     which opens the Store instead of running Python
#   - winget user-scope installs that don't auto-update the current
#     session's PATH (the install lands at %LOCALAPPDATA%\Programs\Python\
#     PythonXY\python.exe but Get-Command python returns nothing yet)
#   - PowerShell's $args automatic-variable shadowing (any function-local
#     $args = ... clobbers the function's argv handling — we use $pyArgs)
#
# Strategy:
#   1. Probe by name first: py -3.12 / -3.11 / -3.10, then python3.X /
#      python3 / python. Reject the Store stub by Source path.
#   2. If nothing on PATH, probe well-known absolute install locations
#      directly. Returning an absolute path is fine — callers run it
#      via `& $resolved.Exe`, no PATH lookup needed.
function Resolve-Python310Plus {
    $byName = @(
        @{ exe = 'py';         args = @('-3.13') },
        @{ exe = 'py';         args = @('-3.12') },
        @{ exe = 'py';         args = @('-3.11') },
        @{ exe = 'py';         args = @('-3.10') },
        @{ exe = 'python3.13'; args = @() },
        @{ exe = 'python3.12'; args = @() },
        @{ exe = 'python3.11'; args = @() },
        @{ exe = 'python3.10'; args = @() },
        @{ exe = 'python3';    args = @() },
        @{ exe = 'python';     args = @() }
    )

    $tryProbe = {
        param($exe, $launcherArgs, $sourcePath)
        # IMPORTANT: the Python snippet must NOT contain double-quotes.
        # PowerShell wraps each splatted arg in double quotes when invoking
        # an external process, and embedded " inside an arg gets mangled
        # before Python sees it (Python receives a syntax error and our
        # caller marks Python missing on a working machine — exactly the
        # bug paying clients hit on 2026-04-25). Use single quotes only,
        # and use `sep` instead of % formatting so we never need %.
        $pyArgs = @() + $launcherArgs + @('-c', "import sys; print(sys.version_info.major, sys.version_info.minor, sep='.')")
        try {
            $verRaw = & $exe @pyArgs 2>$null
            if (-not $verRaw) { return $null }
            $ver = ([string]$verRaw).Trim()
            if ($ver -match '^3\.(1[0-9]|[2-9][0-9])$') {
                return [pscustomobject]@{
                    Exe          = $exe
                    LauncherArgs = $launcherArgs
                    Source       = $sourcePath
                    Version      = $ver
                }
            }
        } catch {}
        return $null
    }

    foreach ($c in $byName) {
        $cmd = Get-Command $c.exe -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        # Reject the Microsoft Store stub explicitly.
        if ($cmd.Source -and $cmd.Source -match 'WindowsApps\\python.*\.exe$') {
            continue
        }
        $hit = & $tryProbe $c.exe $c.args $cmd.Source
        if ($hit) { return $hit }
    }

    # ---- Absolute-path fallback ----
    # winget user-scope installs land here; sometimes the registry PATH
    # update hasn't propagated to the current session.
    $absoluteCandidates = @()
    foreach ($v in @('313','312','311','310')) {
        $absoluteCandidates += "$env:LOCALAPPDATA\Programs\Python\Python$v\python.exe"
        $absoluteCandidates += "$env:ProgramFiles\Python$v\python.exe"
        $absoluteCandidates += "${env:ProgramFiles(x86)}\Python$v\python.exe"
    }
    # winget package store (paths look like
    #   %LOCALAPPDATA%\Microsoft\WinGet\Packages\Python.Python.3.12_*\python.exe)
    $wingetGlob = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\Python.Python.*\python.exe'
    try {
        $absoluteCandidates += @(
            Get-ChildItem -Path $wingetGlob -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty FullName
        )
    } catch {}

    foreach ($p in $absoluteCandidates) {
        if ($p -and (Test-Path $p)) {
            $hit = & $tryProbe $p @() $p
            if ($hit) { return $hit }
        }
    }

    return $null
}

# Force the current PowerShell session to pick up PATH changes that
# winget / package installers wrote to the Machine or User registry hive
# but didn't propagate to this process. Called BEFORE the first prereq
# check (in case the user already installed Python in another window
# and our process started with a stale env) and AFTER any winget call.
function Sync-PathFromRegistry {
    try {
        $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    } catch { $machinePath = '' }
    try {
        $userPath    = [Environment]::GetEnvironmentVariable('Path', 'User')
    } catch { $userPath = '' }
    if ($machinePath -or $userPath) {
        $env:PATH = "$machinePath;$userPath"
    }
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

# Refresh PATH first — if the user installed Python in a previous window
# (or via the FIRST attempt of this same script that died on the recheck),
# the registry has the new entries but our process started with a stale
# copy. Sync now so the prereq scan sees what's really installed.
Sync-PathFromRegistry

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
        Write-Host "Install 'App Installer' from the Microsoft Store, then re-run quickstart:" -ForegroundColor Yellow
        Write-Host "  https://apps.microsoft.com/detail/9NBLGGH4NNS1" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "Press Enter to close this window..." -ForegroundColor DarkGray
        try { Read-Host | Out-Null } catch {}
        exit 0
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
        Write-Host ""
        Write-Host "Press Enter to close this window..." -ForegroundColor DarkGray
        try { Read-Host | Out-Null } catch {}
        exit 0
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
    # Pull the latest registry env vars + the per-machine + per-user
    # locations winget actually uses, then re-probe absolute install
    # paths. The Resolve-Python310Plus + Sync-PathFromRegistry pair
    # handles BOTH cases (PATH updated but process is stale; PATH
    # genuinely not updated yet but binaries are on disk).
    Sync-PathFromRegistry

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
        # Self-heal path: the user installed everything, but PATH didn't
        # propagate to the current process. Spawn a FRESH PowerShell that
        # inherits the latest registry env, and re-run the quickstart
        # there. This avoids the "exit 1 + Windows-Terminal closes the
        # window because of close-on-exit" loop that paying clients hit.
        Write-Host ""
        Write-Host "PATH didn't refresh in this window. Self-healing - opening a fresh shell..." -ForegroundColor Yellow
        Write-Host "  (still missing: $($stillMissing -join ', '))" -ForegroundColor DarkGray
        Write-Host ""

        # Build the relaunch command. Set OASIS_AUTO_INSTALL=1 in the
        # child process so the second pass doesn't re-prompt for consent
        # (they already approved). Single-quoted on the OUTSIDE so we
        # send the literal text into the spawned shell and PowerShell
        # does not try to interpolate the env-var here.
        $reinvoke = Get-QuickstartReinvokeCommand

        # Find a working PowerShell. Prefer pwsh (PS 7+), fall back to
        # Windows PowerShell 5.1 which is universally present on Win10+.
        $psExe = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
        if (-not $psExe) { $psExe = (Get-Command powershell -ErrorAction SilentlyContinue).Source }
        if (-not $psExe) { $psExe = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" }

        # -NoExit keeps the new window open if the wizard finishes/quits,
        # so the user can read any final output instead of the window
        # vanishing behind close-on-exit.
        try {
            Start-Process -FilePath $psExe -ArgumentList @('-NoExit', '-NoProfile', '-Command', $reinvoke) -ErrorAction Stop | Out-Null
            Write-Host "  Fresh PowerShell window opened. The setup will continue there." -ForegroundColor Green
            Write-Host "  You can close this window now." -ForegroundColor DarkGray
            exit 0
        } catch {
            Write-Host "  Could not auto-launch a new window: $_" -ForegroundColor Red
            Write-Host ""
            Write-Host "Manual recovery (paste both lines into a NEW PowerShell window):" -ForegroundColor Yellow
            Write-Host '  $env:OASIS_AUTO_INSTALL=''1''' -ForegroundColor Cyan
            Write-Host "  $reinvoke" -ForegroundColor Cyan
            exit 0  # exit 0 so close-on-exit terminals don't slam shut on the user
        }
    }
}
Write-Host ""

# Clone or update (atomic — Codex P2: a previous failed clone may leave
# a partial directory without a .git/, which would crash the next run).
# --- Invoke-Git helpers (hoisted) ---------------------------------------------
# CRITICAL — PowerShell 5.1 + $ErrorActionPreference='Stop' bug:
# native commands (git, npm, etc.) that write to STDERR get raised as
# terminating NativeCommandError exceptions EVEN ON exit-code-0
# success. `git fetch` writes "From https://..." progress to stderr.
# `git clone` writes "Cloning into..." to stderr. Both are normal,
# successful output — but under EAP=Stop they halt the entire script.
# That bug is what hit CC at 20:05 today after the auto-update path
# ran for the first time.
#
# The fix: every git invocation goes through Invoke-Git, which
# temporarily switches EAP to Continue, runs the command, captures
# stderr into Out-Null, returns $LASTEXITCODE. Never throws on success
# stderr noise. Restores EAP in finally so the rest of the script keeps
# its strict error handling for genuinely terminating errors elsewhere.
function Invoke-Git {
    param([string[]]$GitArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & git @GitArgs 2>&1 | Out-Null
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
}
function Invoke-GitOut {
    # Returns stdout (trimmed) for queries like rev-parse / status.
    param([string[]]$GitArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & git @GitArgs 2>$null
        return ($out | Out-String).Trim()
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Invoke-GhAuthSetupGit {
    if (-not (Test-GhReady)) { return $false }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & gh auth setup-git -h github.com *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Invoke-GitFetchWithAuthRetry {
    param([string]$TargetDir, [string]$Branch)
    $rc = Invoke-Git @('-C', $TargetDir, 'fetch', '--depth', '50', 'origin', $Branch)
    if ($rc -eq 0) { return 0 }
    if (Invoke-GhAuthSetupGit) {
        return Invoke-Git @('-C', $TargetDir, 'fetch', '--depth', '50', 'origin', $Branch)
    }
    return $rc
}

function Invoke-RepoClone {
    param([string]$TargetDir)
    if (Test-GhReady) {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & gh repo clone $RepoFullName $TargetDir -- --depth 10 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) { return 0 }
        } finally {
            $ErrorActionPreference = $prev
        }
        Invoke-GhAuthSetupGit | Out-Null
    }
    return Invoke-Git @('clone', '--depth', '10', $RepoUrl, $TargetDir)
}

if (Test-Path (Join-Path $RepoDir '.git')) {
    Write-Host "==> Updating existing repo at $RepoDir" -ForegroundColor White
    # Shallow-clone-safe update. A `git pull --ff-only` on a depth-10
    # clone fails when upstream is 11+ commits ahead. Fetch with a
    # deeper depth and hard-reset to origin so the user always lands on
    # the latest main. Local edits are stashed first so nothing is lost.

    $curBranch = Invoke-GitOut @('-C', $RepoDir, 'rev-parse', '--abbrev-ref', 'HEAD')
    if (-not $curBranch -or $curBranch -eq 'HEAD') { $curBranch = 'main' }
    $dirty = Invoke-GitOut @('-C', $RepoDir, 'status', '--porcelain')
    if ($dirty) {
        Write-Host "    [!] local changes detected - stashing before update" -ForegroundColor Yellow
        $epoch = [int][double]::Parse((Get-Date -UFormat %s))
        Invoke-Git @('-C', $RepoDir, 'stash', 'push', '-u', '-m', "auto-stash by quickstart $epoch") | Out-Null
    }
    $fetchRc = Invoke-GitFetchWithAuthRetry -TargetDir $RepoDir -Branch $curBranch
    if ($fetchRc -eq 0) {
        $resetRc = Invoke-Git @('-C', $RepoDir, 'reset', '--hard', "origin/$curBranch")
        if ($resetRc -eq 0) {
            Write-Host "    synced to origin/$curBranch" -ForegroundColor DarkGray
        } else {
            Write-Host "    [!] reset failed - using existing local commits" -ForegroundColor Yellow
        }
    } else {
        Write-Host "    [!] fetch failed (offline?) - using existing local commits" -ForegroundColor Yellow
    }
} elseif ((Test-Path $RepoDir) -and -not (Get-ChildItem -Force $RepoDir -ErrorAction SilentlyContinue)) {
    Write-Host "==> Cloning $RepoUrl into $RepoDir (empty dir)" -ForegroundColor White
    Remove-Item -Path $RepoDir -Force -ErrorAction SilentlyContinue
    $cloneRc = Invoke-RepoClone -TargetDir $RepoDir
    if ($cloneRc -ne 0) { throw "git clone failed (exit $cloneRc)" }
} elseif (Test-Path $RepoDir) {
    Write-Host "==> $RepoDir exists but is not a clean git clone - repairing via atomic swap." -ForegroundColor Yellow
    $tmpClone = "$RepoDir.partial.$([guid]::NewGuid().ToString('N').Substring(0,8))"
    $cloneRc = Invoke-RepoClone -TargetDir $tmpClone
    if ($cloneRc -ne 0) { throw "clone into temp dir failed (exit $cloneRc)" }
    $backup = "$RepoDir.broken.$([int][double]::Parse((Get-Date -UFormat %s)))"
    Move-Item -Path $RepoDir -Destination $backup -Force
    Move-Item -Path $tmpClone -Destination $RepoDir -Force
    Write-Host "    old contents preserved at $backup (delete when ready)" -ForegroundColor DarkGray
} else {
    Write-Host "==> Cloning $RepoUrl into $RepoDir" -ForegroundColor White
    $cloneRc = Invoke-RepoClone -TargetDir $RepoDir
    if ($cloneRc -ne 0) { throw "git clone failed (exit $cloneRc)" }
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
    Write-Host "[X] No working Python 3.10+ found at the wizard-launch step." -ForegroundColor Red
    Write-Host "    Open a new PowerShell window so PATH refreshes, then run:" -ForegroundColor Yellow
    Write-Host "      $(Get-QuickstartReinvokeCommand)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Press Enter to close this window..." -ForegroundColor DarkGray
    try { Read-Host | Out-Null } catch {}
    exit 0  # exit 0 so close-on-exit terminals don't slam shut on the user
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

# Open the dashboard the moment the wizard exits cleanly. step_finalize
# already spawned the bridge on :9100, so the chat header turns cyan
# ("local bridge - full repo access") within ~2s of the page loading.
# Skip with $env:OASIS_SKIP_BROWSER_OPEN = '1' for CI / silent installs.
if ($env:OASIS_SKIP_BROWSER_OPEN -ne '1') {
    $dashUrl = if ($env:OASIS_DASHBOARD_URL) { $env:OASIS_DASHBOARD_URL } else { 'https://agent-dashboard-cc90210.vercel.app' }
    try { Start-Process "$dashUrl/agents" | Out-Null } catch { }
}

Write-Host ""
Write-Host "[+] Done." -ForegroundColor Green
Write-Host "   Open a new PowerShell window to pick up the PATH change."
Write-Host "   Then try: bravo doctor  |  bravo status" -ForegroundColor Cyan
