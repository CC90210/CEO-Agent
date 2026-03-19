"""
Google Calendar Integration — Create events with Google Meet links.

Handles OAuth2 authentication and event creation for CC's booking system.
Credentials loaded from .env.agents (never hardcoded).

Required in .env.agents:
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
  (Optional) GOOGLE_CALENDAR_ID — defaults to 'primary'

First-time setup:
  python scripts/google_calendar.py auth     # Opens browser for OAuth consent
  python scripts/google_calendar.py test     # Creates a test event to verify

Usage:
  python scripts/google_calendar.py create --title "Discovery Call" --date 2026-03-25 --time 14:00 --duration 30 --attendee "john@example.com" [--json]
  python scripts/google_calendar.py available --date 2026-03-25 [--json]
  python scripts/google_calendar.py list --date 2026-03-25 [--json]
  python scripts/google_calendar.py auth
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TOKEN_PATH = PROJECT_ROOT / "tmp" / "google_token.json"

# Google Calendar API scopes
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found", file=sys.stderr)
        sys.exit(1)
    env_vars: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


def get_credentials(env_vars: dict):
    """Build Google OAuth2 credentials from .env.agents values.

    If a refresh token exists (either in .env.agents or cached in tmp/google_token.json),
    use it to get a valid access token. Otherwise, run the OAuth consent flow.
    """
    from google.oauth2.credentials import Credentials

    client_id = env_vars.get("GOOGLE_CLIENT_ID", "")
    client_secret = env_vars.get("GOOGLE_CLIENT_SECRET", "")
    refresh_token = env_vars.get("GOOGLE_REFRESH_TOKEN", "")

    if not client_id or not client_secret:
        print("ERROR: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET required in .env.agents", file=sys.stderr)
        print("\nTo set up Google Calendar API:", file=sys.stderr)
        print("1. Go to https://console.cloud.google.com/apis/credentials", file=sys.stderr)
        print("2. Create an OAuth 2.0 Client ID (Desktop app)", file=sys.stderr)
        print("3. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env.agents", file=sys.stderr)
        print("4. Run: python scripts/google_calendar.py auth", file=sys.stderr)
        sys.exit(1)

    # Try cached token first
    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            pass

    # Try refresh token from .env.agents
    if not creds and refresh_token:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        try:
            creds.refresh(Request())
            _save_token(creds)
        except Exception as e:
            print(f"Token refresh failed: {e}", file=sys.stderr)
            creds = None

    if not creds or not creds.valid:
        print("ERROR: No valid credentials. Run: python scripts/google_calendar.py auth", file=sys.stderr)
        sys.exit(1)

    return creds


def _save_token(creds) -> None:
    """Cache the OAuth token to tmp/google_token.json."""
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(creds.to_json())


def get_service(env_vars: dict):
    """Build an authenticated Google Calendar API service object."""
    from googleapiclient.discovery import build
    creds = get_credentials(env_vars)
    return build("calendar", "v3", credentials=creds)


def create_event(
    env_vars: dict,
    title: str,
    start_dt: datetime,
    duration_minutes: int = 30,
    attendee_email: str = "",
    description: str = "",
) -> dict:
    """Create a Google Calendar event with an auto-generated Google Meet link.

    Returns: {success, event_id, meet_link, html_link, start, end, error}
    """
    service = get_service(env_vars)
    calendar_id = env_vars.get("GOOGLE_CALENDAR_ID", "primary")

    end_dt = start_dt + timedelta(minutes=duration_minutes)

    event_body = {
        "summary": title,
        "description": description or f"Booked via OASIS AI — {title}",
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": "America/Toronto",
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": "America/Toronto",
        },
        "conferenceData": {
            "createRequest": {
                "requestId": f"oasis-{int(start_dt.timestamp())}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 15},
            ],
        },
    }

    if attendee_email:
        event_body["attendees"] = [{"email": attendee_email}]

    try:
        event = service.events().insert(
            calendarId=calendar_id,
            body=event_body,
            conferenceDataVersion=1,
            sendUpdates="all" if attendee_email else "none",
        ).execute()

        # Extract the Google Meet link
        meet_link = ""
        if "conferenceData" in event:
            for ep in event["conferenceData"].get("entryPoints", []):
                if ep.get("entryPointType") == "video":
                    meet_link = ep.get("uri", "")
                    break

        return {
            "success": True,
            "event_id": event.get("id", ""),
            "meet_link": meet_link,
            "html_link": event.get("htmlLink", ""),
            "start": event["start"].get("dateTime", ""),
            "end": event["end"].get("dateTime", ""),
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "event_id": None,
            "meet_link": None,
            "html_link": None,
            "start": None,
            "end": None,
            "error": str(e),
        }


def list_events(env_vars: dict, date_str: str) -> list[dict]:
    """List all events for a given date."""
    service = get_service(env_vars)
    calendar_id = env_vars.get("GOOGLE_CALENDAR_ID", "primary")

    from datetime import date as date_type
    target = datetime.strptime(date_str, "%Y-%m-%d").date()
    time_min = datetime.combine(target, datetime.min.time()).isoformat() + "-05:00"
    time_max = datetime.combine(target, datetime.max.time()).isoformat() + "-05:00"

    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    return events_result.get("items", [])


def get_available_slots(env_vars: dict, date_str: str, duration: int = 30) -> list[dict]:
    """Find available 30-min slots on a given date (9am-5pm ET, business hours).

    Returns list of {start, end} dicts for open slots.
    """
    events = list_events(env_vars, date_str)
    target = datetime.strptime(date_str, "%Y-%m-%d").date()

    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/Toronto")

    work_start = datetime.combine(target, datetime.strptime("09:00", "%H:%M").time(), tzinfo=et)
    work_end = datetime.combine(target, datetime.strptime("17:00", "%H:%M").time(), tzinfo=et)

    # Build list of busy periods
    busy = []
    for event in events:
        start = event.get("start", {}).get("dateTime")
        end = event.get("end", {}).get("dateTime")
        if start and end:
            busy.append((
                datetime.fromisoformat(start),
                datetime.fromisoformat(end),
            ))
    busy.sort()

    # Generate available slots
    slots = []
    current = work_start
    while current + timedelta(minutes=duration) <= work_end:
        slot_end = current + timedelta(minutes=duration)
        is_free = all(slot_end <= b[0] or current >= b[1] for b in busy)
        if is_free:
            slots.append({
                "start": current.isoformat(),
                "end": slot_end.isoformat(),
                "display": current.strftime("%-I:%M %p") if hasattr(current, 'strftime') else str(current),
            })
        current += timedelta(minutes=duration)

    return slots


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

def cmd_auth(env_vars: dict, args) -> None:
    """Run the OAuth2 consent flow to get a refresh token."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_id = env_vars.get("GOOGLE_CLIENT_ID", "")
    client_secret = env_vars.get("GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("ERROR: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET required in .env.agents")
        return

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=8090, prompt="consent")
    _save_token(creds)

    print("Authentication successful!")
    print(f"Token cached at: {TOKEN_PATH}")
    if creds.refresh_token:
        print(f"\nAdd this to .env.agents for persistent auth:")
        print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")


def cmd_create(env_vars: dict, args) -> None:
    """Create a calendar event with Google Meet."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/Toronto")

    date_obj = datetime.strptime(args.date, "%Y-%m-%d").date()
    time_obj = datetime.strptime(args.time, "%H:%M").time()
    start_dt = datetime.combine(date_obj, time_obj, tzinfo=et)

    result = create_event(
        env_vars,
        title=args.title,
        start_dt=start_dt,
        duration_minutes=args.duration,
        attendee_email=getattr(args, "attendee", ""),
        description=getattr(args, "description", ""),
    )

    if getattr(args, "output_json", False):
        print(json.dumps(result, default=str))
    else:
        if result["success"]:
            print(f"Event created: {result['html_link']}")
            print(f"Meet link: {result['meet_link']}")
            print(f"Time: {result['start']} - {result['end']}")
        else:
            print(f"Failed: {result['error']}")


def cmd_available(env_vars: dict, args) -> None:
    """Show available slots for a date."""
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    slots = get_available_slots(env_vars, date_str)

    if getattr(args, "output_json", False):
        print(json.dumps({"date": date_str, "slots": slots}, default=str))
    else:
        if slots:
            print(f"Available slots on {date_str}:")
            for s in slots:
                print(f"  {s['display']}")
        else:
            print(f"No available slots on {date_str}")


def cmd_list(env_vars: dict, args) -> None:
    """List events for a date."""
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    events = list_events(env_vars, date_str)

    if getattr(args, "output_json", False):
        print(json.dumps({"date": date_str, "events": [
            {"summary": e.get("summary", ""), "start": e["start"].get("dateTime", ""), "end": e["end"].get("dateTime", "")}
            for e in events
        ]}, default=str))
    else:
        if events:
            print(f"Events on {date_str}:")
            for e in events:
                start = e["start"].get("dateTime", "?")
                print(f"  {start}: {e.get('summary', 'Untitled')}")
        else:
            print(f"No events on {date_str}")


def cmd_test(env_vars: dict, args) -> None:
    """Create a test event 1 hour from now to verify integration works."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/Toronto")

    start = datetime.now(et) + timedelta(hours=1)
    result = create_event(
        env_vars,
        title="[TEST] OASIS Calendar Integration",
        start_dt=start,
        duration_minutes=15,
        description="Test event — safe to delete. Created by scripts/google_calendar.py test",
    )

    if result["success"]:
        print("Test event created successfully!")
        print(f"  Meet: {result['meet_link']}")
        print(f"  Calendar: {result['html_link']}")
        print(f"  Time: {result['start']}")
        print("\nGoogle Calendar integration is working. Delete the test event from your calendar.")
    else:
        print(f"Test failed: {result['error']}")


def main():
    parser = argparse.ArgumentParser(description="Google Calendar Integration")
    parser.add_argument("--json", dest="output_json", action="store_true")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("auth", help="Run OAuth2 consent flow")
    sub.add_parser("test", help="Create a test event to verify integration")

    p_create = sub.add_parser("create", help="Create event with Meet link")
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_create.add_argument("--time", required=True, help="HH:MM (24h, Eastern)")
    p_create.add_argument("--duration", type=int, default=30, help="Minutes (default 30)")
    p_create.add_argument("--attendee", default="", help="Attendee email")
    p_create.add_argument("--description", default="")

    p_avail = sub.add_parser("available", help="Show available slots")
    p_avail.add_argument("--date", default="", help="YYYY-MM-DD")

    p_list = sub.add_parser("list", help="List events for a date")
    p_list.add_argument("--date", default="", help="YYYY-MM-DD")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    env_vars = load_env()

    commands = {
        "auth": cmd_auth,
        "test": cmd_test,
        "create": cmd_create,
        "available": cmd_available,
        "list": cmd_list,
    }
    commands[args.command](env_vars, args)


if __name__ == "__main__":
    main()
