#!/usr/bin/env python3
"""LendSaaS ETL API wrapper — READ-ONLY by design.

LendSaaS is David's servicing system ("my entire business... is ran on it").
Standing rule: NO write operations without Shlomo's explicit instructions —
this wrapper physically cannot POST/PUT/DELETE; every verb is a GET against
the ETL (read) API. The Partner (write) API is intentionally NOT implemented.

Auth: `LendSaas_API_Token` from the agents env (never printed). The ETL spec
(breezeadvance.lendtech.io/backend/api/docs/etl.html) authorizes via a bearer
token; we also fall back to X-API-KEY if bearer is rejected.

Usage:
  python scripts/integrations/lendsaas_tool.py smoke
  python scripts/integrations/lendsaas_tool.py leads [--limit 5]
  python scripts/integrations/lendsaas_tool.py lead <id>
  python scripts/integrations/lendsaas_tool.py payment-activity <lead_id>
  python scripts/integrations/lendsaas_tool.py upcoming-payments [<lead_id>]
  python scripts/integrations/lendsaas_tool.py transactions [--limit 5]
  python scripts/integrations/lendsaas_tool.py ach-schedule
  python scripts/integrations/lendsaas_tool.py positions
  python scripts/integrations/lendsaas_tool.py get <path>   # any ETL GET path
All output is JSON (sanitized; the token never appears).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001 — certifi fallback
    pass
import requests  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402

BASE = "https://breezeadvance.lendtech.io/backend/api/partners"
TIMEOUT = 45


def _token() -> str:
    env = load_env()
    for key in ("LendSaas_API_Token", "LENDSAAS_API_TOKEN", "LendSaaS_API_Token"):
        if env.get(key):
            return env[key].strip()
    print(json.dumps({"ok": False, "error": "LendSaas_API_Token not found in agents env"}))
    sys.exit(1)


def _get(path: str, params: dict | None = None) -> tuple[int, object, str]:
    """GET with bearer auth, X-API-KEY fallback. Returns (status, body, auth_mode)."""
    tok = _token()
    url = f"{BASE}/{path.lstrip('/')}"
    for mode, headers in (
        ("bearer", {"Authorization": f"Bearer {tok}", "Accept": "application/json"}),
        ("x-api-key", {"X-API-KEY": tok, "Accept": "application/json"}),
    ):
        r = requests.get(url, headers=headers, params=params or {}, timeout=TIMEOUT)
        if r.status_code not in (401, 403):
            try:
                return r.status_code, r.json(), mode
            except ValueError:
                return r.status_code, r.text[:2000], mode
    try:
        return r.status_code, r.json(), "both-rejected"  # type: ignore[possibly-undefined]
    except ValueError:
        return r.status_code, r.text[:2000], "both-rejected"  # type: ignore[possibly-undefined]


def _emit(status: int, body: object, auth: str, truncate: int | None = None) -> None:
    if truncate and isinstance(body, list):
        body = body[:truncate]
    print(json.dumps({"ok": 200 <= status < 300, "status": status, "auth": auth, "data": body},
                     indent=2, default=str)[:60000])


def main() -> None:
    p = argparse.ArgumentParser(description="LendSaaS ETL (read-only)")
    sub = p.add_subparsers(dest="verb", required=True)
    sub.add_parser("smoke")
    lp = sub.add_parser("leads"); lp.add_argument("--limit", type=int, default=5)
    ld = sub.add_parser("lead"); ld.add_argument("id")
    pa = sub.add_parser("payment-activity"); pa.add_argument("lead_id")
    up = sub.add_parser("upcoming-payments"); up.add_argument("lead_id", nargs="?")
    tx = sub.add_parser("transactions"); tx.add_argument("--limit", type=int, default=5)
    sub.add_parser("ach-schedule")
    sub.add_parser("positions")
    gp = sub.add_parser("get"); gp.add_argument("path")
    a = p.parse_args()

    if a.verb == "smoke":
        status, body, auth = _get("leads")
        ok = 200 <= status < 300
        sample = body[:1] if isinstance(body, list) else body
        print(json.dumps({"ok": ok, "status": status, "auth": auth,
                          "leads_type": type(body).__name__,
                          "leads_count": len(body) if isinstance(body, list) else None,
                          "sample": sample}, indent=2, default=str)[:8000])
        sys.exit(0 if ok else 1)
    if a.verb == "leads":
        _emit(*_get("leads"), truncate=a.limit)
    elif a.verb == "lead":
        _emit(*_get(f"lead/{a.id}"))
    elif a.verb == "payment-activity":
        _emit(*_get(f"lead/{a.lead_id}/payment-activity"))
    elif a.verb == "upcoming-payments":
        _emit(*_get(f"lead/{a.lead_id}/upcoming-payments" if a.lead_id else "upcoming-payments"))
    elif a.verb == "transactions":
        _emit(*_get("transactions"), truncate=a.limit)
    elif a.verb == "ach-schedule":
        _emit(*_get("ach-schedule"))
    elif a.verb == "positions":
        _emit(*_get("positions"))
    elif a.verb == "get":
        path = a.path.lstrip("/")
        _emit(*_get(path))


if __name__ == "__main__":
    main()
