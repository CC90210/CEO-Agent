<#
Administrator AI workstation feature toggles.

Safe, reversible baseline improvements for large AI/dev workspaces:
  - Enable Windows Long Paths.
  - Keep a high-performance power plan active.

This script does not weaken Defender, firewall, or Controlled Folder Access.
#>

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$TmpDir = Join-Path $RepoRoot "tmp"
$LogPath = Join-Path $TmpDir "admin_enable_ai_workstation_features.log"
New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null
Start-Transcript -Path $LogPath -Force | Out-Null

try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        throw "This script must run as Administrator."
    }

    Write-Host "Enabling Windows Long Paths..." -ForegroundColor Cyan
    New-ItemProperty `
        -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
        -Name "LongPathsEnabled" `
        -Value 1 `
        -PropertyType DWord `
        -Force | Out-Null
    Write-Host "Long Paths enabled. A reboot may be required for every app to notice." -ForegroundColor Green

    Write-Host "Ensuring High performance power plan is active..." -ForegroundColor Cyan
    powercfg /S 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c | Out-Null
    Write-Host "High performance power plan active." -ForegroundColor Green

    Write-Host "AI workstation feature baseline complete." -ForegroundColor Green
} finally {
    Stop-Transcript | Out-Null
}
