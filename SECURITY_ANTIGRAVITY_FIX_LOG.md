# Security Antigravity Fix Log

Date: 2026-05-19 local time
Repo: `C:\Users\User\Business-Empire-Agent`

## Outcome

Antigravity was repaired and launched successfully.

Verified live process path:

```powershell
C:\Users\User\AppData\Local\Programs\Antigravity\Antigravity.exe
```

## Diagnosis

The Antigravity failure was caused by Microsoft Defender Exploit Guard / Attack Surface Reduction rule:

```text
01443614-cd74-433a-b99e-2ecdc07bfc25
```

Defender event log showed Antigravity's installer launching `old-uninstaller.exe` from randomized Temp extraction folders, and ASR blocked it:

```text
Microsoft Defender Exploit Guard has blocked an operation that is not allowed by your IT administrator.
ID: 01443614-CD74-433A-B99E-2ECDC07BFC25
Path: C:\Users\User\AppData\Local\Temp\nsaFA33.tmp\old-uninstaller.exe
Process Name: C:\Users\User\Downloads\Antigravity.exe
Event ID: 1121
```

After the ASR rule was moved to AuditMode, later events changed from block to audit:

```text
Event ID: 1122
Microsoft Defender Exploit Guard audited an operation that is not allowed by your IT administrator.
```

The broken shortcut happened because the previous install/update was interrupted and this path was missing:

```powershell
C:\Users\User\AppData\Local\Programs\Antigravity\Antigravity.exe
```

Other blockers checked:

- Smart App Control: `Off`
- Controlled Folder Access: `Enabled`, but Antigravity already had an allowed app entry
- AppLocker: AppIDSvc stopped, no `SrpV2` policy registry key found, AppLocker cmdlets unavailable on this Windows image
- WDAC / Code Integrity: active Microsoft policy files exist, but `UsermodeCodeIntegrityPolicyEnforcementStatus` was `0`; no fresh Antigravity block found in Code Integrity logs
- Mark-of-the-Web: no `Zone.Identifier` stream found on the downloaded installer during check
- Installer signature: valid Google LLC signature on `C:\Users\User\Downloads\Antigravity.exe`

## Current Security State Observed

ASR configured rule:

```text
01443614-cd74-433a-b99e-2ecdc07bfc25 = 2
```

Action `2` is AuditMode.

Defender status highlights:

```text
AMRunningMode: Normal
AntivirusEnabled: True
RealTimeProtectionEnabled: True
BehaviorMonitorEnabled: True
IoavProtectionEnabled: True
IsTamperProtected: True
SmartAppControlState: Off
EnableControlledFolderAccess: 1
RebootRequired: False
```

## Commands Run

Initial context/admin checks:

```powershell
Get-Location
whoami /groups
whoami /priv
net session
Get-ExecutionPolicy -List
$ExecutionContext.SessionState.LanguageMode
```

Repo boot/context reads:

```powershell
Get-Content -Path brain\AGENT_ROUTER.md -TotalCount 240
Get-Content -Path brain\EXECUTION_RULES.md -TotalCount 260
Get-Content -Path brain\INTENTS.md -TotalCount 220
Get-Content -Path brain\WHEN_TO_USE_SKILLS.md -TotalCount 220
```

Defender diagnostics:

```powershell
Get-MpComputerStatus
Get-MpPreference | Format-List *
Get-MpPreference | Select-Object -ExpandProperty AttackSurfaceReductionRules_Ids
Get-MpPreference | Select-Object -ExpandProperty AttackSurfaceReductionRules_Actions
Get-MpPreference | Select-Object EnableControlledFolderAccess, ControlledFolderAccessAllowedApplications, ExclusionPath, ExclusionProcess | Format-List
Get-MpPreference | Select-Object -ExpandProperty AttackSurfaceReductionOnlyExclusions
Get-MpPreference | Select-Object -ExpandProperty ExclusionPath
```

AppLocker / WDAC / SmartScreen diagnostics:

```powershell
Get-AppLockerPolicy -Effective -Xml
Get-Service AppIDSvc | Format-List Name,Status,StartType
reg query HKLM\SOFTWARE\Policies\Microsoft\Windows\SrpV2 /s
Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard | Format-List *
reg query HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy /s
Get-ChildItem C:\Windows\System32\CodeIntegrity -Force | Select-Object FullName,Length,LastWriteTime | Format-Table -AutoSize
Get-ChildItem C:\Windows\System32\CodeIntegrity\CIPolicies -Recurse -Force | Select-Object FullName,Length,LastWriteTime | Format-Table -AutoSize
reg query HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer /v SmartScreenEnabled
reg query HKLM\SOFTWARE\Policies\Microsoft\Windows\System /v EnableSmartScreen
reg query HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\AppHost /v EnableWebContentEvaluation
```

Event log checks:

```powershell
$start=(Get-Date).AddDays(-14)
Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Windows Defender/Operational'; StartTime=$start} | Where-Object { $_.Message -match 'Antigravity|old-uninstaller|nsFA33|01443614|Attack Surface Reduction|ASR' } | Select-Object TimeCreated,Id,ProviderName,Message | Format-List

$start=(Get-Date).AddDays(-14)
Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-CodeIntegrity/Operational'; StartTime=$start} | Where-Object { $_.Message -match 'Antigravity|old-uninstaller|nsFA33|Policy|blocked|denied' } | Select-Object TimeCreated,Id,ProviderName,Message | Format-List

$start=(Get-Date).AddDays(-14)
Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-AppLocker/EXE and DLL'; StartTime=$start} | Where-Object { $_.Message -match 'Antigravity|old-uninstaller|nsFA33|blocked|denied' } | Select-Object TimeCreated,Id,ProviderName,Message | Format-List

$start=(Get-Date).AddDays(-14)
Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-AppLocker/MSI and Script'; StartTime=$start} | Where-Object { $_.Message -match 'Antigravity|old-uninstaller|nsFA33|blocked|denied' } | Select-Object TimeCreated,Id,ProviderName,Message | Format-List
```

Installer and install path checks:

```powershell
Get-Item 'C:\Users\User\Downloads\Antigravity.exe' -ErrorAction SilentlyContinue | Select-Object FullName,Length,LastWriteTime | Format-List
Get-Item 'C:\Users\User\AppData\Local\Programs\Antigravity\Antigravity.exe' -ErrorAction SilentlyContinue | Select-Object FullName,Length,LastWriteTime | Format-List
Get-AuthenticodeSignature 'C:\Users\User\Downloads\Antigravity.exe' | Format-List Status,StatusMessage,SignerCertificate,Path
Get-Item -Path 'C:\Users\User\Downloads\Antigravity.exe' -Stream Zone.Identifier -ErrorAction SilentlyContinue | Format-List *
```

Fix commands:

```powershell
New-Item -ItemType Directory -Force -Path 'C:\Installers\Antigravity','C:\Installers\Antigravity\Temp' | Select-Object FullName
Copy-Item -Path 'C:\Users\User\Downloads\Antigravity.exe' -Destination 'C:\Installers\Antigravity\Antigravity.exe' -Force
Unblock-File -Path 'C:\Installers\Antigravity\Antigravity.exe'
Get-AuthenticodeSignature 'C:\Installers\Antigravity\Antigravity.exe' | Format-List Status,StatusMessage,Path,SignerCertificate
Add-MpPreference -AttackSurfaceReductionOnlyExclusions 'C:\Installers\Antigravity'
Add-MpPreference -ExclusionPath 'C:\Installers\Antigravity'
$env:TEMP='C:\Installers\Antigravity\Temp'
$env:TMP='C:\Installers\Antigravity\Temp'
$p=Start-Process -FilePath 'C:\Installers\Antigravity\Antigravity.exe' -ArgumentList '/S' -Wait -PassThru
Get-Item 'C:\Users\User\AppData\Local\Programs\Antigravity\Antigravity.exe' -ErrorAction SilentlyContinue | Select-Object FullName,Length,LastWriteTime | Format-List
Start-Process -FilePath 'C:\Users\User\AppData\Local\Programs\Antigravity\Antigravity.exe'
Get-Process | Where-Object { $_.ProcessName -match 'Antigravity' } | Select-Object ProcessName,Id,StartTime,Path | Format-Table -AutoSize
```

Final verification:

```powershell
$start=(Get-Date).AddMinutes(-20)
Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Windows Defender/Operational'; StartTime=$start} | Where-Object { $_.Message -match 'Antigravity|old-uninstaller|C:\\Installers\\Antigravity|01443614' } | Select-Object TimeCreated,Id,Message | Format-List

$start=(Get-Date).AddMinutes(-20)
Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-AppLocker/EXE and DLL'; StartTime=$start} | Where-Object { $_.Message -match 'Antigravity|old-uninstaller|C:\\Installers\\Antigravity' } | Select-Object TimeCreated,Id,Message | Format-List

$start=(Get-Date).AddMinutes(-20)
Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-CodeIntegrity/Operational'; StartTime=$start} | Where-Object { $_.Message -match 'Antigravity|old-uninstaller|C:\\Installers\\Antigravity' } | Select-Object TimeCreated,Id,Message | Format-List
Get-Process | Where-Object { $_.ProcessName -match 'Antigravity' } | Select-Object ProcessName,Id,StartTime,Path | Format-Table -AutoSize
Start-Sleep -Seconds 30
Get-Process | Where-Object { $_.ProcessName -match 'Antigravity|antigravity' } | Select-Object ProcessName,Id,Path | Format-Table -AutoSize
Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'Antigravity|antigravity' } | Select-Object ProcessId,Name,ExecutablePath,CommandLine | Format-List
git status --short
python scripts/state/state_sync.py --note "Repaired Antigravity on Windows: diagnosed Defender ASR rule 01443614 blocking old-uninstaller.exe from Temp, staged signed installer under C:\Installers\Antigravity, added temporary targeted Defender/ASR staging exclusions, reinstalled, launched app, and documented SECURITY_ANTIGRAVITY_FIX_LOG.md."
python scripts/state/state_sync.py --note "Repaired Antigravity on Windows: diagnosed Defender ASR rule 01443614 blocking old-uninstaller.exe from Temp, staged the signed installer in C:/Installers/Antigravity, added temporary targeted Defender and ASR staging exclusions, reinstalled, launched app, and documented SECURITY_ANTIGRAVITY_FIX_LOG.md."
```

Notes from final verification:

- `Antigravity.exe` was running from the repaired install path.
- Two installer helper processes were still running from Temp with `/VERYSILENT /MERGETASKS=!runcode`; these appear to be Antigravity installer/update helpers, not security blocks.
- No fresh AppLocker block was found.
- No fresh Code Integrity block was found.
- The only fresh Defender events after repair were the intentional exclusion changes.
- First `state_sync.py` note partially failed on `STATE.md` because the Windows path backslash sequence was parsed as a bad escape; the second note with forward slashes succeeded for `STATE.md` and `SESSION_LOG.md`.

## Settings Changed

Added temporary ASR-only exclusion:

```powershell
C:\Installers\Antigravity
```

Added temporary Defender path exclusion:

```powershell
C:\Installers\Antigravity
```

No global Defender protection was disabled. Real-time protection, tamper protection, behavior monitoring, cloud protection, and Controlled Folder Access remain enabled.

Existing Antigravity-related ASR exclusions were already present before this fix:

```powershell
C:\Users\User\AppData\Local\Programs\Antigravity\
C:\Users\User\AppData\Local\Programs\Antigravity\Antigravity.exe
C:\Users\User\AppData\Local\Temp\antigravity-update
C:\Users\User\AppData\Local\Temp\AntigravitySetup-stable-*.exe
C:\Users\User\AppData\Local\Temp\AntigravitySetup-stable-*.tmp
C:\Users\User\AppData\Local\Temp\is-*.tmp
```

## Restore Plan

After Antigravity has finished opening/updating cleanly, remove the temporary staging exclusions:

```powershell
Remove-MpPreference -AttackSurfaceReductionOnlyExclusions 'C:\Installers\Antigravity'
Remove-MpPreference -ExclusionPath 'C:\Installers\Antigravity'
```

Optional cleanup after confirming Antigravity works across a reboot:

```powershell
Remove-Item -Path 'C:\Installers\Antigravity' -Recurse -Force
```

Do not remove the existing Antigravity install-path exclusions unless Antigravity continues working without ASR warnings for a few days.

## Reboot Requirement

No reboot was required for the repair. A normal reboot can be used later to verify the shortcut and startup behavior, but it is not required for the current fix.
