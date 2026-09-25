"""Which Stripe account does each configured Stripe credential reach?

    python scripts/integrations/stripe_key_account.py

Prints account id, business name and live/test mode for STRIPE_SECRET_KEY and
for STRIPE_ORG_KEY scoped to STRIPE_OASIS_ACCT_ID. Never prints a key. Used to
decide which credential a service (e.g. the command center's Finances suite)
may be given: a key is just a string, and nothing about it says whose it is.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.secret_loader import load_env  # noqa: E402


def account(key: str, context: str | None = None) -> str:
    req = urllib.request.Request(
        "https://api.stripe.com/v1/account",
        headers={"Authorization": f"Bearer {key}", "User-Agent": "bravo-stripe-key-account/1.0"},
    )
    if context:
        # Organization keys require an explicit API version (stripe_tool.py pins the same one).
        req.add_header("Stripe-Context", context)
        req.add_header("Stripe-Version", "2025-01-27.acacia")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            message = (json.loads(body).get("error") or {}).get("message", "")
        except ValueError:
            message = body
        return f"HTTP {exc.code}: {message[:200]}"
    except urllib.error.URLError as exc:
        return f"network error: {exc.reason}"
    profile = data.get("business_profile") or {}
    dashboard = (data.get("settings") or {}).get("dashboard") or {}
    name = dashboard.get("display_name") or profile.get("name") or "?"
    mode = "live" if key.startswith(("sk_live", "rk_live")) else ("test" if key.startswith(("sk_test", "rk_test")) else "org/other")
    return f"{data.get('id')} | {name} | key mode: {mode}"


def main() -> int:
    env = load_env()
    org = env.get("STRIPE_ORG_KEY") or ""
    oasis = env.get("STRIPE_OASIS_ACCT_ID") or ""
    for name in ("STRIPE_SECRET_KEY", "STRIPE_RESTRICTED_KEY"):
        value = env.get(name) or ""
        print(f"{name}: {account(value) if value else 'absent'}")
    if org and oasis:
        print(f"STRIPE_ORG_KEY -> STRIPE_OASIS_ACCT_ID: {account(org, oasis)}")
    else:
        print(f"STRIPE_ORG_KEY + STRIPE_OASIS_ACCT_ID: {'org key absent' if not org else 'account id absent'}")
    if "--probe" in sys.argv:
        restricted = env.get("STRIPE_RESTRICTED_KEY") or ""
        print("STRIPE_RESTRICTED_KEY read permissions (GET ?limit=1; status only):")
        for path in ("/v1/charges", "/v1/payment_intents", "/v1/balance_transactions", "/v1/refunds",
                     "/v1/subscriptions", "/v1/invoices", "/v1/customers", "/v1/prices", "/v1/products",
                     "/v1/payment_links", "/v1/webhook_endpoints", "/v1/balance"):
            req = urllib.request.Request(f"https://api.stripe.com{path}{'' if path == '/v1/balance' else '?limit=1'}",
                                         headers={"Authorization": f"Bearer {restricted}", "User-Agent": "bravo-stripe-key-account/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    status = resp.status
            except urllib.error.HTTPError as exc:
                status = exc.code
            print(f"  {path:28} {status}")
        # WRITE permissions without side effects: an empty POST is rejected with
        # 403 when the key lacks the permission, and with 400 (missing params)
        # when it has it — Stripe checks permission first, so nothing is created.
        # ONLY endpoints whose create REQUIRES params belong here. /v1/customers
        # does not (an empty POST creates a blank customer — it did, 2026-09-24,
        # and had to be deleted), so it is never probed this way.
        print("STRIPE_RESTRICTED_KEY write permissions (empty POST; 400 = allowed, 403 = denied):")
        for path in ("/v1/products", "/v1/prices", "/v1/payment_links", "/v1/subscriptions", "/v1/invoices"):
            req = urllib.request.Request(f"https://api.stripe.com{path}", data=b"", method="POST",
                                         headers={"Authorization": f"Bearer {restricted}", "User-Agent": "bravo-stripe-key-account/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    status = resp.status
            except urllib.error.HTTPError as exc:
                status = exc.code
            verdict = "allowed" if status == 400 else ("DENIED" if status == 403 else "unexpected")
            print(f"  POST {path:24} {status} {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
