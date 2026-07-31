#!/usr/bin/env python3
"""Persistent event watch over the two real merchants onboarding + connecting a
bank. Designed for the Monitor tool: SILENT on no-change, emits ONE line only on
a real event (a bank connects, an error, or transactions first sync) — each line
becomes a notification AND fires a Telegram ping to CC (same discipline as
breeze_live_watch.py). Read-only; loops until stopped."""
from __future__ import annotations

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
import requests  # noqa: E402
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


def main() -> None:
    e = load_env()
    URL = e.get("Breeze_SUPABASE_URL")
    SVC = e.get("Breeze_SUPABASE_SERVICE_ROLE_KEY")
    if not URL or not SVC:
        print("[watch] missing Breeze creds", flush=True)
        sys.exit(1)
    H = {"apikey": SVC, "authorization": f"Bearer {SVC}"}

    def rows(path: str) -> list:
        try:
            r = requests.get(f"{URL}/rest/v1/{path}", headers=H, timeout=30)
            return r.json() if r.status_code < 300 else []
        except Exception:  # noqa: BLE001
            return []

    def count_tx(m_id: str) -> int:
        try:
            r = requests.get(
                f"{URL}/rest/v1/plaid_transactions?merchant_id=eq.{m_id}&select=id",
                headers={**H, "Prefer": "count=exact", "Range": "0-0"},
                timeout=30,
            )
            tail = r.headers.get("content-range", "*/0").split("/")[-1]
            return int(tail) if tail.isdigit() else 0
        except Exception:  # noqa: BLE001
            return 0

    merchants = rows("merchants?select=id,primary_contact_email")
    mid = {m["primary_contact_email"]: m["id"] for m in merchants}

    def snapshot() -> dict:
        state = {}
        for email, name in TARGETS.items():
            m_id = mid.get(email)
            if not m_id:
                state[name] = {"banks": [], "tx": 0}
                continue
            banks = rows(
                f"bank_accounts?merchant_id=eq.{m_id}"
                "&select=status,institution_name,plaid_item_id,mask,created_at"
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
