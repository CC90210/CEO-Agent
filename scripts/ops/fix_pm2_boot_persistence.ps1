<#
.SYNOPSIS
    Make the PM2 fleet survive an unattended reboot. REQUIRES ADMINISTRATOR.

.DESCRIPTION
    As found on 2026-07-29, the "PM2 Resurrect" scheduled task was:
      * "At logon time" only  -> after a power cut or a Windows Update reboot the
        whole fleet (bravo-scheduler, the Telegram bridges, the chat bridge)
        stayed DOWN until CC physically logged in;
      * "Interactive only"    -> it cannot run without an interactive session;
      * "No Start On Batteries" + "Stop On Battery Mode" -> on a laptop running
        on battery it would not start at all, and would be killed mid-run if the
        machine switched to battery.

    This script rewrites the task to:
      * trigger AT STARTUP (plus keep the logon trigger as a belt),
      * LogonType S4U — "run whether the user is logged on or not" WITHOUT
        storing a password (S4U uses a service-for-user token; the alternative,
        /RU + /RP, would mean putting CC's Windows password in a script),
      * run regardless of battery state and not stop when switching to battery,
      * restart up to 3 times if the resurrect fails,
      * no execution time limit (pm2 resurrect can be slow on a cold boot).

.NOTES
    Run:  powershell -ExecutionPolicy Bypass -File scripts\ops\fix_pm2_boot_persistence.ps1
    (right-click PowerShell -> Run as Administrator, or accept the UAC prompt)

    Verify afterwards:
      schtasks /query /tn "PM2 Resurrect" /fo LIST /v
      python scripts\machine_parity.py
#>

$ErrorActionPreference = 'Stop'
$TaskName = 'PM2 Resurrect'

function Assert-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Error "This script must run elevated (Administrator)."
        exit 1
    }
}

Assert-Admin
Write-Host "Running elevated. Reconfiguring '$TaskName'..." -ForegroundColor Cyan

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Error "Task '$TaskName' not found. Run 'pm2 startup' first, then re-run this."
    exit 1
}

Write-Host "`nBEFORE:" -ForegroundColor Yellow
$existing.Triggers | ForEach-Object { "  trigger : $($_.CimClass.CimClassName)" }
"  battery : AllowStartIfOnBatteries=$($existing.Settings.DisallowStartIfOnBatteries -eq $false)"
"  logon   : $($existing.Principal.LogonType)"

# Keep whatever action the task already had — that is the pm2 resurrect
# invocation (a hidden wscript wrapper, so no console window flashes on boot).
$actions = $existing.Actions

$triggers = @(
    (New-ScheduledTaskTrigger -AtStartup),
    (New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME")
)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

# S4U = run whether logged on or not, no stored password. RunLevel Highest so
# pm2 can bind its ports and write to the user's .pm2 home.
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType S4U `
    -RunLevel Highest

Set-ScheduledTask -TaskName $TaskName `
    -Action $actions -Trigger $triggers -Settings $settings -Principal $principal | Out-Null

$after = Get-ScheduledTask -TaskName $TaskName
Write-Host "`nAFTER:" -ForegroundColor Green
$after.Triggers | ForEach-Object { "  trigger : $($_.CimClass.CimClassName)" }
"  battery : AllowStartIfOnBatteries=$($after.Settings.DisallowStartIfOnBatteries -eq $false)"
"  logon   : $($after.Principal.LogonType)"

Write-Host "`nDone. The fleet will now come back after an unattended reboot." -ForegroundColor Green
Write-Host "Verify: schtasks /query /tn `"$TaskName`" /fo LIST /v" -ForegroundColor DarkGray
