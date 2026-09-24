#!/usr/bin/env python
"""Provision the oasis-store Stripe account (its OWN account — never OASIS/PropFlow/Nostalgic).

    python scripts/integrations/oasis_store_stripe_setup.py whoami                  # which account the key belongs to
    python scripts/integrations/oasis_store_stripe_setup.py plan                    # diff catalog tiers (Turso) vs live Stripe Prices; exit 1 on drift
    python scripts/integrations/oasis_store_stripe_setup.py webhook [--url URL]     # create the endpoint; writes OASIS_STORE_STRIPE_WEBHOOK_SECRET into the agents env (never printed)
    python scripts/integrations/oasis_store_stripe_setup.py portal                  # Customer Portal: payment-method + invoices only; cancellation runs in our UI
    python scripts/integrations/oasis_store_stripe_setup.py tax-check               # Stripe Tax status + registrations

Key: OASIS_STORE_STRIPE_SECRET_KEY in the agents env. The webhook secret is written
straight from Stripe's creation response into .env.agents via the same
_write_env pattern arthrisil_stripe_setup uses — key NAMES only on stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.env_store import locked_update_text  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402

KEY_NAME = "OASIS_STORE_STRIPE_SECRET_KEY"
WEBHOOK_KEY_NAME = "OASIS_STORE_STRIPE_WEBHOOK_SECRET"
# Set when the store rides an existing empire account through an ORGANIZATION key.
# An org key authenticates as the org, not an account, so every call must name the
# account in a Stripe-Context header — without it Stripe answers 401.
ACCOUNT_KEY_NAME = "OASIS_STORE_STRIPE_ACCOUNT"
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


def _account_context() -> str | None:
    return load_env().get(ACCOUNT_KEY_NAME) or None


def stripe(method: str, path: str, data: dict | None = None) -> dict:
    body = urllib.parse.urlencode(_flatten(data or {}), doseq=True).encode() if data else None
    headers = {"Authorization": f"Bearer {_key()}", "Stripe-Version": API_VERSION, "Content-Type": "application/x-www-form-urlencoded"}
    context = _account_context()
    if context:
        headers["Stripe-Context"] = context
    req = urllib.request.Request(f"{API}{path}", data=body, method=method, headers=headers)
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
    def merge(current: str) -> str:
        lines = current.splitlines()
        for key, value in pairs.items():
            replaced = False
            for index, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[index] = f"{key}={value}"
                    replaced = True
                    break
            if not replaced:
                lines.append(f"{key}={value}")
        return "\n".join(lines) + "\n"

    locked_update_text(env_path, merge)
    return list(pairs)


def cmd_gen_secrets(args) -> int:
    """Write the non-Stripe Worker secrets into the agents env if absent (never overwrites)."""
    import secrets as _secrets

    env = load_env()
    pairs: dict[str, str] = {}
    if not env.get("OASIS_STORE__SESSION_SECRET"):
        pairs["OASIS_STORE__SESSION_SECRET"] = _secrets.token_urlsafe(48)
    if not env.get("OASIS_STORE__WORKER_SHARED_SECRET"):
        pairs["OASIS_STORE__WORKER_SHARED_SECRET"] = _secrets.token_urlsafe(48)
    if not env.get("OASIS_STORE__APP_URL"):
        pairs["OASIS_STORE__APP_URL"] = args.app_url or "https://oasis-store.oasisaisolutions.workers.dev"
    if not pairs:
        print("all present: OASIS_STORE__SESSION_SECRET, OASIS_STORE__WORKER_SHARED_SECRET, OASIS_STORE__APP_URL")
        return 0
    written = _write_env(pairs)
    print(f"wrote {', '.join(written)} to the agents env (values not shown)")
    return 0


def cmd_adopt_account(args) -> int:
    """Point the store at an EXISTING empire Stripe account instead of a dedicated one.

    CC's call on 2026-09-19: ship on the OASIS AI Solutions account rather than wait
    on a new sole-prop KYC. This copies the source key to KEY_NAME inside the process
    — the value is never printed, never returned, and never enters an agent's context.
    It verifies the key against Stripe's /account first, so a typo'd source name fails
    here rather than at a shopper's checkout.
    """
    source = args.source
    env = load_env()
    value = env.get(source)
    if not value:
        raise SystemExit(f"{source} is not set in the agents env — nothing to adopt.")
    # No prefix whitelist. Stripe has sk_, rk_ and organization-key formats, and a
    # whitelist that predates a format rejects a key that works perfectly well — which
    # is what happened here. The /account probe below is the authoritative check.
    if len(value) < 20 or any(c.isspace() for c in value):
        raise SystemExit(f"{source} is not a plausible API key (too short, or contains whitespace).")

    existing = env.get(KEY_NAME)
    if existing and existing != value and not args.force:
        raise SystemExit(f"{KEY_NAME} is already set to a different key. Re-run with --force to replace it.")

    context = args.context or env.get("STRIPE_OASIS_ACCT_ID")

    def probe(ctx: str | None) -> tuple[dict | None, str]:
        headers = {"Authorization": f"Bearer {value}", "Stripe-Version": API_VERSION}
        if ctx:
            headers["Stripe-Context"] = ctx
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{API}/account", headers=headers), timeout=30) as r:
                return json.loads(r.read().decode()), ""
        except urllib.error.HTTPError as e:
            return None, f"HTTP {e.code}"

    # An organization key 401s on its own and only works with a context; a plain
    # account key works bare. Try bare first so we store the context only if it is
    # load-bearing — a stray context header would silently retarget every call.
    acct, err = probe(None)
    used_context = None
    if acct is None and context:
        acct, err2 = probe(context)
        if acct is not None:
            used_context = context
        else:
            err = f"{err} bare, {err2} with context {context}"
    if acct is None:
        raise SystemExit(f"{source} was rejected by Stripe ({err}) — not adopting a key that cannot authenticate.")

    pairs = {KEY_NAME: value}
    pairs[ACCOUNT_KEY_NAME] = used_context or ""
    _write_env(pairs)

    live = bool(acct.get("charges_enabled")) and "test" not in value[:8]
    name = (acct.get("settings") or {}).get("dashboard", {}).get("display_name") or acct.get("business_profile", {}).get("name")
    print(f"adopted {source} -> {KEY_NAME} (value not shown)")
    print(f"  account: {acct.get('id')}  name: {name}")
    print(f"  auth mode: {'ORGANIZATION key + Stripe-Context ' + used_context if used_context else 'direct account key'}")
    print(f"  LIVE MODE: {live}")
    if live:
        print("  This account takes REAL money. Disputes here hit the same balance as the rest of")
        print("  this account's revenue. Set a statement descriptor that names the product line.")
    return 0


def cmd_whoami(args) -> int:
    acct = stripe("GET", "/account")
    livemode = _key().startswith("sk_live_")
    print(f"account: {acct.get('id')}  name: {(acct.get('settings') or {}).get('dashboard', {}).get('display_name') or acct.get('business_profile', {}).get('name')}  livemode_key: {livemode}")
    known = {v for k, v in load_env().items() if k in ("STRIPE_OASIS_ACCT_ID", "STRIPE_PROPFLOW_ACCT_ID", "STRIPE_NOSTALGIC_ACCT_ID")}
    if acct.get("id") in known:
        if not getattr(args, "allow_shared_account", False):
            print("REFUSING: this key belongs to an existing empire account (agency/PropFlow/Nostalgic).")
            print("  Why this default exists: dropship shipping times and auto-renew are the two biggest")
            print("  chargeback drivers, Stripe risk-reviews per account, and a dispute spike can put a")
            print("  rolling reserve on the funds in THIS account — which is where your agency gets paid.")
            print("  If you have weighed that and want the speed anyway, re-run with --allow-shared-account.")
            return 1
        print("WARNING --allow-shared-account: the consumer store will share an account with existing")
        print("  empire revenue. Set a per-product statement descriptor so card statements name the")
        print("  product line, and plan to split before ad spend scales volume.")
    print("ok: dedicated account" if acct.get("id") not in known else "ok: shared account (override acknowledged)")
    return 0


def cmd_plan(args) -> int:
    from oasis_store_db import query  # noqa: E402  (same folder)

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
            print(f"  DRIFT promo {code}: {'inactive' if found else 'missing'} in Stripe — run: oasis_store_stripe_setup.py promo")
            drift += 1
    print(f"\n{len(tiers)} tiers checked, {drift} drift" if tiers else f"no live/unlisted tiers to check, {drift} drift")
    return 1 if drift else 0


def cmd_webhook(args) -> int:
    url = args.url or f"{load_env().get('OASIS_STORE__APP_URL', 'https://oasis-store.oasisaisolutions.workers.dev').rstrip('/')}/api/stripe/webhook"
    existing = stripe("GET", "/webhook_endpoints?limit=100").get("data", [])
    for e in existing:
        if e.get("url") == url:
            print(f"webhook already exists: {e['id']} → {url} (secret only shown at creation; delete it in the dashboard to rotate)")
            return 0
    created = stripe("POST", "/webhook_endpoints", {"url": url, "enabled_events": WEBHOOK_EVENTS, "api_version": API_VERSION, "description": "oasis-store"})
    secret = created.get("secret")
    if not secret:
        raise SystemExit("Stripe returned no signing secret")
    written = _write_env({WEBHOOK_KEY_NAME: secret})
    print(f"created {created['id']} → {url}")
    print(f"wrote {', '.join(written)} to the agents env (value not shown). Next: wrangler_tool.py secrets-push --app oasis-store")
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
        "default_return_url": f"{load_env().get('OASIS_STORE__APP_URL', 'https://oasis-store.oasisaisolutions.workers.dev').rstrip('/')}/account",
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
    from oasis_store_db import query  # noqa: E402

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
    p = sub.add_parser("whoami")
    p.add_argument("--allow-shared-account", action="store_true", dest="allow_shared_account",
                   help="proceed even if the key belongs to an existing empire account (speed over isolation)")
    p = sub.add_parser("adopt-account", help="copy an existing empire Stripe key into the store's key name")
    p.add_argument("--source", default="STRIPE_SECRET_KEY", help="agents-env key name to copy FROM (default: STRIPE_SECRET_KEY, the OASIS account)")
    p.add_argument("--context", help="acct_... to send as Stripe-Context; required when --source is an ORGANIZATION key")
    p.add_argument("--force", action="store_true", help="replace an existing store key")
    p = sub.add_parser("gen-secrets"); p.add_argument("--app-url")
    sub.add_parser("plan")
    p = sub.add_parser("webhook"); p.add_argument("--url")
    sub.add_parser("portal")
    sub.add_parser("tax-check")
    p = sub.add_parser("promo"); p.add_argument("--code"); p.add_argument("--pct", type=int)
    args = parser.parse_args(argv)
    return {"adopt-account": cmd_adopt_account, "whoami": cmd_whoami, "gen-secrets": cmd_gen_secrets, "plan": cmd_plan, "webhook": cmd_webhook, "portal": cmd_portal, "tax-check": cmd_tax_check, "promo": cmd_promo}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
