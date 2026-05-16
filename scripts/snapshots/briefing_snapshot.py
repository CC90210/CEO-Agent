"""Daily briefing snapshot — deterministic Python aggregation.

Runs at 06:00 daily (via n8n cron). Calls existing engines, merges into a
single JSON file at state/snapshots/briefing_YYYY-MM-DD.json plus a
state/snapshots/latest_briefing.json copy. This is the "Prep Table" layer
from brain/AGENTIC_OS_REFERENCE.md §3 — pre-aggregate so agents spend their
context on synthesis, not retrieval.

CLI:
  python scripts/snapshots/briefing_snapshot.py             # write snapshot
  python scripts/snapshots/briefing_snapshot.py --dry-run   # print, don't write
  python scripts/snapshots/briefing_snapshot.py --json      # stdout JSON

Read-path: skills/ceo-briefing/SKILL.md, skills/ceo-dashboard/SKILL.md,
agents/chief-of-staff.md should prefer the snapshot when latest is <24h old.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = PROJECT_ROOT / "state" / "snapshots"
TIMEOUT_SEC = 30
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


def _call(args: list[str]) -> dict | list | None:
    # Phase 9.4 — Windows-only flag to suppress the console window the
    # subprocess would otherwise pop. Imported lazily so the snapshot
    # script still runs on Mac/Linux where the constant isn't defined.
    try:
        from _subprocess_helpers import WINDOWLESS_FLAGS  # type: ignore
    except ImportError:
        WINDOWLESS_FLAGS = 0x08000000 if sys.platform == "win32" else 0
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
    mrr = _call(["scripts/revenue_engine.py", "mrr", "--json"])
    goal = _call(["scripts/revenue_engine.py", "goal", "--json"])
    pipeline = _call(["scripts/lead_engine.py", "pipeline", "--json"])
    followups = _call(["scripts/lead_engine.py", "followups", "--json"])
    health_alerts = _call(["scripts/client_health.py", "alerts", "--json"])
    briefing = _call(["scripts/ceo_dashboard.py", "briefing", "--json"])

    return {
        "snapshot_type": "briefing",
        "ts": datetime.now(timezone.utc).isoformat(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "revenue": {"mrr": mrr, "goal": goal},
        "pipeline": pipeline,
        "followups_due": followups,
        "client_health_alerts": health_alerts,
        "briefing": briefing,
    }


def write_snapshot(payload: dict) -> tuple[Path, Path]:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = payload["date"]
    dated = SNAPSHOT_DIR / f"briefing_{date_str}.json"
    latest = SNAPSHOT_DIR / "latest_briefing.json"
    blob = json.dumps(payload, indent=2, default=str)
    dated.write_text(blob, encoding="utf-8")
    latest.write_text(blob, encoding="utf-8")
    return dated, latest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build daily CEO briefing snapshot.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout in addition to writing files")
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
