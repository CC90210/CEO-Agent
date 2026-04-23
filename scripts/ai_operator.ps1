<#
AI Operator Console

Single-command control surface for the Windows AI workstation.
Designed to be safe by default: status/log/doctor are read-only; restart only
touches known PM2 AI services.
#>

[CmdletBinding()]
param(
    [ValidateSet("status", "doctor", "services", "logs", "restart-bravo", "security-events", "performance", "tools", "upgrade-plan")]
    [string]$Command = "status",

    [int]$Lines = 60
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Doctor {
    & (Join-Path $PSScriptRoot "ai_workstation_doctor.ps1")
}

function Show-Services {
    $pm2 = Get-Command pm2 -ErrorAction SilentlyContinue
    if (-not $pm2) {
        Write-Host "pm2 is not installed or not on PATH." -ForegroundColor Red
        return
    }
    pm2 list
}

function Show-Logs {
    $pm2 = Get-Command pm2 -ErrorAction SilentlyContinue
    if (-not $pm2) {
        Write-Host "pm2 is not installed or not on PATH." -ForegroundColor Red
        return
    }
    pm2 logs bravo-telegram --lines $Lines --nostream
    pm2 logs bravo-scheduler --lines $Lines --nostream
}

function Restart-Bravo {
    $pm2 = Get-Command pm2 -ErrorAction SilentlyContinue
    if (-not $pm2) {
        Write-Host "pm2 is not installed or not on PATH." -ForegroundColor Red
        return
    }
    pm2 restart bravo-telegram bravo-scheduler
}

function Show-SecurityEvents {
    try {
        Get-WinEvent -LogName "Microsoft-Windows-Windows Defender/Operational" -MaxEvents 120 |
            Where-Object { $_.Id -in 1121, 1123, 5007 } |
            Select-Object -First 20 TimeCreated, Id, Message |
            Format-List
    } catch {
        Write-Host "Could not read Defender event log: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Show-Performance {
    Write-Host "Top CPU processes" -ForegroundColor Cyan
    Get-Process | Sort-Object CPU -Descending |
        Select-Object -First 15 ProcessName, Id, CPU, @{Name="MemoryMB";Expression={[math]::Round($_.WorkingSet64 / 1MB, 1)}}, Path |
        Format-Table -AutoSize

    Write-Host ""
    Write-Host "Top memory processes" -ForegroundColor Cyan
    Get-Process | Sort-Object WorkingSet64 -Descending |
        Select-Object -First 15 ProcessName, Id, CPU, @{Name="MemoryMB";Expression={[math]::Round($_.WorkingSet64 / 1MB, 1)}}, Path |
        Format-Table -AutoSize

    Write-Host ""
    powercfg /L
}

function Show-Tools {
    $commands = "python", "node", "npm", "pm2", "git", "winget", "wsl", "uv", "bun", "claude", "gemini", "ollama", "nvidia-smi"
    $rows = foreach ($name in $commands) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            $version = ""
            try { $version = (& $name --version 2>$null | Select-Object -First 1) } catch {}
            [pscustomobject]@{ Command = $name; State = "OK"; Version = $version; Source = $cmd.Source }
        } else {
            [pscustomobject]@{ Command = $name; State = "MISSING"; Version = ""; Source = "" }
        }
    }
    $rows | Format-Table -AutoSize
}

function Show-UpgradePlan {
    Write-Host "AI Workstation Upgrade Plan" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Now:"
    Write-Host "  1. Keep High performance power plan active."
    Write-Host "  2. Enable DOCP/XMP in BIOS so the 3200-series RAM runs near rated speed."
    Write-Host "  3. Enable Windows Long Paths for large AI/JS/Python repos."
    Write-Host "  4. Install WSL 2 when ready for Linux AI tooling."
    Write-Host ""
    Write-Host "Next hardware:"
    Write-Host "  1. RAM: 64 GB preferred for agents + browsers + local models."
    Write-Host "  2. GPU: NVIDIA RTX with 16 GB VRAM minimum for local AI; 32 GB if budget allows."
    Write-Host "  3. Storage: add a 1-2 TB NVMe for models, datasets, recordings, and browser profiles."
    Write-Host "  4. PSU/cooling: size for GPU transient spikes and sustained AI loads."
    Write-Host ""
    Write-Host "After GPU:"
    Write-Host "  1. Install NVIDIA Studio/Game Ready driver."
    Write-Host "  2. Verify nvidia-smi."
    Write-Host "  3. Install Ollama or LM Studio."
    Write-Host "  4. Add local-model routing to Bravo for private/offline tasks."
}

switch ($Command) {
    "status" {
        Invoke-Doctor
        Write-Host ""
        Show-Services
    }
    "doctor" { Invoke-Doctor }
    "services" { Show-Services }
    "logs" { Show-Logs }
    "restart-bravo" { Restart-Bravo }
    "security-events" { Show-SecurityEvents }
    "performance" { Show-Performance }
    "tools" { Show-Tools }
    "upgrade-plan" { Show-UpgradePlan }
}
