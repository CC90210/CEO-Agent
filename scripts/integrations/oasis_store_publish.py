#!/usr/bin/env python
"""Publish a store product's tiers to Stripe, and optionally make it public.

    python scripts/integrations/oasis_store_publish.py month-kit
    python scripts/integrations/oasis_store_publish.py month-kit --status live

Thin runner around the app's own scripts/publish-product.ts so the pricing logic
has exactly ONE implementation (lib/stripe-publish.ts, shared with the admin
panel's "Sync prices to Stripe" button). Its job is credentials: the Turso and
Stripe values move from the agents env store into the child process's
environment and are never printed, logged, or returned.
"""
from __future__ import annotations

import argparse
import os
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

from lib.app_registry import app_dir  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402
import wrangler_tool as wt  # noqa: E402

SLUG = "oasis-store"
NEEDED = [
    "OASIS_STORE_TURSO_DATABASE_URL",
    "OASIS_STORE_TURSO_AUTH_TOKEN",
    "OASIS_STORE_STRIPE_SECRET_KEY",
]
OPTIONAL = ["OASIS_STORE_STRIPE_ACCOUNT", "OASIS_STORE__APP_URL"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", help="product slug, e.g. month-kit")
    ap.add_argument("--status", choices=["live", "unlisted"], help="also set the product status once every tier has a Price")
    args = ap.parse_args(argv)

    env_store = load_env()
    missing = [k for k in NEEDED if not env_store.get(k)]
    if missing:
        raise SystemExit(f"missing from the agents env: {', '.join(missing)}")

    child = os.environ.copy()
    for k in NEEDED + OPTIONAL:
        v = env_store.get(k)
        if v:
            child[k] = v

    cmd = [wt._npx(), "tsx", "scripts/publish-product.ts", args.slug]
    if args.status:
        cmd += ["--status", args.status]

    proc = subprocess.run(cmd, cwd=str(app_dir(SLUG)), env=child, text=True, encoding="utf-8", errors="replace")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
