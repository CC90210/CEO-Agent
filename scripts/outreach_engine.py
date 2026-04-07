"""
Outreach Engine - Personalized email outreach with Google Meet + .ics invite.
Zero n8n dependency. Gmail SMTP directly. Supabase for logging and history.
All credentials loaded from .env.agents (never hardcoded).

Usage:
  python scripts/outreach_engine.py send --lead-id <uuid>
  python scripts/outreach_engine.py list [--limit 20]
  python scripts/outreach_engine.py stats
  python scripts/outreach_engine.py --json list
"""

import argparse
import json
import os
import smtplib
import sys
import uuid
from datetime import datetime, timedelta, timezone
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


# -- Credentials ---------------------------------------------------------------


def load_env():
    """Load .env.agents from project root."""
    env_path = Path(__file__).resolve().parent.parent / ".env.agents"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found", file=sys.stderr)
        sys.exit(1)

    env_vars = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    # Also set into os.environ so helpers that read os.environ directly work.
    for k, v in env_vars.items():
        if k not in os.environ:
            os.environ[k] = v
    return env_vars


def get_supabase(env_vars):
    """Create Supabase client using Bravo project credentials."""
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: supabase package not installed. Run: pip install supabase", file=sys.stderr)
        sys.exit(1)

    url = env_vars.get("BRAVO_SUPABASE_URL")
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        print("ERROR: Missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY in .env.agents", file=sys.stderr)
        sys.exit(1)

    return create_client(url, key)


# -- Core outreach helpers (original functions, preserved) ---------------------


def generate_meet_link():
    """
    Generate a Google Meet link.
    Uses the stored GOOGLE_MEET_LINK from .env.agents if available,
    otherwise returns the new-meeting URL for CC to use.
    """
    stored = os.environ.get("GOOGLE_MEET_LINK")
    if stored:
        return stored
    return "https://meet.google.com/new"


def generate_ics(
    lead_name, lead_email, meeting_datetime, duration_min, meet_link, organizer_email
):
    """Generate an .ics calendar invite string."""
    start = datetime.fromisoformat(meeting_datetime)
    end = start + timedelta(minutes=duration_min)
    uid = str(uuid.uuid4())

    fmt = "%Y%m%dT%H%M%S"
    now = datetime.now(tz=timezone.utc).strftime(fmt) + "Z"
    # Ensure start/end have Z suffix for UTC interpretation by calendar clients
    start_str = start.strftime(fmt) + "Z"
    end_str = end.strftime(fmt) + "Z"

    ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//OASIS AI Solutions//Bravo Outreach//EN
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
UID:{uid}
DTSTART:{start_str}
DTEND:{end_str}
DTSTAMP:{now}
ORGANIZER;CN=OASIS AI Solutions:mailto:{organizer_email}
ATTENDEE;CN={lead_name};RSVP=TRUE:mailto:{lead_email}
SUMMARY:OASIS AI Solutions - Discovery Call with {lead_name}
DESCRIPTION:Quick intro call to explore how AI automation can save your team 10+ hours/week.\\n\\nJoin via Google Meet: {meet_link}
LOCATION:{meet_link}
STATUS:CONFIRMED
SEQUENCE:0
END:VEVENT
END:VCALENDAR"""
    return ics


def build_email_body(lead_name, business_name, business_type, meet_link, meeting_datetime):
    """Build the outreach email body. Authentic, direct, no hustle-culture."""
    start = datetime.fromisoformat(meeting_datetime)
    date_str = start.strftime("%A, %B %d at %I:%M %p")

    body = f"""Hi {lead_name},

I came across {business_name} and noticed a few areas where AI automation could make a real difference - specifically around scheduling, follow-ups, and client communication.

At OASIS AI Solutions, we build custom automation systems for {business_type} businesses. Our clients typically save 10-15 hours per week on manual tasks and see faster response times that directly improve close rates.

I'd love to show you exactly how this works for your business. No pitch, just a quick walkthrough.

I've set aside time for a 30-minute discovery call:

    {date_str} EST
    Google Meet: {meet_link}

If that time doesn't work, just reply with what does.

Looking forward to connecting.

Conaugh McKenna
Founder, OASIS AI Solutions
oasisai.work"""
    return body


def send_outreach(
    lead_name,
    lead_email,
    business_name,
    business_type,
    meeting_datetime,
    meeting_duration_min=30,
    dry_run=False,
    custom_subject=None,
    custom_body=None
):
    """
    Full outreach pipeline:
    1. Generate Meet link
    2. Build personalized email
    3. Generate .ics calendar invite
    4. Send email with invite attached
    """
    gmail_user = os.environ.get("GMAIL_USER", "oasisaisolutions@gmail.com")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_app_password:
        raise ValueError("GMAIL_APP_PASSWORD not set. Load from .env.agents.")

    meet_link = generate_meet_link()
    if custom_body:
        email_body = custom_body
    else:
        email_body = build_email_body(
            lead_name, business_name, business_type, meet_link, meeting_datetime
        )
    ics_content = generate_ics(
        lead_name, lead_email, meeting_datetime, meeting_duration_min,
        meet_link, gmail_user
    )

    subject = custom_subject if custom_subject else f"{business_name} - Save 10+ Hours/Week with AI Automation"

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = f"OASIS AI Solutions <{gmail_user}>"
    msg["To"] = lead_email

    msg.attach(MIMEText(email_body, "plain"))

    ics_part = MIMEBase("text", "calendar", method="REQUEST")
    ics_part.set_payload(ics_content.encode("utf-8"))
    encoders.encode_base64(ics_part)
    ics_part.add_header(
        "Content-Disposition", "attachment", filename="meeting.ics"
    )
    msg.attach(ics_part)

    if dry_run:
        print(f"[DRY RUN] Would send to: {lead_email}")
        print(f"[DRY RUN] Subject: {subject}")
        print(f"[DRY RUN] Meet link: {meet_link}")
        print(f"[DRY RUN] Body:\n{email_body}")
        return {"status": "dry_run", "to": lead_email, "meet_link": meet_link}

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(gmail_user, gmail_app_password)
            smtp.send_message(msg)
        return {
            "status": "sent",
            "to": lead_email,
            "meet_link": meet_link,
            "meeting_time": meeting_datetime,
        }
    except smtplib.SMTPAuthenticationError as e:
        return {"status": "error", "error": f"SMTP authentication failed — check GMAIL_APP_PASSWORD in .env.agents: {e}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# -- Formatting helpers --------------------------------------------------------


def fmt_date(iso_str):
    """Format an ISO timestamp to a readable short date."""
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return iso_str[:10] if iso_str else "-"


def truncate(text, max_len=50):
    if not text:
        return ""
    return text[:max_len - 3] + "..." if len(text) > max_len else text


# -- Command handlers ----------------------------------------------------------


def cmd_send(db, args, output_json):
    """Send an outreach email to a lead by UUID."""
    lead_result = db.table("leads").select("*").eq("id", args.lead_id).execute()
    if not lead_result.data:
        print(f"ERROR: Lead '{args.lead_id}' not found.", file=sys.stderr)
        sys.exit(1)

    lead = lead_result.data[0]
    lead_name = lead.get("name") or lead.get("first_name", "there")
    lead_email = lead.get("email")
    business_name = lead.get("company") or lead.get("business_name") or lead_name
    business_type = lead.get("business_type") or lead.get("industry") or "business"

    if not lead_email:
        print(f"ERROR: Lead '{args.lead_id}' has no email address.", file=sys.stderr)
        sys.exit(1)

    meeting_datetime = getattr(args, "meeting_datetime", None)
    if not meeting_datetime:
        # Default to next business day at 2pm
        tomorrow = datetime.now(timezone.utc).replace(
            hour=14, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        meeting_datetime = tomorrow.strftime("%Y-%m-%dT%H:%M:%S")

    result = send_outreach(
        lead_name=lead_name,
        lead_email=lead_email,
        business_name=business_name,
        business_type=business_type,
        meeting_datetime=meeting_datetime,
        meeting_duration_min=getattr(args, "duration", 30),
        dry_run=getattr(args, "dry_run", False),
        custom_subject=getattr(args, "subject", None),
        custom_body=getattr(args, "body", None),
    )

    # Log to email_log table if the send was real (not a dry run)
    if result.get("status") == "sent":
        try:
            email_body = result.get("body", "")
            db.table("email_log").insert({
                "to_email": lead_email,
                "subject": f"{business_name} - Save 10+ Hours/Week with AI Automation",
                "status": "sent",
                "lead_id": args.lead_id,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "body_preview": email_body[:200] if email_body else "",
            }).execute()
        except Exception as e:
            print(f"Warning: could not write to email_log: {e}", file=sys.stderr)

    if output_json:
        print(json.dumps(result, indent=2, default=str))
        return

    status = result.get("status", "unknown")
    if status == "sent":
        print(f"Outreach sent to {lead_name} <{lead_email}>")
        print(f"  Meet link: {result.get('meet_link')}")
        print(f"  Meeting:   {meeting_datetime}")
    elif status == "dry_run":
        pass  # send_outreach already printed dry run details
    else:
        print(f"ERROR: {result.get('error', 'Unknown error')}", file=sys.stderr)
        sys.exit(1)


def cmd_list(db, args, output_json):
    """List outreach emails from email_log (identified by subject pattern)."""
    limit = getattr(args, "limit", 20)

    try:
        result = (
            db.table("email_log")
            .select("id, to_email, subject, status, sent_at, lead_id")
            .ilike("subject", "%Save%Hours%AI Automation%")
            .order("sent_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    rows = result.data or []

    if output_json:
        print(json.dumps(rows, indent=2, default=str))
        return

    if not rows:
        print("No outreach records found.")
        return

    cols = (11, 28, 8, 40)  # date, to, status, subject

    header = "  ".join([
        "SENT".ljust(cols[0]),
        "TO".ljust(cols[1]),
        "STATUS".ljust(cols[2]),
        "SUBJECT".ljust(cols[3]),
    ])
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    for row in rows:
        sent = fmt_date(row.get("sent_at"))
        to = truncate(row.get("to_email", "-"), cols[1])
        status = (row.get("status") or "-").upper()[:cols[2]]
        subject = truncate(row.get("subject", "-"), cols[3])
        print("  ".join([
            sent.ljust(cols[0]),
            to.ljust(cols[1]),
            status.ljust(cols[2]),
            subject.ljust(cols[3]),
        ]))

    print(sep)
    print(f"  {len(rows)} outreach email(s)")


def cmd_stats(db, output_json):
    """Show outreach stats: sent count and failure count."""
    try:
        result = (
            db.table("email_log")
            .select("status")
            .ilike("subject", "%Save%Hours%AI Automation%")
            .execute()
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    rows = result.data or []
    total = len(rows)
    sent = sum(1 for r in rows if r.get("status") == "sent")
    failed = sum(1 for r in rows if r.get("status") == "failed")
    queued = sum(1 for r in rows if r.get("status") == "queued")

    stats = {
        "total": total,
        "sent": sent,
        "queued": queued,
        "failed": failed,
    }

    if output_json:
        print(json.dumps(stats, indent=2))
        return

    print("Outreach Statistics:\n")
    print(f"  Total logged:  {total}")
    print(f"  Sent:          {sent}")
    print(f"  Queued:        {queued}")
    print(f"  Failed:        {failed}")


# -- Argument parser -----------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        prog="outreach_engine.py",
        description="OASIS AI Outreach Engine - Personalized email + Meet invite via Gmail SMTP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s send --lead-id <uuid>
  %(prog)s send --lead-id <uuid> --meeting-datetime 2026-04-01T14:00:00 --dry-run
  %(prog)s list
  %(prog)s list --limit 50
  %(prog)s stats
  %(prog)s --json list
  %(prog)s --json stats
        """,
    )

    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="Output raw JSON for agent consumption",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # -- send ------------------------------------------------------------------
    p_send = subparsers.add_parser(
        "send",
        help="Send an outreach email to a lead (looks up lead details from Supabase)",
    )
    p_send.add_argument(
        "--lead-id",
        dest="lead_id",
        required=True,
        help="Lead UUID from the leads table",
    )
    p_send.add_argument(
        "--meeting-datetime",
        dest="meeting_datetime",
        default=None,
        metavar="YYYY-MM-DDTHH:MM:SS",
        help="Proposed meeting time in ISO format (default: tomorrow at 2pm UTC)",
    )
    p_send.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Meeting duration in minutes (default: 30)",
    )
    p_send.add_argument(
        "--subject",
        default=None,
        help="Custom email subject (overrides auto-generated subject)",
    )
    p_send.add_argument(
        "--body",
        default=None,
        help="Custom email body (overrides auto-generated body)",
    )
    p_send.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Preview email without sending",
    )

    # -- list ------------------------------------------------------------------
    p_list = subparsers.add_parser(
        "list",
        help="List all sent outreach from email_log (purpose starts with 'outreach')",
    )
    p_list.add_argument("--limit", "-l", type=int, default=20)

    # -- stats -----------------------------------------------------------------
    subparsers.add_parser(
        "stats",
        help="Show outreach stats (sent count, open rate, reply rate)",
    )

    return parser


# -- Entry point ---------------------------------------------------------------


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    env_vars = load_env()
    output_json = getattr(args, "output_json", False)

    if args.command == "send":
        db = get_supabase(env_vars)
        try:
            cmd_send(db, args, output_json)
        except Exception as e:
            if output_json:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "list":
        db = get_supabase(env_vars)
        try:
            cmd_list(db, args, output_json)
        except Exception as e:
            if output_json:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "stats":
        db = get_supabase(env_vars)
        try:
            cmd_stats(db, output_json)
        except Exception as e:
            if output_json:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
