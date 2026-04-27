# Browser Harness Windows Patch

The installed Browser Harness checkout at `C:\Users\User\APPS\browser-harness` has a local Windows compatibility patch.

## Why

Upstream Browser Harness currently assumes Unix sockets. On this Windows workstation, `socket.AF_UNIX` is unavailable in the Python environment used by the installed harness, so upstream `browser-harness --doctor` crashed before diagnostics could run.

## Local Changes

Patched files in the editable checkout:

- `admin.py`
- `daemon.py`
- `helpers.py`

Repo-preserved patch:

- `browser/patches/browser-harness-windows.patch`

Patch behavior:

- If Unix sockets are available, keep upstream behavior.
- If Unix sockets are unavailable, use deterministic localhost TCP based on `BU_NAME`.
- Move cache/pid/log paths to the platform temp directory on Windows.
- Make screenshot default output use the platform temp directory.
- Improve Windows setup by opening `chrome://inspect/#remote-debugging` through Chrome or Edge when possible.

## Verification

Run:

```powershell
python scripts/browser_harness_doctor.py
```

Expected current result:

- install: OK
- attach: PENDING until CC enables Chrome/Edge remote debugging once

## Upgrade Note

Because this is an editable install, `browser-harness --update -y` may refuse while the checkout is dirty. If upstream adds native Windows support later, compare before removing the local patch.
