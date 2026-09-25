#!/usr/bin/env python3
"""wise_tool — read-only access to OASIS's Wise business account.

The command center's invoices print Wise RECEIVING details (the bank details a
client pays into) and reconcile incoming Wise deposits against open invoices
(APPS/oasis-command-center/lib/founders-finances/wise-io.ts). This tool is the
sanctioned way for an agent to look at the same account: probe an endpoint's
real response shape before code is written against it, check a balance, or see
what arrived.

READ-ONLY BY CONSTRUCTION. Every verb is a GET. Transfers, quotes, recipients
and conversions are deliberately absent: moving money is an operator decision,
and a tool that can look should not also be able to pay.

Credentials: WISE_API_TOKEN + WISE_PROFILE_ID through lib.secret_loader. The
token is sent only in the Authorization header and is never printed. Account
numbers and IBANs in receiving details are masked to their last 4 digits in
all output — these are the business's bank coordinates, and a terminal log is
not where they belong.

Usage:
    python scripts/integrations/wise_tool.py profiles [--json]
    python scripts/integrations/wise_tool.py balances [--json]
    python scripts/integrations/wise_tool.py account-details [--currency CAD] [--json]
    python scripts/integrations/wise_tool.py activities [--since 2026-09-01] [--json]
    python scripts/integrations/wise_tool.py statement --currency CAD [--since 2026-09-01] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.secret_loader import load_env  # noqa: E402

BASE_URL = "https://api.transferwise.com"
# A named client: an edge that blocks the default Python user agent answers
# with an HTML error page, which reads like an API outage.
USER_AGENT = "oasis-bravo-wise-tool/1.0 (+https://oasisai.work)"
TIMEOUT_S = 20

# Detail fields that identify THE account (not the bank): masked everywhere.
_SENSITIVE_LABEL = re.compile(r"account\s*(number|no\.?)|accountnumber|iban|card", re.IGNORECASE)
# Any other run of 7+ digits (spaces allowed inside, as in an IBAN) is masked
# too. Dashes are NOT joined, so a date or a sort code is left readable.
_LONG_DIGITS = re.compile(r"\d[\d ]{5,}\d")
# Keys whose values are labels, ids or timestamps — never bank coordinates.
_PLAIN_KEYS = frozenset({
    "type", "title", "label", "name", "scheme", "accountType", "currency", "code",
    "id", "date", "referenceNumber", "profileId", "balanceId", "createdOn", "updatedOn",
    "creationTime", "modificationTime", "intervalStart", "intervalEnd",
})


class WiseApiError(RuntimeError):
    def __init__(self, status: int, path: str, detail: str):
        super().__init__(f"Wise GET {path} failed: HTTP {status}{' - ' + detail if detail else ''}")
        self.status = status
        self.path = path


def build_request(token: str, path: str, params: dict[str, Any] | None = None) -> tuple[str, dict[str, str]]:
    """PURE. URL + headers for a GET. Parameters with a None value are dropped."""
    if not path.startswith("/"):
        raise ValueError("path must start with /")
    query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
    url = f"{BASE_URL}{path}{'?' + query if query else ''}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    return url, headers


def mask_value(value: str) -> str:
    """'12345678' -> '****5678'. Anything with fewer than 5 digits is left alone."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 5:
        return value
    return f"****{digits[-4:]}"


def mask_long_digit_runs(text: str) -> str:
    """Mask every run of 7+ digits (spaces allowed inside) to its last 4."""
    return _LONG_DIGITS.sub(lambda m: mask_value(m.group(0)) if len(re.sub(r"\D", "", m.group(0))) >= 7 else m.group(0), text)


def sanitize_details(node: Any, label: str = "") -> Any:
    """Deep-copy a receiving-details payload with account numbers masked.

    A value is masked when its own key, or the title/type of the detail object
    it sits in, names an account number or IBAN; any other long digit run is
    masked too, so a field Wise adds later cannot slip through unmasked.
    """
    if isinstance(node, dict):
        own = " ".join(str(node.get(k, "")) for k in ("type", "title", "label", "name", "accountType"))
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k in _PLAIN_KEYS and not isinstance(v, (dict, list)):
                out[k] = v
            elif isinstance(v, str) and _SENSITIVE_LABEL.search(f"{label} {own} {k}"):
                out[k] = mask_value(v)
            else:
                out[k] = sanitize_details(v, own if isinstance(v, (dict, list)) else label)
        return out
    if isinstance(node, list):
        return [sanitize_details(x, label) for x in node]
    if isinstance(node, str):
        return mask_long_digit_runs(node)
    return node


def _credentials() -> tuple[str, str]:
    env = load_env(required=["WISE_API_TOKEN", "WISE_PROFILE_ID"])
    return env["WISE_API_TOKEN"].strip(), env["WISE_PROFILE_ID"].strip()


def wise_get(path: str, params: dict[str, Any] | None = None) -> Any:
    import requests

    token, _ = _credentials()
    url, headers = build_request(token, path, params)
    res = requests.get(url, headers=headers, timeout=TIMEOUT_S)
    if res.status_code >= 400:
        detail = ""
        try:
            body = res.json()
            detail = str(body.get("message") or body.get("error") or body.get("errors") or "")[:200]
        except ValueError:
            detail = res.text[:120].replace("\n", " ")
        if res.status_code == 403 and res.headers.get("x-2fa-approval"):
            detail = "this endpoint needs Strong Customer Authentication (x-2fa-approval) — not available to a plain API token"
        raise WiseApiError(res.status_code, path.split("?")[0], detail)
    return res.json()


def _since(value: str | None, days: int = 30) -> str:
    if value:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def cmd_profiles(_args) -> Any:
    return wise_get("/v2/profiles")


def cmd_balances(_args) -> Any:
    _, profile = _credentials()
    return wise_get(f"/v4/profiles/{profile}/balances", {"types": "STANDARD"})


def _balance_for(profile: str, currency: str) -> dict:
    balances = wise_get(f"/v4/profiles/{profile}/balances", {"types": "STANDARD"})
    match = next((b for b in balances if isinstance(b, dict) and b.get("currency") == currency), None)
    if not match:
        raise WiseApiError(404, "balances", f"no {currency} balance on this profile")
    return match


def _statement(profile: str, balance: dict, since: str, days: int = 30) -> dict:
    end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return wise_get(
        f"/v1/profiles/{profile}/balance-statements/{balance['id']}/statement.json",
        {"currency": balance["currency"], "intervalStart": since, "intervalEnd": end, "type": "COMPACT"},
    )


def cmd_account_details(args) -> Any:
    """Receiving details per currency, LABELLED as Wise labels them.

    WHY the statement and not /v1/profiles/{id}/account-details: probed live
    2026-09-24, that endpoint answers 403 access.denied for this (read-only)
    token. The balance statement carries the same coordinates with Wise's own
    scheme names ("Institution number", "Transit number", "Routing number",
    "Swift/BIC") — the legacy /v1/borderless-accounts bankDetails does not
    carry the CAD transit number at all. A one-day interval keeps it cheap.
    """
    _, profile = _credentials()
    currencies = [args.currency.upper()] if args.currency else ["CAD", "USD"]
    out = []
    for cur in currencies:
        stmt = _statement(profile, _balance_for(profile, cur), _since(None, days=1))
        live = [d for d in stmt.get("bankDetails") or [] if isinstance(d, dict) and not d.get("deprecated")]
        out.append({"currency": cur, "holder": (stmt.get("accountHolder") or {}).get("businessName"), "bankDetails": live})
    return sanitize_details(out)


def cmd_activities(args) -> Any:
    _, profile = _credentials()
    return wise_get(f"/v1/profiles/{profile}/activities", {"since": _since(args.since), "size": 100})


def cmd_statement(args) -> Any:
    _, profile = _credentials()
    balance = _balance_for(profile, args.currency.upper())
    return sanitize_details(_statement(profile, balance, _since(args.since)))


def _print_human(cmd: str, data: Any) -> None:
    if cmd == "profiles":
        for p in data if isinstance(data, list) else []:
            print(f"{p.get('id')}  {p.get('type')}  {p.get('fullName') or p.get('businessName') or ''}")
    elif cmd == "balances":
        for b in data if isinstance(data, list) else []:
            amt = b.get("amount") or {}
            print(f"{b.get('currency')}  {amt.get('value')}  (balance id {b.get('id')})")
    elif cmd == "activities":
        for a in (data or {}).get("activities", []):
            title = re.sub(r"<[^>]+>", "", str(a.get("title") or ""))
            print(f"{a.get('createdOn')}  {a.get('type')}  {a.get('status')}  {a.get('primaryAmount')}  {title}")
    else:
        print(json.dumps(data, indent=2, ensure_ascii=True))


COMMANDS = {
    "profiles": cmd_profiles,
    "balances": cmd_balances,
    "account-details": cmd_account_details,
    "activities": cmd_activities,
    "statement": cmd_statement,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("profiles", "balances"):
        sub.add_parser(name).add_argument("--json", action="store_true")
    p = sub.add_parser("account-details")
    p.add_argument("--currency", default="")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("activities")
    p.add_argument("--since", default=None, help="YYYY-MM-DD (default: 30 days ago)")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("statement")
    p.add_argument("--currency", required=True)
    p.add_argument("--since", default=None, help="YYYY-MM-DD (default: 30 days ago)")
    p.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        data = COMMANDS[args.cmd](args)
    except WiseApiError as e:
        print(json.dumps({"ok": False, "status": e.status, "error": str(e)}) if args.json else str(e), file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"not configured: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=True))
    else:
        _print_human(args.cmd, data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
