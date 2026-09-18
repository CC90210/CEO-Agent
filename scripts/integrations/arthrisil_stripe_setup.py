#!/usr/bin/env python
"""Provision Arthrisil's catalogue in Trytan Health's LIVE Stripe account.

    python scripts/integrations/arthrisil_stripe_setup.py plan      # read-only
    python scripts/integrations/arthrisil_stripe_setup.py apply     # create
    python scripts/integrations/arthrisil_stripe_setup.py webhook   # endpoint + secret

WHY THIS EXISTS AT ALL, given the site builds its Checkout line items from
inline `price_data` and needs none of these objects: the Stripe dashboard is
where the client reads their own business. Without Products the payments list is
a wall of untitled charges, subscription reporting has nothing to group by, and
the Customer Portal has no plan to show. These objects are for the humans.

THE AMOUNTS ARE NOT WRITTEN DOWN HERE. They are parsed out of the site's
lib/pricing.ts, which is the single source of truth for money. If this file
carried its own copy of 3495 it would be exactly the second source of truth that
let the PayPal button charge $29.95 while the page advertised something else.

IDEMPOTENT: identity is carried by price `lookup_key`, product `metadata.slug`,
and shipping-rate display name + amount. Re-running finds and reports; it never
creates a duplicate and never archives or deletes anything.

SECRETS: the API key is read through lib.secret_loader and never printed. The
webhook signing secret goes straight from Stripe's response into .env.agents via
_write_env — the agent running this never sees it, which is the point.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.app_registry import app_dir  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402

API = "https://api.stripe.com/v1"
API_VERSION = "2026-08-26.dahlia"
KEY_NAME = "Trytan_Health_Secret_key"
WEBHOOK_SECRET_KEY = "STRIPE_WEBHOOK_SECRET_TRYTAN"
ENV_FILE = PROJECT_ROOT / ".env.agents"
APP_SLUG = "arthrisil-website"


def pricing_ts() -> Path:
    """lib/pricing.ts, located via the fleet registry rather than a typed path."""
    return app_dir(APP_SLUG) / "lib" / "pricing.ts"
WEBHOOK_URL = "https://arthrisil.com/api/stripe/webhook"
WEBHOOK_EVENTS = [
    "checkout.session.completed",
    # Without these the site hears about a subscription exactly once, at birth:
    # renewals are charged and recorded nowhere, and a cancellation is invisible
    # — and you cannot make a retention offer to a churn you never learn about.
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
]


class StripeError(RuntimeError):
    pass


# --------------------------------------------------------------------- pricing

def read_pricing() -> dict[str, int]:
    """Parse the money constants out of lib/pricing.ts.

    Deliberately a parse rather than a duplicate: a number typed here could
    drift from the site silently, and the drift would only surface as a customer
    being charged one amount while reading another.
    """
    path = pricing_ts()
    if not path.exists():
        raise SystemExit(f"cannot find {path} — is the site repo checked out?")
    text = path.read_text(encoding="utf-8")

    def const(name: str) -> int:
        match = re.search(rf"export const {name}\s*=\s*([0-9_]+)\s*;", text)
        if not match:
            raise SystemExit(f"{name} not found in lib/pricing.ts — did the file change shape?")
        return int(match.group(1).replace("_", ""))

    unit = const("UNIT_PRICE_CENTS")
    pct = const("SUBSCRIBE_SAVE_PCT")
    bottles = const("BUNDLE_BOTTLES")
    return {
        "unit": unit,
        "shipping": const("SHIPPING_CENTS"),
        "bundle_shipping": const("BUNDLE_SHIPPING_CENTS"),
        # Mirrors the TS: Math.round(unit * (100 - pct) / 100) and unit * (bottles - 1).
        "subscription": round(unit * (100 - pct) / 100),
        "bundle": unit * (bottles - 1),
        "bottles": bottles,
        "pct": pct,
    }


# ----------------------------------------------------------------------- stripe

def _key() -> str:
    key = load_env().get(KEY_NAME)
    if not key:
        raise SystemExit(f"{KEY_NAME} is not set in .env.agents")
    return key


def call(method: str, path: str, data: dict | None = None) -> dict:
    body = urllib.parse.urlencode(data, doseq=True).encode() if data else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {_key()}",
            "Stripe-Version": API_VERSION,
            "Content-Type": "application/x-www-form-urlencoded",
            # A default urllib User-Agent is a client identity an edge can block.
            "User-Agent": "arthrisil-setup/1.0 (+https://arthrisil.com)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        raise StripeError(
            f"{method} {path} -> HTTP {err.code}\n{err.read().decode('utf-8', 'replace')[:800]}"
        ) from None


def whoami() -> dict:
    account = call("GET", "/account")
    key = _key()
    return {
        "id": account.get("id"),
        "name": (account.get("business_profile") or {}).get("name"),
        "country": account.get("country"),
        "livemode": key.startswith("sk_live_"),
        "charges_enabled": account.get("charges_enabled"),
    }


def find_product(slug: str) -> dict | None:
    for product in call("GET", "/products?limit=100&active=true").get("data", []):
        if (product.get("metadata") or {}).get("slug") == slug:
            return product
    return None


def find_price(lookup_key: str) -> dict | None:
    data = call("GET", f"/prices?lookup_keys[]={urllib.parse.quote(lookup_key)}&limit=1").get("data", [])
    return data[0] if data else None


def find_shipping_rate(name: str, amount: int) -> dict | None:
    for rate in call("GET", "/shipping_rates?limit=100&active=true").get("data", []):
        if rate.get("display_name") == name and (rate.get("fixed_amount") or {}).get("amount") == amount:
            return rate
    return None


def find_promo(code: str) -> dict | None:
    data = call("GET", f"/promotion_codes?code={urllib.parse.quote(code)}&limit=1").get("data", [])
    return data[0] if data else None


def find_webhook(url: str) -> dict | None:
    for endpoint in call("GET", "/webhook_endpoints?limit=100").get("data", []):
        if endpoint.get("url") == url:
            return endpoint
    return None


# ------------------------------------------------------------------- env write

def _write_env(pairs: dict[str, str]) -> list[str]:
    """Append/replace keys in the agents env file WITHOUT returning their values.

    The caller gets key names only. This is the same contract as
    turso_admin._write_env and exists for the same reason: the alternative is
    printing a live signing secret into a transcript and asking a human to paste
    it back. A timestamped backup is written first.
    """
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    existing = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    if existing:
        ENV_FILE.with_suffix(f".agents.bak.{stamp}").write_text(
            "\n".join(existing) + "\n", encoding="utf-8"
        )
    out: list[str] = []
    replaced: set[str] = set()
    for line in existing:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in pairs:
            out.append(f"{key}={pairs[key]}")
            replaced.add(key)
        else:
            out.append(line)
    for key, value in pairs.items():
        if key not in replaced:
            out.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    return sorted(pairs)


# -------------------------------------------------------------------- commands

def catalogue(p: dict) -> list[tuple[str, str, int]]:
    """(kind, identity, expected_amount) for everything this script manages."""
    return [
        ("price", "arthrisil_onetime_usd", p["unit"]),
        ("price", "arthrisil_monthly_usd", p["subscription"]),
        ("price", "arthrisil_bundle3_usd", p["bundle"]),
        ("shipping_rate", "Standard shipping", p["shipping"]),
        ("shipping_rate", "Shipping & handling", p["bundle_shipping"]),
        ("shipping_rate", "Free shipping", 0),
    ]


def cmd_plan(args) -> int:
    p = read_pricing()
    who = whoami()

    if getattr(args, "json", False):
        # Machine-readable drift report. RULE 2: every CLI tool speaks --json,
        # so a cron or another agent can act on this without scraping columns.
        rows = []
        for kind, identity, expected in catalogue(p):
            obj = find_price(identity) if kind == "price" else find_shipping_rate(identity, expected)
            live = None
            if obj is not None:
                live = obj.get("unit_amount") if kind == "price" else (obj.get("fixed_amount") or {}).get("amount")
            rows.append({
                "kind": kind, "identity": identity, "expected": expected,
                "live": live, "id": obj["id"] if obj else None,
                "status": "missing" if obj is None else ("ok" if live == expected else "drift"),
            })
        promo = find_promo("WELCOME10")
        hook = find_webhook(WEBHOOK_URL)
        payload = {
            "account": who,
            "pricing_source": str(pricing_ts()),
            "expected": p,
            "objects": rows,
            "promo": {"code": "WELCOME10", "present": bool(promo),
                      "id": promo["id"] if promo else None,
                      "active": promo["active"] if promo else None},
            "webhook": {"url": WEBHOOK_URL, "present": bool(hook),
                        "id": hook["id"] if hook else None,
                        "status": hook.get("status") if hook else None},
            "drift": [r["identity"] for r in rows if r["status"] == "drift"],
            "missing": [r["identity"] for r in rows if r["status"] == "missing"],
        }
        payload["ok"] = not payload["drift"]
        print(json.dumps(payload, indent=2))
        return 1 if payload["drift"] else 0

    print(f"account : {who['id']}  {who['name']}  ({who['country']}, "
          f"{'LIVE' if who['livemode'] else 'TEST'}, charges={who['charges_enabled']})")
    print(f"pricing : bottle {p['unit']}  monthly {p['subscription']}  "
          f"bundle {p['bundle']} ({p['bottles']} bottles)  "
          f"ship {p['shipping']}/{p['bundle_shipping']}   [from lib/pricing.ts]\n")

    drift = 0
    for kind, identity, expected in catalogue(p):
        obj = find_price(identity) if kind == "price" else find_shipping_rate(identity, expected)
        if obj is None:
            print(f"  MISSING  {kind:<14} {identity:<26} expected {expected}")
            continue
        live = obj.get("unit_amount") if kind == "price" else (obj.get("fixed_amount") or {}).get("amount")
        if live == expected:
            print(f"  ok       {kind:<14} {identity:<26} {live}  {obj['id']}")
        else:
            drift += 1
            print(f"  DRIFT    {kind:<14} {identity:<26} live={live} expected={expected}  {obj['id']}")

    promo = find_promo("WELCOME10")
    print(f"  {'ok      ' if promo else 'MISSING '} promo          WELCOME10"
          f"{'':<18}{(' active=' + str(promo['active']) + '  ' + promo['id']) if promo else ''}")

    hook = find_webhook(WEBHOOK_URL)
    print(f"  {'ok      ' if hook else 'MISSING '} webhook        {WEBHOOK_URL}"
          f"{('  ' + hook['id'] + '  status=' + hook.get('status', '?')) if hook else ''}")

    if drift:
        print(f"\n{drift} price(s) DRIFTED from lib/pricing.ts. A live price that disagrees with the "
              f"page is the one defect this whole arrangement exists to prevent — fix before shipping.")
        return 1
    return 0


def cmd_apply(_args) -> int:
    p = read_pricing()
    who = whoami()
    print(f"account : {who['id']}  {who['name']}  ({'LIVE' if who['livemode'] else 'TEST'})\n")

    bottle = find_product("arthrisil-bottle")
    if bottle is None:
        bottle = call("POST", "/products", {
            "name": "Arthrisil",
            "description": "Natural joint support — 90 capsules, 30-day supply. NPN 80065384.",
            "metadata[slug]": "arthrisil-bottle",
            "metadata[npn]": "80065384",
            "images[0]": "https://arthrisil.com/brand/arthrisil-bottle.png",
            "shippable": "true",
        })
        print(f"  CREATED product        {bottle['id']}  {bottle['name']}")
    else:
        print(f"  exists  product        {bottle['id']}  {bottle['name']}")

    bundle = find_product("arthrisil-bundle-3")
    if bundle is None:
        bundle = call("POST", "/products", {
            "name": "Arthrisil — Buy 2, Get 1 Free",
            "description": f"{p['bottles']} bottles of Arthrisil for the price of two. "
                           f"{p['bottles']} x 90 capsules. NPN 80065384.",
            "metadata[slug]": "arthrisil-bundle-3",
            "metadata[npn]": "80065384",
            "images[0]": "https://arthrisil.com/brand/arthrisil-bottle.png",
            "shippable": "true",
        })
        print(f"  CREATED product        {bundle['id']}  {bundle['name']}")
    else:
        print(f"  exists  product        {bundle['id']}  {bundle['name']}")

    prices = [
        ("arthrisil_onetime_usd", bottle["id"], p["unit"], False, "One bottle"),
        ("arthrisil_monthly_usd", bottle["id"], p["subscription"], True, f"Monthly ({p['pct']}% off)"),
        ("arthrisil_bundle3_usd", bundle["id"], p["bundle"], False, f"Buy 2 get 1 free ({p['bottles']} bottles)"),
    ]
    for lookup, product_id, amount, recurring, nickname in prices:
        found = find_price(lookup)
        if found:
            flag = "" if found["unit_amount"] == amount else f"  !! DRIFT expected {amount}"
            print(f"  exists  price          {found['id']}  {lookup}  {found['unit_amount']}{flag}")
            continue
        payload = {
            "product": product_id, "currency": "usd", "unit_amount": str(amount),
            "lookup_key": lookup, "nickname": nickname,
        }
        if recurring:
            payload["recurring[interval]"] = "month"
        created = call("POST", "/prices", payload)
        print(f"  CREATED price          {created['id']}  {lookup}  {created['unit_amount']}")

    for name, amount in [("Standard shipping", p["shipping"]),
                         ("Shipping & handling", p["bundle_shipping"]),
                         ("Free shipping", 0)]:
        found = find_shipping_rate(name, amount)
        if found:
            print(f"  exists  shipping_rate  {found['id']}  {name}  {amount}")
            continue
        created = call("POST", "/shipping_rates", {
            "display_name": name, "type": "fixed_amount",
            "fixed_amount[amount]": str(amount), "fixed_amount[currency]": "usd",
            "delivery_estimate[minimum][unit]": "business_day",
            "delivery_estimate[minimum][value]": "3",
            "delivery_estimate[maximum][unit]": "business_day",
            "delivery_estimate[maximum][value]": "10",
        })
        print(f"  CREATED shipping_rate  {created['id']}  {name}  {amount}")

    promo = find_promo("WELCOME10")
    if promo:
        print(f"  exists  promo          {promo['id']}  WELCOME10  active={promo['active']}")
    else:
        # Reuse a matching coupon rather than minting another on every retry.
        coupon = next(
            (c for c in call("GET", "/coupons?limit=100").get("data", [])
             if c.get("name") == "10% welcome" and c.get("percent_off") == 10.0),
            None,
        )
        if coupon is None:
            coupon = call("POST", "/coupons",
                          {"percent_off": "10", "duration": "once", "name": "10% welcome"})
            print(f"  CREATED coupon         {coupon['id']}")
        # API 2026-08-26.dahlia replaced the flat `coupon` param with a
        # `promotion` hash; posting `coupon` returns parameter_unknown.
        promo = call("POST", "/promotion_codes", {
            "promotion[type]": "coupon", "promotion[coupon]": coupon["id"], "code": "WELCOME10",
        })
        print(f"  CREATED promo          {promo['id']}  WELCOME10")

    print("\nNothing was deleted or archived. Run `plan` to verify against lib/pricing.ts.")
    return 0


def cmd_portal(args) -> int:
    """Configure the Stripe Customer Portal — the cancellation mechanism.

    Two things make this the right vehicle rather than a page we build:

    1. IDENTITY. The site has no customer accounts, so "let me cancel" has to
       prove it is them. `login_page.enabled` gives a hosted page where the
       customer enters their email and STRIPE emails them the link. That works
       today, while our own outbound email does not.

    2. COMPLIANCE. The FTC's negative-option rule requires cancelling be no
       harder than subscribing. A vendor-hosted flow built for that rule is far
       easier to defend than a bespoke funnel, and it cannot drift into one.

    mode=at_period_end with proration_behavior=none is the "runs to the end of
    what they paid for" choice: no further charges, no refund, no surprise.
    """
    existing = [
        c for c in call("GET", "/billing_portal/configurations?limit=100&is_default=true").get("data", [])
    ]
    fields = {
        "business_profile[headline]": "Trytan Health — manage your Arthrisil subscription",
        "business_profile[privacy_policy_url]": "https://arthrisil.com/#faq",
        "business_profile[terms_of_service_url]": "https://arthrisil.com/#faq",
        "features[subscription_cancel][enabled]": "true",
        "features[subscription_cancel][mode]": "at_period_end",
        "features[subscription_cancel][proration_behavior]": "none",
        # The exit survey. It does NOT gate the cancel — it is asked alongside
        # it — so it stays the right side of "no harder than signing up", and it
        # is the only churn data this business would otherwise have.
        "features[subscription_cancel][cancellation_reason][enabled]": "true",
        "features[subscription_cancel][cancellation_reason][options][0]": "too_expensive",
        "features[subscription_cancel][cancellation_reason][options][1]": "unused",
        "features[subscription_cancel][cancellation_reason][options][2]": "low_quality",
        "features[subscription_cancel][cancellation_reason][options][3]": "switched_service",
        "features[subscription_cancel][cancellation_reason][options][4]": "other",
        # Customers expect to see what they were charged and to fix a dead card.
        # A portal that only cancels is a portal that only gets used to cancel.
        "features[invoice_history][enabled]": "true",
        "features[payment_method_update][enabled]": "true",
        "features[customer_update][enabled]": "true",
        "features[customer_update][allowed_updates][0]": "email",
        "features[customer_update][allowed_updates][1]": "address",
        "features[customer_update][allowed_updates][2]": "phone",
        "login_page[enabled]": "true",
    }

    if existing:
        config = call("POST", f"/billing_portal/configurations/{existing[0]['id']}", fields)
        action = "UPDATED"
    else:
        config = call("POST", "/billing_portal/configurations", fields)
        action = "CREATED"

    login_url = (config.get("login_page") or {}).get("url")
    if getattr(args, "json", False):
        print(json.dumps({
            "action": action.lower(), "id": config["id"], "is_default": config.get("is_default"),
            "login_url": login_url,
            "cancel_mode": ((config.get("features") or {}).get("subscription_cancel") or {}).get("mode"),
        }, indent=2))
        return 0

    print(f"portal {action}: {config['id']}  (default={config.get('is_default')})")
    print(f"cancel mode   : {((config.get('features') or {}).get('subscription_cancel') or {}).get('mode')}"
          f", prorate={((config.get('features') or {}).get('subscription_cancel') or {}).get('proration_behavior')}")
    print(f"login page    : {login_url or '(not generated)'}")
    print("\nPut that login URL in the site's SUBSCRIPTION_PORTAL_URL so /manage can link to it.")
    return 0


def cmd_webhook(_args) -> int:
    """Create the webhook endpoint and store its signing secret, unseen.

    Stripe returns the signing secret exactly once, at creation. It goes
    straight into .env.agents; only the key NAME is printed.
    """
    existing = find_webhook(WEBHOOK_URL)
    if existing:
        current = set(existing.get("enabled_events", []))
        wanted = set(WEBHOOK_EVENTS)
        if current != wanted:
            # Subscribe to any events added since the endpoint was created.
            # Updating never touches the signing secret, so this is safe to
            # re-run and does not invalidate the key already in .env.agents.
            updated = call(
                "POST",
                f"/webhook_endpoints/{existing['id']}",
                {"enabled_events[]": sorted(wanted)},
            )
            added = sorted(wanted - current)
            removed = sorted(current - wanted)
            print(f"endpoint UPDATED: {updated['id']}")
            if added:
                print(f"  + {', '.join(added)}")
            if removed:
                print(f"  - {', '.join(removed)}")
            print("  (signing secret unchanged)")
            return 0
        print(f"endpoint exists : {existing['id']}  status={existing.get('status')}")
        print(f"events          : {', '.join(sorted(current))}")
        print(
            "\nIts signing secret is shown only at creation, so it cannot be re-read here.\n"
            f"If {WEBHOOK_SECRET_KEY} is not already set, roll the secret in the Stripe\n"
            "dashboard and paste it in, or delete this endpoint and re-run."
        )
        return 0

    created = call("POST", "/webhook_endpoints", {
        "url": WEBHOOK_URL,
        "enabled_events[]": WEBHOOK_EVENTS,
        "description": "Arthrisil site — record paid orders",
        "api_version": API_VERSION,
    })
    secret = created.get("secret")
    if not secret:
        raise SystemExit("Stripe returned no signing secret; endpoint created but unusable.")

    names = _write_env({WEBHOOK_SECRET_KEY: secret})
    del secret  # not that it helps much, but it does not linger in a local either

    print(f"endpoint CREATED: {created['id']}")
    print(f"url             : {created['url']}")
    print(f"events          : {', '.join(created.get('enabled_events', []))}")
    print(f"api_version     : {created.get('api_version')}")
    print(f"stored in .env.agents (names only): {', '.join(names)}")
    print("\nNext: python scripts/integrations/wrangler_tool.py secrets-push --app arthrisil-website")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # Registered on the top-level parser AND each subparser, the way the other
    # tools here do it: argparse otherwise rejects `plan --json` outright.
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan", parents=[common], help="read-only: what exists, and does it match lib/pricing.ts")
    sub.add_parser("apply", parents=[common], help="create anything missing (never deletes)")
    sub.add_parser("webhook", parents=[common], help="create the webhook endpoint and store its secret")
    sub.add_parser("portal", parents=[common], help="configure the customer portal (the cancel path)")
    args = parser.parse_args()
    try:
        return {
            "plan": cmd_plan, "apply": cmd_apply,
            "webhook": cmd_webhook, "portal": cmd_portal,
        }[args.cmd](args)
    except StripeError as exc:
        print(f"Stripe error:\n{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
