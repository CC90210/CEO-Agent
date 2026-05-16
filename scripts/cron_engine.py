"""
Cron Engine - Business Automation Job Manager
Defines and tracks all automated business workflows. Not a cron runner itself -
n8n handles scheduling. This is the source of truth for what should be automated,
seeded into Supabase so n8n and agents share a single registry.

All credentials loaded from .env.agents (never hardcoded).

Usage:
  python scripts/cron_engine.py list [--active-only]
  python scripts/cron_engine.py add --name "Daily Content Post" --schedule "0 9 * * *" --type content_post --config '{"pillar": "ceo_log", "platform": "x"}'
  python scripts/cron_engine.py toggle <job_id>
  python scripts/cron_engine.py run <job_id>
  python scripts/cron_engine.py due
  python scripts/cron_engine.py seed
  python scripts/cron_engine.py --json <any command>
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


# -- Credential loading --------------------------------------------------------

def load_env() -> dict[str, str]:
    """Load .env.agents from project root."""
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
    """Create a Supabase client for the bravo project."""
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: 'supabase' package not installed. Run: pip install supabase", file=sys.stderr)
        sys.exit(1)

    url = env_vars.get("BRAVO_SUPABASE_URL")
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        print(
            "ERROR: Missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY in .env.agents",
            file=sys.stderr,
        )
        sys.exit(1)

    return create_client(url, key)


# -- Seed definitions ----------------------------------------------------------

SEED_JOBS: list[dict] = [
    # Marketing/social cron jobs (content_post × 3, content_planning,
    # ig_research) were removed from this seed on 2026-04-26 when
    # marketing/social ownership transferred to Maven (CMO-Agent).
    # Maven seeds its own equivalents in CMO-Agent/scripts/cron_engine.py.
    {
        "name": "Lead Follow-up Check",
        "description": "Check for overdue follow-ups, send reminders",
        "schedule": "0 8 * * MON-FRI",
        "action_type": "lead_followup",
        "action_config": {"overdue_threshold_days": 3, "notify_channel": "telegram"},
        "is_active": True,
    },
    {
        # Phase 5c — OASIS HQ daily AI brief. Sonnet narrates the
        # briefing_snapshot into a 5-bullet morning summary, shipped to
        # CC's Telegram via notify(force=True). Empty MRR / pipeline data
        # still produces a brief that says "nothing happened" — the cron's
        # job is to fire reliably, not to gate on activity.
        "name": "Daily Bravo Brief",
        "description": "AI-narrated morning brief — pipeline, MRR, follow-ups — sent to CC's Telegram",
        "schedule": "0 6 * * *",
        "action_type": "daily_brief",
        "action_config": {"notify_channel": "telegram"},
        "is_active": True,
    },
    {
        # Phase 6a — OASIS auto-score sweep. Scans tenant_records for
        # OASIS leads with no ai_score and scores them in batches of 25
        # so the operator's morning view already has scores on
        # overnight-arrived leads. Daily at 05:45 — finishes before the
        # 06:00 Daily Brief so the brief can cite the new scores.
        "name": "OASIS Auto-Score Leads",
        "description": "Score any unscored OASIS leads in scorable stages (new/contacted/qualified/proposal/negotiation). Daily, batches of 25.",
        "schedule": "45 5 * * *",
        "action_type": "auto_score_leads",
        "action_config": {"batch_size": 25},
        "is_active": True,
    },
    {
        # Phase 10.2 — Morning Pow Wow Call. Claude drafts a ~120-word
        # motivational/flirty monologue, ElevenLabs renders it in Aura's
        # voice, Telegram sendVoice ships it as an inline voicemail at
        # 08:00 every morning. Cost ~$0.02/day. CC opts in/out via the
        # standard toggle.
        "name": "Morning Pow Wow Call",
        "description": "Daily 8 a.m. voice note from Aura — a ~120-word motivational + flirty kickoff monologue delivered as a Telegram voice message. Cost ~$0.02/day (Claude draft + ElevenLabs TTS).",
        "schedule": "0 8 * * *",
        "action_type": "morning_powwow",
        "action_config": {"voice": "aura"},
        "is_active": True,
    },
    {
        "name": "Booking Reminders",
        "description": "Send reminders for tomorrow's bookings",
        "schedule": "0 18 * * *",
        "action_type": "booking_reminder",
        "action_config": {"hours_ahead": 24, "channels": ["email", "sms"]},
        "is_active": True,
    },
    {
        "name": "Stripe Revenue Sync",
        "description": "Sync latest Stripe events to revenue_events",
        "schedule": "0 6 * * *",
        "action_type": "stripe_sync",
        "action_config": {"lookback_hours": 25},
        "is_active": True,
    },
    {
        "name": "Weekly MRR Report",
        "description": "Generate and log weekly MRR dashboard",
        "schedule": "0 9 * * MON",
        "action_type": "revenue_report",
        "action_config": {"report_type": "mrr_weekly", "notify_channel": "telegram"},
        "is_active": True,
    },
    {
        "name": "Weekly Pipeline Review",
        "description": "Score all leads, identify hot prospects",
        "schedule": "0 10 * * MON",
        "action_type": "pipeline_review",
        "action_config": {"auto_score": True, "hot_threshold": 70},
        "is_active": True,
    },
    {
        "name": "Nurture Sequence Check",
        "description": "Process pending nurture sequence steps",
        "schedule": "0 10 * * MON-FRI",
        "action_type": "nurture_check",
        "action_config": {"max_sends_per_run": 20},
        "is_active": True,
    },
    {
        "name": "Monthly Metrics Snapshot",
        "description": "Log monthly_metrics for the previous month",
        "schedule": "0 9 1 * *",
        "action_type": "monthly_snapshot",
        "action_config": {"tables": ["revenue_events", "leads", "content_calendar"]},
        "is_active": True,
    },
    {
        "name": "Funnel Lead Sync",
        "description": "Sync new funnel_leads to CRM leads table + fire welcome email (24h backstop)",
        "schedule": "*/5 * * * *",
        "action_type": "funnel_sync",
        "action_config": {"auto_welcome_email": True},
        "is_active": True,
    },
    {
        "name": "Funnel Fast-Poll",
        "description": "Near-realtime funnel_leads detection (2-minute window). Fires high-priority Telegram digest when new form submissions land, so CC knows within ~1 min of a lead filling out the CC Funnel on Instagram/social.",
        "schedule": "*/1 * * * *",
        "action_type": "funnel_fast_poll",
        "action_config": {"window_seconds": 120, "priority": True},
        "is_active": True,
    },
    {
        "name": "Daily Briefing Snapshot",
        "description": "Prep Table layer (brain/AGENTIC_OS_REFERENCE.md §3). Aggregates revenue/pipeline/health into state/snapshots/latest_briefing.json so ceo-briefing skill reads one JSON instead of running 4 engines live. Runnable manually until n8n handler exists.",
        "schedule": "0 6 * * *",
        "action_type": "snapshot_run",
        "action_config": {"script": "scripts/snapshots/briefing_snapshot.py", "args": []},
        "is_active": True,
    },
    {
        "name": "Weekly Qualified-Leads Snapshot",
        "description": "Saturday 22:00 ranking of leads scoring >= 60 by MRR potential. Output: state/snapshots/latest_leads.json. Revenue-Hunter agent cherry-picks from this instead of running opencli + scoring per session.",
        "schedule": "0 22 * * SAT",
        "action_type": "snapshot_run",
        "action_config": {"script": "scripts/snapshots/leads_snapshot.py", "args": ["--min-score", "60"]},
        "is_active": True,
    },
    {
        "name": "Daily Client Alerts Snapshot",
        "description": "Daily 07:00 RED/ORANGE client extraction with risk factors + suggested actions. Output: state/snapshots/latest_client_alerts.json. Chief-of-Staff reads this instead of full health report.",
        "schedule": "0 7 * * *",
        "action_type": "snapshot_run",
        "action_config": {"script": "scripts/snapshots/client_alerts_snapshot.py", "args": []},
        "is_active": True,
    },
]


# -- Cron schedule parsing (next-run approximation) ----------------------------

def _next_run_approx(schedule: str) -> Optional[str]:
    """
    Best-effort approximation of the next UTC run time for a 5-field cron expression.
    Handles simple cases (numeric fields, '*', step '/N'). Day-of-week names
    (MON, MON-FRI, etc.) are normalised before parsing.
    Returns an ISO-8601 string or None if the expression is not parseable.
    """
    DAY_NAMES = {
        "SUN": "0", "MON": "1", "TUE": "2", "WED": "3",
        "THU": "4", "FRI": "5", "SAT": "6",
    }

    def normalise(field: str) -> str:
        """Replace day-name abbreviations with numeric equivalents."""
        for name, num in DAY_NAMES.items():
            field = field.replace(name, num)
        return field

    parts = schedule.strip().split()
    if len(parts) != 5:
        return None

    minute_f, hour_f, dom_f, month_f, dow_f = [normalise(p) for p in parts]

    def parse_int(field: str) -> Optional[int]:
        try:
            return int(field)
        except (ValueError, TypeError):
            return None

    # Only handle simple numeric or '*' fields for the direct values
    minute = parse_int(minute_f)
    hour = parse_int(hour_f)
    if minute is None or hour is None:
        return None

    now = datetime.now(timezone.utc)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # Advance forward if the candidate is already in the past
    if candidate <= now:
        candidate = candidate + timedelta(days=1)

    # If specific weekdays are requested, walk forward until one matches
    if dow_f != "*":
        allowed_days: set[int] = set()
        for part in dow_f.split(","):
            if "-" in part:
                start, end = part.split("-", 1)
                s, e = parse_int(start), parse_int(end)
                if s is not None and e is not None:
                    for d in range(s, e + 1):
                        allowed_days.add(d % 7)
            else:
                d = parse_int(part)
                if d is not None:
                    allowed_days.add(d % 7)

        if allowed_days:
            # Python: Monday=0 ... Sunday=6; cron: Sunday=0 ... Saturday=6
            for _ in range(8):
                python_weekday = candidate.weekday()
                # convert Python weekday to cron weekday (Sun=0)
                cron_weekday = (python_weekday + 1) % 7
                if cron_weekday in allowed_days:
                    break
                candidate = candidate + timedelta(days=1)

    return candidate.isoformat()


# -- Formatting helpers --------------------------------------------------------

def fmt_date(iso_str: str | None) -> str:
    """Format an ISO timestamp to a readable short datetime."""
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso_str[:16] if iso_str else "-"


def truncate(text: str, max_len: int = 40) -> str:
    if not text:
        return ""
    return text[: max_len - 1] + "..." if len(text) > max_len else text


# -- Command handlers ----------------------------------------------------------

def cmd_list(client, args, output_json: bool) -> None:
    """List cron jobs with optional active-only filter."""
    query = client.table("cron_jobs").select("*")

    if args.active_only:
        query = query.eq("is_active", True)

    query = query.order("created_at", desc=False)
    result = query.execute()
    jobs = result.data or []

    if output_json:
        print(json.dumps(jobs, indent=2, default=str))
        return

    if not jobs:
        print("No cron jobs found.")
        return

    col_id      = 8
    col_name    = 28
    col_sched   = 18
    col_type    = 20
    col_active  = 7
    col_runs    = 6
    col_last    = 16

    header = (
        f"{'ID':<{col_id}}  "
        f"{'NAME':<{col_name}}  "
        f"{'SCHEDULE':<{col_sched}}  "
        f"{'TYPE':<{col_type}}  "
        f"{'ACTIVE':<{col_active}}  "
        f"{'RUNS':>{col_runs}}  "
        f"{'LAST RUN':<{col_last}}"
    )
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    for job in jobs:
        job_id   = str(job.get("id", ""))[:col_id]
        name     = truncate(job.get("name", "-"), col_name)
        schedule = truncate(job.get("schedule", "-"), col_sched)
        jtype    = truncate(job.get("action_type", "-"), col_type)
        active   = "YES" if job.get("is_active") else "no"
        runs     = str(job.get("run_count") or 0)
        last_run = fmt_date(job.get("last_run_at"))

        print(
            f"{job_id:<{col_id}}  "
            f"{name:<{col_name}}  "
            f"{schedule:<{col_sched}}  "
            f"{jtype:<{col_type}}  "
            f"{active:<{col_active}}  "
            f"{runs:>{col_runs}}  "
            f"{last_run:<{col_last}}"
        )

    print(sep)
    active_count = sum(1 for j in jobs if j.get("is_active"))
    print(f"  {len(jobs)} job(s) - {active_count} active")


def cmd_add(client, args, output_json: bool) -> None:
    """Add a new cron job definition."""
    try:
        config = json.loads(args.config) if args.config else {}
    except json.JSONDecodeError:
        print("ERROR: --config must be valid JSON.", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(timezone.utc).isoformat()
    next_run = _next_run_approx(args.schedule)

    payload: dict = {
        "name": args.name,
        "schedule": args.schedule,
        "action_type": args.type,
        "action_config": config,
        "is_active": True,
        "run_count": 0,
        "created_at": now,
    }
    if args.description:
        payload["description"] = args.description
    if next_run:
        payload["next_run_at"] = next_run

    result = client.table("cron_jobs").insert(payload).execute()
    job = result.data[0] if result.data else {}

    if output_json:
        print(json.dumps(job, indent=2, default=str))
        return

    print("Cron job added.")
    print(f"  ID:          {job.get('id', '?')}")
    print(f"  Name:        {job.get('name')}")
    print(f"  Schedule:    {job.get('schedule')}")
    print(f"  Type:        {job.get('action_type')}")
    print(f"  Next run:    {fmt_date(job.get('next_run_at'))}")
    print(f"  Active:      yes")


def cmd_toggle(client, args, output_json: bool) -> None:
    """Toggle a cron job's is_active state."""
    result = client.table("cron_jobs").select("id, name, is_active").eq("id", args.job_id).execute()
    if not result.data:
        print(f"ERROR: Cron job '{args.job_id}' not found.", file=sys.stderr)
        sys.exit(1)

    job = result.data[0]
    new_state = not job.get("is_active", False)

    updated_result = (
        client.table("cron_jobs")
        .update({"is_active": new_state})
        .eq("id", args.job_id)
        .execute()
    )
    updated = updated_result.data[0] if updated_result.data else {}

    if output_json:
        print(json.dumps(updated, indent=2, default=str))
        return

    state_label = "enabled" if new_state else "disabled"
    print(f"Cron job {state_label}: {job.get('name', args.job_id)}")
    print(f"  ID:     {args.job_id}")
    print(f"  Active: {'yes' if new_state else 'no'}")


def cmd_run(client, args, output_json: bool) -> None:
    """Mark a cron job as run: update last_run_at and increment run_count."""
    result = client.table("cron_jobs").select("*").eq("id", args.job_id).execute()
    if not result.data:
        print(f"ERROR: Cron job '{args.job_id}' not found.", file=sys.stderr)
        sys.exit(1)

    job = result.data[0]
    now = datetime.now(timezone.utc).isoformat()
    new_count = (job.get("run_count") or 0) + 1
    next_run = _next_run_approx(job.get("schedule", ""))

    updates: dict = {
        "last_run_at": now,
        "run_count": new_count,
        "last_result": args.result or "ok",
    }
    if next_run:
        updates["next_run_at"] = next_run

    updated_result = client.table("cron_jobs").update(updates).eq("id", args.job_id).execute()
    updated = updated_result.data[0] if updated_result.data else {}

    if output_json:
        print(json.dumps(updated, indent=2, default=str))
        return

    print(f"Cron job marked as run: {job.get('name', args.job_id)}")
    print(f"  Run count:  {new_count}")
    print(f"  Last run:   {fmt_date(now)}")
    print(f"  Next run:   {fmt_date(next_run)}")
    print(f"  Result:     {updates['last_result']}")


def cmd_due(client, args, output_json: bool) -> None:
    """Show active jobs whose next_run_at is now or overdue."""
    now_iso = datetime.now(timezone.utc).isoformat()

    result = (
        client.table("cron_jobs")
        .select("*")
        .eq("is_active", True)
        .lte("next_run_at", now_iso)
        .not_.is_("next_run_at", "null")
        .order("next_run_at", desc=False)
        .execute()
    )
    jobs = result.data or []

    if output_json:
        print(json.dumps(jobs, indent=2, default=str))
        return

    if not jobs:
        print("No cron jobs are due right now.")
        return

    now_display = fmt_date(now_iso)
    print(f"Due now (as of {now_display}):\n")
    for job in jobs:
        next_run = fmt_date(job.get("next_run_at"))
        overdue = " [OVERDUE]" if (job.get("next_run_at") or "") < now_iso else ""
        print(f"  {next_run}{overdue}")
        print(f"    [{str(job.get('id', ''))[:8]}] {job.get('name', '-')} - {job.get('action_type', '-')}")
        if job.get("description"):
            print(f"    {job['description']}")
        print()

    print(f"  {len(jobs)} job(s) due.")


def cmd_seed(client, args, output_json: bool) -> None:
    """Seed the initial set of business automation cron jobs (skips existing by name)."""
    # Fetch existing names to avoid duplicates
    existing_result = client.table("cron_jobs").select("name").execute()
    existing_names: set[str] = {r["name"] for r in (existing_result.data or [])}

    inserted: list[dict] = []
    skipped: list[str] = []

    now = datetime.now(timezone.utc).isoformat()

    for definition in SEED_JOBS:
        if definition["name"] in existing_names:
            skipped.append(definition["name"])
            continue

        next_run = _next_run_approx(definition["schedule"])
        payload = {
            **definition,
            "run_count": 0,
            "created_at": now,
        }
        if next_run:
            payload["next_run_at"] = next_run

        result = client.table("cron_jobs").insert(payload).execute()
        if result.data:
            inserted.append(result.data[0])

    if output_json:
        print(json.dumps({"inserted": inserted, "skipped": skipped}, indent=2, default=str))
        return

    if inserted:
        print(f"Seeded {len(inserted)} cron job(s):\n")
        for job in inserted:
            print(f"  [{str(job.get('id', ''))[:8]}] {job.get('name', '-')}")
            print(f"    Schedule: {job.get('schedule', '-')}  Type: {job.get('action_type', '-')}")
            print(f"    Next run: {fmt_date(job.get('next_run_at'))}")
            print()
    else:
        print("No new jobs inserted.")

    if skipped:
        print(f"Skipped {len(skipped)} already-existing job(s):")
        for name in skipped:
            print(f"  - {name}")


# -- Argument parser -----------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cron_engine.py",
        description="Cron Engine - Business Automation Job Manager (Supabase-backed)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list
  %(prog)s list --active-only
  %(prog)s add --name "Daily Content Post" --schedule "0 9 * * *" --type content_post --config '{"pillar": "ceo_log", "platform": "x"}'
  %(prog)s toggle <job_id>
  %(prog)s run <job_id>
  %(prog)s run <job_id> --result "error: timeout"
  %(prog)s due
  %(prog)s seed
  %(prog)s --json list
  %(prog)s --json due
        """,
    )

    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="Output raw JSON for agent consumption",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # -- list ------------------------------------------------------------------
    p_list = subparsers.add_parser("list", help="List all cron jobs")
    p_list.add_argument(
        "--active-only",
        dest="active_only",
        action="store_true",
        help="Only show active jobs",
    )

    # -- add -------------------------------------------------------------------
    p_add = subparsers.add_parser("add", help="Add a new cron job definition")
    p_add.add_argument("--name", required=True, help="Human-readable job name")
    p_add.add_argument("--schedule", required=True, help="5-field cron expression (e.g. '0 9 * * *')")
    p_add.add_argument("--type", required=True, dest="type", help="action_type identifier (e.g. content_post)")
    p_add.add_argument("--config", default="{}", help="JSON action_config object")
    p_add.add_argument("--description", help="Human-readable description of what this job does")

    # -- toggle ----------------------------------------------------------------
    p_toggle = subparsers.add_parser("toggle", help="Enable or disable a cron job")
    p_toggle.add_argument("job_id", help="Cron job UUID")

    # -- run -------------------------------------------------------------------
    p_run = subparsers.add_parser("run", help="Mark a job as run (updates last_run_at and run_count)")
    p_run.add_argument("job_id", help="Cron job UUID")
    p_run.add_argument("--result", help="Result string to store in last_result (default: 'ok')")

    # -- due -------------------------------------------------------------------
    subparsers.add_parser("due", help="Show active jobs that are due or overdue right now")

    # -- seed ------------------------------------------------------------------
    subparsers.add_parser("seed", help="Seed the initial 12 business automation cron jobs")

    return parser


# -- Entry point ---------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    output_json: bool = getattr(args, "output_json", False)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    env_vars = load_env()
    client = get_client(env_vars)

    dispatch = {
        "list":   cmd_list,
        "add":    cmd_add,
        "toggle": cmd_toggle,
        "run":    cmd_run,
        "due":    cmd_due,
        "seed":   cmd_seed,
    }

    handler = dispatch.get(args.command)
    if handler:
        try:
            handler(client, args, output_json)
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
