<# 
Replaces the current user's Windows PowerShell profile with guarded AI aliases.

This removes blanket-approval behavior from the default claude and gemini
commands while keeping explicit planning/edit aliases available.

If Windows Security Controlled Folder Access blocks this script, allow the
blocked PowerShell app once or paste the guarded profile content manually into:
  $PROFILE.CurrentUserCurrentHost
#>

$ErrorActionPreference = "Stop"

$ProfilePath = $PROFILE.CurrentUserCurrentHost
$ProfileDir = Split-Path -Parent $ProfilePath
$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackupDir = Join-Path $RepoRoot "tmp\powershell_profile_backups"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupPath = Join-Path $BackupDir "Microsoft.PowerShell_profile.ps1.$Timestamp.bak"

$GuardedProfile = @'
function claude {
    & "$env:USERPROFILE\.local\bin\claude.exe" @args
}

function claude-plan {
    & "$env:USERPROFILE\.local\bin\claude.exe" --permission-mode plan @args
}

function claude-edits {
    & "$env:USERPROFILE\.local\bin\claude.exe" --permission-mode acceptEdits @args
}

function gemini {
    & "$env:APPDATA\npm\gemini.cmd" @args
}

function gemini-plan {
    & "$env:APPDATA\npm\gemini.cmd" --approval-mode plan @args
}

function ai-status {
    Write-Host "AI operator mode: guarded" -ForegroundColor Cyan
    & "$env:USERPROFILE\.local\bin\claude.exe" --version
    & "$env:APPDATA\npm\gemini.cmd" --version
}

function ai-operator {
    & "$env:USERPROFILE\Business-Empire-Agent\scripts\ai_operator.ps1" @args
}

function ai-doctor {
    & "$env:USERPROFILE\Business-Empire-Agent\scripts\ai_workstation_doctor.ps1" @args
}

function ai-services {
    & "$env:USERPROFILE\Business-Empire-Agent\scripts\ai_operator.ps1" services @args
}

function ai-logs {
    & "$env:USERPROFILE\Business-Empire-Agent\scripts\ai_operator.ps1" logs @args
}

function ai-restart-bravo {
    & "$env:USERPROFILE\Business-Empire-Agent\scripts\ai_operator.ps1" restart-bravo @args
}

$__psArgs = [Environment]::GetCommandLineArgs()
$__isScriptedShell =
    ($__psArgs -contains "-Command") -or
    ($__psArgs -contains "-EncodedCommand") -or
    ($__psArgs -contains "-File") -or
    ($env:CI -eq "true") -or
    ($env:NONINTERACTIVE -eq "true")

if (-not $__isScriptedShell) {
    Write-Host "AI operator mode: guarded. Use claude-plan/gemini-plan for read-only planning." -ForegroundColor Cyan

    function global:prompt {
        $path = (Get-Location).Path
        $leaf = Split-Path $path -Leaf
        $branch = ""
        try {
            $gitBranch = git branch --show-current 2>$null
            if ($gitBranch) { $branch = " [$gitBranch]" }
        } catch {}
        $time = Get-Date -Format "HH:mm"
        return "[$time] $leaf$branch> "
    }
}
'@

try {
    New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    if (Test-Path -LiteralPath $ProfilePath) {
        Copy-Item -LiteralPath $ProfilePath -Destination $BackupPath -Force
        Write-Host "Backed up existing profile to $BackupPath" -ForegroundColor Yellow
    }

    $Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($ProfilePath, $GuardedProfile, $Utf8NoBom)
    Write-Host "Installed guarded PowerShell profile at $ProfilePath" -ForegroundColor Green
    Write-Host "Open a new terminal and run ai-status." -ForegroundColor Cyan
} catch [System.UnauthorizedAccessException] {
    Write-Host "Windows blocked the profile write." -ForegroundColor Red
    Write-Host "Open Windows Security > Virus & threat protection > Ransomware protection > Allow an app through Controlled folder access." -ForegroundColor Yellow
    Write-Host "Choose Add a recently blocked app and allow PowerShell, then rerun this script." -ForegroundColor Yellow
    throw
}
