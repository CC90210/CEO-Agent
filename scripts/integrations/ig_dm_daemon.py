#!/usr/bin/env python3
"""ig_dm_daemon.py — a dedicated loop for the Instagram DM setter.

WHY THIS EXISTS. The poller was a row in `cron_jobs`, run by scripts/scheduler.py.
That scheduler is a SINGLE-THREADED loop: it collects every due job, runs them
one after another, and only then sleeps. So the DM poller's real interval is not
its cron expression — it is

    (its own run) + (every other due job in the same cycle) + the loop's sleep

Measured on 2026-08-21 with the row set to `* * * * *`: the Inbound Email Sweep
alone took 84s, Training Corpus Ingest followed, and the observed gap between DM
polls was ~291s. A prospect who typed "Yo Wsp" waited 3m46s for an answer. No
cron expression fixes that, because the queue is the bottleneck, not the schedule.

Batch jobs are fine behind a queue. A conversation is not: the person is sitting
there watching for the typing indicator. So the setter gets its own process, and
its latency stops depending on how slow the email sweep was this cycle.

WHAT IT DOES. Every INTERVAL seconds it runs the poller as a SUBPROCESS —
deliberately, not as an import:
  * a crash or hang in one tick cannot kill the loop,
  * each tick picks up the current code without a restart,
  * the poller's own O_EXCL lock still guarantees one poll at a time, even
    against a manual run.

EXACTLY ONE RUNNER. Two live runners on this script answer every prospect twice,
which already happened once (2026-08-20). Enabling this daemon REQUIRES the
`Instagram DM Closer` cron row to be inactive; --check-conflict verifies that
against the live DB and refuses to start if the row is armed.

Usage:
    python scripts/integrations/ig_dm_daemon.py                 # run the loop
    python scripts/integrations/ig_dm_daemon.py --interval 20
    python scripts/integrations/ig_dm_daemon.py --once          # one tick, then exit
    python scripts/integrations/ig_dm_daemon.py --check-conflict # is the cron row armed?
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

CAPABILITY_META = {
    "category": "growth.inbound",
    "lifecycle": "active",
    "risk": "external_send",
    "triggers": ["instagram dm daemon", "run the dm setter", "ig setter loop"],
    "owner": "bravo",
    "project": "oasis",
    "bridge": {"visible": True},
}

POLLER = PROJECT_ROOT / "scripts" / "integrations" / "instagram_dm_poller.py"
CRON_ROW_NAME = "Instagram DM Closer"
OASIS_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"

# 20s: fast enough that a reply feels prompt, and cheap when nothing has changed —
# an idle tick is ONE HTTP GET, because every conversation gate runs before a
# model call is spent. Model turns are capped per tick by the poller itself.
DEFAULT_INTERVAL = 20

# A tick that outlives this is treated as hung and killed, so a stalled Zernio
# read cannot freeze the setter. The poller's own deadline is well inside it.
TICK_TIMEOUT = 300


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log(msg: str) -> None:
    print(f"[{_now()}] {msg}", flush=True)


def cron_row_is_armed() -> bool | None:
    """True/False, or None when the DB cannot be read.

    None is NOT treated as "safe to start". An unreadable registry means we
    cannot rule out a second live runner, and guessing wrong double-messages
    real prospects.
    """
    try:
        from lib.db_turso import get_db  # noqa: PLC0415

        rows = get_db().query(
            "select is_active from cron_jobs where tenant_id = ? and name = ?",
            (OASIS_TENANT_ID, CRON_ROW_NAME),
        )
    except Exception as exc:  # noqa: BLE001 — a broken check must be loud
        _log(f"ERROR: could not read the cron registry: {exc}")
        return None
    if not rows:
        return False
    return bool(int(rows[0].get("is_active") or 0))


def run_tick(extra_args: list[str]) -> int:
    """One poll, as a subprocess. Returns its exit code."""
    argv = [sys.executable, str(POLLER), "--live", "--json", *extra_args]
    try:
        proc = subprocess.run(
            argv, cwd=str(PROJECT_ROOT), capture_output=True, text=True,
            timeout=TICK_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        _log(f"ERROR: tick exceeded {TICK_TIMEOUT}s and was killed")
        return 124

    out = (proc.stdout or "").strip().splitlines()
    summary = out[-1] if out else ""
    if proc.returncode != 0:
        # "another poll is already running" is an EXPECTED, healthy outcome when a
        # manual run holds the lock — it is the guard working, not a fault.
        detail = (proc.stderr or proc.stdout or "").strip()
        if "another poll is already running" in detail:
            _log("skipped: another poll holds the lock")
            return 0
        _log(f"ERROR: tick exited {proc.returncode}: {detail[:300]}")
        return proc.returncode

    try:
        data = json.loads(summary)
    except (json.JSONDecodeError, ValueError):
        _log(f"tick ok: {summary[:160]}")
        return 0

    # Quiet ticks are the common case; say something only when work happened or
    # something went wrong. A log line per 20s would bury the events that matter.
    if data.get("replied") or data.get("errors") or data.get("handoffs"):
        _log(f"tick: {summary[:200]}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                   help=f"seconds between ticks (default {DEFAULT_INTERVAL})")
    p.add_argument("--once", action="store_true", help="one tick, then exit")
    p.add_argument("--check-conflict", action="store_true",
                   help="report whether the cron row is armed, then exit")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--max-model-calls", type=int, default=2)
    p.add_argument("--allow-cron-conflict", action="store_true",
                   help=argparse.SUPPRESS)  # escape hatch; never use in production
    args = p.parse_args()

    armed = cron_row_is_armed()
    if args.check_conflict:
        print(json.dumps({"cron_row": CRON_ROW_NAME, "is_active": armed,
                          "safe_to_run_daemon": armed is False}, indent=2))
        return 0 if armed is False else 1

    if armed is not False and not args.allow_cron_conflict:
        state = "ARMED" if armed else "UNREADABLE"
        _log(f"REFUSING TO START: the '{CRON_ROW_NAME}' cron row is {state}.")
        _log("Two live runners on one script answer every prospect twice — that")
        _log("already happened on 2026-08-20. Disable the cron row first.")
        return 1

    extra = ["--limit", str(args.limit), "--max-model-calls", str(args.max_model_calls)]

    if args.once:
        return run_tick(extra)

    _log(f"Instagram DM setter daemon up — every {args.interval}s, "
         f"{args.max_model_calls} model turn(s) per tick")
    while True:
        started = time.monotonic()
        try:
            run_tick(extra)
        except Exception as exc:  # noqa: BLE001 — the loop must outlive one bad tick
            import traceback
            traceback.print_exc()
            _log(f"ERROR: tick raised {exc}")
        # Sleep the REMAINDER, so the period is the interval rather than
        # interval + work — the additive-sleep mistake scheduler.py made.
        time.sleep(max(1.0, args.interval - (time.monotonic() - started)))


if __name__ == "__main__":
    sys.exit(main())
