"""V6 Apex Phase 2 — local consumer for dashboard-driven override decisions.

Polls the Supabase `exec_overrides` mirror for rows where the operator has
clicked Approve / Deny in the dashboard but the local SQLite hasn't been
updated yet (consumer_synced_at IS NULL). For each row:

  - decision='approve' → state_manager.approve_override_request(request_id)
                          → SQLite row becomes status='approved' + HMAC-signed
                          → mirror back to Supabase via mark_synced
                          → exec_guard at next attempt sees the approval

  - decision='deny'    → state_manager.deny_override_request(request_id)
                          → mirror back to Supabase

Run as a daemon (PM2 / systemd) on CC's machine:

    python scripts/exec_override_consumer.py loop                # default 5s poll
    python scripts/exec_override_consumer.py loop --interval 10
    python scripts/exec_override_consumer.py once                # single tick

Single-machine safety: this daemon is read-from-Supabase, write-to-local-SQLite.
Two copies running on different machines would each try to apply the same
intent — but the bridge_lock module handles agent-singleton enforcement, and
state_manager.approve_override_request is idempotent on the SQLite side
(second call on an already-approved row raises ValueError, which we catch
and treat as 'already applied — just mark synced').
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import state_manager                                  # noqa: E402
from lib import exec_override_mirror                  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _apply_one(intent: dict) -> tuple[bool, str]:
    """Apply one dashboard intent to local SQLite + mark synced in Supabase.

    Returns (success, message). Never raises — daemons should keep ticking.
    """
    request_id = intent["request_id"]
    decision = intent["dashboard_decision"]

    if decision == "approve":
        try:
            row = state_manager.approve_override_request(
                request_id,
                approved_by="dashboard",
                approved_reason=intent.get("dashboard_reason"),
            )
        except ValueError as e:
            # Already approved / expired / consumed locally — mark synced to
            # stop the poller from retrying forever.
            exec_override_mirror.mark_synced(
                request_id, final_status="approved",
            )
            return True, f"local-already-handled: {e}"
        ok = exec_override_mirror.mark_synced(
            request_id,
            final_status="approved",
            hmac_sig=row.get("hmac_sig"),
            approved_at=row.get("approved_at"),
            approved_by=row.get("approved_by"),
        )
        return ok, "approved + synced" if ok else "approved local, mirror-sync failed"

    if decision == "deny":
        applied = state_manager.deny_override_request(
            request_id, reason=intent.get("dashboard_reason"),
        )
        ok = exec_override_mirror.mark_synced(
            request_id, final_status="denied",
        )
        if not applied:
            return ok, "denied (already in terminal state locally)"
        return ok, "denied + synced" if ok else "denied local, mirror-sync failed"

    return False, f"unknown decision: {decision}"


def tick(verbose: bool = False) -> int:
    """One poll cycle. Returns number of intents applied."""
    intents = exec_override_mirror.fetch_pending_intents(limit=25)
    if not intents:
        if verbose:
            print(".", end="", flush=True)
        return 0

    applied = 0
    for intent in intents:
        ok, msg = _apply_one(intent)
        if ok:
            applied += 1
        if verbose or not ok:
            tag = "OK" if ok else "ERR"
            print(f"\n  [{tag}] {intent['request_id']} {intent['dashboard_decision']} — {msg}",
                  flush=True)
    return applied


def loop(interval: int, verbose: bool) -> int:
    """Run forever (Ctrl-C to stop)."""
    print(f"[exec_override_consumer] polling every {interval}s — Ctrl-C to stop", flush=True)
    total = 0
    try:
        while True:
            try:
                applied = tick(verbose=verbose)
                total += applied
                if applied and not verbose:
                    print(f"\n[{applied}] intent(s) applied (running total: {total})",
                          flush=True)
            except KeyboardInterrupt:
                raise
            except Exception as e:  # noqa: BLE001
                print(f"\n[tick error] {e}", flush=True)
            time.sleep(max(1, interval))
    except KeyboardInterrupt:
        print(f"\n[exec_override_consumer] stopped. {total} intent(s) applied total.")
        return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V6 dashboard override decision poller")
    sub = p.add_subparsers(dest="command", required=True)

    once = sub.add_parser("once", help="Apply pending intents once and exit")
    once.add_argument("--verbose", action="store_true")
    once.set_defaults(func=lambda a: 0 if tick(verbose=a.verbose) >= 0 else 1)

    lp = sub.add_parser("loop", help="Poll continuously")
    lp.add_argument("--interval", type=int, default=5,
                    help="seconds between polls (default: 5)")
    lp.add_argument("--verbose", action="store_true")
    lp.set_defaults(func=lambda a: loop(a.interval, a.verbose))

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
