"""
Booking Engine — Self-hosted scheduling system replacing Cal.com.
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
  python scripts/booking_engine.py cancel <booking_id> [--reason "Rescheduled"]
  python scripts/booking_engine.py list [--status confirmed|completed|cancelled] [--upcoming]
  python scripts/booking_engine.py view <booking_id>

  python scripts/booking_engine.py available [--type discovery] [--next 7]
  python scripts/booking_engine.py remind
  python scripts/booking_engine.py complete <booking_id> [--notes "Good call"]

  Add --json to any command for machine-readable output.
"""

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path


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
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


def get_client(env_vars: dict[str, str]):
    """Create a Supabase client using BRAVO_SUPABASE_* credentials."""
    from supabase import create_client  # type: ignore[import-untyped]

    url = env_vars.get("BRAVO_SUPABASE_URL")
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        print(
            "ERROR: Missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY in .env.agents",
            file=sys.stderr,
        )
        sys.exit(1)

    return create_client(url, key)


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
# Slot generation helpers
# ---------------------------------------------------------------------------

def _generate_slot_times(start: str, end: str, interval_minutes: int) -> list[tuple[str, str]]:
    """
    Return list of (start_time, end_time) string pairs for the given range.
    start/end are "HH:MM" strings. Slots run from start up to (not including) end.

    Example: start=10:00, end=11:00, interval=30 → [(10:00, 10:30), (10:30, 11:00)]
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
# Command implementations
# ---------------------------------------------------------------------------

def cmd_slots_open(client, args, json_mode: bool) -> None:
    """Create individual time slots for a single date."""
    slot_times = _generate_slot_times(args.start, args.end, args.interval)
    if not slot_times:
        fail(
            f"No slots generated — check that --end ({args.end}) is at least "
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
            print(f"  {slot['start_time']} – {slot['end_time']}  id={slot['id']}")


def cmd_slots_open_week(client, args, json_mode: bool) -> None:
    """Create time slots across multiple weekdays starting from a given date."""
    dates = _dates_for_week(args.start_date, args.days)
    if not dates:
        fail("No matching dates found — check --days abbreviations (mon,tue,wed,thu,fri,sat,sun).", json_mode)

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
            print(f"  [{available}] {s['start_time']} – {s['end_time']}  {s['meeting_type']}  id={s['id']}")
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
        print(f"Slot closed: {s['slot_date']} {s['start_time']} – {s['end_time']}  id={s['id']}")


def cmd_book(client, args, json_mode: bool) -> None:
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
    booking_record: dict = {
        "slot_id": args.slot_id,
        "name": args.name,
        "email": args.email,
        "meeting_type": slot["meeting_type"],
        "status": "confirmed",
        "reminder_sent": False,
    }
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

    if json_mode:
        output({"booking": booking, "slot": slot}, json_mode=True)
    else:
        print(f"Booking confirmed:")
        print(f"  id:      {booking['id']}")
        print(f"  name:    {booking['name']}")
        print(f"  email:   {booking['email']}")
        print(f"  date:    {slot['slot_date']} {slot['start_time']} – {slot['end_time']}")
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
    query = client.table("bookings").select("*, booking_slots(slot_date, start_time, end_time)")

    if hasattr(args, "status") and args.status:
        query = query.eq("status", args.status)

    if hasattr(args, "upcoming") and args.upcoming:
        today = date.today().isoformat()
        # Filter via the related slot date — use a subquery approach via order + gte on joined data
        # PostgREST supports filtering on embedded tables with the dot notation
        query = query.gte("booking_slots.slot_date", today)

    query = query.order("created_at", desc=True)
    result = query.execute()
    bookings = result.data

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
            f"  [{b['status']:10}] {slot_date} {slot_start}–{slot_end}  "
            f"{b['name']} <{b['email']}>  id={b['id']}"
        )


def cmd_view(client, args, json_mode: bool) -> None:
    """View full details of a single booking."""
    result = (
        client.table("bookings")
        .select("*, booking_slots(slot_date, start_time, end_time, meeting_type)")
        .eq("id", args.booking_id)
        .execute()
    )
    if not result.data:
        fail(f"Booking {args.booking_id} not found.", json_mode)

    booking = result.data[0]

    if json_mode:
        output(booking, json_mode=True)
        return

    slot_info = booking.get("booking_slots") or {}
    print(f"Booking {booking['id']}:")
    print(f"  name:          {booking['name']}")
    print(f"  email:         {booking['email']}")
    print(f"  phone:         {booking.get('phone') or '—'}")
    print(f"  meeting_type:  {booking['meeting_type']}")
    print(f"  status:        {booking['status']}")
    print(f"  date:          {slot_info.get('slot_date', '?')} {slot_info.get('start_time', '?')}–{slot_info.get('end_time', '?')}")
    print(f"  meeting_link:  {booking.get('meeting_link') or '—'}")
    print(f"  reminder_sent: {booking['reminder_sent']}")
    print(f"  notes:         {booking.get('notes') or '—'}")
    print(f"  created_at:    {booking['created_at']}")
    if booking.get("lead_id"):
        print(f"  lead_id:       {booking['lead_id']}")


def cmd_available(client, args, json_mode: bool) -> None:
    """Show all available slots grouped by date — the public-facing view."""
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
        day_label = date.fromisoformat(d).strftime("%A, %B %-d")
        print(f"  {day_label}:")
        for s in day_slots:
            print(f"    {s['start_time']} – {s['end_time']}  ({s['meeting_type']})  id={s['id']}")
        print()


def cmd_remind(client, args, json_mode: bool) -> None:
    """
    Find confirmed bookings scheduled for tomorrow that have not had a reminder sent.
    Prints them — the caller is responsible for sending the actual reminder.
    """
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    # Join bookings → booking_slots where slot_date = tomorrow
    result = (
        client.table("bookings")
        .select("*, booking_slots(slot_date, start_time, end_time)")
        .eq("status", "confirmed")
        .eq("reminder_sent", False)
        .execute()
    )

    # Filter client-side on the joined slot_date (PostgREST embedded filter)
    pending = [
        b for b in result.data
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
        print(f"    {slot_info.get('start_time', '?')}–{slot_info.get('end_time', '?')}  {b['meeting_type']}")
        if b.get("phone"):
            print(f"    phone: {b['phone']}")
        print()

    print("To mark reminder sent for a booking:")
    print("  python scripts/supabase_tool.py update bookings '{\"reminder_sent\": true}' --match '{\"id\": \"<id>\"}'")


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
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Booking Engine — self-hosted Cal.com replacement backed by Supabase",
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
        cmd_book(client, args, json_mode)
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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
