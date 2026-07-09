---
name: booking-management
description: Manage discovery call scheduling using booking_engine.py — a self-hosted Cal.com replacement backed by Supabase. Covers opening slots, booking leads, sending reminders, and completing meetings.
triggers: [booking, calendar, schedule, discovery call, slot, reminder, appointment, meeting]
tier: standard
dependencies: [lead-management, email-marketing]
---

# Booking Management — Self-Hosted Scheduling

## Overview

`booking_engine.py` replaces Cal.com with zero subscription cost. Slots and bookings are stored in the Supabase bravo project. The engine handles the full lifecycle: open slots, confirm bookings, send email reminders, and log meeting outcomes back to the lead record. Run `remind` daily in the heartbeat to catch same-day and next-day meetings automatically.

---

## Tool Routing

All operations go through `python scripts/booking_engine.py`. Append `--json` to any command for machine-readable output.

### Slot Management

| Operation | Command |
|-----------|---------|
| Open a single day of slots | `booking_engine.py slots open --date 2026-03-24 --start 10:00 --end 16:00 --interval 30 --type discovery` |
| Open a full week of slots | `booking_engine.py slots open-week --start-date 2026-03-24 --days mon,tue,wed,thu,fri --start 10:00 --end 16:00 --interval 30 --type discovery` |
| List slots | `booking_engine.py slots list --available-only --type discovery` |
| Close a slot | `booking_engine.py slots close <slot_id>` |
| View available slots (next N days) | `booking_engine.py available --type discovery --next 7` |

### Booking Operations

| Operation | Command |
|-----------|---------|
| Book a slot for a lead | `booking_engine.py book <slot_id> --name "John Smith" --email "john@acme.com" --lead-id uuid --notes "Interested in AI automation"` |
| Cancel a booking | `booking_engine.py cancel <booking_id> --reason "Rescheduled"` |
| List upcoming bookings | `booking_engine.py list --status confirmed --upcoming` |
| View a booking | `booking_engine.py view <booking_id>` |
| Mark meeting complete | `booking_engine.py complete <booking_id> --notes "Great call. Sending proposal Monday."` |

### Reminders

| Operation | Command |
|-----------|---------|
| Send due reminders | `booking_engine.py remind` |

---

## Slot Management Rules

- Open slots at the start of each week for the week ahead. Don't open rolling months — it creates calendar pressure.
- Default slot type for OASIS AI outreach: `discovery` (20-30 min calls).
- Block off personal commitments by simply not opening those times — there is no "busy" state; absence of a slot is the block.
- Close slots that go unbooled by end of day: `booking_engine.py slots list --date YYYY-MM-DD` then `slots close <slot_id>` for each empty one.

---

## Booking Flow

The standard flow for converting a hot lead into a booked call:

1. Lead reaches `qualified` status in lead_engine (`lead_engine.py update <lead_id> --status qualified`)
2. Pull next available slot: `booking_engine.py available --type discovery --next 7 --json`
3. Book the slot: `booking_engine.py book <slot_id> --name "..." --email "..." --lead-id <lead_id>`
4. Send confirmation email with meeting link: `email_engine.py send --to <email> --subject "Discovery Call Confirmed" --body "..." --lead-id <lead_id>`
5. Log the interaction: `lead_engine.py interact <lead_id> --type meeting --channel phone --subject "Discovery call booked"`

The engine stores a `meeting_link` field on each booking. Populate it with the Google Meet or Zoom link when sending the confirmation.

---

## Reminder System

Run `booking_engine.py remind` daily — ideally in the morning heartbeat. It sends reminder emails to all leads with confirmed bookings due in the next 24 hours, using the `email_engine.py send` flow internally.

Reminders fire once per booking (the `reminder_sent` flag prevents duplicates). If a reminder fails (email bounce, SMTP error), it is logged with `status=failed` and the flag stays false — it will retry on the next `remind` run.

---

## Post-Meeting Workflow

After every discovery call, run this sequence within 2 hours while the conversation is fresh:

1. Mark complete with notes: `booking_engine.py complete <booking_id> --notes "Discussed X, pain point is Y, budget is Z"`
2. Update lead status: `lead_engine.py update <lead_id> --status proposal --notes "Call complete. Sending proposal."`
3. Log meeting interaction: `lead_engine.py interact <lead_id> --type meeting --channel phone --subject "Discovery call"`
4. If advancing to proposal: prepare and send within 24 hours

Meeting notes on `complete` are stored against the booking record. Pull them back when writing a proposal: `booking_engine.py view <booking_id>`.

---

## Integration Points

- **lead_engine.py** — the booking flow starts when a lead hits `qualified`; post-meeting, update the lead status immediately
- **email_engine.py** — confirmation and reminder emails are sent via email_engine; pass `--lead-id` to keep the interaction log accurate
- **revenue_engine.py** — meetings that close into retainers should be logged: `revenue_engine.py log-revenue` the day the contract is confirmed — on explicit CC request only; Atlas (CFO) owns revenue reporting


## Outbound Gate Compliance

> **All outbound communications** (emails, notifications, messages) referenced in this skill
> MUST be routed through `scripts/integrations/send_gateway.py`. Direct `smtplib` or raw
> SMTP calls are architecturally prohibited (V5.6 chokepoint rule). Use:
> ```bash
> python scripts/integrations/send_gateway.py send --channel email --to <email> --subject "..." --body "..." --lead-id <uuid>
> ```
> See [[skills/send-gateway/SKILL.md]] for the full contract.

## Obsidian Links
- [[skills/INDEX.md]] | [[brain/CAPABILITIES]]
