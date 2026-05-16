"""Weekly qualified-leads snapshot — Sat 22:00.

Pulls the lead pipeline once a week, filters to leads scoring >= MIN_SCORE,
ranks by MRR potential / urgency. Output is the Revenue Hunter agent's
"Prep Table" — instead of running opencli + scoring on every outreach session,
it cherry-picks from this pre-ranked list.

CLI:
  python scripts/snapshots/leads_snapshot.py
  python scripts/snapshots/leads_snapshot.py --min-score 50
  python scripts/snapshots/leads_snapshot.py --dry-run
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
TIMEOUT_SEC = 60
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
DEFAULT_MIN_SCORE = 60


def _call(args: list[str]) -> dict | list | None:
    # Phase 9.4 — suppress the console window the subprocess would
    # otherwise pop when triggered by the empire scheduler.
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


def _extract_leads(payload) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("leads", "items", "results", "rows"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
    return []


def _score(lead: dict) -> float:
    for key in ("score", "lead_score", "weighted_score"):
        v = lead.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def build_snapshot(min_score: float) -> dict:
    pipeline = _call(["scripts/lead_engine.py", "pipeline", "--json"])
    leads_raw = _call(["scripts/lead_engine.py", "list", "--json"])
    funnel = _call(["scripts/lead_engine.py", "funnel", "--json"])

    leads = _extract_leads(leads_raw)
    qualified = [lead for lead in leads if _score(lead) >= min_score]
    qualified.sort(key=_score, reverse=True)

    now = datetime.now(timezone.utc)
    iso_year, iso_week, _ = now.isocalendar()
    return {
        "snapshot_type": "leads_qualified",
        "ts": now.isoformat(),
        "iso_week": f"{iso_year}-W{iso_week:02d}",
        "min_score": min_score,
        "total_leads": len(leads),
        "qualified_count": len(qualified),
        "qualified_leads": qualified,
        "pipeline_summary": pipeline,
        "funnel_summary": funnel,
    }


def write_snapshot(payload: dict) -> tuple[Path, Path]:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    week = payload["iso_week"]
    dated = SNAPSHOT_DIR / f"leads_qualified_{week}.json"
    latest = SNAPSHOT_DIR / "latest_leads.json"
    blob = json.dumps(payload, indent=2, default=str)
    dated.write_text(blob, encoding="utf-8")
    latest.write_text(blob, encoding="utf-8")
    return dated, latest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build weekly qualified-leads snapshot.")
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_snapshot(args.min_score)
    if args.dry_run:
        print(json.dumps(payload, indent=2, default=str))
        return 0
    dated, latest = write_snapshot(payload)
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(f"wrote: {dated}")
        print(f"wrote: {latest}")
        print(f"qualified: {payload['qualified_count']} / {payload['total_leads']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
