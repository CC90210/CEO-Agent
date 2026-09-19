#!/usr/bin/env python
"""Provision the nomad-store Stripe account (its OWN account — never OASIS/PropFlow/Nostalgic).

    python scripts/integrations/nomad_stripe_setup.py whoami                  # which account the key belongs to
    python scripts/integrations/nomad_stripe_setup.py plan                    # diff catalog tiers (Turso) vs live Stripe Prices; exit 1 on drift
    python scripts/integrations/nomad_stripe_setup.py webhook [--url URL]     # create the endpoint; writes NOMAD_STRIPE_WEBHOOK_SECRET into the agents env (never printed)
    python scripts/integrations/nomad_stripe_setup.py portal                  # Customer Portal: payment-method + invoices only; cancellation runs in our UI
    python scripts/integrations/nomad_stripe_setup.py tax-check               # Stripe Tax status + registrations

Key: NOMAD_STRIPE_SECRET_KEY in the agents env. The webhook secret is written
straight from Stripe's creation response into .env.agents via the same
_write_env pattern arthrisil_stripe_setup uses — key NAMES only on stdout.
"""
from __future__ import annotations

import argparse
import datetime
import json
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.secret_loader import load_env  # noqa: E402

KEY_NAME = "NOMAD_STRIPE_SECRET_KEY"
WEBHOOK_KEY_NAME = "NOMAD_STRIPE_WEBHOOK_SECRET"
API = "https://api.stripe.com/v1"
API_VERSION = "2026-08-26.dahlia"
WEBHOOK_EVENTS = [
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.expired",
    "invoice.paid",
    "invoice.payment_failed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "charge.dispute.created",
    "charge.refunded",
]


def _key() -> str:
    key = load_env().get(KEY_NAME)
    if not key:
        raise SystemExit(f"{KEY_NAME} is not set in the agents env. CC opens the dedicated Stripe account, then adds the sk_ key under that name.")
    return key


def stripe(method: str, path: str, data: dict | None = None) -> dict:
    body = urllib.parse.urlencode(_flatten(data or {}), doseq=True).encode() if data else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=body,
        method=method,
        headers={"Authorization": f"Bearer {_key()}", "Stripe-Version": API_VERSION, "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Stripe {method} {path} → HTTP {e.code}: {e.read().decode('utf-8','replace')[:400]}") from None


def _flatten(d: dict, prefix: str = "") -> dict:
    out: dict = {}
    for k, v in d.items():
        key = f"{prefix}[{k}]" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    out.update(_flatten(item, f"{key}[{i}]"))
                else:
                    out[f"{key}[{i}]"] = item
        elif isinstance(v, bool):
            out[key] = "true" if v else "false"
        elif v is not None:
            out[key] = v
    return out


def _write_env(pairs: dict[str, str]) -> list[str]:
    env_path = PROJECT_ROOT / ".env.agents"
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(env_path, env_path.with_suffix(f".agents.bak-{stamp}"))
    lines = env_path.read_text(encoding="utf-8").splitlines()
    written = []
    for k, v in pairs.items():
        replaced = False
        for i, line in enumerate(lines):
            if line.startswith(f"{k}="):
                lines[i] = f"{k}={v}"
                replaced = True
                break
        if not replaced:
            lines.append(f"{k}={v}")
        written.append(k)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return written


def cmd_gen_secrets(args) -> int:
    """Write the non-Stripe Worker secrets into the agents env if absent (never overwrites)."""
    import secrets as _secrets

    env = load_env()
    pairs: dict[str, str] = {}
    if not env.get("NOMAD_STORE__SESSION_SECRET"):
        pairs["NOMAD_STORE__SESSION_SECRET"] = _secrets.token_urlsafe(48)
    if not env.get("NOMAD_STORE__WORKER_SHARED_SECRET"):
        pairs["NOMAD_STORE__WORKER_SHARED_SECRET"] = _secrets.token_urlsafe(48)
    if not env.get("NOMAD_STORE__APP_URL"):
        pairs["NOMAD_STORE__APP_URL"] = args.app_url or "https://nomad-store.oasisaisolutions.workers.dev"
    if not pairs:
        print("all present: NOMAD_STORE__SESSION_SECRET, NOMAD_STORE__WORKER_SHARED_SECRET, NOMAD_STORE__APP_URL")
        return 0
    written = _write_env(pairs)
    print(f"wrote {', '.join(written)} to the agents env (values not shown)")
    return 0


def cmd_whoami(args) -> int:
    acct = stripe("GET", "/account")
    livemode = _key().startswith("sk_live_")
    print(f"account: {acct.get('id')}  name: {(acct.get('settings') or {}).get('dashboard', {}).get('display_name') or acct.get('business_profile', {}).get('name')}  livemode_key: {livemode}")
    known = {v for k, v in load_env().items() if k in ("STRIPE_OASIS_ACCT_ID", "STRIPE_PROPFLOW_ACCT_ID", "STRIPE_NOSTALGIC_ACCT_ID")}
    if acct.get("id") in known:
        print("REFUSING: this key belongs to an existing empire account. The store must run on its OWN Stripe account.")
        return 1
    print("ok: dedicated account")
    return 0


def cmd_plan(args) -> int:
    from nomad_db import query  # noqa: E402  (same folder)

    tiers = query(
        "SELECT p.slug, t.id, t.label, t.units, t.onetime_cents, t.subscribe_cents, t.stripe_onetime_price_id, t.stripe_subscribe_price_id "
        "FROM product_tiers t JOIN products p ON p.id = t.product_id WHERE p.status IN ('unlisted','live')"
    )
    drift = 0
    for t in tiers:
        for mode, pid_key, cents_key, recurring in (("onetime", "stripe_onetime_price_id", "onetime_cents", False), ("subscribe", "stripe_subscribe_price_id", "subscribe_cents", True)):
            pid = t.get(pid_key)
            want = int(t[cents_key])
            if not pid:
                print(f"  DRIFT {t['slug']} {t['label']} {mode}: no Stripe price (publish in admin)")
                drift += 1
                continue
            price = stripe("GET", f"/prices/{pid}")
            have = price.get("unit_amount")
            is_rec = bool(price.get("recurring"))
            ok = price.get("active") and have == want and is_rec == recurring
            print(f"  {'ok   ' if ok else 'DRIFT'} {t['slug']} {t['label']} {mode}: db={want} stripe={have} active={price.get('active')} recurring={is_rec}")
            if not ok:
                drift += 1
    # The first-order code is shown to shoppers by the capture modal; if it does not exist in
    # Stripe, Checkout rejects it in front of the customer. That is drift, not a to-do.
    settings = {r["key"]: r["value"] for r in query("SELECT key, value FROM settings WHERE key IN ('capture_enabled','capture_code')")}
    if settings.get("capture_enabled", "1") == "1":
        code = (settings.get("capture_code") or "WELCOME10").upper()
        found = stripe("GET", f"/promotion_codes?code={code}&limit=1").get("data", [])
        if found and found[0].get("active"):
            print(f"  ok    promo {code} exists and is active")
        else:
            print(f"  DRIFT promo {code}: {'inactive' if found else 'missing'} in Stripe — run: nomad_stripe_setup.py promo")
            drift += 1
    print(f"\n{len(tiers)} tiers checked, {drift} drift" if tiers else f"no live/unlisted tiers to check, {drift} drift")
    return 1 if drift else 0


def cmd_webhook(args) -> int:
    url = args.url or f"{load_env().get('NOMAD_STORE__APP_URL', 'https://nomad-store.oasisaisolutions.workers.dev').rstrip('/')}/api/stripe/webhook"
    existing = stripe("GET", "/webhook_endpoints?limit=100").get("data", [])
    for e in existing:
        if e.get("url") == url:
            print(f"webhook already exists: {e['id']} → {url} (secret only shown at creation; delete it in the dashboard to rotate)")
            return 0
    created = stripe("POST", "/webhook_endpoints", {"url": url, "enabled_events": WEBHOOK_EVENTS, "api_version": API_VERSION, "description": "nomad-store"})
    secret = created.get("secret")
    if not secret:
        raise SystemExit("Stripe returned no signing secret")
    written = _write_env({WEBHOOK_KEY_NAME: secret})
    print(f"created {created['id']} → {url}")
    print(f"wrote {', '.join(written)} to the agents env (value not shown). Next: wrangler_tool.py secrets-push --app nomad-store")
    return 0


def cmd_portal(args) -> int:
    cfgs = stripe("GET", "/billing_portal/configurations?limit=10").get("data", [])
    body = {
        "business_profile": {"headline": "Manage your payment method and invoices"},
        "features": {
            "customer_update": {"enabled": True, "allowed_updates": ["email", "address", "phone", "shipping"]},
            "invoice_history": {"enabled": True},
            "payment_method_update": {"enabled": True},
            # Cancellation, pause and plan changes run in OUR account UI so the retention flow and the
            # cancel confirmation email are one path. The portal is payment-method + invoices only.
            "subscription_cancel": {"enabled": False},
            "subscription_update": {"enabled": False},
        },
        "default_return_url": f"{load_env().get('NOMAD_STORE__APP_URL', 'https://nomad-store.oasisaisolutions.workers.dev').rstrip('/')}/account",
    }
    target = next((c for c in cfgs if c.get("is_default")), None)
    if target:
        stripe("POST", f"/billing_portal/configurations/{target['id']}", body)
        print(f"updated default portal configuration {target['id']}")
    else:
        c = stripe("POST", "/billing_portal/configurations", body)
        print(f"created portal configuration {c['id']}")
    return 0


def cmd_promo(args) -> int:
    """Create the first-order promotion code (settings.capture_code / capture_pct) in Stripe, once."""
    from nomad_db import query  # noqa: E402

    rows = {r["key"]: r["value"] for r in query("SELECT key, value FROM settings WHERE key IN ('capture_code','capture_pct')")}
    code = (args.code or rows.get("capture_code") or "WELCOME10").upper()
    pct = int(args.pct or rows.get("capture_pct") or 10)
    existing = stripe("GET", f"/promotion_codes?code={code}&limit=1").get("data", [])
    if existing:
        print(f"promotion code {code} exists: {existing[0]['id']} (active={existing[0].get('active')})")
        return 0
    coupon = stripe("POST", "/coupons", {"percent_off": pct, "duration": "once", "name": f"First order {pct}% off"})
    promo = stripe("POST", "/promotion_codes", {"promotion_code": code, "coupon": coupon["id"], "restrictions": {"first_time_transaction": True}})
    print(f"created coupon {coupon['id']} + promotion code {code} ({promo['id']}), first-time customers only")
    return 0


def cmd_tax_check(args) -> int:
    settings = stripe("GET", "/tax/settings")
    regs = stripe("GET", "/tax/registrations?limit=100").get("data", [])
    print(f"tax status: {settings.get('status')}  head office: {(settings.get('head_office') or {}).get('address', {}).get('country')}")
    print(f"registrations: {len(regs)}")
    for r in regs:
        print(f"  {r.get('country')} {r.get('country_options', {}).get(r.get('country','').lower(), {}).get('state', '')} active_from={r.get('active_from')}")
    if settings.get("status") != "active":
        print("ACTION (CC): finish Stripe Tax setup in the dashboard (origin address + product tax code). automatic_tax on Checkout stays on; it collects only where a registration exists.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("whoami")
    p = sub.add_parser("gen-secrets"); p.add_argument("--app-url")
    sub.add_parser("plan")
    p = sub.add_parser("webhook"); p.add_argument("--url")
    sub.add_parser("portal")
    sub.add_parser("tax-check")
    p = sub.add_parser("promo"); p.add_argument("--code"); p.add_argument("--pct", type=int)
    args = parser.parse_args(argv)
    return {"whoami": cmd_whoami, "gen-secrets": cmd_gen_secrets, "plan": cmd_plan, "webhook": cmd_webhook, "portal": cmd_portal, "tax-check": cmd_tax_check, "promo": cmd_promo}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
