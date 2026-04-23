<#
AI Workstation Doctor

Read-only diagnostics for the Windows production AI workstation.
Writes a JSON and Markdown report under tmp/ without changing system settings.
#>

[CmdletBinding()]
param(
    [switch]$Json,
    [switch]$NoWrite
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$TmpDir = Join-Path $RepoRoot "tmp"
$JsonPath = Join-Path $TmpDir "ai_workstation_report.json"
$MdPath = Join-Path $TmpDir "AI_WORKSTATION_REPORT.md"

function Convert-BytesToGb {
    param([Nullable[UInt64]]$Bytes)
    if ($null -eq $Bytes) { return $null }
    return [math]::Round(($Bytes / 1GB), 2)
}

function Get-CommandVersion {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        return [pscustomobject]@{ name = $Name; installed = $false; source = $null; version = $null }
    }
    $version = $null
    try {
        $version = (& $Name --version 2>$null | Select-Object -First 1)
    } catch {}
    return [pscustomobject]@{
        name = $Name
        installed = $true
        source = $cmd.Source
        version = $version
    }
}

function Get-DefenderEvents {
    try {
        return @(Get-WinEvent -LogName "Microsoft-Windows-Windows Defender/Operational" -MaxEvents 200 |
            Where-Object { $_.Id -in 1121, 1123 } |
            Select-Object -First 12 TimeCreated, Id, Message)
    } catch {
        return @()
    }
}

function Get-WslState {
    $wsl = Get-Command wsl -ErrorAction SilentlyContinue
    if (-not $wsl) {
        return [pscustomobject]@{ installed = $false; status = "wsl.exe missing"; distributions = @() }
    }
    $status = ""
    $list = ""
    try { $status = ((wsl --status 2>&1 | Out-String) -replace "`0", "").Trim() } catch { $status = $_.Exception.Message }
    try { $list = ((wsl --list --verbose 2>&1 | Out-String) -replace "`0", "").Trim() } catch { $list = $_.Exception.Message }
    $installed = -not ($status -match "not\s+installed" -or $list -match "not\s+installed")
    return [pscustomobject]@{
        installed = $installed
        status = $status
        distributions = $list
    }
}

function Get-Pm2Snapshot {
    $pm2 = Get-Command pm2 -ErrorAction SilentlyContinue
    if (-not $pm2) { return @() }
    try {
        $raw = pm2 jlist 2>$null
        if (-not $raw) { return @() }
        return @($raw | ConvertFrom-Json | ForEach-Object {
            [pscustomobject]@{
                name = $_.name
                pid = $_.pid
                status = $_.pm2_env.status
                restarts = $_.pm2_env.restart_time
                uptime_ms = if ($_.pm2_env.pm_uptime) { [int64](([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) - $_.pm2_env.pm_uptime) } else { $null }
                memory_mb = if ($_.monit.memory) { [math]::Round($_.monit.memory / 1MB, 1) } else { $null }
                cpu = $_.monit.cpu
            }
        })
    } catch {
        return @()
    }
}

New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null

$computer = Get-ComputerInfo | Select-Object CsName, WindowsProductName, WindowsVersion, OsBuildNumber, OsArchitecture, CsManufacturer, CsModel, CsTotalPhysicalMemory
$cpu = Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed, L2CacheSize, L3CacheSize
$ram = @(Get-CimInstance Win32_PhysicalMemory | ForEach-Object {
    [pscustomobject]@{
        manufacturer = $_.Manufacturer
        part_number = ($_.PartNumber -as [string]).Trim()
        capacity_gb = Convert-BytesToGb $_.Capacity
        speed = $_.Speed
        configured_clock_speed = $_.ConfiguredClockSpeed
        slot = $_.DeviceLocator
    }
})
$gpu = @(Get-CimInstance Win32_VideoController | ForEach-Object {
    [pscustomobject]@{
        name = $_.Name
        adapter_ram_gb = Convert-BytesToGb $_.AdapterRAM
        driver_version = $_.DriverVersion
        driver_date = $_.DriverDate
        video_processor = $_.VideoProcessor
    }
})
$disks = @(Get-PhysicalDisk | Select-Object FriendlyName, MediaType, BusType, HealthStatus, OperationalStatus, @{Name="size_gb";Expression={Convert-BytesToGb $_.Size}})
$volumes = @(Get-Volume | Where-Object DriveLetter | Select-Object DriveLetter, FileSystemLabel, FileSystem, HealthStatus, @{Name="free_gb";Expression={Convert-BytesToGb $_.SizeRemaining}}, @{Name="size_gb";Expression={Convert-BytesToGb $_.Size}})
$pageFile = @(Get-CimInstance Win32_PageFileUsage | Select-Object Name, AllocatedBaseSize, CurrentUsage, PeakUsage)
$powerSchemes = (powercfg /L 2>$null | Out-String).Trim()
$activePower = (($powerSchemes -split "`n") | Where-Object { $_ -match "Power Scheme GUID:.*\*" } | Select-Object -First 1).Trim()
$longPaths = (Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -ErrorAction SilentlyContinue).LongPathsEnabled
$defenderPref = Get-MpPreference | Select-Object EnableControlledFolderAccess, DisableRealtimeMonitoring
$tools = @("python", "node", "npm", "pm2", "git", "winget", "wsl", "uv", "bun", "claude", "gemini", "ollama", "nvidia-smi") | ForEach-Object { Get-CommandVersion $_ }
$topCpu = @(Get-Process | Sort-Object CPU -Descending | Select-Object -First 12 ProcessName, Id, CPU, @{Name="memory_mb";Expression={[math]::Round($_.WorkingSet64 / 1MB, 1)}}, Path)
$topMem = @(Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 12 ProcessName, Id, CPU, @{Name="memory_mb";Expression={[math]::Round($_.WorkingSet64 / 1MB, 1)}}, Path)

$findings = New-Object System.Collections.Generic.List[string]
if (($computer.CsTotalPhysicalMemory / 1GB) -lt 32) { $findings.Add("RAM is below the recommended 32-64 GB for heavy local AI and browser automation.") }
if (($ram | Where-Object { $_.configured_clock_speed -lt 3000 }).Count -gt 0) { $findings.Add("RAM appears to be running below 3000 MHz; BIOS DOCP/XMP may be disabled.") }
if (($gpu | Where-Object { $_.name -match "NVIDIA" }).Count -eq 0) { $findings.Add("No NVIDIA GPU detected; local LLM acceleration is not available yet.") }
if (($tools | Where-Object { $_.name -eq "ollama" -and -not $_.installed }).Count -gt 0) { $findings.Add("Ollama is not installed; local model serving is not configured yet.") }
if (($tools | Where-Object { $_.name -eq "nvidia-smi" -and -not $_.installed }).Count -gt 0) { $findings.Add("nvidia-smi is missing; expected until a discrete NVIDIA GPU and drivers are installed.") }
if ($longPaths -ne 1) { $findings.Add("Windows Long Paths are disabled; large JS/Python/AI repos can hit path limits.") }
if (-not (Get-WslState).installed) { $findings.Add("WSL is not installed; Linux AI tooling and GPU containers are not ready.") }
if ($activePower -notmatch "High performance|Ultimate Performance") { $findings.Add("High performance power plan is not active.") }

$report = [pscustomobject]@{
    generated_at = (Get-Date).ToString("o")
    repo_root = $RepoRoot
    computer = $computer
    cpu = $cpu
    ram = $ram
    gpu = $gpu
    disks = $disks
    volumes = $volumes
    page_file = $pageFile
    power = [pscustomobject]@{ active = $activePower; schemes = $powerSchemes }
    windows = [pscustomobject]@{ long_paths_enabled = $longPaths; wsl = Get-WslState }
    defender = [pscustomobject]@{ preferences = $defenderPref; recent_blocks = Get-DefenderEvents }
    tools = $tools
    pm2 = Get-Pm2Snapshot
    top_cpu_processes = $topCpu
    top_memory_processes = $topMem
    findings = @($findings)
}

if (-not $NoWrite) {
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $JsonPath -Encoding UTF8

    $md = @()
    $md += "# AI Workstation Report"
    $md += ""
    $md += "- Generated: $($report.generated_at)"
    $md += "- Machine: $($computer.CsName)"
    $md += "- Windows: $($computer.WindowsProductName) build $($computer.OsBuildNumber)"
    $md += "- CPU: $($cpu.Name) ($($cpu.NumberOfCores)c/$($cpu.NumberOfLogicalProcessors)t)"
    $md += "- RAM: $([math]::Round($computer.CsTotalPhysicalMemory / 1GB, 2)) GB"
    $md += "- Active power plan: $activePower"
    $md += ""
    $md += "## Findings"
    if ($findings.Count -eq 0) {
        $md += "- No major workstation findings."
    } else {
        foreach ($finding in $findings) { $md += "- $finding" }
    }
    $md += ""
    $md += "## Tools"
    foreach ($tool in $tools) {
        $state = if ($tool.installed) { "OK" } else { "MISSING" }
        $md += "- $($tool.name): $state $($tool.version)"
    }
    $md += ""
    $md += "## PM2"
    foreach ($proc in $report.pm2) {
        $md += "- $($proc.name): $($proc.status), pid $($proc.pid), restarts $($proc.restarts), mem $($proc.memory_mb) MB"
    }
    $md | Set-Content -LiteralPath $MdPath -Encoding UTF8
}

if ($Json) {
    $report | ConvertTo-Json -Depth 8
} else {
    Write-Host "AI Workstation Doctor" -ForegroundColor Cyan
    Write-Host "Machine: $($computer.CsName) | CPU: $($cpu.Name) | RAM: $([math]::Round($computer.CsTotalPhysicalMemory / 1GB, 2)) GB"
    Write-Host "Power: $activePower"
    Write-Host ""
    Write-Host "Findings:" -ForegroundColor Yellow
    if ($findings.Count -eq 0) {
        Write-Host "  OK - no major workstation findings."
    } else {
        foreach ($finding in $findings) { Write-Host "  - $finding" }
    }
    if (-not $NoWrite) {
        Write-Host ""
        Write-Host "Reports written:" -ForegroundColor Green
        Write-Host "  $JsonPath"
        Write-Host "  $MdPath"
    }
}
