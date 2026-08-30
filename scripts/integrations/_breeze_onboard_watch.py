#!/usr/bin/env python3
"""Persistent event watch over the two real merchants onboarding + connecting a
bank. Designed for the Monitor tool: SILENT on no-change, emits ONE line only on
a real event (a bank connects, an error, or transactions first sync) — each line
becomes a notification AND fires a Telegram ping to CC (same discipline as
breeze_live_watch.py). Read-only; loops until stopped.

Data plane follows EMPIRE_DATA_BACKEND (see _client below) — Supabase today,
the breeze Turso database once the flag is on."""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass
from lib.secret_loader import load_env  # noqa: E402

try:
    from notify import notify  # scripts/ is on sys.path
except Exception:  # noqa: BLE001
    def notify(*_a, **_k):  # type: ignore
        return False

TARGETS = {
    "andy@docbuddy.com": "Doc Buddy",
    "operations@resourcehealthcare.org": "Resource Healthcare",
}
INTERVAL = 90  # seconds between polls


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _alert(msg: str, sound: bool = True) -> None:
    try:
        notify(f"Breeze onboarding: {msg}", category="system", force=True, silent=not sound)
    except Exception:  # noqa: BLE001
        pass


def _client():
    """A supabase-dialect client pointed at the BREEZE project's data.

    NOT `supabase.create_client(Breeze_SUPABASE_URL, ...)`. Under
    EMPIRE_DATA_BACKEND=turso_cloud, sitecustomize swaps create_client for
    turso_supabase_compat.create_client, which discards the url/key it is handed
    and always resolves `bravo` (turso_supabase_compat.py:618-621). Calling it
    here would read `merchants` / `bank_accounts` / `plaid_transactions` out of
    the harness database instead of Breeze's — a silent wrong-database read, not
    an error. So the breeze target is resolved explicitly; with the flag off we
    fall through to the real Supabase client for the same project.
    """
    if os.environ.get("EMPIRE_DATA_BACKEND") == "turso_cloud":
        from lib.db_turso import TursoDB, resolve_project_target  # noqa: PLC0415
        from lib.turso_supabase_compat import TursoSupabaseCompat  # noqa: PLC0415

        return TursoSupabaseCompat(TursoDB(*resolve_project_target("breeze")))

    e = load_env()
    url = e.get("Breeze_SUPABASE_URL")
    svc = e.get("Breeze_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not svc:
        raise RuntimeError("missing Breeze creds")
    from supabase import create_client  # noqa: PLC0415

    return create_client(url, svc)


def main() -> None:
    try:
        sb = _client()
    except Exception as exc:  # noqa: BLE001
        print(f"[watch] {exc}", flush=True)
        sys.exit(1)

    def rows(query) -> list:
        try:
            return query.execute().data or []
        except Exception:  # noqa: BLE001
            return []

    def count_tx(m_id: str) -> int:
        try:
            res = (
                sb.table("plaid_transactions")
                .select("id", count="exact", head=True)
                .eq("merchant_id", m_id)
                .execute()
            )
            return int(res.count or 0)
        except Exception:  # noqa: BLE001
            return 0

    merchants = rows(sb.table("merchants").select("id,primary_contact_email"))
    mid = {m["primary_contact_email"]: m["id"] for m in merchants}

    def snapshot() -> dict:
        state = {}
        for email, name in TARGETS.items():
            m_id = mid.get(email)
            if not m_id:
                state[name] = {"banks": [], "tx": 0}
                continue
            banks = rows(
                sb.table("bank_accounts")
                .select("status,institution_name,plaid_item_id,mask,created_at")
                .eq("merchant_id", m_id)
            )
            state[name] = {"banks": banks, "tx": count_tx(m_id)}
        return state

    base = snapshot()
    banks0 = {n: len(s["banks"]) for n, s in base.items()}
    print(f"[watch] {ts()} armed — baseline banks {banks0} (silent until an event)", flush=True)

    while True:
        time.sleep(INTERVAL)
        cur = snapshot()
        if not cur:
            continue
        for name, s in cur.items():
            prev = base.get(name, {"banks": [], "tx": 0})
            if len(s["banks"]) > len(prev["banks"]):
                b = s["banks"][0]
                print(
                    f"[watch] {ts()} CONNECTED: {name} — {b.get('institution_name','?')} "
                    f"••{b.get('mask','?')} [{b.get('status')}]",
                    flush=True,
                )
                _alert(
                    f"{name} just connected their bank "
                    f"({b.get('institution_name','?')} ••{b.get('mask','?')}) ✅",
                    sound=True,
                )
            prev_err = any(pb.get("status") == "error" for pb in prev["banks"])
            cur_err = any(b.get("status") == "error" for b in s["banks"])
            if cur_err and not prev_err:
                print(f"[watch] {ts()} ERROR: {name} bank status=error", flush=True)
                _alert(f"{name} bank connection ERROR — needs attention ⚠️", sound=True)
            if s["tx"] > prev["tx"]:
                print(
                    f"[watch] {ts()} {name}: transactions synced {prev['tx']} -> {s['tx']}",
                    flush=True,
                )
        base = cur


if __name__ == "__main__":
    main()
