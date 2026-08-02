"""
Cross-agent domain ping — CC directive 2026-08-01.

When Bravo does work in a peer's domain (marketing → Maven, finance → Atlas,
ops → everyone), a structured event must land on the shared channel so the
peer resumes with full awareness of what Bravo changed. DB-only — no
Telegram/email (outbound still goes through send_gateway when needed).

Writes two rows:
  1. `agent_activity` row (agent=cc-agent, status=done, task="[domain] ...",
     detail=summary, files=...) — visible to peers polling `peers`/`recent`.
  2. `agent_events` publish (type `domain.ping`, target=peer agent) via
     event_bus — falls back to the offline queue if Supabase is down.

Usage:
  python scripts/core/cross_agent_ping.py --domain marketing \
      --summary "Rebuilt funnel CTA on oasis site" \
      --files apps/web/funnel.tsx,brain/STATE.md

Exit codes: 0 = row landed in agent_activity; 1 = write failed (loud).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
for _p in (_SCRIPTS, _SCRIPTS / "core", _SCRIPTS / "integrations"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import agent_activity  # noqa: E402
import event_bus  # noqa: E402

# Force UTF-8 stdout/stderr on Windows (same pattern as state_sync.py).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

# Domain -> event-bus target agent (None = broadcast to all agents).
DOMAIN_TARGETS = {"marketing": "maven", "finance": "atlas", "ops": None}


def ping(domain: str, summary: str, files: list[str] | None = None) -> dict:
    """Post the domain ping to agent_activity + the event bus. Raises on
    agent_activity failure — the caller is responsible for failing loud."""
    target = DOMAIN_TARGETS[domain]
    task = f"[{domain}] domain ping"

    act = agent_activity.post(status="done", task=task, files=files, detail=summary)

    evt = event_bus.publish(
        event_type="domain.ping",
        payload={
            "domain": domain,
            "summary": summary,
            "files": files or [],
            "actor": "bravo",
        },
        source="bravo",
        target=target,
    )
    return {"activity_row": act.get("row"), "activity_line": act["line"], "event": evt}


def main() -> int:
    p = argparse.ArgumentParser(
        description="Post a cross-agent domain ping so Maven/Atlas resume with "
                    "awareness of what Bravo changed in their domain (DB bus only)."
    )
    p.add_argument("--domain", required=True, choices=list(DOMAIN_TARGETS),
                   help="Whose domain the work touched: marketing→Maven, finance→Atlas, ops→broadcast")
    p.add_argument("--summary", required=True, help="What Bravo changed (becomes the row detail)")
    p.add_argument("--files", help="Comma-separated files touched")
    args = p.parse_args()

    files = [f.strip() for f in args.files.split(",") if f.strip()] if args.files else None

    try:
        res = ping(args.domain, args.summary, files)
    except Exception as e:  # noqa: BLE001
        print(f"[cross_agent_ping] FAILED to write agent_activity row: {e}", file=sys.stderr)
        return 1

    evt = res["event"]
    evt_note = evt["status"]
    if evt["status"] == "offline":
        evt_note = f"offline ({evt['reason'][:120]})"
    print(f"[cross_agent_ping] {res['activity_line']} · event_bus: {evt_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
