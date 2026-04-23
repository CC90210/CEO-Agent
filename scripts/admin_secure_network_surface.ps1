<#
Administrator network hardening for the AI workstation.

Conservative defaults:
  - Keep Tailscale.
  - Keep PM2/AI services.
  - Keep outbound internet.
  - Close public-network inbound allowances for dev/game/browser tools.
  - Keep SSH reachable over Tailscale/localhost, not the whole LAN.
  - Disable Remote Assistance firewall rules.

This script is reversible from Windows Defender Firewall advanced settings.
#>

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$TmpDir = Join-Path $RepoRoot "tmp"
$LogPath = Join-Path $TmpDir "admin_secure_network_surface.log"
New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null
Start-Transcript -Path $LogPath -Force | Out-Null

try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        throw "This script must run as Administrator."
    }

    Write-Host "Hardening public inbound firewall rules..." -ForegroundColor Cyan
    $publicInboundPatterns = @(
        "Antigravity",
        "Node.js JavaScript Runtime",
        "python.exe",
        "chrome.exe",
        "obs-browser-page",
        "EpicGamesLauncher",
        "fivem_chromebrowser",
        "ACSETUP",
        "DriverPack aria2c.exe",
        "DriverPack-Alice",
        "Snappy Driver Installer",
        "Grand Theft Auto V",
        "Microsoft Office Groove",
        "Microsoft Office OneNote",
        "Microsoft Office Outlook",
        "Standalone version of Social Stream Ninja",
        "Google Chrome (mDNS-In)",
        "Microsoft Edge (mDNS-In)",
        "Opera Internet Browser (mDNS-In)",
        "RazerAppEngine",
        "RazerAppEngineUpgrade",
        "ArmouryHtmlDebugServer",
        "ArmourySocketServer",
        "Framework Service",
        "ROGLiveService",
        "Airhost service for Zoom Video Meetings",
        "Hybrid Conference for Zoom Video Meetings",
        "Zoom Video Meeting",
        "AgentService.exe",
        "tiktoklivestudio",
        "Microsoft Teams",
        "Armoury Crate",
        "MyASUS",
        "ms-resource:AppDisplayName",
        "AsusSwitchNet_56ACDA9B",
        "AsusSwitchNetMDNS_269A2EB3"
    )

    foreach ($pattern in $publicInboundPatterns) {
        $rules = @(Get-NetFirewallRule -Enabled True -Direction Inbound -Action Allow -ErrorAction SilentlyContinue |
            Where-Object {
                $profileText = $_.Profile.ToString()
                $profileText -match "Public|Any" -and $_.DisplayName -eq $pattern
            })
        foreach ($rule in $rules) {
            Disable-NetFirewallRule -Name $rule.Name
            Write-Host "Disabled public inbound rule: $($rule.DisplayName) [$($rule.Name)]" -ForegroundColor Yellow
        }
    }

    Write-Host "Restricting SSH firewall access to Tailscale + localhost..." -ForegroundColor Cyan
    $sshAllow = Get-NetFirewallRule -DisplayName "SSH - Allow Tailscale" -ErrorAction SilentlyContinue
    if ($sshAllow) {
        $sshAllow | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -RemoteAddress @("100.64.0.0/10", "127.0.0.1")
        Write-Host "SSH - Allow Tailscale now allows only 100.64.0.0/10 + IPv4 localhost." -ForegroundColor Green
    } else {
        Write-Host "SSH - Allow Tailscale rule not found; leaving SSH firewall rules unchanged." -ForegroundColor Yellow
    }

    Write-Host "Disabling Remote Assistance firewall rules..." -ForegroundColor Cyan
    $raRules = @(Get-NetFirewallRule -DisplayName "Remote Assistance*" -ErrorAction SilentlyContinue |
        Where-Object { $_.Enabled -eq "True" })
    foreach ($rule in $raRules) {
        Disable-NetFirewallRule -Name $rule.Name
        Write-Host "Disabled Remote Assistance rule: $($rule.DisplayName)" -ForegroundColor Yellow
    }

    Write-Host "Network surface hardening complete." -ForegroundColor Green
} finally {
    Stop-Transcript | Out-Null
}
