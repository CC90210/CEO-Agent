<#
Administrator wrapper for scripts/harden_powershell_profile.ps1.

Controlled Folder Access blocks PowerShell from writing the user profile.
This wrapper temporarily allow-lists Windows PowerShell, installs the guarded
profile, then removes the temporary allow-list entry if it was not present
before this run.
#>

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$TmpDir = Join-Path $RepoRoot "tmp"
$LogPath = Join-Path $TmpDir "admin_harden_powershell_profile.log"
$PowerShellExe = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
$Hardener = Join-Path $PSScriptRoot "harden_powershell_profile.ps1"

New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null
Start-Transcript -Path $LogPath -Force | Out-Null

try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        throw "This wrapper must run as Administrator."
    }

    $prefs = Get-MpPreference
    $existingAllowed = @($prefs.ControlledFolderAccessAllowedApplications)
    $alreadyAllowed = $existingAllowed -contains $PowerShellExe

    if (-not $alreadyAllowed) {
        Write-Host "Temporarily allowing Windows PowerShell through Controlled Folder Access..." -ForegroundColor Yellow
        Add-MpPreference -ControlledFolderAccessAllowedApplications $PowerShellExe
        Start-Sleep -Seconds 1
    } else {
        Write-Host "Windows PowerShell was already allowed through Controlled Folder Access." -ForegroundColor Cyan
    }

    try {
        & $Hardener
    } finally {
        if (-not $alreadyAllowed) {
            Write-Host "Removing temporary Windows PowerShell Controlled Folder Access allow-list entry..." -ForegroundColor Yellow
            Remove-MpPreference -ControlledFolderAccessAllowedApplications $PowerShellExe
        }
    }
} finally {
    Stop-Transcript | Out-Null
}
