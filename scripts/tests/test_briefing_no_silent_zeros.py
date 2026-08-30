"""Regression gate: the CEO briefing must never report silent zeros.

The bug this locks out (found 2026-08-13): `_build_north_star` called
lead_engine.py and client_health.py with timeout=20 while both genuinely take
~35s. Every run raised TimeoutExpired, which `except Exception: pass` swallowed,
so the briefing reported `active_leads: 0` and `client_health.avg_score: 0.0`
with a straight face while the CRM held 11 active leads. A plausible fake zero
is worse than an error — this test fails if the briefing's pipeline disagrees
with lead_engine, which is the source of truth.

Run:  python scripts/tests/test_briefing_no_silent_zeros.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WINDOWLESS = 0x08000000 if sys.platform == "win32" else 0
# Generous: these engines legitimately take ~35s each against live Turso.
CALL_TIMEOUT = 180


def _run_json(rel: str, *args: str, allow_empty: bool = False):
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / rel), *args],
        capture_output=True, text=True, timeout=CALL_TIMEOUT,
        cwd=str(PROJECT_ROOT), creationflags=WINDOWLESS,
        encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise AssertionError(f"{rel} {' '.join(args)} exited {proc.returncode}: {proc.stderr[-400:]}")
    start = proc.stdout.find("{") if "{" in proc.stdout else proc.stdout.find("[")
    if start < 0:
        # Some engines print a human line instead of JSON when the result set is
        # genuinely empty (client_health: "No clients found ..."). That is a real
        # empty, not a swallowed failure — callers opt in with allow_empty.
        if allow_empty:
            return None
        raise AssertionError(f"{rel} produced no JSON: {proc.stdout[:200]!r}")
    return json.loads(proc.stdout[start:])


def main() -> int:
    failures: list[str] = []

    briefing = _run_json("scripts/ceo_dashboard.py", "--json", "briefing")
    pipeline = _run_json("scripts/lead_engine.py", "--json", "pipeline")

    # Source of truth: lead_engine's own stage counts.
    ACTIVE = {"new", "contacted", "qualified", "proposal"}
    expected_active = sum(
        int((v or {}).get("count", 0) or 0)
        for k, v in pipeline.items()
        if isinstance(v, dict) and k in ACTIVE
    )
    got_active = int(briefing.get("pipeline", {}).get("active_leads", 0) or 0)

    if got_active != expected_active:
        failures.append(
            f"briefing.pipeline.active_leads={got_active} but lead_engine reports "
            f"{expected_active} active leads — the briefing is swallowing a failure"
        )

    # A degraded sub-engine must announce itself rather than pass off a zero.
    errors = briefing.get("_errors") or {}
    if got_active == 0 and expected_active == 0 and errors:
        print(f"[note] briefing reported degraded sources: {errors}")

    health = briefing.get("client_health", {})
    if health.get("avg_score", 0) == 0 and "client_health" not in errors:
        # Only a failure if client_health actually has clients to score. With
        # zero clients on the books, avg_score=0.0 is the honest answer.
        clients = _run_json("scripts/client_health.py", "--json", "report", allow_empty=True)
        if isinstance(clients, list) and clients:
            failures.append(
                f"briefing.client_health.avg_score=0.0 but client_health.py returned "
                f"{len(clients)} client(s) and reported no error — silent zero"
            )

    for f in failures:
        print(f"FAIL: {f}")
    if failures:
        return 1
    print(f"PASS: briefing agrees with lead_engine ({expected_active} active leads), "
          f"client_health avg={health.get('avg_score')}, no silent zeros")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
