"""Mint and place FINANCE_AGENT_TOKEN — Atlas's bearer for the OASIS Finances API.

The command center's /api/internal/finance/* routes accept exactly one bearer
(FINANCE_AGENT_TOKEN, >= 24 chars; see APPS/oasis-command-center/docs/
FINANCES_SUITE.md). Two sides must hold the SAME value:

  1. this repo's env store, under the Worker manifest's namespaced source
     (OASIS_COMMAND_CENTER__FINANCE_AGENT_TOKEN) — wrangler_tool secrets-push
     sends it to the Worker from there;
  2. Atlas's own store, CFO-Agent/.env.agents (FINANCE_AGENT_TOKEN), plus the
     API base URL, which Atlas's secret_loader reads.

Idempotent: an existing token is reused, never rotated by a re-run (rotation is
`--rotate`, which rewrites both sides together). Values are never printed —
only a short digest so the two sides can be compared.

Usage:
  python scripts/integrations/finance_agent_token.py status
  python scripts/integrations/finance_agent_token.py place [--rotate]
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.env_store import digest, parse_file, update_env_values  # noqa: E402
from lib.secret_loader import ENV_FILE  # noqa: E402

WORKER_SOURCE = "OASIS_COMMAND_CENTER__FINANCE_AGENT_TOKEN"
ATLAS_ENV = Path("C:/Users/User/APPS/CFO-Agent/.env.agents")
ATLAS_KEY = "FINANCE_AGENT_TOKEN"
ATLAS_BASE_KEY = "OASIS_FINANCE_API_BASE"
API_BASE = "https://oasisai.work"


def _read(path: Path) -> dict[str, str]:
    return parse_file(path) if path.exists() else {}


def status() -> int:
    bea = _read(ENV_FILE).get(WORKER_SOURCE) or ""
    atlas = _read(ATLAS_ENV).get(ATLAS_KEY) or ""
    print(f"bea  {WORKER_SOURCE}: {'set ' + digest(bea) if bea else 'absent'}")
    print(f"atlas {ATLAS_KEY}: {'set ' + digest(atlas) if atlas else 'absent'}")
    print(f"match: {bool(bea) and bea == atlas}")
    return 0 if bea and bea == atlas else 1


def place(rotate: bool) -> int:
    current = _read(ENV_FILE).get(WORKER_SOURCE) or ""
    token = current if current and len(current) >= 24 and not rotate else secrets.token_urlsafe(36)
    if token != current:
        update_env_values(ENV_FILE, {WORKER_SOURCE: token})
    atlas = _read(ATLAS_ENV)
    atlas_updates = {
        k: v
        for k, v in ((ATLAS_KEY, token), (ATLAS_BASE_KEY, API_BASE))
        if atlas.get(k) != v
    }
    if atlas_updates:
        update_env_values(ATLAS_ENV, atlas_updates)
    print(f"{'rotated' if rotate else ('minted' if token != current else 'reused')} token {digest(token)}; "
          f"atlas keys written: {sorted(atlas_updates) or 'none (already current)'}")
    print("next: wrangler_tool.py secrets-push --app oasis-command-center (the Worker reads it on its next request)")
    return status()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("place")
    p.add_argument("--rotate", action="store_true", help="replace the token on both sides")
    args = ap.parse_args(argv)
    return status() if args.cmd == "status" else place(args.rotate)


if __name__ == "__main__":
    raise SystemExit(main())
