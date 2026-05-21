param(
    [int]$TargetVolume = 100,
    [switch]$RepairSessionsOnly,
    [switch]$ResetPolicyStore,
    [switch]$InstallScheduledTask,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-AudioTmpDir {
    $dir = Join-Path (Get-RepoRoot) "tmp\chrome-audio"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Write-AudioLog {
    param([string]$Message)
    $line = "$(Get-Date -Format o) $Message"
    Add-Content -LiteralPath (Join-Path (Get-AudioTmpDir) "repair.log") -Value $line
}

$coreAudioCode = @'
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

public class ChromeAudioRepair {
    enum EDataFlow { eRender = 0, eCapture = 1, eAll = 2 }
    enum ERole { eConsole = 0, eMultimedia = 1, eCommunications = 2 }
    enum AudioSessionState { Inactive = 0, Active = 1, Expired = 2 }

    const int DEVICE_STATE_ACTIVE = 0x00000001;
    const int CLSCTX_ALL = 23;
    static readonly Guid IID_IAudioSessionManager2 = new Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F");

    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    class MMDeviceEnumerator { }

    [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDeviceEnumerator {
        int EnumAudioEndpoints(EDataFlow dataFlow, int dwStateMask, out IMMDeviceCollection ppDevices);
        int GetDefaultAudioEndpoint(EDataFlow dataFlow, ERole role, out IMMDevice ppEndpoint);
        int GetDevice([MarshalAs(UnmanagedType.LPWStr)] string pwstrId, out IMMDevice ppDevice);
        int RegisterEndpointNotificationCallback(IntPtr pClient);
        int UnregisterEndpointNotificationCallback(IntPtr pClient);
    }

    [ComImport, Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDeviceCollection {
        int GetCount(out uint pcDevices);
        int Item(uint nDevice, out IMMDevice ppDevice);
    }

    [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDevice {
        int Activate(ref Guid iid, int dwClsCtx, IntPtr pActivationParams, [MarshalAs(UnmanagedType.IUnknown)] out object ppInterface);
        int OpenPropertyStore(int stgmAccess, out IPropertyStore ppProperties);
        int GetId([MarshalAs(UnmanagedType.LPWStr)] out string ppstrId);
        int GetState(out int pdwState);
    }

    [StructLayout(LayoutKind.Sequential)]
    struct PROPERTYKEY { public Guid fmtid; public uint pid; }

    [StructLayout(LayoutKind.Sequential)]
    struct PROPVARIANT {
        public ushort vt;
        public ushort wReserved1;
        public ushort wReserved2;
        public ushort wReserved3;
        public IntPtr p;
        public int p2;
    }

    [ComImport, Guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyStore {
        int GetCount(out uint cProps);
        int GetAt(uint iProp, out PROPERTYKEY pkey);
        int GetValue(ref PROPERTYKEY key, out PROPVARIANT pv);
        int SetValue(ref PROPERTYKEY key, ref PROPVARIANT pv);
        int Commit();
    }

    [ComImport, Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioSessionManager2 {
        int GetAudioSessionControl(ref Guid AudioSessionGuid, int StreamFlags, out IAudioSessionControl SessionControl);
        int GetSimpleAudioVolume(ref Guid AudioSessionGuid, int StreamFlags, out ISimpleAudioVolume AudioVolume);
        int GetSessionEnumerator(out IAudioSessionEnumerator SessionEnum);
        int RegisterSessionNotification(IntPtr SessionNotification);
        int UnregisterSessionNotification(IntPtr SessionNotification);
        int RegisterDuckNotification(string sessionID, IntPtr duckNotification);
        int UnregisterDuckNotification(IntPtr duckNotification);
    }

    [ComImport, Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioSessionEnumerator {
        int GetCount(out int SessionCount);
        int GetSession(int SessionCount, out IAudioSessionControl Session);
    }

    [ComImport, Guid("F4B1A599-7266-4319-A8CA-E70ACB11E8CD"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioSessionControl {
        int GetState(out AudioSessionState pRetVal);
        int GetDisplayName([MarshalAs(UnmanagedType.LPWStr)] out string pRetVal);
        int SetDisplayName([MarshalAs(UnmanagedType.LPWStr)] string Value, ref Guid EventContext);
        int GetIconPath([MarshalAs(UnmanagedType.LPWStr)] out string pRetVal);
        int SetIconPath([MarshalAs(UnmanagedType.LPWStr)] string Value, ref Guid EventContext);
        int GetGroupingParam(out Guid pRetVal);
        int SetGroupingParam(ref Guid Override, ref Guid EventContext);
        int RegisterAudioSessionNotification(IntPtr NewNotifications);
        int UnregisterAudioSessionNotification(IntPtr NewNotifications);
    }

    [ComImport, Guid("bfb7ff88-7239-4fc9-8fa2-07c950be9c6d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioSessionControl2 {
        int GetState(out AudioSessionState pRetVal);
        int GetDisplayName([MarshalAs(UnmanagedType.LPWStr)] out string pRetVal);
        int SetDisplayName([MarshalAs(UnmanagedType.LPWStr)] string Value, ref Guid EventContext);
        int GetIconPath([MarshalAs(UnmanagedType.LPWStr)] out string pRetVal);
        int SetIconPath([MarshalAs(UnmanagedType.LPWStr)] string Value, ref Guid EventContext);
        int GetGroupingParam(out Guid pRetVal);
        int SetGroupingParam(ref Guid Override, ref Guid EventContext);
        int RegisterAudioSessionNotification(IntPtr NewNotifications);
        int UnregisterAudioSessionNotification(IntPtr NewNotifications);
        int GetSessionIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string pRetVal);
        int GetSessionInstanceIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string pRetVal);
        int GetProcessId(out uint pRetVal);
        int IsSystemSoundsSession();
        int SetDuckingPreference(bool optOut);
    }

    [ComImport, Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface ISimpleAudioVolume {
        int SetMasterVolume(float fLevel, ref Guid EventContext);
        int GetMasterVolume(out float pfLevel);
        int SetMute(bool bMute, ref Guid EventContext);
        int GetMute(out bool pbMute);
    }

    static string FriendlyName(IMMDevice dev) {
        try {
            IPropertyStore store;
            dev.OpenPropertyStore(0, out store);
            PROPERTYKEY key = new PROPERTYKEY { fmtid = new Guid("a45c254e-df1c-4efd-8020-67d146a850e0"), pid = 14 };
            PROPVARIANT pv;
            store.GetValue(ref key, out pv);
            if (pv.vt == 31 && pv.p != IntPtr.Zero) return Marshal.PtrToStringUni(pv.p);
        } catch { }
        return "(unknown)";
    }

    public static string Repair(int targetVolumePercent) {
        float targetVolume = Math.Max(0, Math.Min(100, targetVolumePercent)) / 100.0f;
        var sb = new StringBuilder();
        var enumerator = (IMMDeviceEnumerator)(new MMDeviceEnumerator());
        IMMDevice defaultDev;
        string defaultId = "";
        if (enumerator.GetDefaultAudioEndpoint(EDataFlow.eRender, ERole.eMultimedia, out defaultDev) == 0) {
            defaultDev.GetId(out defaultId);
        }

        IMMDeviceCollection devices;
        int hr = enumerator.EnumAudioEndpoints(EDataFlow.eRender, DEVICE_STATE_ACTIVE, out devices);
        if (hr != 0) return "error=EnumAudioEndpoints failed 0x" + hr.ToString("X");

        uint count;
        devices.GetCount(out count);
        int repaired = 0;
        int seen = 0;

        for (uint i = 0; i < count; i++) {
            IMMDevice dev;
            devices.Item(i, out dev);
            string id;
            dev.GetId(out id);
            string deviceName = FriendlyName(dev);
            object managerObject;
            Guid managerGuid = IID_IAudioSessionManager2;
            if (dev.Activate(ref managerGuid, CLSCTX_ALL, IntPtr.Zero, out managerObject) != 0 || managerObject == null) continue;

            var manager = (IAudioSessionManager2)managerObject;
            IAudioSessionEnumerator sessionEnumerator;
            if (manager.GetSessionEnumerator(out sessionEnumerator) != 0 || sessionEnumerator == null) continue;

            int sessionCount;
            sessionEnumerator.GetCount(out sessionCount);
            for (int s = 0; s < sessionCount; s++) {
                IAudioSessionControl control;
                if (sessionEnumerator.GetSession(s, out control) != 0 || control == null) continue;

                uint pid = 0;
                string processName = "";
                try {
                    var control2 = (IAudioSessionControl2)control;
                    control2.GetProcessId(out pid);
                    if (pid != 0) processName = Process.GetProcessById((int)pid).ProcessName;
                } catch { }

                if (!String.Equals(processName, "chrome", StringComparison.OrdinalIgnoreCase)) continue;
                seen++;

                var simpleVolume = (ISimpleAudioVolume)control;
                float beforeVolume;
                bool beforeMute;
                simpleVolume.GetMasterVolume(out beforeVolume);
                simpleVolume.GetMute(out beforeMute);

                Guid eventContext = Guid.Empty;

                if (beforeMute) {
                    simpleVolume.SetMute(false, ref eventContext);
                }
                if (Math.Abs(beforeVolume - targetVolume) > 0.001f) {
                    simpleVolume.SetMasterVolume(targetVolume, ref eventContext);
                }

                float afterVolume;
                bool afterMute;
                simpleVolume.GetMasterVolume(out afterVolume);
                simpleVolume.GetMute(out afterMute);

                if (beforeMute != afterMute || Math.Abs(beforeVolume - afterVolume) > 0.001f) repaired++;

                sb.AppendLine(String.Format(
                    "device=\"{0}\" default={1} pid={2} beforeVolume={3} beforeMuted={4} afterVolume={5} afterMuted={6}",
                    deviceName,
                    id == defaultId ? "true" : "false",
                    pid,
                    Math.Round(beforeVolume * 100),
                    beforeMute,
                    Math.Round(afterVolume * 100),
                    afterMute
                ));
            }
        }

        if (seen == 0) sb.AppendLine("no live chrome audio sessions found");
        sb.AppendLine("seen=" + seen + " repaired=" + repaired);
        return sb.ToString();
    }
}
'@

if (-not ("ChromeAudioRepair" -as [type])) {
    Add-Type -TypeDefinition $coreAudioCode
}

$result = [ordered]@{
    ok = $true
    target_volume = $TargetVolume
    session_repair = $null
    policy_reset = $null
    scheduled_task = $null
}

$repairOutput = [ChromeAudioRepair]::Repair($TargetVolume)
$result.session_repair = $repairOutput
if ($repairOutput -match "repaired=([1-9][0-9]*)") {
    Write-AudioLog "Repaired Chrome audio session(s): $repairOutput"
}

if ($ResetPolicyStore -and -not $RepairSessionsOnly) {
    $base = "HKCU:\Software\Microsoft\Internet Explorer\LowRegistry\Audio\PolicyConfig\PropertyStore"
    $policyResult = [ordered]@{
        keys_removed = 0
        backup = $null
        removed_keys = @()
    }

    if (Test-Path $base) {
        $backupPath = Join-Path (Get-AudioTmpDir) ("policy-store-backup-{0}.reg" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
        & reg.exe export "HKCU\Software\Microsoft\Internet Explorer\LowRegistry\Audio\PolicyConfig\PropertyStore" $backupPath /y | Out-Null
        $policyResult.backup = $backupPath

        $chromeKeys = @(Get-ChildItem -LiteralPath $base -ErrorAction SilentlyContinue | Where-Object {
            $value = (Get-ItemProperty -LiteralPath $_.PSPath -Name "(default)" -ErrorAction SilentlyContinue)."(default)"
            $value -match "\\Program Files\\Google\\Chrome\\Application\\chrome\.exe" -and
            $value -notmatch "ms-playwright|chrome-headless-shell"
        })

        foreach ($key in $chromeKeys) {
            $policyResult.removed_keys += $key.PSChildName
            Remove-Item -LiteralPath $key.PSPath -Recurse -Force
        }
        $policyResult.keys_removed = $chromeKeys.Count
        if ($chromeKeys.Count -gt 0) {
            Write-AudioLog "Reset Chrome policy-store keys: $($policyResult.removed_keys -join ', ')"
        }
    }

    $result.policy_reset = $policyResult
}

if ($InstallScheduledTask -and -not $RepairSessionsOnly) {
    $taskName = "OASIS Chrome Audio Guard"
    $scriptPath = $PSCommandPath
    $taskRun = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -RepairSessionsOnly -TargetVolume $TargetVolume -Json"
    $taskOutput = & schtasks.exe /Create /TN $taskName /SC MINUTE /MO 5 /TR $taskRun /F 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to register scheduled task ${taskName}: $taskOutput"
    }
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
    Set-ScheduledTask -TaskName $taskName -Settings $settings | Out-Null
    $result.scheduled_task = [ordered]@{
        name = $taskName
        interval = "5 minutes"
        action = "repair Chrome audio sessions to $TargetVolume percent"
        raw = ($taskOutput -join "`n")
    }
    Write-AudioLog "Installed scheduled task: $taskName"
}

if ($Json) {
    $result | ConvertTo-Json -Depth 5
} else {
    $result.GetEnumerator() | ForEach-Object { "{0}: {1}" -f $_.Key, $_.Value }
}
