"""Daily client-health alerts snapshot — 07:00.

Pulls client_health.py alerts (RED + ORANGE only), enriches with risk factors
and suggested next action. Chief-of-Staff agent reads this instead of running
the full health report on every check-in.

CLI:
  python scripts/snapshots/client_alerts_snapshot.py
  python scripts/snapshots/client_alerts_snapshot.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = PROJECT_ROOT / "state" / "snapshots"
TIMEOUT_SEC = 30


def _call(args: list[str]) -> dict | list | None:
    try:
        result = subprocess.run(
            [sys.executable, *args],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
            cwd=str(PROJECT_ROOT),
            encoding="utf-8",
            errors="replace",
            creationflags=WINDOWLESS_FLAGS,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"_error": str(e)}
    if result.returncode != 0:
        return {"_error": result.stderr.strip()[:500] or "non-zero exit"}
    raw = result.stdout.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"_raw": raw[:500]}


def build_snapshot() -> dict:
    alerts = _call(["scripts/client_health.py", "alerts", "--json"])
    report = _call(["scripts/client_health.py", "report", "--json"])

    now = datetime.now(timezone.utc)
    return {
        "snapshot_type": "client_alerts",
        "ts": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "alerts": alerts,
        "full_report_summary": _summarize(report),
    }


def _summarize(report) -> dict:
    if not isinstance(report, dict):
        return {}
    clients = report.get("clients") or report.get("results") or []
    if not isinstance(clients, list):
        return {}
    buckets = {"GREEN": 0, "YELLOW": 0, "ORANGE": 0, "RED": 0, "UNKNOWN": 0}
    for c in clients:
        status = (c.get("status") or c.get("health") or "UNKNOWN").upper()
        buckets[status if status in buckets else "UNKNOWN"] += 1
    return {"total": len(clients), "by_status": buckets}


def write_snapshot(payload: dict) -> tuple[Path, Path]:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = payload["date"]
    dated = SNAPSHOT_DIR / f"client_alerts_{date_str}.json"
    latest = SNAPSHOT_DIR / "latest_client_alerts.json"
    blob = json.dumps(payload, indent=2, default=str)
    dated.write_text(blob, encoding="utf-8")
    latest.write_text(blob, encoding="utf-8")
    return dated, latest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build daily client-health alerts snapshot.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_snapshot()
    if args.dry_run:
        print(json.dumps(payload, indent=2, default=str))
        return 0
    dated, latest = write_snapshot(payload)
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(f"wrote: {dated}")
        print(f"wrote: {latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
