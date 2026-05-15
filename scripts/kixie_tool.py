"""
Kixie CLI Tool — outbound dialer + click-to-call + live transfer.

Phase 5.2 of the SunBiz CRM build (2026-05-15). Per the SunBiz meeting,
Kixie covers the "live transfer + outbound calling" lane that complements
TextTorrent (SMS blast) and Twilio (personalized 1:1 SMS). Multi-channel
contact distribution is what keeps SunBiz numbers from getting marked
as spam.

Kixie's public API: https://docs.kixie.com/

Usage:
  python scripts/kixie_tool.py call --to <e164> --agent <agent_email>
  python scripts/kixie_tool.py click-to-call --lead-id <uuid> --to <e164>
  python scripts/kixie_tool.py transfer --call-id <id> --to <agent_email>
  python scripts/kixie_tool.py agents
  python scripts/kixie_tool.py status

Credentials (in .env.agents):
  KIXIE_API_KEY        bearer token from https://app.kixie.com/settings/api
  KIXIE_BUSINESS_ID    Kixie business ID (visible in URL after login)
  KIXIE_API_URL        defaults to https://apig.kixie.com/app/event
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
    print("ERROR: 'requests' package not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_API_URL = "https://apig.kixie.com/app/event"
DEFAULT_TIMEOUT_S = 30


def load_env() -> dict:
    """Mirror text_torrent_tool / stripe_tool credential-loading pattern."""
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


def resolve_credentials() -> tuple[str, str, str]:
    """Returns (api_key, business_id, api_url). Exits on missing."""
    env = load_env()
    api_key = (env.get("KIXIE_API_KEY") or os.environ.get("KIXIE_API_KEY") or "").strip()
    business_id = (
        env.get("KIXIE_BUSINESS_ID") or os.environ.get("KIXIE_BUSINESS_ID") or ""
    ).strip()
    if not api_key:
        print(
            "ERROR: KIXIE_API_KEY missing in .env.agents. Get one from https://app.kixie.com/settings/api",
            file=sys.stderr,
        )
        sys.exit(1)
    if not business_id:
        print(
            "ERROR: KIXIE_BUSINESS_ID missing in .env.agents. Look at the URL when logged in to app.kixie.com — the numeric ID after /business/.",
            file=sys.stderr,
        )
        sys.exit(1)
    api_url = (
        env.get("KIXIE_API_URL")
        or os.environ.get("KIXIE_API_URL")
        or DEFAULT_API_URL
    ).rstrip("/")
    return api_key, business_id, api_url


class KixieError(Exception):
    def __init__(self, message: str, exit_code: int):
        super().__init__(message)
        self.exit_code = exit_code


def _request(eventname: str, params: dict) -> Any:
    """Kixie's API is a single POST endpoint that takes an `eventname`
    parameter to dispatch. Mirror that shape rather than fighting it."""
    api_key, business_id, api_url = resolve_credentials()
    body = {
        "businessid": business_id,
        "apikey": api_key,
        "eventname": eventname,
        **params,
    }
    try:
        r = requests.post(
            api_url,
            json=body,
            timeout=DEFAULT_TIMEOUT_S,
            headers={"user-agent": "oasis-bravo/kixie-tool/1.0"},
        )
    except requests.RequestException as e:
        raise KixieError(f"network error contacting Kixie: {e}", 3) from e

    if r.status_code >= 400:
        try:
            body_out = r.json()
        except ValueError:
            body_out = r.text[:400]
        raise KixieError(f"HTTP {r.status_code} from Kixie: {body_out}", 2)

    try:
        return r.json()
    except ValueError:
        return {"raw": r.text}


def cmd_call(args) -> dict:
    """Initiate an outbound call. Kixie routes through the assigned
    agent's softphone — they hear the ring + the prospect answers.
    Used by Helios for warm follow-up calls."""
    return _request(
        "outbound_call",
        {
            "number": args.to,
            "email": args.agent,  # Kixie agent identifier
        },
    )


def cmd_click_to_call(args) -> dict:
    """Generate a click-to-call URL the operator can paste into outreach
    or the dashboard. Phone rings the agent's softphone on click; the
    prospect's number is auto-dialled. lead_id is passed through so
    Kixie's webhook back to /api/webhooks/kixie can correlate."""
    body = {
        "number": args.to,
        "customField1": args.lead_id,
    }
    return _request("click_to_call_url", body)


def cmd_transfer(args) -> dict:
    """Transfer an in-flight call to another agent (warm-transfer
    pattern — primary agent qualifies, transfers to a closer)."""
    return _request(
        "warm_transfer",
        {
            "callid": args.call_id,
            "email": args.to,
        },
    )


def cmd_agents(_args) -> dict:
    """List Kixie agents under the business. Useful for operator UX
    showing "transfer to which agent?" pickers."""
    return _request("list_agents", {})


def cmd_status(_args) -> dict:
    """Health check — confirms the API key + business ID are valid."""
    return _request("status", {})


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="kixie_tool",
        description="Kixie CLI — outbound dialer, click-to-call links, live transfer.",
    )
    p.add_argument("--json", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    call = sub.add_parser("call", help="Initiate an outbound call")
    call.add_argument("--to", required=True, help="E.164 number to dial")
    call.add_argument("--agent", required=True, help="Kixie agent email")
    call.set_defaults(func=cmd_call)

    ctc = sub.add_parser("click-to-call", help="Generate a click-to-call URL")
    ctc.add_argument("--lead-id", required=True, help="Bravo lead UUID — echoed back via webhook")
    ctc.add_argument("--to", required=True, help="E.164 number to dial")
    ctc.set_defaults(func=cmd_click_to_call)

    t = sub.add_parser("transfer", help="Warm-transfer an active call")
    t.add_argument("--call-id", required=True)
    t.add_argument("--to", required=True, help="Destination Kixie agent email")
    t.set_defaults(func=cmd_transfer)

    sub.add_parser("agents", help="List Kixie agents").set_defaults(func=cmd_agents)
    sub.add_parser("status", help="Health check").set_defaults(func=cmd_status)

    args = p.parse_args(argv)
    try:
        result = args.func(args)
    except KixieError as e:
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
        print(json.dumps(result, default=str, indent=2) if isinstance(result, (dict, list)) else result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
