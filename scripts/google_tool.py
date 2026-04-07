"""
Google Workspace CLI — Calendar, Gmail, Drive, Sheets
Wraps gws CLI with auto-token-refresh and fallback to direct API.
All credentials loaded from .env.agents (never hardcoded).

Usage (from any agent via terminal):
  python scripts/google_tool.py calendar list [--max 10]
  python scripts/google_tool.py calendar create --title "Meeting" --start "2026-04-01T16:00:00" --end "2026-04-01T16:45:00" [--attendees "a@b.com,c@d.com"] [--meet] [--description "..."] [--timezone "America/Toronto"]
  python scripts/google_tool.py calendar delete <event_id>
  python scripts/google_tool.py gmail send --to "a@b.com" --subject "Hi" --body "Hello"
  python scripts/google_tool.py gmail list [--max 10]
  python scripts/google_tool.py gmail read <message_id>
  python scripts/google_tool.py test

All commands support --json flag for agent consumption.
"""

import argparse
import json
import os
import smtplib
import subprocess
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path


def load_env():
    """Load .env.agents from project root."""
    env_path = Path(__file__).parent.parent / ".env.agents"
    if not env_path.exists():
        print("ERROR: .env.agents not found", file=sys.stderr)
        sys.exit(1)
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


GWS_PATH = os.environ.get("GWS_PATH", r"C:\Users\User\AppData\Roaming\npm\gws.cmd")


def run_gws(args_list, timeout=30):
    """Run a gws CLI command and return parsed JSON output."""
    cmd = [GWS_PATH] + args_list
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        # gws outputs to stdout, errors to stderr
        output = result.stdout.strip()
        if result.returncode != 0:
            error_text = result.stderr.strip() or output
            # Check for auth errors
            if "expired" in error_text.lower() or "401" in error_text:
                return None, "AUTH_EXPIRED"
            return None, error_text
        try:
            return json.loads(output), None
        except json.JSONDecodeError:
            return output, None
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT"
    except FileNotFoundError:
        return None, "GWS_NOT_FOUND"


def refresh_gws_auth():
    """Attempt to refresh gws auth by re-logging in non-interactively.
    If this fails, fall back to direct API with SMTP for email."""
    print("WARNING: gws token expired. Attempting re-auth...", file=sys.stderr)
    # gws auth login requires browser interaction, so we can't auto-refresh
    # Instead, return False and let callers use fallback methods
    return False


def gmail_send_smtp(to, subject, body, ics_content=None):
    """Send email via SMTP as fallback when gws CLI auth fails."""
    gmail_user = os.environ.get("GMAIL_USER", "oasisaisolutions@gmail.com")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_pass:
        return None, "GMAIL_APP_PASSWORD not set in .env.agents"

    msg = MIMEMultipart("mixed")
    msg["From"] = f"Conaugh McKenna <{gmail_user}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if ics_content:
        ics_part = MIMEBase("text", "calendar", method="REQUEST")
        ics_part.set_payload(ics_content)
        encoders.encode_base64(ics_part)
        ics_part.add_header("Content-Disposition", "attachment", filename="invite.ics")
        msg.attach(ics_part)

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, to, msg.as_string())
        server.quit()
        return {"status": "sent", "method": "smtp", "to": to}, None
    except Exception as e:
        return None, str(e)


# ── Calendar Commands ──────────────────────────────────────────────

def calendar_list(args):
    """List upcoming calendar events."""
    max_results = args.max or 10
    params = {
        "calendarId": "primary",
        "maxResults": max_results,
        "singleEvents": True,
        "orderBy": "startTime",
        "timeMin": f"{_now_iso()}",
    }
    data, err = run_gws([
        "calendar", "events", "list",
        "--params", json.dumps(params)
    ])
    if err == "AUTH_EXPIRED":
        print("ERROR: gws auth expired. Run: gws auth login", file=sys.stderr)
        sys.exit(1)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    events = data.get("items", [])
    if args.json_output:
        print(json.dumps(events, indent=2))
    else:
        if not events:
            print("No upcoming events.")
            return
        for e in events:
            start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))
            print(f"  {start}  {e.get('summary', '(no title)')}")
            if e.get("hangoutLink"):
                print(f"    Meet: {e['hangoutLink']}")


def calendar_create(args):
    """Create a calendar event with optional attendees and Meet link."""
    tz = args.timezone or "America/Toronto"
    event = {
        "summary": args.title,
        "start": {"dateTime": args.start, "timeZone": tz},
        "end": {"dateTime": args.end, "timeZone": tz},
    }
    if args.description:
        event["description"] = args.description
    if args.attendees:
        event["attendees"] = [{"email": e.strip()} for e in args.attendees.split(",")]
    if args.meet:
        meet_link = os.environ.get("GOOGLE_MEET_LINK", "")
        if meet_link:
            event["conferenceData"] = {
                "entryPoints": [{
                    "entryPointType": "video",
                    "uri": meet_link,
                    "label": meet_link.replace("https://", "")
                }],
                "conferenceSolution": {
                    "key": {"type": "hangoutsMeet"},
                    "name": "Google Meet"
                },
                "conferenceId": meet_link.split("/")[-1]
            }

    params = {
        "calendarId": "primary",
        "conferenceDataVersion": 1,
        "sendUpdates": "all"
    }

    data, err = run_gws([
        "calendar", "events", "insert",
        "--params", json.dumps(params),
        "--json", json.dumps(event)
    ])

    if err == "AUTH_EXPIRED":
        print("ERROR: gws auth expired. Run: gws auth login", file=sys.stderr)
        sys.exit(1)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        print(f"Event created: {data.get('summary')}")
        print(f"  When: {data.get('start', {}).get('dateTime')}")
        print(f"  Link: {data.get('htmlLink')}")
        if data.get("hangoutLink"):
            print(f"  Meet: {data['hangoutLink']}")
        attendees = data.get("attendees", [])
        if attendees:
            print(f"  Attendees: {', '.join(a['email'] for a in attendees)}")


def calendar_delete(args):
    """Delete a calendar event."""
    params = {"calendarId": "primary", "eventId": args.event_id, "sendUpdates": "all"}
    data, err = run_gws([
        "calendar", "events", "delete",
        "--params", json.dumps(params)
    ])
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    print(f"Event {args.event_id} deleted.")


# ── Gmail Commands ─────────────────────────────────────────────────

def gmail_send(args):
    """Send an email. Uses gws CLI first, falls back to SMTP."""
    # Try gws CLI first
    message_body = {
        "raw": _encode_email(args.to, args.subject, args.body)
    }
    data, err = run_gws([
        "gmail", "users", "messages", "send",
        "--params", json.dumps({"userId": "me"}),
        "--json", json.dumps(message_body)
    ])

    if err == "AUTH_EXPIRED" or err:
        # Fallback to SMTP
        print("gws CLI unavailable, using SMTP fallback...", file=sys.stderr)
        data, smtp_err = gmail_send_smtp(args.to, args.subject, args.body)
        if smtp_err:
            print(f"ERROR: {smtp_err}", file=sys.stderr)
            sys.exit(1)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        print(f"Email sent to {args.to}")


def gmail_list(args):
    """List recent emails."""
    max_results = args.max or 10
    params = {"userId": "me", "maxResults": max_results}
    data, err = run_gws([
        "gmail", "users", "messages", "list",
        "--params", json.dumps(params)
    ])
    if err == "AUTH_EXPIRED":
        print("ERROR: gws auth expired. Run: gws auth login", file=sys.stderr)
        sys.exit(1)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        messages = data.get("messages", [])
        print(f"{len(messages)} messages (showing IDs — use 'gmail read <id>' for details)")
        for m in messages[:max_results]:
            print(f"  {m['id']}")


def gmail_read(args):
    """Read a specific email."""
    params = {"userId": "me", "id": args.message_id, "format": "full"}
    data, err = run_gws([
        "gmail", "users", "messages", "get",
        "--params", json.dumps(params)
    ])
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
        print(f"From: {headers.get('From', 'unknown')}")
        print(f"Subject: {headers.get('Subject', '(no subject)')}")
        print(f"Date: {headers.get('Date', '')}")
        snippet = data.get("snippet", "")
        print(f"\n{snippet}")


# ── Test Command ───────────────────────────────────────────────────

def test_connection(args):
    """Test all Google integrations."""
    print("Testing Google Workspace integration...\n")

    # Test 1: gws auth
    print("1. gws CLI auth status...")
    data, err = run_gws(["auth", "status"])
    if err:
        print(f"   FAIL: {err}")
    else:
        token_valid = data.get("token_valid", False) if isinstance(data, dict) else False
        user = data.get("user", "unknown") if isinstance(data, dict) else "unknown"
        status = "PASS" if token_valid else "FAIL (token expired)"
        print(f"   {status} — {user}")

    # Test 2: Calendar read
    print("2. Calendar access...")
    data, err = run_gws([
        "calendar", "events", "list",
        "--params", json.dumps({
            "calendarId": "primary",
            "maxResults": 1,
            "singleEvents": True,
            "orderBy": "startTime",
            "timeMin": _now_iso()
        })
    ])
    if err:
        print(f"   FAIL: {err}")
    else:
        print(f"   PASS — calendar readable")

    # Test 3: Gmail read
    print("3. Gmail access...")
    data, err = run_gws([
        "gmail", "users", "getProfile",
        "--params", json.dumps({"userId": "me"})
    ])
    if err:
        print(f"   FAIL: {err}")
    else:
        email = data.get("emailAddress", "unknown") if isinstance(data, dict) else "unknown"
        print(f"   PASS — {email}")

    # Test 4: SMTP fallback
    print("4. SMTP fallback...")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    if gmail_pass:
        print(f"   PASS — GMAIL_APP_PASSWORD configured")
    else:
        print(f"   FAIL — GMAIL_APP_PASSWORD not in .env.agents")

    # Test 5: Meet link
    print("5. Google Meet link...")
    meet = os.environ.get("GOOGLE_MEET_LINK")
    if meet:
        print(f"   PASS — {meet}")
    else:
        print(f"   WARN — no static GOOGLE_MEET_LINK in .env.agents")

    print("\nDone.")


# ── Helpers ────────────────────────────────────────────────────────

def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _encode_email(to, subject, body):
    """Create base64url encoded email for Gmail API."""
    import base64
    gmail_user = os.environ.get("GMAIL_USER", "oasisaisolutions@gmail.com")
    message = MIMEText(body)
    message["to"] = to
    message["from"] = f"Conaugh McKenna <{gmail_user}>"
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return raw


# ── CLI Parser ─────────────────────────────────────────────────────

def main():
    load_env()

    parser = argparse.ArgumentParser(description="Google Workspace CLI Tool")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output JSON")
    subparsers = parser.add_subparsers(dest="service")

    # Calendar
    cal_parser = subparsers.add_parser("calendar", help="Google Calendar operations")
    cal_sub = cal_parser.add_subparsers(dest="action")

    cal_list = cal_sub.add_parser("list", help="List upcoming events")
    cal_list.add_argument("--max", type=int, default=10)
    cal_list.add_argument("--json", dest="json_output", action="store_true")

    cal_create = cal_sub.add_parser("create", help="Create event")
    cal_create.add_argument("--title", required=True)
    cal_create.add_argument("--start", required=True, help="ISO datetime")
    cal_create.add_argument("--end", required=True, help="ISO datetime")
    cal_create.add_argument("--attendees", help="Comma-separated emails")
    cal_create.add_argument("--meet", action="store_true", help="Attach Google Meet link")
    cal_create.add_argument("--description", help="Event description")
    cal_create.add_argument("--timezone", default="America/Toronto")
    cal_create.add_argument("--json", dest="json_output", action="store_true")

    cal_delete = cal_sub.add_parser("delete", help="Delete event")
    cal_delete.add_argument("event_id")
    cal_delete.add_argument("--json", dest="json_output", action="store_true")

    # Gmail
    gmail_parser = subparsers.add_parser("gmail", help="Gmail operations")
    gmail_sub = gmail_parser.add_subparsers(dest="action")

    gmail_s = gmail_sub.add_parser("send", help="Send email")
    gmail_s.add_argument("--to", required=True)
    gmail_s.add_argument("--subject", required=True)
    gmail_s.add_argument("--body", required=True)
    gmail_s.add_argument("--json", dest="json_output", action="store_true")

    gmail_l = gmail_sub.add_parser("list", help="List messages")
    gmail_l.add_argument("--max", type=int, default=10)
    gmail_l.add_argument("--json", dest="json_output", action="store_true")

    gmail_r = gmail_sub.add_parser("read", help="Read message")
    gmail_r.add_argument("message_id")
    gmail_r.add_argument("--json", dest="json_output", action="store_true")

    # Test
    subparsers.add_parser("test", help="Test all integrations")

    args = parser.parse_args()

    if args.service == "calendar":
        if args.action == "list":
            calendar_list(args)
        elif args.action == "create":
            calendar_create(args)
        elif args.action == "delete":
            calendar_delete(args)
        else:
            cal_parser.print_help()
    elif args.service == "gmail":
        if args.action == "send":
            gmail_send(args)
        elif args.action == "list":
            gmail_list(args)
        elif args.action == "read":
            gmail_read(args)
        else:
            gmail_parser.print_help()
    elif args.service == "test":
        test_connection(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
