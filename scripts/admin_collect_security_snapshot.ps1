<#
Collect admin-only security facts for the AI workstation audit.
Read-only. Writes JSON to tmp/admin_security_snapshot.json.
#>

$ErrorActionPreference = "Continue"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$TmpDir = Join-Path $RepoRoot "tmp"
$OutPath = Join-Path $TmpDir "admin_security_snapshot.json"
$LogPath = Join-Path $TmpDir "admin_collect_security_snapshot.log"
New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null
Start-Transcript -Path $LogPath -Force | Out-Null

try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

    $secureBoot = $null
    $secureBootError = $null
    try { $secureBoot = Confirm-SecureBootUEFI } catch { $secureBootError = $_.Exception.Message }

    $tpm = $null
    $tpmError = $null
    try { $tpm = Get-Tpm } catch { $tpmError = $_.Exception.Message }

    $bitLocker = $null
    $bitLockerError = $null
    try {
        $bitLocker = @(Get-BitLockerVolume | Select-Object MountPoint, VolumeStatus, ProtectionStatus, EncryptionPercentage, EncryptionMethod)
    } catch { $bitLockerError = $_.Exception.Message }

    $mpPref = $null
    $mpError = $null
    try {
        $mp = Get-MpPreference
        $mpPref = [pscustomobject]@{
            ControlledFolderAccessAllowedApplications = @($mp.ControlledFolderAccessAllowedApplications)
            ControlledFolderAccessProtectedFolders = @($mp.ControlledFolderAccessProtectedFolders)
            ExclusionPath = @($mp.ExclusionPath)
            ExclusionProcess = @($mp.ExclusionProcess)
            ExclusionExtension = @($mp.ExclusionExtension)
            AttackSurfaceReductionOnlyExclusions = @($mp.AttackSurfaceReductionOnlyExclusions)
        }
    } catch { $mpError = $_.Exception.Message }

    $snapshot = [pscustomobject]@{
        generated_at = (Get-Date).ToString("o")
        is_admin = $isAdmin
        secure_boot = $secureBoot
        secure_boot_error = $secureBootError
        tpm = $tpm
        tpm_error = $tpmError
        bitlocker = $bitLocker
        bitlocker_error = $bitLockerError
        defender_exclusions = $mpPref
        defender_exclusions_error = $mpError
    }

    $snapshot | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutPath -Encoding UTF8
    Write-Host "Security snapshot written to $OutPath" -ForegroundColor Green
} finally {
    Stop-Transcript | Out-Null
}
