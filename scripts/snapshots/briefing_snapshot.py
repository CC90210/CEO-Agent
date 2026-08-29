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

from concurrent.futures import ThreadPoolExecutor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = PROJECT_ROOT / "state" / "snapshots"
# Must remain above ceo_dashboard.SUBENGINE_TIMEOUT_SEC and below
# daily_brief.SNAPSHOT_REGEN_TIMEOUT_SEC. See the timeout-contract regression
# test in test_harness_reporting_integrity.py.
# RAISED 65 -> 90 (2026-08-28). Measured, not guessed: the generator's whole
# wall came in at 64s, 68s and 70s across three runs, which means the slowest
# engine was landing within a few seconds of the 65s per-engine cap. Engines
# that cross it are recorded as {"_error": ...} and the brief then renders
# "⚠️ unavailable" — which is exactly what CC saw for `Client health` and
# `Follow-ups due` while the underlying data was fine (client_health_alerts read
# "All clients are GREEN or YELLOW").
#
# This is the timeout-below-measured-duration trap: a cap at the measured
# duration manufactures failures on ordinary variance. Caps go above p95, and on
# this machine every subprocess pays AV-inflated spawn cost (a bare
# `python -c pass` measures 3.7s), so seven parallel engines contend far harder
# than the "wall-clock ≈ the slowest engine" note below assumes.
#
# Kept coherent with the callers, which were raised in the same commit:
#   engines 90  ->  daily_brief regen cap 110  ->  scheduler daily_brief 200
TIMEOUT_SEC = 90
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402


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
        # RECORD THE CODE, NOT JUST "non-zero exit". An abnormal Windows
        # termination arrives with empty stdout AND empty stderr AND no
        # traceback, so the old string was the same for a crashed child, a
        # killed child and a child that simply printed nothing. The brief's
        # "Client health: unavailable" was re-diagnosed as a timeout three
        # separate times because of it — the real cause was a 43-second
        # per-connect schema walk, which the returncode would have ruled out
        # in one reading.
        rc = result.returncode
        detail = result.stderr.strip()[:500]
        if not detail:
            # Windows NTSTATUS codes arrive as large unsigned values; anything
            # above 0xC0000000 is a crash, not an exit status the child chose.
            abnormal = (rc & 0xFFFFFFFF) > 0xC0000000
            detail = (f"abnormal termination 0x{rc & 0xFFFFFFFF:08X}"
                      if abnormal else f"exit {rc}, no output")
        return {"_error": detail, "_returncode": rc}
    raw = result.stdout.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"_raw": raw[:500]}


def build_snapshot() -> dict:
    calls = {
        "mrr": ["scripts/revenue_engine.py", "--json", "mrr"],
        "goal": ["scripts/revenue_engine.py", "--json", "goal"],
        "pipeline": ["scripts/lead_engine.py", "--json", "pipeline"],
        "followups": ["scripts/lead_engine.py", "--json", "followups"],
        # Sibling agents (Maven, Atlas, APEX, Codex) post here when they need
        # Bravo. Until now the ONLY things that read it were the session-start
        # hook — which needs a human to open a session — and the Sunday digest.
        # So a HIGH message from another agent reached CC weekly at best, and
        # seven were sitting unread. An inbox nothing reads on a schedule is a
        # channel that exists on paper.
        "agent_inbox": ["scripts/core/agent_inbox.py", "--json", "list", "--to", "bravo"],
        "health_alerts": ["scripts/client_health.py", "--json", "alerts"],
        "health_full": ["scripts/client_health.py", "--json", "report"],
        "briefing": ["scripts/ceo_dashboard.py", "--json", "briefing"],
    }

    results: dict[str, dict | list | None] = {}
    # One worker per call: with 7 tasks through 4 workers the run took two
    # batches (~74s), which overran daily_brief's 60s regen budget and left CC
    # reading a snapshot stamped `_stale: true`. These are subprocesses blocking
    # on Turso/Stripe I/O, not CPU work, so widening costs nothing and makes
    # wall-clock ≈ the single slowest engine (~40s).
    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        futures = {key: executor.submit(_call, cmd) for key, cmd in calls.items()}
        for key, future in futures.items():
            results[key] = future.result()

    mrr = results["mrr"]
    goal = results["goal"]
    pipeline = results["pipeline"]
    followups = results["followups"]
    health_alerts = results["health_alerts"]
    health_full = results["health_full"]
    briefing = results["briefing"]

    monitored_count = 0
    if isinstance(health_full, list):
        monitored_count = len(health_full)
    elif isinstance(health_full, dict) and isinstance(health_full.get("clients"), list):
        monitored_count = len(health_full["clients"])
    if isinstance(briefing, dict) and isinstance(briefing.get("client_health"), dict):
        briefing["client_health"]["monitored"] = monitored_count
        if monitored_count == 0:
            briefing["client_health"]["_note"] = (
                "NO CLIENTS MONITORED — health engine has 0 rows tagged "
                "status='client'. CC's Stripe-paying customers are not "
                "visible here. Surface this as a CRM data-hygiene gap, "
                "do NOT report 'all clients green'."
            )

    return {
        "snapshot_type": "briefing",
        "ts": datetime.now(timezone.utc).isoformat(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "revenue": {"mrr": mrr, "goal": goal},
        "pipeline": pipeline,
        "followups_due": followups,
        "client_health_alerts": health_alerts,
        # Listed explicitly, like every other key: this function returns a
        # hand-built dict, so an engine added to `calls` and not added HERE runs
        # on every snapshot and is thrown away. Caught by rendering the brief and
        # finding the section absent, not by reading the code.
        "agent_inbox": results["agent_inbox"],
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
