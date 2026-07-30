---
tags: [sop, windows, avg, antivirus, tls, networking, reliability, operator-action]
last_updated: 2026-07-30
freshness_threshold_days: 180
verified: 2026-07-30
---

# SOP — stop AVG breaking the agent fleet's HTTPS

**Operator action. ~2 minutes. Requires the AVG UI; there is no CLI for this.**

## Why this exists

AVG intercepts TLS on this machine to scan encrypted traffic. Doing that means
terminating the agent's connection and re-originating it, and AVG's proxy is not
reliable enough to be invisible. Two distinct failure modes, both measured here:

| Symptom | What AVG did | Where it was fixed |
|---|---|---|
| `CERTIFICATE_VERIFY_FAILED` | Presented its own CA, which `certifi` doesn't trust | `lib/tls_trust.py` — uses the OS trust store |
| `PermissionError` on `SSLKEYLOGFILE` | Injected `\\.\avgMonFltProxy\<handle>`; the handle goes stale and CPython opens it in `ssl.create_default_context()` | `lib/tls_trust.py::neutralize_keylog()` |
| `[WinError 10054] connection forcibly closed` · `SSL: UNEXPECTED_EOF` · `Server disconnected` | Killed a live socket mid-request | `lib/db_resilience.py` — connection retries |

Measured 2026-07-30 across the scheduler logs: **92 check-cycle failures**, 58 of
them `WinError 10054`. Peak days were 07-21 (34) and 07-22 (44).

**The code fixes make the fleet survive this. Only the exclusion stops it.**
Retries turn a hard failure into a slower success; they cost latency on every
occurrence and they cannot help a connection that dies twice in a row.

## What to exclude

```
C:\Users\User\Business-Empire-Agent\.venv\Scripts\python.exe
C:\Users\User\Business-Empire-Agent\.venv\Scripts\pythonw.exe
```

`pythonw.exe` is the one that matters most — every PM2 daemon and every cron
child runs under it. Excluding the whole `Business-Empire-Agent` folder is also
reasonable and saves repeating this after a venv rebuild.

## Steps (AVG Antivirus 26.6.11052.1050, verified 2026-07-30)

1. Open **AVG AntiVirus** → **☰ Menu** → **Settings**.
2. **General → Exceptions → Add Exception.**
3. Paste the folder `C:\Users\User\Business-Empire-Agent` (or add the two `.exe`
   paths above individually), then **Add Exception**.
4. Go to **Basic Protection → Web Shield**.
5. Turn **OFF "Enable HTTPS scanning"**.

Step 5 is the one that actually stops the interception; the exclusion in step 3
covers file-level scanning. Do both.

> AVG moves menu items between releases. If the labels differ, you are looking
> for (a) an **Exceptions** / **Exclusions** list, and (b) a **Web Shield** or
> **Core Shields** toggle mentioning **HTTPS** or **encrypted connections**.
> Do not disable Web Shield entirely — only its HTTPS scanning.

## Verify it worked

```bash
python scripts/harness_eval.py          # expect ALL GREEN
```

Then check the failure rate stops climbing:

```powershell
Get-ChildItem tmp\pm2-scheduler-out*.log |
  ForEach-Object { (Get-Content $_ | Select-String "WinError 10054|UNEXPECTED_EOF").Count } |
  Measure-Object -Sum
```

Re-run after a day. A working exclusion means the count stops growing. It will
not reset — the historical lines stay in the logs.

## Do NOT script this

AVG self-protects its configuration; its registry keys under
`HKLM:\SOFTWARE\AVG\Antivirus` are not a supported configuration surface, and
writing them is a good way to break antivirus rather than configure it. The
install ships no exclusion CLI — `C:\Program Files\AVG\Antivirus\` contains only
`AvEmUpdate.exe` and `sched.exe`. The UI is the interface.

## Related

In-repo: [[docs/onboarding/FLEET_ALERT_DISCIPLINE_2026-07-30]] ·
[[brain/EXECUTION_RULES]] · `scripts/lib/tls_trust.py` ·
`scripts/lib/db_resilience.py`

The three matching agent-memory notes (`pattern_av_tls_mitm_breaks_certifi`,
`pattern_av_sslkeylogfile_poisons_pm2_children`,
`pattern_verify_the_running_daemon_not_the_repo`) live in the operator's private
memory directory, outside this vault — named here deliberately as plain text,
because a wiki-link to them can never resolve and would show up forever as a
broken edge in the graph.
