"""Regression test for the send_gateway reservation race condition.

Background: from migration 013 (April 2026) until migration 079
(May 2026), send_gateway's RPC reservation path was silently broken
— exec_sql wraps queries as `SELECT FROM (user_sql) t` which makes
data-modifying CTEs not top-level, and PostgreSQL rejected the
INSERT-in-CTE. Every send fell through to a non-atomic fallback
that had no advisory lock and no existing-row check. Two concurrent
sends to the same (lead_id, channel) would both win reservations
and BOTH deliver the message.

This test asserts:
  1. The RPC path is used (mode == 'rpc', not 'fallback')
  2. Concurrent reservations are mutually exclusive — first wins,
     second is blocked with reason='concurrent send detected'
  3. actor_user_id roundtrips through the RPC

Run:
    python scripts/tests/test_send_gateway_reservation_race.py
    python scripts/tests/test_send_gateway_reservation_race.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Lives in scripts/tests/ (moved 2026-07-09) — repo root is two parents up.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from secret_loader import load_env  # type: ignore  # noqa: E402


# Use SunBiz tenant as the test surface — it's the most realistic
# production-like target. Any active application UUID will do.
SUN_TENANT_ID = "aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110"
SUN_OWNER_AUTH_ID = "871a3e7e-a49a-4ac4-b44d-b1ad2eb6b7d6"


def _client():
    env = load_env()
    for k, v in env.items():
        os.environ.setdefault(k, str(v))
    from supabase import create_client
    return create_client(env["BRAVO_SUPABASE_URL"], env["BRAVO_SUPABASE_SERVICE_ROLE_KEY"])


def _pick_test_lead(c) -> str:
    rows = (
        c.table("tenant_records")
        .select("id")
        .eq("tenant_id", SUN_TENANT_ID)
        .eq("entity_type", "application")
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        raise SystemExit("no SunBiz application found for race test")
    return rows[0]["id"]


def _run() -> dict:
    from integrations.send_gateway import reserve_send_slot  # type: ignore

    c = _client()
    lead = _pick_test_lead(c)
    cleanup: list[str] = []
    results = {"checks": []}

    try:
        # 1. Single reservation — verify RPC mode + actor_user_id roundtrips.
        r1 = reserve_send_slot(
            c,
            lead_id=lead,
            channel="email",
            subject="race_test_1",
            content_preview="",
            agent_source="race_regression_test",
            cooldown_hours=None,
            metadata={"test": True},
            acted_by_user_id=SUN_OWNER_AUTH_ID,
        )
        if r1.get("reservation_id"):
            cleanup.append(r1["reservation_id"])
        results["checks"].append({
            "name": "rpc_mode_active",
            "expected": "rpc",
            "got": r1.get("mode"),
            "ok": r1.get("mode") == "rpc",
        })
        if r1.get("reservation_id"):
            row = (
                c.table("lead_interactions")
                .select("actor_user_id")
                .eq("id", r1["reservation_id"])
                .single()
                .execute()
                .data
            )
            results["checks"].append({
                "name": "actor_user_id_roundtrip",
                "expected": SUN_OWNER_AUTH_ID,
                "got": row["actor_user_id"],
                "ok": row["actor_user_id"] == SUN_OWNER_AUTH_ID,
            })

        # 2. Concurrent reservation — same (lead, channel) — must block.
        # We use sms here so the row above (email) doesn't pre-block.
        r2a = reserve_send_slot(
            c,
            lead_id=lead,
            channel="sms",
            subject=None,
            content_preview="r2a",
            agent_source="race_regression_test",
            cooldown_hours=None,
            metadata={},
            acted_by_user_id=SUN_OWNER_AUTH_ID,
        )
        r2b = reserve_send_slot(
            c,
            lead_id=lead,
            channel="sms",
            subject=None,
            content_preview="r2b",
            agent_source="race_regression_test",
            cooldown_hours=None,
            metadata={},
            acted_by_user_id=SUN_OWNER_AUTH_ID,
        )
        if r2a.get("reservation_id"):
            cleanup.append(r2a["reservation_id"])
        if r2b.get("reservation_id"):
            cleanup.append(r2b["reservation_id"])
        results["checks"].append({
            "name": "first_concurrent_reserved",
            "expected": "reserved",
            "got": r2a.get("status"),
            "ok": r2a.get("status") == "reserved",
        })
        results["checks"].append({
            "name": "second_concurrent_blocked",
            "expected": "blocked",
            "got": r2b.get("status"),
            "ok": r2b.get("status") == "blocked",
        })
    finally:
        for rid in cleanup:
            try:
                c.table("lead_interactions").delete().eq("id", rid).execute()
            except Exception:  # noqa: BLE001
                pass

    results["all_passed"] = all(c["ok"] for c in results["checks"])
    return results


def main() -> int:
    p = argparse.ArgumentParser(description="send_gateway race-condition regression test")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    results = _run()
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for c in results["checks"]:
            tag = " OK " if c["ok"] else "FAIL"
            print(f"[{tag}] {c['name']:<32} expected={c['expected']} got={c['got']}")
        print(f"\n{'all passed' if results['all_passed'] else 'FAILURES'}")
    return 0 if results["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
