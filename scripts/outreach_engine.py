"""
Bravo Outreach Engine - Complete lead outreach pipeline.
Sends personalized email with Google Meet link + calendar invite (.ics).
No n8n dependency. Uses Gmail SMTP directly.

Usage:
    from outreach_engine import send_outreach
    send_outreach(
        lead_name="John Smith",
        lead_email="john@example.com",
        business_name="Smith HVAC",
        business_type="HVAC",
        meeting_datetime="2026-03-05T14:00:00",
        meeting_duration_min=30
    )
"""

import os
import smtplib
import uuid
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders


def load_env():
    """Load .env.agents if env vars aren't set."""
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env.agents')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    if key.strip() not in os.environ:
                        os.environ[key.strip()] = val.strip()


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
    now = datetime.now(tz=__import__('datetime').timezone.utc).strftime(fmt) + "Z"

    ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//OASIS AI Solutions//Bravo Outreach//EN
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
UID:{uid}
DTSTART:{start.strftime(fmt)}
DTEND:{end.strftime(fmt)}
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
    load_env()

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
        print(f"Email sent to {lead_email} with Meet invite")
        return {
            "status": "sent",
            "to": lead_email,
            "meet_link": meet_link,
            "meeting_time": meeting_datetime,
        }
    except Exception as e:
        print(f"Error sending email: {e}")
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    # Dry run example:
    result = send_outreach(
        lead_name="Test Lead",
        lead_email="test@example.com",
        business_name="Test HVAC Co",
        business_type="HVAC",
        meeting_datetime="2026-03-05T14:00:00",
        dry_run=True
    )
    print(result)
