"""codex_review.py — run a Codex review AND record its verdict (telemetry loop).

Before 2026-07-10, RULE 8 Codex reviews ran via codex-companion.mjs directly:
the review text reached CC but the VERDICT evaporated — task_outcomes.py had
zero writers and first-pass success was permanently null. This wrapper closes
that loop without touching the shared global plugin (~/.claude/codex-plugin is
cross-workspace substrate — Rule 10):

    run codex-companion (review | adversarial-review) --wait
      → print the review VERBATIM (RULE 8: never paraphrase Codex)
      → parse the verdict line → task_outcomes.py record --source codex

Verdict mapping (conservative):
    "no-ship" / "No-ship" anywhere            → reject
    "needs-attention"                          → warn
    "no correctness issues" / no findings      → approve
    unparseable                                → warn (flag, don't flatter)

CLI:
  python scripts/core/codex_review.py review [--session <slug>]
  python scripts/core/codex_review.py adversarial-review "<focus>" [--session <slug>]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPANION = Path.home() / ".claude" / "codex-plugin" / "scripts" / "codex-companion.mjs"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def classify(review_text: str) -> tuple[str, str]:
    """(verdict, reason) from the review body."""
    low = review_text.lower()
    if "no-ship" in low:
        return "reject", "codex marked no-ship"
    if "needs-attention" in low:
        n_high = len(re.findall(r"\[high\]", low))
        n_med = len(re.findall(r"\[medium\]", low))
        return "warn", f"needs-attention ({n_high} high, {n_med} medium)"
    if "no correctness issues" in low or "no issues" in low:
        return "approve", "codex found no issues"
    return "warn", "verdict unparseable — review manually"


def record(session: str, verdict: str, reason: str) -> bool:
    try:
        r = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "core" / "task_outcomes.py"),
             "record", "--session", session, "--verdict", verdict,
             "--source", "codex", "--detail", reason[:200]],
            capture_output=True, text=True, timeout=30,
        )
        return r.returncode == 0
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Codex review with verdict telemetry")
    p.add_argument("mode", choices=["review", "adversarial-review"])
    p.add_argument("focus", nargs="?", default=None, help="focus prompt (adversarial-review)")
    p.add_argument("--session", default=None, help="task slug for the telemetry row")
    args = p.parse_args(argv)

    if not COMPANION.exists():
        print(f"ERROR: codex-companion not found at {COMPANION}", file=sys.stderr)
        return 2

    cmd = ["node", str(COMPANION), args.mode]
    if args.mode == "adversarial-review" and args.focus:
        cmd.append(args.focus)
    cmd.append("--wait")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1200,
                              encoding="utf-8", errors="replace", cwd=str(PROJECT_ROOT))
    except subprocess.TimeoutExpired:
        print("ERROR: codex review timed out (20 min)", file=sys.stderr)
        return 3

    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    # RULE 8: present Codex verbatim — the wrapper adds telemetry, never edits.
    print(out)

    verdict, reason = classify(out)
    session = args.session or f"codex-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M')}"
    recorded = record(session, verdict, reason)
    print(f"\n[telemetry] verdict={verdict} ({reason}) — "
          f"{'recorded' if recorded else 'RECORD FAILED'} as session={session}")
    return 0 if proc.returncode == 0 else proc.returncode


if __name__ == "__main__":
    sys.exit(main())
