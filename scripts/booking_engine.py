"""
Booking Engine - Self-hosted scheduling system replacing Cal.com.
Zero paid services. Backed by Supabase (bravo project).
All credentials loaded from .env.agents (never hardcoded).

Tables required (bravo Supabase project):
  booking_slots (id, slot_date, start_time, end_time, meeting_type, is_available, created_at)
  bookings      (id, lead_id, slot_id, name, email, phone, meeting_type, notes,
                 status, meeting_link, reminder_sent, created_at)

Usage:
  python scripts/booking_engine.py slots open --date 2026-03-24 --start 10:00 --end 16:00 --interval 30 --type discovery
  python scripts/booking_engine.py slots open-week --start-date 2026-03-24 --days mon,tue,wed,thu,fri --start 10:00 --end 16:00 --interval 30 --type discovery
  python scripts/booking_engine.py slots list [--date 2026-03-24] [--available-only] [--type discovery]
  python scripts/booking_engine.py slots close <slot_id>

  python scripts/booking_engine.py book <slot_id> --name "John Smith" --email "john@acme.com" [--phone "555-1234"] [--notes "..."] [--lead-id uuid]
  python scripts/booking_engine.py auto-book --name "John Smith" --email "john@acme.com" --preferred-time "2026-03-25 10:00" [--type discovery] [--phone "555-1234"] [--notes "..."] [--lead-id uuid]
  python scripts/booking_engine.py cancel <booking_id> [--reason "Rescheduled"]
  python scripts/booking_engine.py list [--status confirmed|completed|cancelled] [--upcoming]
  python scripts/booking_engine.py view <booking_id>

  python scripts/booking_engine.py available [--type discovery] [--next 7]
  python scripts/booking_engine.py generate-link [--type discovery] [--next 7]
  python scripts/booking_engine.py remind
  python scripts/booking_engine.py send-reminders [--dry-run]
  python scripts/booking_engine.py complete <booking_id> [--notes "Good call"]

  Add --json to any command for machine-readable output.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

# Optional Telegram notifications — non-fatal if notify.py is absent
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from notify import notify as _telegram_notify  # noqa: F401
except ImportError:
    def _telegram_notify(*_args: object, **_kwargs: object) -> bool:  # type: ignore[misc]
        return False

# Physical send + CASL footer + List-Unsubscribe + ledger logging all live in
# send_gateway (2026-04-20 rewire). Booking confirmations and reminders are
# TRANSACTIONAL mail (recipient booked the call themselves, implied consent
# under CASL s. 10(9)) — the gateway's intent="transactional" keyword handles
# that by skipping the suppression check while still adding footer + headers.


# ---------------------------------------------------------------------------
# Credential loading
# ---------------------------------------------------------------------------

def load_env() -> dict[str, str]:
    """Load .env.agents from project root. Exits on missing file."""
    env_path = Path(__file__).resolve().parent.parent / ".env.agents"
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


def get_client(env_vars: dict[str, str]):
    """Create a Supabase client using BRAVO_SUPABASE_* credentials."""
    from supabase import create_client  # type: ignore[import-untyped]

    url = env_vars.get("BRAVO_SUPABASE_URL") or "https://bravo.turso.compat"
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "turso-compat-key"
    if not url or not key:
        print(
            "ERROR: Missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY in .env.agents",
            file=sys.stderr,
        )
        sys.exit(1)

    return create_client(url, key)


def _join_slots(client, bookings: list[dict],
                cols: str = "slot_date,start_time,end_time") -> list[dict]:
    """Attach each booking's slot as ``booking_slots`` (PostgREST embedded shape).

    The Supabase->Turso compat layer cannot transpile PostgREST's
    embedded-resource select (``*, booking_slots(slot_date, start_time)``): it
    quotes every comma token as an identifier, so the query fails at runtime
    (found 2026-08-11 while smoke-testing the booking_reminder cron path).
    Fetch the two tables separately and merge in Python instead — same final
    shape, no JOIN dialect to keep in sync with the transpiler.
    """
    wanted = tuple(sorted(c.strip() for c in cols.split(",")))
    slot_ids = sorted({b.get("slot_id") for b in bookings if b.get("slot_id")})
    by_id: dict[str, dict] = {}
    if slot_ids:
        rows = (
            client.table("booking_slots")
            .select(",".join(("id",) + wanted))
            .in_("id", slot_ids)
            .execute()
        ).data or []
        by_id = {r["id"]: r for r in rows}
    out: list[dict] = []
    for b in bookings:
        row = dict(b)
        row["booking_slots"] = by_id.get(row.get("slot_id")) or {}
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def output(data: object, json_mode: bool) -> None:
    """Print data as JSON or formatted text depending on mode."""
    if json_mode:
        print(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, list):
            for item in data:
                _print_record(item)
        elif isinstance(data, dict):
            _print_record(data)
        else:
            print(data)


def _print_record(record: dict) -> None:
    """Print a single dict record as readable key: value lines."""
    for k, v in record.items():
        print(f"  {k}: {v}")
    print()


def fail(message: str, json_mode: bool) -> None:
    """Print an error and exit with code 1."""
    if json_mode:
        print(json.dumps({"error": message}), file=sys.stderr)
    else:
        print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Google Calendar helper
# ---------------------------------------------------------------------------

def _create_calendar_event(env_vars: dict[str, str], booking: dict, slot: dict) -> bool:  # noqa: ARG001
    """Create a Google Calendar event for the booking using gws CLI. Non-fatal."""
    try:
        import subprocess as _sp

        slot_date = slot.get("slot_date", "")
        start_time = slot.get("start_time", "")[:5]  # HH:MM
        end_time = slot.get("end_time", "")[:5]
        name = booking.get("name", "Unknown")
        email = booking.get("email", "")
        meeting_type = booking.get("meeting_type", "discovery")
        meet_link = booking.get("meeting_link", "")

        # Build the title and description
        title = f"{meeting_type.title()} Call — {name}"
        description_parts = [
            f"Booking with {name}",
            f"Email: {email}",
        ]
        if booking.get("phone"):
            description_parts.append(f"Phone: {booking['phone']}")
        if booking.get("notes"):
            description_parts.append(f"Notes: {booking['notes']}")
        if meet_link:
            description_parts.append(f"Meet: {meet_link}")
        description = "\\n".join(description_parts)

        # Use the gws-wrapper.cmd to call gws calendar +insert
        wrapper = Path(__file__).resolve().parent / "gws-wrapper.cmd"
        if not wrapper.exists():
            return False

        # gws calendar +insert expects: title, start datetime, end datetime
        start_dt = f"{slot_date}T{start_time}:00"
        end_dt = f"{slot_date}T{end_time}:00"

        cmd = [
            "cmd", "/c", str(wrapper),
            "calendar", "+insert",
            "--title", title,
            "--start", start_dt,
            "--end", end_dt,
            "--description", description,
        ]
        if email:
            cmd.extend(["--attendees", email])

        result = _sp.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            cwd=str(Path(__file__).resolve().parent.parent),
        )

        if result.returncode == 0:
            return True
        else:
            # Log but don't crash
            print(f"Calendar event creation failed: {result.stderr[:200]}", flush=True)
            return False
    except Exception as e:  # noqa: BLE001 — non-fatal, must not crash booking flow
        print(f"Calendar event creation error: {e}", flush=True)
        return False


# ---------------------------------------------------------------------------
# Slot generation helpers
# ---------------------------------------------------------------------------

def _generate_slot_times(start: str, end: str, interval_minutes: int) -> list[tuple[str, str]]:
    """
    Return list of (start_time, end_time) string pairs for the given range.
    start/end are "HH:MM" strings. Slots run from start up to (not including) end.

    Example: start=10:00, end=11:00, interval=30 -> [(10:00, 10:30), (10:30, 11:00)]
    """
    fmt = "%H:%M"
    cursor = datetime.strptime(start, fmt)
    fence = datetime.strptime(end, fmt)
    delta = timedelta(minutes=interval_minutes)

    slots: list[tuple[str, str]] = []
    while cursor + delta <= fence:
        slot_end = cursor + delta
        slots.append((cursor.strftime(fmt), slot_end.strftime(fmt)))
        cursor = slot_end

    return slots


_DAY_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3,
    "fri": 4, "sat": 5, "sun": 6,
}


def _dates_for_week(start_date_str: str, days_str: str) -> list[date]:
    """
    Return sorted list of dates starting from start_date that match the given
    weekday abbreviations (comma-separated, e.g. "mon,tue,wed,thu,fri").
    Returns at most 7 dates (one calendar week).
    """
    target_days = {_DAY_MAP[d.strip().lower()] for d in days_str.split(",")}
    start = date.fromisoformat(start_date_str)
    result: list[date] = []
    for offset in range(7):
        candidate = start + timedelta(days=offset)
        if candidate.weekday() in target_days:
            result.append(candidate)
    return sorted(result)


# ---------------------------------------------------------------------------
# Confirmation email helpers
# ---------------------------------------------------------------------------

def _build_confirmation_ics(
    attendee_name: str,
    attendee_email: str,
    slot_date: str,
    start_time: str,
    end_time: str,
    organizer_email: str,
    notes: str | None,
) -> str:
    """Return an iCalendar (RFC 5545) string for the booked discovery call."""
    # Parse slot date + times into datetime objects
    start_dt = datetime.fromisoformat(f"{slot_date}T{start_time}")
    end_dt = datetime.fromisoformat(f"{slot_date}T{end_time}")
    now_utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fmt = "%Y%m%dT%H%M%S"
    uid = str(uuid.uuid4())

    description = "Discovery call with Conaugh McKenna, founder of OASIS AI Solutions."
    if notes:
        # Strip any non-ASCII chars to stay safe on cp1252 terminals
        safe_notes = notes.encode("ascii", errors="replace").decode("ascii")
        description += f"\\nNotes: {safe_notes}"

    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//OASIS AI Solutions//Bravo Booking//EN\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:REQUEST\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTART:{start_dt.strftime(fmt)}\r\n"
        f"DTEND:{end_dt.strftime(fmt)}\r\n"
        f"DTSTAMP:{now_utc}\r\n"
        f"ORGANIZER;CN=Conaugh McKenna:mailto:{organizer_email}\r\n"
        f"ATTENDEE;CN={attendee_name};RSVP=TRUE:mailto:{attendee_email}\r\n"
        "SUMMARY:Discovery Call with Conaugh McKenna\r\n"
        f"DESCRIPTION:{description}\r\n"
        "STATUS:CONFIRMED\r\n"
        "SEQUENCE:0\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )


def _build_confirmation_body(
    attendee_name: str,
    slot_date: str,
    start_time: str,
    end_time: str,
    meeting_type: str,
    notes: str | None,
) -> str:
    """Return the plain-text confirmation email body. ASCII only."""
    start_dt = datetime.fromisoformat(f"{slot_date}T{start_time}")
    end_dt = datetime.fromisoformat(f"{slot_date}T{end_time}")
    date_label = start_dt.strftime("%A, %B %d, %Y")
    time_label = f"{start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')} EST"

    lines = [
        f"Hi {attendee_name},",
        "",
        "Your discovery call is confirmed. Here are the details:",
        "",
        f"  Date:  {date_label}",
        f"  Time:  {time_label}",
        f"  Type:  {meeting_type}",
    ]
    if notes:
        safe_notes = notes.encode("ascii", errors="replace").decode("ascii")
        lines.append(f"  Notes: {safe_notes}")
    lines += [
        "",
        "A calendar invite (.ics) is attached -- add it to your calendar with one click.",
        "",
        "If anything changes on your end, just reply to this email and we will sort it out.",
        "",
        "Looking forward to connecting.",
        "",
        "Conaugh McKenna",
        "Founder, OASIS AI Solutions",
        "oasisai.work",
    ]
    return "\n".join(lines)


def _send_booking_confirmation(
    env_vars: dict[str, str],
    client,
    booking: dict,
    slot: dict,
) -> None:
    """Send the booking confirmation via send_gateway (REWIRED 2026-04-20).

    Transactional intent — the attendee just booked this call themselves,
    so CASL suppression check is skipped (s. 10(9) implied-consent
    exemption). CASL footer + List-Unsubscribe headers still applied.
    SMTP failure is non-fatal — the booking itself stands even if the
    confirmation email fails to deliver.
    """
    from send_gateway import send as gateway_send  # local import avoids cycles

    attendee_name = booking["name"]
    attendee_email = booking["email"]
    slot_date = slot["slot_date"]
    start_time = slot["start_time"]
    end_time = slot["end_time"]
    meeting_type = booking["meeting_type"]
    notes = booking.get("notes")

    gmail_address = env_vars.get("GMAIL_USER") or env_vars.get("GMAIL_ADDRESS", "")
    subject = "Your Discovery Call with Conaugh McKenna - Confirmed"
    body_text = _build_confirmation_body(
        attendee_name, slot_date, start_time, end_time, meeting_type, notes
    )
    ics_content = _build_confirmation_ics(
        attendee_name, attendee_email, slot_date, start_time, end_time,
        gmail_address, notes
    )

    gw = gateway_send(
        channel="email",
        agent_source="booking_engine",
        to_email=attendee_email,
        lead_id=booking.get("lead_id"),
        subject=subject,
        body_text=body_text,
        brand="oasis",
        intent="transactional",
        ics_content=ics_content,
        ics_filename="invite.ics",
        metadata={
            "booking_id": booking.get("id"),
            "slot_id": slot.get("id"),
            "slot_date": slot_date,
            "meeting_type": meeting_type,
        },
    )
    if gw.get("status") != "sent":
        print(
            f"Warning: booking confirmation not sent — "
            f"{gw.get('status')} — {gw.get('reason')}",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def cmd_slots_open(client, args, json_mode: bool) -> None:
    """Create individual time slots for a single date."""
    slot_times = _generate_slot_times(args.start, args.end, args.interval)
    if not slot_times:
        fail(
            f"No slots generated - check that --end ({args.end}) is at least "
            f"{args.interval} minutes after --start ({args.start}).",
            json_mode,
        )

    records = [
        {
            "slot_date": args.date,
            "start_time": s,
            "end_time": e,
            "meeting_type": args.type,
            "is_available": True,
        }
        for s, e in slot_times
    ]

    result = client.table("booking_slots").insert(records).execute()
    created = result.data

    if json_mode:
        output({"created": len(created), "slots": created}, json_mode=True)
    else:
        print(f"Opened {len(created)} slots on {args.date} ({args.type}):")
        for slot in created:
            print(f"  {slot['start_time']} - {slot['end_time']}  id={slot['id']}")


def cmd_slots_open_week(client, args, json_mode: bool) -> None:
    """Create time slots across multiple weekdays starting from a given date."""
    dates = _dates_for_week(args.start_date, args.days)
    if not dates:
        fail("No matching dates found - check --days abbreviations (mon,tue,wed,thu,fri,sat,sun).", json_mode)

    all_created: list[dict] = []
    for d in dates:
        slot_times = _generate_slot_times(args.start, args.end, args.interval)
        records = [
            {
                "slot_date": d.isoformat(),
                "start_time": s,
                "end_time": e,
                "meeting_type": args.type,
                "is_available": True,
            }
            for s, e in slot_times
        ]
        result = client.table("booking_slots").insert(records).execute()
        all_created.extend(result.data)

    if json_mode:
        output({"created": len(all_created), "slots": all_created}, json_mode=True)
    else:
        print(f"Opened {len(all_created)} slots across {len(dates)} day(s) ({args.type}):")
        for d in dates:
            day_slots = [s for s in all_created if s["slot_date"] == d.isoformat()]
            print(f"  {d.isoformat()} ({d.strftime('%a')}): {len(day_slots)} slots")


def cmd_slots_list(client, args, json_mode: bool) -> None:
    """List slots, optionally filtered by date, availability, and type."""
    query = client.table("booking_slots").select("*")

    if hasattr(args, "date") and args.date:
        query = query.eq("slot_date", args.date)
    if hasattr(args, "available_only") and args.available_only:
        query = query.eq("is_available", True)
    if hasattr(args, "type") and args.type:
        query = query.eq("meeting_type", args.type)

    query = query.order("slot_date").order("start_time")
    result = query.execute()
    slots = result.data

    if json_mode:
        output(slots, json_mode=True)
        return

    if not slots:
        print("No slots found.")
        return

    # Group by date for readable output
    by_date: dict[str, list[dict]] = {}
    for s in slots:
        by_date.setdefault(s["slot_date"], []).append(s)

    for d, day_slots in sorted(by_date.items()):
        day_label = date.fromisoformat(d).strftime("%a %Y-%m-%d")
        print(f"{day_label}:")
        for s in day_slots:
            available = "open  " if s["is_available"] else "booked"
            print(f"  [{available}] {s['start_time']} - {s['end_time']}  {s['meeting_type']}  id={s['id']}")
        print()


def cmd_slots_close(client, args, json_mode: bool) -> None:
    """Mark a slot as unavailable (without cancelling any booking)."""
    result = (
        client.table("booking_slots")
        .update({"is_available": False})
        .eq("id", args.slot_id)
        .execute()
    )
    updated = result.data
    if not updated:
        fail(f"Slot {args.slot_id} not found.", json_mode)

    if json_mode:
        output(updated[0], json_mode=True)
    else:
        s = updated[0]
        print(f"Slot closed: {s['slot_date']} {s['start_time']} - {s['end_time']}  id={s['id']}")


def cmd_book(client, args, json_mode: bool, env_vars: dict[str, str] | None = None) -> None:
    """Book an available slot."""
    # Fetch the slot
    slot_result = (
        client.table("booking_slots")
        .select("*")
        .eq("id", args.slot_id)
        .execute()
    )
    if not slot_result.data:
        fail(f"Slot {args.slot_id} not found.", json_mode)

    slot = slot_result.data[0]
    if not slot["is_available"]:
        fail(f"Slot {args.slot_id} is not available.", json_mode)

    # Create the booking
    meet_link = (env_vars or {}).get("GOOGLE_MEET_LINK")
    booking_record: dict = {
        "slot_id": args.slot_id,
        "name": args.name,
        "email": args.email,
        "meeting_type": slot["meeting_type"],
        "status": "confirmed",
        "reminder_sent": False,
    }
    if meet_link:
        booking_record["meeting_link"] = meet_link
    if hasattr(args, "phone") and args.phone:
        booking_record["phone"] = args.phone
    if hasattr(args, "notes") and args.notes:
        booking_record["notes"] = args.notes
    if hasattr(args, "lead_id") and args.lead_id:
        booking_record["lead_id"] = args.lead_id

    booking_result = client.table("bookings").insert(booking_record).execute()
    booking = booking_result.data[0]

    # Mark the slot as unavailable
    client.table("booking_slots").update({"is_available": False}).eq("id", args.slot_id).execute()

    # Send confirmation email with .ics invite (non-fatal on failure)
    _send_booking_confirmation(env_vars or {}, client, booking, slot)

    # Create Google Calendar event (non-fatal)
    _create_calendar_event(env_vars or {}, booking, slot)

    if json_mode:
        output({"booking": booking, "slot": slot}, json_mode=True)
    else:
        print(f"Booking confirmed:")
        print(f"  id:      {booking['id']}")
        print(f"  name:    {booking['name']}")
        print(f"  email:   {booking['email']}")
        print(f"  date:    {slot['slot_date']} {slot['start_time']} - {slot['end_time']}")
        print(f"  type:    {booking['meeting_type']}")
        print(f"  status:  {booking['status']}")


def cmd_cancel(client, args, json_mode: bool) -> None:
    """Cancel a booking and re-open the slot."""
    # Fetch the booking
    booking_result = (
        client.table("bookings")
        .select("*")
        .eq("id", args.booking_id)
        .execute()
    )
    if not booking_result.data:
        fail(f"Booking {args.booking_id} not found.", json_mode)

    booking = booking_result.data[0]
    if booking["status"] == "cancelled":
        fail(f"Booking {args.booking_id} is already cancelled.", json_mode)

    update_data: dict = {"status": "cancelled"}
    if hasattr(args, "reason") and args.reason:
        existing_notes = booking.get("notes") or ""
        update_data["notes"] = f"{existing_notes}\nCancellation reason: {args.reason}".strip()

    updated_result = (
        client.table("bookings")
        .update(update_data)
        .eq("id", args.booking_id)
        .execute()
    )
    updated_booking = updated_result.data[0]

    # Re-open the slot
    client.table("booking_slots").update({"is_available": True}).eq("id", booking["slot_id"]).execute()

    if json_mode:
        output(updated_booking, json_mode=True)
    else:
        print(f"Booking {args.booking_id} cancelled.")
        print(f"  Slot {booking['slot_id']} is now available again.")


def cmd_list_bookings(client, args, json_mode: bool) -> None:
    """List bookings with optional status and upcoming filters."""
    query = client.table("bookings").select("*")

    if hasattr(args, "status") and args.status:
        query = query.eq("status", args.status)

    query = query.order("created_at", desc=True)
    bookings = _join_slots(client, query.execute().data or [])

    # Client-side filter for --upcoming (PostgREST dot-notation on embedded resources is unreliable)
    if hasattr(args, "upcoming") and args.upcoming:
        today = date.today().isoformat()
        bookings = [
            b for b in bookings
            if (b.get("booking_slots") or {}).get("slot_date", "") >= today
        ]

    if json_mode:
        output(bookings, json_mode=True)
        return

    if not bookings:
        print("No bookings found.")
        return

    for b in bookings:
        slot_info = b.get("booking_slots") or {}
        slot_date = slot_info.get("slot_date", "?")
        slot_start = slot_info.get("start_time", "?")
        slot_end = slot_info.get("end_time", "?")
        print(
            f"  [{b['status']:10}] {slot_date} {slot_start}-{slot_end}  "
            f"{b['name']} <{b['email']}>  id={b['id']}"
        )


def cmd_view(client, args, json_mode: bool) -> None:
    """View full details of a single booking."""
    result = (
        client.table("bookings")
        .select("*")
        .eq("id", args.booking_id)
        .execute()
    )
    if not result.data:
        fail(f"Booking {args.booking_id} not found.", json_mode)

    booking = _join_slots(client, result.data, cols="slot_date,start_time,end_time,meeting_type")[0]

    if json_mode:
        output(booking, json_mode=True)
        return

    slot_info = booking.get("booking_slots") or {}
    print(f"Booking {booking['id']}:")
    print(f"  name:          {booking['name']}")
    print(f"  email:         {booking['email']}")
    print(f"  phone:         {booking.get('phone') or '-'}")
    print(f"  meeting_type:  {booking['meeting_type']}")
    print(f"  status:        {booking['status']}")
    print(f"  date:          {slot_info.get('slot_date', '?')} {slot_info.get('start_time', '?')}-{slot_info.get('end_time', '?')}")
    print(f"  meeting_link:  {booking.get('meeting_link') or '-'}")
    print(f"  reminder_sent: {booking['reminder_sent']}")
    print(f"  notes:         {booking.get('notes') or '-'}")
    print(f"  created_at:    {booking['created_at']}")
    if booking.get("lead_id"):
        print(f"  lead_id:       {booking['lead_id']}")


def cmd_available(client, args, json_mode: bool) -> None:
    """Show all available slots grouped by date - the public-facing view."""
    today = date.today()
    days_ahead = args.next if hasattr(args, "next") and args.next else 7
    cutoff = (today + timedelta(days=days_ahead)).isoformat()

    query = (
        client.table("booking_slots")
        .select("*")
        .eq("is_available", True)
        .gte("slot_date", today.isoformat())
        .lte("slot_date", cutoff)
        .order("slot_date")
        .order("start_time")
    )

    if hasattr(args, "type") and args.type:
        query = query.eq("meeting_type", args.type)

    result = query.execute()
    slots = result.data

    if json_mode:
        output(slots, json_mode=True)
        return

    if not slots:
        print("No available slots found.")
        return

    by_date: dict[str, list[dict]] = {}
    for s in slots:
        by_date.setdefault(s["slot_date"], []).append(s)

    print(f"Available slots (next {days_ahead} days):\n")
    for d, day_slots in sorted(by_date.items()):
        day_label = date.fromisoformat(d).strftime("%A, %B") + f" {date.fromisoformat(d).day}"
        print(f"  {day_label}:")
        for s in day_slots:
            print(f"    {s['start_time']} - {s['end_time']}  ({s['meeting_type']})  id={s['id']}")
        print()


def cmd_remind(client, args, json_mode: bool) -> None:
    """
    Find confirmed bookings scheduled for tomorrow that have not had a reminder sent.
    Prints them - the caller is responsible for sending the actual reminder.
    """
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    # Join bookings -> booking_slots where slot_date = tomorrow
    result = (
        client.table("bookings")
        .select("*")
        .eq("status", "confirmed")
        .eq("reminder_sent", False)
        .execute()
    )

    # Filter client-side on the joined slot_date (PostgREST embedded filter)
    pending = [
        b for b in _join_slots(client, result.data or [])
        if (b.get("booking_slots") or {}).get("slot_date") == tomorrow
    ]

    if json_mode:
        output(pending, json_mode=True)
        return

    if not pending:
        print(f"No reminders pending for tomorrow ({tomorrow}).")
        return

    print(f"Reminders needed for {len(pending)} booking(s) on {tomorrow}:\n")
    for b in pending:
        slot_info = b.get("booking_slots") or {}
        print(f"  [{b['id']}] {b['name']} <{b['email']}>")
        print(f"    {slot_info.get('start_time', '?')}-{slot_info.get('end_time', '?')}  {b['meeting_type']}")
        if b.get("phone"):
            print(f"    phone: {b['phone']}")
        print()

    print("To mark reminder sent for a booking:")
    print("  python scripts/integrations/supabase_tool.py update bookings '{\"reminder_sent\": true}' --match '{\"id\": \"<id>\"}'")


def cmd_complete(client, args, json_mode: bool) -> None:
    """Mark a booking as completed, optionally appending call notes."""
    booking_result = (
        client.table("bookings")
        .select("*")
        .eq("id", args.booking_id)
        .execute()
    )
    if not booking_result.data:
        fail(f"Booking {args.booking_id} not found.", json_mode)

    booking = booking_result.data[0]
    update_data: dict = {"status": "completed"}

    if hasattr(args, "notes") and args.notes:
        existing_notes = booking.get("notes") or ""
        separator = "\n" if existing_notes else ""
        update_data["notes"] = f"{existing_notes}{separator}Post-call: {args.notes}".strip()

    result = (
        client.table("bookings")
        .update(update_data)
        .eq("id", args.booking_id)
        .execute()
    )
    updated = result.data[0]

    if json_mode:
        output(updated, json_mode=True)
    else:
        print(f"Booking {args.booking_id} marked as completed.")
        if update_data.get("notes"):
            print(f"  notes: {update_data['notes']}")


# ---------------------------------------------------------------------------
# New commands: auto-book, generate-link, send-reminders
# ---------------------------------------------------------------------------

def _build_reminder_body(
    attendee_name: str,
    slot_date: str,
    start_time: str,
    end_time: str,
    meeting_type: str,
    meet_link: str | None,
) -> str:
    """Return the plain-text reminder email body. ASCII only."""
    start_dt = datetime.fromisoformat(f"{slot_date}T{start_time}")
    end_dt = datetime.fromisoformat(f"{slot_date}T{end_time}")
    date_label = start_dt.strftime("%A, %B %d, %Y")
    time_label = f"{start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')} EST"

    lines = [
        f"Hi {attendee_name},",
        "",
        "Just a quick reminder about your call tomorrow:",
        "",
        f"  Date:  {date_label}",
        f"  Time:  {time_label}",
        f"  Type:  {meeting_type}",
    ]
    if meet_link:
        lines.append(f"  Link:  {meet_link}")
    lines += [
        "",
        "Looking forward to it. Reply to this email if anything comes up.",
        "",
        "Conaugh McKenna",
        "Founder, OASIS AI Solutions",
        "oasisai.work",
    ]
    return "\n".join(lines)


def _send_reminder_email(
    env_vars: dict[str, str],
    booking: dict,
    slot: dict,
    meet_link: str | None,
) -> tuple[bool, str | None]:
    """Send a next-day reminder via send_gateway (REWIRED 2026-04-20).
    Transactional intent. Returns (success, error_message)."""
    from send_gateway import send as gateway_send  # noqa: F401  (used below)

    attendee_name = booking["name"]
    attendee_email = booking["email"]
    slot_date = slot["slot_date"]
    start_time = slot["start_time"]
    end_time = slot["end_time"]
    meeting_type = booking["meeting_type"]

    subject = "Reminder: Your Call Tomorrow with Conaugh McKenna"
    body_text = _build_reminder_body(
        attendee_name, slot_date, start_time, end_time, meeting_type, meet_link
    )

    gw = gateway_send(
        channel="email",
        agent_source="booking_engine",
        to_email=attendee_email,
        lead_id=booking.get("lead_id"),
        subject=subject,
        body_text=body_text,
        brand="oasis",
        intent="transactional",
        metadata={
            "booking_id": booking.get("id"),
            "slot_id": slot.get("id"),
            "reminder_for_date": slot_date,
            "meet_link": meet_link,
        },
    )
    if gw.get("status") == "sent":
        return True, None
    return False, gw.get("reason", f"gateway status={gw.get('status')}")


def cmd_auto_book(client, args, json_mode: bool, env_vars: dict[str, str]) -> None:
    """
    Find the first available slot on or after --preferred-time, book it,
    send a confirmation email, and notify CC via Telegram.

    --preferred-time accepts "YYYY-MM-DD HH:MM" or "YYYY-MM-DD".
    When only a date is given, the earliest slot on that date is used.
    """
    # Parse preferred time
    preferred_str: str = args.preferred_time.strip()
    preferred_date: str
    preferred_start: str | None = None

    if "T" in preferred_str or " " in preferred_str:
        # "2026-03-25 10:00" or "2026-03-25T10:00"
        sep = "T" if "T" in preferred_str else " "
        parts = preferred_str.split(sep, 1)
        preferred_date = parts[0]
        preferred_start = parts[1][:5]  # HH:MM
    else:
        preferred_date = preferred_str

    # Fetch available slots from the preferred date forward (next 30 days max)
    cutoff = (date.fromisoformat(preferred_date) + timedelta(days=30)).isoformat()
    query = (
        client.table("booking_slots")
        .select("*")
        .eq("is_available", True)
        .gte("slot_date", preferred_date)
        .lte("slot_date", cutoff)
        .order("slot_date")
        .order("start_time")
    )
    meeting_type = getattr(args, "type", None) or "discovery"
    query = query.eq("meeting_type", meeting_type)

    result = query.execute()
    slots = result.data

    if not slots:
        fail(
            f"No available {meeting_type} slots found from {preferred_date} (checked 30 days ahead).",
            json_mode,
        )

    # Pick the closest slot to the preferred time
    chosen_slot: dict | None = None
    if preferred_start:
        # Prefer exact match on start_time on the preferred date; fall back to next nearest
        for s in slots:
            if s["slot_date"] == preferred_date and s["start_time"][:5] == preferred_start:
                chosen_slot = s
                break
        if chosen_slot is None:
            # Take the first slot on or after the preferred date
            chosen_slot = slots[0]
    else:
        chosen_slot = slots[0]

    assert chosen_slot is not None  # unreachable — slots is non-empty here

    # Attach the Google Meet link
    meet_link = env_vars.get("GOOGLE_MEET_LINK")

    # Create the booking record
    booking_record: dict = {
        "slot_id": chosen_slot["id"],
        "name": args.name,
        "email": args.email,
        "meeting_type": chosen_slot["meeting_type"],
        "status": "confirmed",
        "reminder_sent": False,
    }
    if meet_link:
        booking_record["meeting_link"] = meet_link
    if getattr(args, "phone", None):
        booking_record["phone"] = args.phone
    if getattr(args, "notes", None):
        booking_record["notes"] = args.notes
    if getattr(args, "lead_id", None):
        booking_record["lead_id"] = args.lead_id

    booking_result = client.table("bookings").insert(booking_record).execute()
    booking = booking_result.data[0]

    # Mark slot unavailable
    client.table("booking_slots").update({"is_available": False}).eq("id", chosen_slot["id"]).execute()

    # Send confirmation email (non-fatal)
    _send_booking_confirmation(env_vars, client, booking, chosen_slot)

    # Create Google Calendar event (non-fatal)
    _create_calendar_event(env_vars, booking, chosen_slot)

    # Notify CC via Telegram (non-fatal)
    slot_date = chosen_slot["slot_date"]
    start_t = chosen_slot["start_time"]
    end_t = chosen_slot["end_time"]
    tg_message = (
        f"New booking: {args.name} ({args.email})\n"
        f"{slot_date} {start_t}-{end_t} [{chosen_slot['meeting_type']}]\n"
        f"Booking ID: {booking['id']}"
    )
    if meet_link:
        tg_message += f"\nMeet: {meet_link}"
    _telegram_notify(tg_message, category="booking")

    if json_mode:
        output({"booking": booking, "slot": chosen_slot}, json_mode=True)
    else:
        print("Booking confirmed:")
        print(f"  id:      {booking['id']}")
        print(f"  name:    {booking['name']}")
        print(f"  email:   {booking['email']}")
        print(f"  date:    {slot_date} {start_t} - {end_t}")
        print(f"  type:    {booking['meeting_type']}")
        print(f"  status:  {booking['status']}")
        if meet_link:
            print(f"  link:    {meet_link}")


def cmd_generate_link(client, args, json_mode: bool, env_vars: dict[str, str]) -> None:
    """
    Generate a shareable availability message with the Google Meet link.
    Outputs formatted text that CC can paste directly into a DM or email.
    """
    meet_link = env_vars.get("GOOGLE_MEET_LINK")
    today = date.today()
    days_ahead: int = args.next if hasattr(args, "next") and args.next else 7
    cutoff = (today + timedelta(days=days_ahead)).isoformat()

    query = (
        client.table("booking_slots")
        .select("*")
        .eq("is_available", True)
        .gte("slot_date", today.isoformat())
        .lte("slot_date", cutoff)
        .order("slot_date")
        .order("start_time")
    )
    if hasattr(args, "type") and args.type:
        query = query.eq("meeting_type", args.type)

    result = query.execute()
    slots = result.data

    if json_mode:
        output(
            {
                "meet_link": meet_link,
                "available_slots": slots,
                "days_ahead": days_ahead,
            },
            json_mode=True,
        )
        return

    if not slots:
        print("No available slots found. Open some slots first:")
        print("  python scripts/booking_engine.py slots open-week ...")
        return

    # Group by date
    by_date: dict[str, list[dict]] = {}
    for s in slots:
        by_date.setdefault(s["slot_date"], []).append(s)

    lines = [
        "Hey! Here are my available times for a quick call:",
        "",
    ]
    for d, day_slots in sorted(by_date.items()):
        day_label = date.fromisoformat(d).strftime("%A, %B") + f" {date.fromisoformat(d).day}"
        slot_labels = [
            f"{s['start_time'][:5]}-{s['end_time'][:5]} EST"
            for s in day_slots
        ]
        lines.append(f"  {day_label}: {', '.join(slot_labels)}")

    lines.append("")
    if meet_link:
        lines.append(f"All times are via Google Meet: {meet_link}")
    else:
        lines.append("(Google Meet link — set GOOGLE_MEET_LINK in .env.agents)")

    lines += [
        "",
        "Just reply with what works and I'll confirm it.",
        "",
        "-- Conaugh",
    ]

    print("\n".join(lines))


def cmd_send_reminders(client, args, json_mode: bool, env_vars: dict[str, str]) -> None:
    """
    Send reminder emails for all confirmed bookings scheduled for tomorrow
    that have not yet had a reminder sent. Marks reminder_sent=true on success.

    --dry-run prints what would be sent without touching Supabase or SMTP.
    """
    dry_run: bool = getattr(args, "dry_run", False)
    meet_link = env_vars.get("GOOGLE_MEET_LINK")
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    result = (
        client.table("bookings")
        .select("*")
        .eq("status", "confirmed")
        .eq("reminder_sent", False)
        .execute()
    )

    pending = [
        b for b in _join_slots(client, result.data or [])
        if (b.get("booking_slots") or {}).get("slot_date") == tomorrow
    ]

    if not pending:
        msg = f"No reminders pending for tomorrow ({tomorrow})."
        if json_mode:
            output({"sent": 0, "failed": 0, "message": msg}, json_mode=True)
        else:
            print(msg)
        return

    results: list[dict] = []

    for booking in pending:
        slot_info = booking.get("booking_slots") or {}
        name = booking["name"]
        email_addr = booking["email"]
        start_t = slot_info.get("start_time", "?")
        end_t = slot_info.get("end_time", "?")

        if dry_run:
            results.append({
                "booking_id": booking["id"],
                "name": name,
                "email": email_addr,
                "time": f"{start_t}-{end_t}",
                "status": "dry-run",
            })
            continue

        # Construct a minimal slot dict for _send_reminder_email
        slot_dict = {
            "slot_date": tomorrow,
            "start_time": start_t,
            "end_time": end_t,
        }

        success, error = _send_reminder_email(env_vars, booking, slot_dict, meet_link)
        status = "sent" if success else "failed"

        if success:
            # Mark reminder_sent so we don't double-send
            try:
                client.table("bookings").update({"reminder_sent": True}).eq("id", booking["id"]).execute()
            except Exception as exc:  # noqa: BLE001 — non-fatal, booking record still exists
                print(f"Warning: could not mark reminder_sent for {booking['id']}: {exc}", file=sys.stderr)

            # Telegram alert to CC
            _telegram_notify(
                f"Reminder sent to {name} ({email_addr}) for tomorrow {start_t}-{end_t}",
                category="booking",
                silent=True,
            )
        else:
            print(f"Warning: reminder not sent to {email_addr} — {error}", file=sys.stderr)

        results.append({
            "booking_id": booking["id"],
            "name": name,
            "email": email_addr,
            "time": f"{start_t}-{end_t}",
            "status": status,
            "error": error,
        })

    sent = sum(1 for r in results if r["status"] == "sent")
    failed = sum(1 for r in results if r["status"] == "failed")
    dry = sum(1 for r in results if r["status"] == "dry-run")

    if json_mode:
        output(
            {"sent": sent, "failed": failed, "dry_run": dry, "results": results},
            json_mode=True,
        )
        return

    label = "[DRY RUN] " if dry_run else ""
    print(f"{label}Reminder run complete for {tomorrow}:")
    for r in results:
        status_label = r["status"].upper()
        print(f"  [{status_label}] {r['name']} <{r['email']}> — {r['time']}")
        if r.get("error"):
            print(f"    Error: {r['error']}")
    if not dry_run:
        print(f"\n  {sent} sent, {failed} failed.")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Booking Engine - self-hosted Cal.com replacement backed by Supabase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="Output results as JSON",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ---- slots ----
    p_slots = sub.add_parser("slots", help="Manage time slots")
    slots_sub = p_slots.add_subparsers(dest="slots_command", metavar="ACTION")

    # slots open
    p_open = slots_sub.add_parser("open", help="Open slots for a single date")
    p_open.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    p_open.add_argument("--start", required=True, help="Start time (HH:MM)")
    p_open.add_argument("--end", required=True, help="End time (HH:MM)")
    p_open.add_argument("--interval", required=True, type=int, metavar="MINUTES", help="Slot duration in minutes")
    p_open.add_argument("--type", required=True, dest="type", metavar="MEETING_TYPE", help="Meeting type (e.g. discovery)")

    # slots open-week
    p_open_week = slots_sub.add_parser("open-week", help="Open slots across multiple weekdays")
    p_open_week.add_argument("--start-date", required=True, help="First date of the week (YYYY-MM-DD)")
    p_open_week.add_argument("--days", required=True, help="Weekday abbreviations, comma-separated (e.g. mon,tue,wed,thu,fri)")
    p_open_week.add_argument("--start", required=True, help="Daily start time (HH:MM)")
    p_open_week.add_argument("--end", required=True, help="Daily end time (HH:MM)")
    p_open_week.add_argument("--interval", required=True, type=int, metavar="MINUTES", help="Slot duration in minutes")
    p_open_week.add_argument("--type", required=True, dest="type", metavar="MEETING_TYPE", help="Meeting type")

    # slots list
    p_slots_list = slots_sub.add_parser("list", help="List slots")
    p_slots_list.add_argument("--date", help="Filter by date (YYYY-MM-DD)")
    p_slots_list.add_argument("--available-only", action="store_true", help="Only show available slots")
    p_slots_list.add_argument("--type", dest="type", metavar="MEETING_TYPE", help="Filter by meeting type")

    # slots close
    p_close = slots_sub.add_parser("close", help="Mark a slot as unavailable")
    p_close.add_argument("slot_id", help="Slot UUID")

    # ---- book ----
    p_book = sub.add_parser("book", help="Book an available slot")
    p_book.add_argument("slot_id", help="Slot UUID to book")
    p_book.add_argument("--name", required=True, help="Attendee name")
    p_book.add_argument("--email", required=True, help="Attendee email")
    p_book.add_argument("--phone", help="Attendee phone (optional)")
    p_book.add_argument("--notes", help="Notes (optional)")
    p_book.add_argument("--lead-id", dest="lead_id", help="Link to a lead UUID (optional)")

    # ---- cancel ----
    p_cancel = sub.add_parser("cancel", help="Cancel a booking")
    p_cancel.add_argument("booking_id", help="Booking UUID")
    p_cancel.add_argument("--reason", help="Cancellation reason (optional)")

    # ---- list ----
    p_list = sub.add_parser("list", help="List bookings")
    p_list.add_argument("--status", choices=["confirmed", "completed", "cancelled"], help="Filter by status")
    p_list.add_argument("--upcoming", action="store_true", help="Only show future bookings")

    # ---- view ----
    p_view = sub.add_parser("view", help="View a single booking")
    p_view.add_argument("booking_id", help="Booking UUID")

    # ---- available ----
    p_avail = sub.add_parser("available", help="Show available slots (public view)")
    p_avail.add_argument("--type", dest="type", metavar="MEETING_TYPE", help="Filter by meeting type")
    p_avail.add_argument("--next", type=int, default=7, metavar="DAYS", help="How many days ahead to show (default: 7)")

    # ---- remind ----
    sub.add_parser("remind", help="Find bookings needing reminders (tomorrow, not yet sent)")

    # ---- complete ----
    p_complete = sub.add_parser("complete", help="Mark a booking as completed")
    p_complete.add_argument("booking_id", help="Booking UUID")
    p_complete.add_argument("--notes", help="Post-call notes (optional)")

    # ---- auto-book ----
    p_auto = sub.add_parser(
        "auto-book",
        help="Find first available slot near a preferred time, book it, confirm by email, alert CC",
    )
    p_auto.add_argument("--name", required=True, help="Attendee full name")
    p_auto.add_argument("--email", required=True, help="Attendee email address")
    p_auto.add_argument(
        "--preferred-time",
        dest="preferred_time",
        required=True,
        help='Preferred date/time: "YYYY-MM-DD HH:MM" or "YYYY-MM-DD" for earliest on that day',
    )
    p_auto.add_argument("--type", dest="type", default="discovery", metavar="MEETING_TYPE",
                        help="Meeting type (default: discovery)")
    p_auto.add_argument("--phone", help="Attendee phone (optional)")
    p_auto.add_argument("--notes", help="Notes (optional)")
    p_auto.add_argument("--lead-id", dest="lead_id", help="Link to a lead UUID (optional)")

    # ---- generate-link ----
    p_link = sub.add_parser(
        "generate-link",
        help="Print a shareable availability message with the Google Meet link",
    )
    p_link.add_argument("--type", dest="type", metavar="MEETING_TYPE",
                        help="Filter by meeting type (optional)")
    p_link.add_argument("--next", type=int, default=7, metavar="DAYS",
                        help="Days ahead to include (default: 7)")

    # ---- send-reminders ----
    p_reminders = sub.add_parser(
        "send-reminders",
        help="Send reminder emails for all confirmed bookings scheduled for tomorrow",
    )
    p_reminders.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Print what would be sent without emailing or updating Supabase",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    json_mode: bool = getattr(args, "output_json", False)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    env_vars = load_env()
    client = get_client(env_vars)

    if args.command == "slots":
        if not args.slots_command:
            # Find and print the slots subparser help
            for action in parser._subparsers._actions:  # type: ignore[attr-defined]
                for name, subparser in getattr(action, "_name_parser_map", {}).items():
                    if name == "slots":
                        subparser.print_help()
                        break
            sys.exit(1)

        dispatch = {
            "open": cmd_slots_open,
            "open-week": cmd_slots_open_week,
            "list": cmd_slots_list,
            "close": cmd_slots_close,
        }
        handler = dispatch.get(args.slots_command)
        if handler:
            handler(client, args, json_mode)
        else:
            parser.print_help()

    elif args.command == "book":
        cmd_book(client, args, json_mode, env_vars)
    elif args.command == "cancel":
        cmd_cancel(client, args, json_mode)
    elif args.command == "list":
        cmd_list_bookings(client, args, json_mode)
    elif args.command == "view":
        cmd_view(client, args, json_mode)
    elif args.command == "available":
        cmd_available(client, args, json_mode)
    elif args.command == "remind":
        cmd_remind(client, args, json_mode)
    elif args.command == "complete":
        cmd_complete(client, args, json_mode)
    elif args.command == "auto-book":
        cmd_auto_book(client, args, json_mode, env_vars)
    elif args.command == "generate-link":
        cmd_generate_link(client, args, json_mode, env_vars)
    elif args.command == "send-reminders":
        cmd_send_reminders(client, args, json_mode, env_vars)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
