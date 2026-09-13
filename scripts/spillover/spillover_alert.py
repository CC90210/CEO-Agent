#!/usr/bin/env python3
"""spillover_alert.py <kind> <message> - one Claude Spillover alert on two channels.

Called on each transition (entered fallback, fallback down, back on Claude) and by
omniroute_tool.py (fault injection).

  toast     <python_exe> <bea_repo>/scripts/windows_control.py notify, windowless
            (Windows only)
  telegram  notify(msg, category="system", dedup_key="claude-spillover-<kind>") from
            <bea_repo>/scripts/notify.py, imported with that scripts/ dir on
            sys.path. The dedup key is the kind, so repeats of one kind inside
            notify's window are suppressed - use a distinct kind per condition.

Config (HOME_DIR/config.json): bea_repo (default C:/Users/User/Business-Empire-Agent),
python_exe (default: this interpreter), proxy.alerts.toast and
proxy.alerts.telegram (default true).

A channel that fails writes a loud line to HOME_DIR/state/logs/alerts.log and to
stderr, and the script still exits 0: an alert helper must never take its caller
down. Exit 1 only on a usage error. Run it WITHOUT -S, because notify.py needs the
venv's packages. HOME_DIR is %LOCALAPPDATA%\\bravo-spillover (Windows) or
~/Library/Application Support/bravo-spillover (macOS); the env var
BRAVO_SPILLOVER_HOME overrides it (tests).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

KIND_RE = re.compile(r"^[a-z_]{1,40}$")
DEFAULT_REPO = "C:/Users/User/Business-Empire-Agent"
TITLE = "Claude Spillover"
MAX_MESSAGE = 1000
CREATE_NO_WINDOW = 0x08000000


def home_dir() -> str:
    override = os.environ.get("BRAVO_SPILLOVER_HOME")
    if override:
        return override
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "bravo-spillover")
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "bravo-spillover")


def load_config(home: str) -> dict:
    try:
        with open(os.path.join(home, "config.json"), encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"spillover_alert: config.json unreadable ({exc}); using defaults\n")
        return {}
    return data if isinstance(data, dict) else {}


def log_failure(home: str, kind: str, channel: str, error: str, message: str) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "level": "ERROR",
        "event": "ALERT DELIVERY FAILED",
        "kind": kind[:40],
        "channel": channel,
        "error": str(error)[:500],
        "message": message[:500],
    }
    sys.stderr.write(f"spillover_alert: ALERT DELIVERY FAILED ({channel}, {kind[:40]}): {str(error)[:300]}\n")
    try:
        log_dir = os.path.join(home, "state", "logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "alerts.log"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError as exc:
        sys.stderr.write(f"spillover_alert: could not write alerts.log either: {exc}\n")


def send_toast(repo: str, python_exe: str, message: str) -> str | None:
    script = os.path.join(repo, "scripts", "windows_control.py")
    if not os.path.isfile(script):
        return f"{script} not found"
    proc = subprocess.run(
        [python_exe, script, "notify", "--title", TITLE, "--message", message],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=60, cwd=repo, creationflags=CREATE_NO_WINDOW,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or ["no output"]
        return f"windows_control.py notify exit {proc.returncode}: {tail[0][:200]}"
    return None


def send_telegram(repo: str, kind: str, message: str) -> str | None:
    scripts = os.path.join(repo, "scripts")
    if not os.path.isfile(os.path.join(scripts, "notify.py")):
        return f"{scripts}/notify.py not found"
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import notify  # noqa: PLC0415 - the repo's scripts/notify.py

    sent = notify.notify(f"{TITLE} [{kind}]: {message}", category="system",
                         dedup_key=f"claude-spillover-{kind}")
    if sent or getattr(notify, "LAST_SUPPRESSED", False):  # suppressed = CC was already told
        return None
    reason = "refused the payload" if getattr(notify, "LAST_REFUSED", False) else \
        "returned False (disabled, muted, no route or transport failure)"
    return f"notify() {reason}"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    home = home_dir()
    if len(argv) != 2 or not KIND_RE.match(argv[0]) or not argv[1].strip():
        sys.stderr.write("usage: spillover_alert.py <kind> <message>   (kind: [a-z_]{1,40})\n")
        log_failure(home, argv[0] if argv else "?", "usage", "bad arguments", " ".join(argv))
        return 1
    kind, message = argv[0], argv[1].strip()[:MAX_MESSAGE]
    cfg = load_config(home)
    repo = cfg.get("bea_repo") or DEFAULT_REPO
    python_exe = cfg.get("python_exe") or sys.executable
    proxy = cfg.get("proxy") if isinstance(cfg.get("proxy"), dict) else {}
    alerts = proxy.get("alerts") if isinstance(proxy.get("alerts"), dict) else {}

    if alerts.get("toast", True) and os.name == "nt":
        try:
            err = send_toast(repo, python_exe, message)
        except Exception as exc:  # noqa: BLE001 - logged loudly below
            err = f"{type(exc).__name__}: {exc}"
        if err:
            log_failure(home, kind, "toast", err, message)
    if alerts.get("telegram", True):
        try:
            err = send_telegram(repo, kind, message)
        except BaseException as exc:  # noqa: BLE001 - notify.py can sys.exit; still log it
            err = f"{type(exc).__name__}: {exc}"
        if err:
            log_failure(home, kind, "telegram", err, message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
