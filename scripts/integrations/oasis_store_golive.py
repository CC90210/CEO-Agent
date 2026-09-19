#!/usr/bin/env python
"""Take the Oasis Solutions store from "I have a Stripe key" to "it is selling", in one command.

    python scripts/integrations/oasis_store_golive.py check     # what is ready, what is missing — changes nothing
    python scripts/integrations/oasis_store_golive.py run        # do every remaining step, in order, stopping at the first real failure
    python scripts/integrations/oasis_store_golive.py run --yes  # same, without the confirmation prompt

WHY THIS EXISTS. Going live is eight steps across three tools, and the failure
modes are silent: a webhook pointed at the wrong origin, prices synced to the
wrong Stripe account, a promo code the storefront advertises but Checkout
rejects. Each step here VERIFIES rather than assumes, and the run stops at the
first real problem instead of reporting a green finish over a broken store.

The only prerequisite is OASIS_STORE_STRIPE_SECRET_KEY in the agents env.
Nothing here prints a secret.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from lib.secret_loader import load_env  # noqa: E402

APP = "oasis-store"
TOOL = PROJECT_ROOT / "scripts" / "integrations"
OK, BAD, WARN = "  ok   ", "  FAIL ", "  warn "


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def py(script: str, *args: str) -> list[str]:
    return [sys.executable, str(TOOL / script), *args]


# ----------------------------------------------------------------- readiness

def check(verbose: bool = True) -> dict:
    env = load_env()
    state: dict = {}

    state["stripe_key"] = bool(env.get("OASIS_STORE_STRIPE_SECRET_KEY"))
    state["stripe_live_mode"] = (env.get("OASIS_STORE_STRIPE_SECRET_KEY") or "").startswith("sk_live_")
    state["webhook_secret"] = bool(env.get("OASIS_STORE_STRIPE_WEBHOOK_SECRET"))
    state["turso"] = bool(env.get("OASIS_STORE_TURSO_DATABASE_URL"))
    state["app_url"] = env.get("OASIS_STORE__APP_URL", "")
    state["mailbox"] = bool(env.get("OASIS_STORE_MAIL_USER") and env.get("OASIS_STORE_MAIL_APP_PASSWORD"))
    state["supplier"] = bool(env.get("CJ_API_KEY"))
    # The daemon resolves the operator chat from TELEGRAM_ALLOWED_USERS when
    # TELEGRAM_CHAT_ID is absent, matching the rest of the fleet.
    state["telegram"] = bool(env.get("TELEGRAM_BOT_TOKEN") and (env.get("TELEGRAM_CHAT_ID") or env.get("TELEGRAM_ALLOWED_USERS")))

    try:
        import oasis_store_db as db

        products = db.query("SELECT slug, status FROM products")
        state["products_live"] = [p["slug"] for p in products if p["status"] in ("live", "unlisted")]
        state["products_total"] = len(products)
        tiers = db.query(
            "SELECT COUNT(*) AS n FROM product_tiers t JOIN products p ON p.id = t.product_id "
            "WHERE p.status IN ('live','unlisted') AND (t.stripe_subscribe_price_id IS NULL OR t.stripe_onetime_price_id IS NULL)"
        )
        state["tiers_missing_prices"] = int(tiers[0]["n"])
        state["owner_exists"] = int(db.query("SELECT COUNT(*) AS n FROM users")[0]["n"]) > 0
    except Exception as exc:  # noqa: BLE001 — the report must survive a DB outage
        state["db_error"] = str(exc)[:200]

    if verbose:
        print(f"\nOASIS STORE — GO-LIVE READINESS ({state.get('app_url') or 'no APP_URL'})\n")
        print("  Only you can do these:")
        print(f"{OK if state['stripe_key'] else BAD} Stripe key         OASIS_STORE_STRIPE_SECRET_KEY"
              + ("" if state["stripe_key"] else "   <- THE blocker: no key, no sales"))
        if state["stripe_key"]:
            print(f"{OK if state['stripe_live_mode'] else WARN} Stripe mode        {'LIVE' if state['stripe_live_mode'] else 'TEST key — real cards will not work'}")
        print(f"{OK if state['mailbox'] else WARN} Store mailbox      OASIS_STORE_MAIL_USER / _APP_PASSWORD"
              + ("" if state["mailbox"] else "   <- every email sits queued until this exists"))
        print(f"{OK if state['supplier'] else WARN} Supplier API       CJ_API_KEY"
              + ("" if state["supplier"] else "   <- orders route to Telegram as manual cards without it"))
        print(f"{OK if state['telegram'] else WARN} Operator alerts    TELEGRAM_BOT_TOKEN / _CHAT_ID")
        print("\n  Automated (this script does them):")
        print(f"{OK if state['turso'] else BAD} Database           {'connected' if state['turso'] else 'missing'}")
        print(f"{OK if state['webhook_secret'] else BAD} Stripe webhook     {'registered' if state['webhook_secret'] else 'not registered yet'}")
        if "db_error" in state:
            print(f"{BAD} Database read      {state['db_error']}")
        else:
            print(f"{OK if state['owner_exists'] else WARN} Admin owner        {'created' if state['owner_exists'] else 'not created — run oasis_store_db.py invite'}")
            live = state.get("products_live", [])
            print(f"{OK if live else WARN} Sellable products  {', '.join(live) if live else 'none live/unlisted'}")
            missing = state.get("tiers_missing_prices", 0)
            print(f"{OK if not missing else BAD} Stripe prices      {'all tiers synced' if not missing else f'{missing} tier(s) have no Stripe price — publish in admin'}")
        print()
    return state


# ----------------------------------------------------------------- the run

def golive(args) -> int:
    state = check(verbose=True)

    if not state["stripe_key"]:
        print("STOP. Add OASIS_STORE_STRIPE_SECRET_KEY to .env.agents first.")
        print("  1. Open a Stripe account for the consumer store (sibling to your existing ones).")
        print("  2. Developers -> API keys -> copy the secret key.")
        print("  3. Add the line OASIS_STORE_STRIPE_SECRET_KEY=sk_... to .env.agents")
        print("  4. Re-run this command.")
        return 2
    if not state["turso"]:
        print("STOP. Database credentials missing — run: turso_admin.py create --db oasis-store --write-env")
        return 2

    if not args.yes:
        mode = "LIVE (real money)" if state["stripe_live_mode"] else "TEST"
        reply = input(f"\nProceed with go-live against a {mode} Stripe key? [y/N] ").strip().lower()
        if reply != "y":
            print("aborted — nothing changed")
            return 1

    steps: list[tuple[str, list[str], bool]] = [
        ("Confirm the Stripe account is the store's own, not an empire account",
         py("oasis_store_stripe_setup.py", "whoami", *(["--allow-shared-account"] if getattr(args, "allow_shared_account", False) else [])), True),
        ("Register the webhook endpoint", py("oasis_store_stripe_setup.py", "webhook"), True),
        ("Configure the customer portal (cards + invoices only; cancellation stays in our UI)", py("oasis_store_stripe_setup.py", "portal"), True),
        ("Create the first-order promo code", py("oasis_store_stripe_setup.py", "promo"), False),
        ("Apply any pending database migrations", py("oasis_store_db.py", "migrate"), True),
        ("Push secrets to the Worker", py("wrangler_tool.py", "secrets-push", "--app", APP), True),
        ("Deploy the Worker", py("wrangler_tool.py", "deploy", "--app", APP, "--skip-secrets"), True),
        ("Verify catalog prices match Stripe", py("oasis_store_stripe_setup.py", "plan"), False),
        ("Check Stripe Tax registrations", py("oasis_store_stripe_setup.py", "tax-check"), False),
    ]

    print()
    for i, (label, cmd, fatal) in enumerate(steps, 1):
        print(f"[{i}/{len(steps)}] {label}")
        code, out = run(cmd)
        tail = "\n".join(out.splitlines()[-6:])
        if code == 0:
            print(f"{OK} {tail[:600]}\n" if tail else f"{OK} done\n")
            continue
        print(f"{BAD if fatal else WARN} exit {code}\n{tail[:900]}\n")
        if fatal:
            print(f"STOPPED at step {i}. Fix the above and re-run — completed steps are idempotent.")
            return 1

    print("\nGO-LIVE SEQUENCE COMPLETE. Final state:\n")
    check(verbose=True)
    print("Still yours to do, in order of what unblocks revenue:")
    if not state["mailbox"]:
        print("  - Store mailbox (Google, 2-step + app password) -> .env.agents, then start the VPS daemon")
    if not state["supplier"]:
        print("  - Supplier account + API key, or keep manual fulfilment via Telegram")
    print("  - Put a real product live in /admin and press 'Sync prices to Stripe'")
    print("  - Place one real test order end to end before spending a dollar on traffic")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("run")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument("--allow-shared-account", action="store_true", dest="allow_shared_account",
                   help="allow an existing empire Stripe account (speed over isolation — see whoami)")
    args = parser.parse_args(argv)
    if args.cmd == "check":
        check(verbose=True)
        return 0
    return golive(args)


if __name__ == "__main__":
    sys.exit(main())
