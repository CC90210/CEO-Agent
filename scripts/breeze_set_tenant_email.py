"""Wire the BreezeAdvance tenant's email sender via the funder Settings UI.

Sealed-credential pattern: loads GMAIL_USER / GMAIL_APP_PASSWORD through
lib.secret_loader (audit-logged) and TYPES them into the production
/lender/settings Email form as the QA funder (owner role). Values never
print to stdout, never enter the agent context. This exercises the exact
per-tenant path David will later use with his own mailbox — swapping to
admin@breezeadvance.com is the same form, no redeploy.

Usage:
  python scripts/breeze_set_tenant_email.py                  # plan only; no login/write
  python scripts/breeze_set_tenant_email.py --apply          # set creds + save
  python scripts/breeze_set_tenant_email.py --apply --test   # also send test email
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from lib.secret_loader import load_env  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

CAPABILITY_META = {
    "category": "client.onboarding",
    "lifecycle": "one_off",
    "risk": "external_write",
    "triggers": ["configure breeze tenant email", "set breeze sender", "breeze email setup"],
    "owner": "bravo",
    "project": "breeze",
    "bridge": {"visible": False},
}

BASE = "https://breeze-portal-mu.vercel.app"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true", help="log in and save the sealed sender credentials"
    )
    parser.add_argument(
        "--test", action="store_true", help="send a test email after saving (requires --apply)"
    )
    args = parser.parse_args()
    if args.test and not args.apply:
        parser.error("--test requires --apply")
    if not args.apply:
        print("dry_run=true writes_skipped=true target=breeze_tenant_email_settings")
        return 0

    send_test = args.test
    env = load_env(
        required=[
            "GMAIL_USER",
            "GMAIL_APP_PASSWORD",
            "BREEZE_QA_FUNDER_EMAIL",
            "BREEZE_QA_FUNDER_PASSWORD",
        ]
    )
    gmail_user = env["GMAIL_USER"]
    gmail_pass = env["GMAIL_APP_PASSWORD"]
    qa_funder = env["BREEZE_QA_FUNDER_EMAIL"]
    qa_password = env["BREEZE_QA_FUNDER_PASSWORD"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{BASE}/funder-login", wait_until="networkidle")
        page.fill('input[type="email"]', qa_funder)
        page.fill('input[type="password"]', qa_password)
        page.click('button[type="submit"]')
        page.wait_for_url("**/lender/**", timeout=30000)
        print("[ok] funder session established")

        page.goto(f"{BASE}/lender/settings", wait_until="networkidle")
        # Email sender card: address input (placeholder you@yourcompany.com)
        # + app-password input (placeholder mentions app password / saved dots).
        page.fill('input[placeholder="you@yourcompany.com"]', gmail_user)
        pw_input = page.locator(
            'input[placeholder*="app password"], input[placeholder*="(saved)"]'
        ).first
        pw_input.fill(gmail_pass)

        # The Email card's own Save button — scope to the card containing the
        # "Send test email" button so we don't hit Branding/Plaid saves.
        card = page.locator("section,div").filter(
            has=page.get_by_role("button", name="Send test email")
        ).last
        card.get_by_role("button", name="Save", exact=False).first.click()
        time.sleep(3)
        print("[ok] email sender saved (tenant-level, encrypted in DB)")

        if send_test:
            page.get_by_role("button", name="Send test email").click()
            time.sleep(5)
            print("[ok] test email requested — verify receipt in the inbox")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
