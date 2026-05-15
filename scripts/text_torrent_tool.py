"""
TextTorrent CLI Tool — direct API client for SMS blast + analytics + local-
area-code phone management.

Phase 5.1 of the SunBiz CRM build (2026-05-15). Replaces the prior
"TextTorrent as Twilio relabel" stopgap with a real TT API client. TT's
actual API surface (analytics on delivery / conversions / which list
generated the most engagement, plus area-code-matched phone-number
purchase for local-presence dialing) doesn't map onto Twilio's; conflating
them gave SunBiz operators a worse UI than either platform provides
natively.

Usage:
  python scripts/text_torrent_tool.py blast --list <list_id> --message "..." [--from-label "Solara"]
  python scripts/text_torrent_tool.py send --to <e164> --message "..."
  python scripts/text_torrent_tool.py lists [--limit 25]
  python scripts/text_torrent_tool.py list-stats --list <list_id>
  python scripts/text_torrent_tool.py purchase-number --area-code 416 [--label "Toronto local"]
  python scripts/text_torrent_tool.py numbers
  python scripts/text_torrent_tool.py status

All commands support --json for agent-consumable output.

Credentials (in .env.agents):
  TEXTTORRENT_API_KEY      bearer token
  TEXTTORRENT_API_URL      defaults to https://api.texttorrent.com/v1
  TEXTTORRENT_DEFAULT_FROM optional sender label override

Exit codes:
  0  success
  1  user error (missing args, bad credentials)
  2  API error (4xx / 5xx from TT)
  3  network error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print(
        "ERROR: 'requests' package not installed. Run: pip install requests",
        file=sys.stderr,
    )
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_API_URL = "https://api.texttorrent.com/v1"
DEFAULT_TIMEOUT_S = 30


# ─────────────────────────────────────────────────────────────────────
# Credentials loading — mirrors stripe_tool.py / google_tool.py pattern
# ─────────────────────────────────────────────────────────────────────


def load_env() -> dict:
    """Load .env.agents via the shared secret loader. Falls back to a
    direct read if the loader isn't importable (matches the resilience
    pattern stripe_tool uses)."""
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from lib.secret_loader import load_env as _load  # type: ignore
        return _load()
    except Exception:
        pass
    env_path = REPO_ROOT / ".env.agents"
    if not env_path.exists():
        return {}
    out: dict = {}
    with env_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                out[key.strip()] = value.strip()
    return out


def resolve_credentials() -> tuple[str, str, str | None]:
    """Returns (api_key, api_url, default_from). Exits on missing key."""
    env = load_env()
    api_key = (env.get("TEXTTORRENT_API_KEY") or os.environ.get("TEXTTORRENT_API_KEY") or "").strip()
    if not api_key:
        print(
            "ERROR: TEXTTORRENT_API_KEY missing in .env.agents. Sign up at "
            "https://texttorrent.com/ and paste the key into your .env.agents.",
            file=sys.stderr,
        )
        sys.exit(1)
    api_url = (
        env.get("TEXTTORRENT_API_URL")
        or os.environ.get("TEXTTORRENT_API_URL")
        or DEFAULT_API_URL
    ).rstrip("/")
    default_from = env.get("TEXTTORRENT_DEFAULT_FROM") or os.environ.get("TEXTTORRENT_DEFAULT_FROM")
    return api_key, api_url, default_from


# ─────────────────────────────────────────────────────────────────────
# Tiny HTTP wrapper — kept minimal because the actual TT REST shape is
# best confirmed against operator docs. The endpoint paths below match
# TT's public conventions as of 2026-05-15; if TT's docs disagree, the
# fix is one line per command + verify against the actual response shape.
# ─────────────────────────────────────────────────────────────────────


class TTError(Exception):
    """Raised on non-2xx responses. exit_code distinguishes API vs network."""

    def __init__(self, message: str, exit_code: int):
        super().__init__(message)
        self.exit_code = exit_code


def _request(method: str, path: str, *, json_body: dict | None = None, params: dict | None = None) -> Any:
    api_key, api_url, _ = resolve_credentials()
    url = f"{api_url}/{path.lstrip('/')}"
    headers = {
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json",
        "user-agent": "oasis-bravo/text-torrent-tool/1.0",
    }
    try:
        r = requests.request(
            method,
            url,
            headers=headers,
            json=json_body,
            params=params,
            timeout=DEFAULT_TIMEOUT_S,
        )
    except requests.RequestException as e:
        raise TTError(f"network error contacting TextTorrent: {e}", 3) from e

    if r.status_code >= 400:
        # TT errors typically include a JSON body with {error, message};
        # surface both raw and parsed so operators can debug from logs.
        try:
            body = r.json()
        except ValueError:
            body = r.text[:400]
        raise TTError(f"HTTP {r.status_code} from TT: {body}", 2)

    try:
        return r.json()
    except ValueError:
        return {"raw": r.text}


# ─────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────


def cmd_blast(args) -> dict:
    """Send to a TextTorrent list. Blasts are best for >50 recipients;
    single sends use cmd_send."""
    body = {"list_id": args.list, "message": args.message}
    if args.from_label:
        body["from_label"] = args.from_label
    elif resolve_credentials()[2]:
        body["from_label"] = resolve_credentials()[2]
    return _request("POST", "/messages/blast", json_body=body)


def cmd_send(args) -> dict:
    """Send to a single E.164 number. TextTorrent picks the
    matching-area-code outbound number automatically when the lead's
    number falls in a region TT has purchased presence for."""
    body = {"to": args.to, "message": args.message}
    if args.from_label:
        body["from_label"] = args.from_label
    return _request("POST", "/messages", json_body=body)


def cmd_lists(args) -> dict:
    """Return the operator's TT contact lists."""
    return _request("GET", "/lists", params={"limit": args.limit})


def cmd_list_stats(args) -> dict:
    """Engagement analytics for one list. Includes delivery rate,
    conversion rate (TT-side definition), and per-number bounce data."""
    return _request("GET", f"/lists/{args.list}/stats")


def cmd_purchase_number(args) -> dict:
    """Purchase a phone number with the requested area code so outbound
    SMS shows a local-presence sender. TT bills the operator's TT
    account directly; OASIS doesn't intermediate billing."""
    body = {"area_code": args.area_code}
    if args.label:
        body["label"] = args.label
    return _request("POST", "/numbers/purchase", json_body=body)


def cmd_numbers(_args) -> dict:
    """List phone numbers the operator owns in TT."""
    return _request("GET", "/numbers")


def cmd_status(_args) -> dict:
    """Account-level status: balance / quota / billing health.
    Useful for monitoring before drip sequences push large blasts."""
    return _request("GET", "/account")


# ─────────────────────────────────────────────────────────────────────
# Argparse
# ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="text_torrent_tool",
        description="TextTorrent CLI — direct API client for SMS blast, analytics, and local-area phone management.",
    )
    p.add_argument("--json", action="store_true", help="Output JSON (agent-consumable)")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("blast", help="Send a message to a TT list")
    b.add_argument("--list", required=True, help="TT list ID")
    b.add_argument("--message", required=True, help="Message body (160 chars optimal)")
    b.add_argument("--from-label", default=None, help="Sender label, e.g. 'Solara'")
    b.set_defaults(func=cmd_blast)

    s = sub.add_parser("send", help="Send to a single E.164 number")
    s.add_argument("--to", required=True, help="E.164 phone number, e.g. +14165550123")
    s.add_argument("--message", required=True)
    s.add_argument("--from-label", default=None)
    s.set_defaults(func=cmd_send)

    lst = sub.add_parser("lists", help="List operator's TT contact lists")
    lst.add_argument("--limit", type=int, default=25)
    lst.set_defaults(func=cmd_lists)

    ls = sub.add_parser("list-stats", help="Engagement analytics for one list")
    ls.add_argument("--list", required=True)
    ls.set_defaults(func=cmd_list_stats)

    pn = sub.add_parser("purchase-number", help="Buy a local-area outbound number")
    pn.add_argument("--area-code", required=True, help="3-digit area code, e.g. 416")
    pn.add_argument("--label", default=None, help="Display label, e.g. 'Toronto local'")
    pn.set_defaults(func=cmd_purchase_number)

    nums = sub.add_parser("numbers", help="List operator-owned phone numbers")
    nums.set_defaults(func=cmd_numbers)

    st = sub.add_parser("status", help="Account balance + quota + billing health")
    st.set_defaults(func=cmd_status)

    args = p.parse_args(argv)

    try:
        result = args.func(args)
    except TTError as e:
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return e.exit_code
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130

    if args.json:
        print(json.dumps({"ok": True, "result": result}, default=str, indent=2))
    else:
        # Pretty-print for terminal use.
        if isinstance(result, (dict, list)):
            print(json.dumps(result, default=str, indent=2))
        else:
            print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
