"""
Content Calendar & Template Engine - CC's content operations hub.
Supabase-backed. Designed to feed Late MCP for publishing.
All credentials loaded from .env.agents (never hardcoded).

Keys required: BRAVO_SUPABASE_URL, BRAVO_SUPABASE_SERVICE_ROLE_KEY

Usage:
  python scripts/content_engine.py calendar [--status draft|scheduled|posted] [--platform x|linkedin|instagram] [--next 7]
  python scripts/content_engine.py create --platform x --pillar ceo_log --body "Built 14 new tables tonight..."
  python scripts/content_engine.py create-multi --platforms x,linkedin,instagram --pillar quote_drop --body "..."
  python scripts/content_engine.py edit <content_id> --body "Updated text" [--status scheduled]
  python scripts/content_engine.py delete <content_id>
  python scripts/content_engine.py view <content_id>
  python scripts/content_engine.py due
  python scripts/content_engine.py mark-posted <content_id> [--late-post-id abc123]
  python scripts/content_engine.py templates list
  python scripts/content_engine.py templates create --name "..." --platform x --pillar ceo_log --template "..." --vars '["day"]'
  python scripts/content_engine.py templates render <template_id> --vars '{"day": "47"}'
  python scripts/content_engine.py stats [--days 30]
  python scripts/content_engine.py week-plan
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# -- Platform character limits -------------------------------------------------

PLATFORM_LIMITS: dict[str, int] = {
    "x": 280,
    "threads": 500,
    "instagram": 2200,
    "linkedin": 3000,
    "tiktok": 4000,
}

# -- Content pillars -----------------------------------------------------------

PILLARS = [
    "sobriety_log",
    "quote_drop",
    "ceo_log",
    "educational",
    "promotional",
]

# -- Week-plan slot definitions (ET hour, pillar) -----------------------------

WEEK_PLAN_SLOTS = [
    (9,  "quote_drop"),
    (13, "ceo_log"),        # alternates with educational - handled in week_plan logic
    (19, "sobriety_log"),
]

WEEK_PLAN_PLATFORM = "x"   # default platform for week-plan drafts


# -- Env loading ---------------------------------------------------------------

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
    """Create a Supabase client for the Bravo project."""
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: 'supabase' package not installed. Run: pip install supabase", file=sys.stderr)
        sys.exit(1)

    url = env_vars.get("BRAVO_SUPABASE_URL")
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        print("ERROR: Missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY in .env.agents", file=sys.stderr)
        sys.exit(1)

    return create_client(url, key)


# -- Helpers -------------------------------------------------------------------

def truncate_for_platform(body: str, platform: str) -> str:
    """Truncate body to fit within platform's character limit."""
    limit = PLATFORM_LIMITS.get(platform)
    if limit is None or len(body) <= limit:
        return body
    # Reserve 3 chars for ellipsis
    return body[: limit - 3] + "..."


def warn_limit(body: str, platform: str) -> None:
    """Print a warning to stderr if body exceeds platform limit."""
    limit = PLATFORM_LIMITS.get(platform)
    if limit is not None and len(body) > limit:
        print(
            f"WARNING: Body length {len(body)} exceeds {platform} limit of {limit} chars.",
            file=sys.stderr,
        )


def render_template(template_body: str, variables: dict[str, str]) -> str:
    """Replace {{var}} placeholders with provided values."""
    result = template_body
    for key, value in variables.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    # Report any unreplaced placeholders
    remaining = re.findall(r"\{\{(\w+)\}\}", result)
    if remaining:
        print(f"WARNING: Unreplaced variables in template: {remaining}", file=sys.stderr)
    return result


def format_datetime(value: str | None) -> str:
    """Return a clean human-readable datetime string or a dash."""
    if not value:
        return "-"
    # Strip microseconds for readability
    return value[:16].replace("T", " ")


# -- Commands: content calendar ------------------------------------------------

def cmd_calendar(client, args) -> None:
    query = client.table("content_calendar").select("*")

    if args.status:
        query = query.eq("status", args.status)
    if args.platform:
        query = query.eq("platform", args.platform)
    if args.next:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=args.next)
        query = (
            query
            .gte("scheduled_for", now.isoformat())
            .lte("scheduled_for", cutoff.isoformat())
        )

    query = query.order("scheduled_for", desc=False)
    result = query.execute()
    rows = result.data or []

    if args.output_json:
        print(json.dumps(rows, indent=2, default=str))
        return

    if not rows:
        print("No content found matching filters.")
        return

    print(f"Content Calendar ({len(rows)} entries):\n")
    for r in rows:
        scheduled = format_datetime(r.get("scheduled_for"))
        posted = format_datetime(r.get("posted_at"))
        body_preview = (r.get("body") or "")[:60].replace("\n", " ")
        print(
            f"  [{r['id']}] [{r.get('status', '?')}] [{r.get('platform', '?')}]"
            f" [{r.get('pillar', '?')}]"
        )
        print(f"    Scheduled: {scheduled}  Posted: {posted}")
        if r.get("title"):
            print(f"    Title: {r['title']}")
        print(f"    Body:  {body_preview}...")
        print()


def cmd_create(client, args) -> None:
    platform = args.platform
    body = args.body

    warn_limit(body, platform)

    row: dict[str, object] = {
        "platform": platform,
        "pillar": args.pillar,
        "body": body,
        "status": "draft",
    }
    if args.title:
        row["title"] = args.title
    if args.scheduled_for:
        row["scheduled_for"] = args.scheduled_for
        row["status"] = "scheduled"
    if args.hashtags:
        row["hashtags"] = args.hashtags

    result = client.table("content_calendar").insert(row).execute()
    created = result.data[0] if result.data else {}

    if args.output_json:
        print(json.dumps(created, indent=2, default=str))
        return

    print(f"Content created!")
    print(f"  ID:        {created.get('id', '?')}")
    print(f"  Platform:  {platform}")
    print(f"  Pillar:    {args.pillar}")
    print(f"  Status:    {created.get('status', '?')}")
    if args.scheduled_for:
        print(f"  Scheduled: {args.scheduled_for}")
    print(f"  Body ({len(body)} chars):  {body[:80]}")


def cmd_create_multi(client, args) -> None:
    platforms = [p.strip() for p in args.platforms.split(",")]
    original_body = args.body
    created_rows: list[dict] = []

    for platform in platforms:
        body = truncate_for_platform(original_body, platform)
        if len(original_body) != len(body):
            print(
                f"INFO: Body truncated for {platform}: {len(original_body)} -> {len(body)} chars",
                file=sys.stderr,
            )

        row: dict[str, object] = {
            "platform": platform,
            "pillar": args.pillar,
            "body": body,
            "status": "draft",
        }
        if args.title:
            row["title"] = args.title
        if args.scheduled_for:
            row["scheduled_for"] = args.scheduled_for
            row["status"] = "scheduled"
        if args.hashtags:
            row["hashtags"] = args.hashtags

        result = client.table("content_calendar").insert(row).execute()
        if result.data:
            created_rows.append(result.data[0])

    if args.output_json:
        print(json.dumps(created_rows, indent=2, default=str))
        return

    print(f"Created {len(created_rows)} content entries:\n")
    for r in created_rows:
        body_len = len(r.get("body") or "")
        limit = PLATFORM_LIMITS.get(r.get("platform", ""), 9999)
        flag = " [TRUNCATED]" if body_len < len(original_body) else ""
        print(f"  [{r['id']}] {r.get('platform', '?')} - {body_len}/{limit} chars{flag}")


def cmd_edit(client, args) -> None:
    content_id = args.content_id
    updates: dict[str, object] = {}

    if args.body is not None:
        updates["body"] = args.body
        # Retrieve platform for limit check
        existing = client.table("content_calendar").select("platform").eq("id", content_id).execute()
        if existing.data:
            platform = existing.data[0].get("platform", "")
            warn_limit(args.body, platform)
    if args.status is not None:
        updates["status"] = args.status
    if args.scheduled_for is not None:
        updates["scheduled_for"] = args.scheduled_for
    if args.title is not None:
        updates["title"] = args.title
    if args.hashtags is not None:
        updates["hashtags"] = args.hashtags

    if not updates:
        print("ERROR: No fields to update. Provide at least one of --body, --status, --scheduled-for, --title, --hashtags.", file=sys.stderr)
        sys.exit(1)

    result = client.table("content_calendar").update(updates).eq("id", content_id).execute()
    updated = result.data[0] if result.data else {}

    if args.output_json:
        print(json.dumps(updated, indent=2, default=str))
        return

    print(f"Content [{content_id}] updated.")
    for k, v in updates.items():
        print(f"  {k}: {str(v)[:80]}")


def cmd_delete(client, args) -> None:
    content_id = args.content_id

    # Fetch first to show what's being deleted
    existing = client.table("content_calendar").select("*").eq("id", content_id).execute()
    if not existing.data:
        print(f"ERROR: Content [{content_id}] not found.", file=sys.stderr)
        sys.exit(1)

    row = existing.data[0]
    client.table("content_calendar").delete().eq("id", content_id).execute()

    if args.output_json:
        print(json.dumps({"deleted": True, "id": content_id}, indent=2))
        return

    print(f"Deleted [{content_id}] - {row.get('platform', '?')} / {row.get('pillar', '?')}")
    print(f"  Body: {(row.get('body') or '')[:60]}...")


def cmd_view(client, args) -> None:
    content_id = args.content_id
    result = client.table("content_calendar").select("*").eq("id", content_id).execute()

    if not result.data:
        print(f"ERROR: Content [{content_id}] not found.", file=sys.stderr)
        sys.exit(1)

    row = result.data[0]

    if args.output_json:
        print(json.dumps(row, indent=2, default=str))
        return

    print(f"Content [{content_id}]:\n")
    for field in ["platform", "pillar", "status", "title", "hashtags", "media_url",
                  "scheduled_for", "posted_at", "late_post_id", "engagement", "created_at"]:
        val = row.get(field)
        if val is not None:
            print(f"  {field:15s}: {val}")
    print(f"\n  body ({len(row.get('body') or '')} chars):")
    print(f"  {row.get('body', '')}")


def cmd_due(client, args) -> None:
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    result = (
        client.table("content_calendar")
        .select("*")
        .eq("status", "scheduled")
        .gte("scheduled_for", start_of_day.isoformat())
        .lt("scheduled_for", end_of_day.isoformat())
        .order("scheduled_for", desc=False)
        .execute()
    )
    rows = result.data or []

    if args.output_json:
        print(json.dumps(rows, indent=2, default=str))
        return

    if not rows:
        print("No content due today.")
        return

    print(f"Due today ({now.strftime('%Y-%m-%d')}) - {len(rows)} post(s):\n")
    for r in rows:
        scheduled = format_datetime(r.get("scheduled_for"))
        body_preview = (r.get("body") or "")[:70].replace("\n", " ")
        print(f"  [{r['id']}] {scheduled} - [{r.get('platform', '?')}] [{r.get('pillar', '?')}]")
        print(f"    {body_preview}...")
        print()


def cmd_mark_posted(client, args) -> None:
    content_id = args.content_id
    now = datetime.now(timezone.utc).isoformat()

    updates: dict[str, object] = {
        "status": "posted",
        "posted_at": now,
    }
    if args.late_post_id:
        updates["late_post_id"] = args.late_post_id

    result = client.table("content_calendar").update(updates).eq("id", content_id).execute()
    updated = result.data[0] if result.data else {}

    if args.output_json:
        print(json.dumps(updated, indent=2, default=str))
        return

    print(f"Content [{content_id}] marked as posted.")
    print(f"  Posted at: {now}")
    if args.late_post_id:
        print(f"  Late post ID: {args.late_post_id}")


# -- Commands: templates -------------------------------------------------------

def cmd_templates_list(client, args) -> None:
    query = client.table("content_templates").select("*").order("created_at", desc=True)
    result = query.execute()
    rows = result.data or []

    if args.output_json:
        print(json.dumps(rows, indent=2, default=str))
        return

    if not rows:
        print("No templates found.")
        return

    print(f"Content Templates ({len(rows)}):\n")
    for r in rows:
        variables = r.get("variables") or []
        times_used = r.get("times_used") or 0
        print(f"  [{r['id']}] {r.get('name', 'unnamed')} - [{r.get('platform', '?')}] [{r.get('pillar', '?')}]")
        print(f"    Variables: {variables}  Used: {times_used}x")
        print(f"    Template:  {(r.get('template_body') or '')[:80]}...")
        print()


def cmd_templates_create(client, args) -> None:
    variables = json.loads(args.vars) if args.vars else []

    row: dict[str, object] = {
        "name": args.name,
        "platform": args.platform,
        "pillar": args.pillar,
        "template_body": args.template,
        "variables": variables,
        "times_used": 0,
    }
    if args.example_output:
        row["example_output"] = args.example_output

    result = client.table("content_templates").insert(row).execute()
    created = result.data[0] if result.data else {}

    if args.output_json:
        print(json.dumps(created, indent=2, default=str))
        return

    print(f"Template created!")
    print(f"  ID:        {created.get('id', '?')}")
    print(f"  Name:      {args.name}")
    print(f"  Platform:  {args.platform}")
    print(f"  Variables: {variables}")


def cmd_templates_render(client, args) -> None:
    template_id = args.template_id
    variables = json.loads(args.vars) if args.vars else {}

    result = client.table("content_templates").select("*").eq("id", template_id).execute()
    if not result.data:
        print(f"ERROR: Template [{template_id}] not found.", file=sys.stderr)
        sys.exit(1)

    template = result.data[0]
    rendered = render_template(template.get("template_body") or "", variables)

    # Increment times_used
    current = template.get("times_used") or 0
    client.table("content_templates").update({"times_used": current + 1}).eq("id", template_id).execute()

    platform = template.get("platform", "")
    warn_limit(rendered, platform)

    if args.output_json:
        print(json.dumps({"rendered": rendered, "length": len(rendered)}, indent=2))
        return

    limit = PLATFORM_LIMITS.get(platform, 0)
    print(f"Rendered template [{template_id}] - {len(rendered)}/{limit} chars:\n")
    print(rendered)


# -- Commands: stats -----------------------------------------------------------

def cmd_stats(client, args) -> None:
    days = args.days
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    result = (
        client.table("content_calendar")
        .select("platform,pillar,status,engagement,posted_at")
        .gte("created_at", since)
        .execute()
    )
    rows = result.data or []

    # Aggregate
    by_platform: dict[str, int] = {}
    by_pillar: dict[str, int] = {}
    by_status: dict[str, int] = {}
    total_engagement = 0

    for r in rows:
        p = r.get("platform") or "unknown"
        pl = r.get("pillar") or "unknown"
        s = r.get("status") or "unknown"
        eng = r.get("engagement") or 0

        by_platform[p] = by_platform.get(p, 0) + 1
        by_pillar[pl] = by_pillar.get(pl, 0) + 1
        by_status[s] = by_status.get(s, 0) + 1
        total_engagement += eng

    stats = {
        "period_days": days,
        "total_entries": len(rows),
        "by_platform": by_platform,
        "by_pillar": by_pillar,
        "by_status": by_status,
        "total_engagement": total_engagement,
    }

    if args.output_json:
        print(json.dumps(stats, indent=2))
        return

    print(f"Content Stats - Last {days} days ({len(rows)} total entries):\n")
    print("  By Platform:")
    for k, v in sorted(by_platform.items(), key=lambda x: -x[1]):
        print(f"    {k:15s}: {v}")
    print("\n  By Pillar:")
    for k, v in sorted(by_pillar.items(), key=lambda x: -x[1]):
        print(f"    {k:15s}: {v}")
    print("\n  By Status:")
    for k, v in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"    {k:15s}: {v}")
    print(f"\n  Total Engagement: {total_engagement}")


# -- Commands: week-plan -------------------------------------------------------

def cmd_week_plan(client, args) -> None:
    """Generate 21 draft content entries (3/day x 7 days)."""
    now = datetime.now(timezone.utc)
    # Start from the next full day at midnight UTC
    base_date = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    # ET is UTC-4 (EDT) or UTC-5 (EST). Use -4 as default for spring/summer.
    et_offset_hours = 4

    rows_to_insert: list[dict] = []

    for day_offset in range(7):
        day = base_date + timedelta(days=day_offset)
        for slot_index, (hour_et, pillar) in enumerate(WEEK_PLAN_SLOTS):
            # Alternate slot_index 1 between ceo_log and educational by day parity
            if slot_index == 1:
                pillar = "ceo_log" if day_offset % 2 == 0 else "educational"

            # Convert ET hour to UTC
            scheduled_utc = day + timedelta(hours=hour_et + et_offset_hours)

            rows_to_insert.append({
                "platform": WEEK_PLAN_PLATFORM,
                "pillar": pillar,
                "body": f"[DRAFT - {pillar.replace('_', ' ').title()} - {day.strftime('%a %b %d')}]",
                "status": "draft",
                "scheduled_for": scheduled_utc.isoformat(),
            })

    result = client.table("content_calendar").insert(rows_to_insert).execute()
    created = result.data or []

    if args.output_json:
        print(json.dumps(created, indent=2, default=str))
        return

    print(f"Week plan created - {len(created)} draft entries:\n")
    # Group by day for display
    current_day = ""
    for r in created:
        scheduled = r.get("scheduled_for") or ""
        day_str = scheduled[:10]
        if day_str != current_day:
            current_day = day_str
            print(f"  {day_str}")
        time_str = scheduled[11:16] if len(scheduled) >= 16 else "?"
        print(f"    {time_str} UTC - [{r.get('pillar', '?')}] ID: {r.get('id', '?')}")
    print(f"\nAll created as status=draft on platform={WEEK_PLAN_PLATFORM}.")
    print("Fill in body text for each entry with: content_engine.py edit <id> --body '...'")


# -- Argument parser -----------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Content Calendar & Template Engine - Supabase-backed, Late MCP-ready",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s calendar
  %(prog)s calendar --status draft --platform x --next 7
  %(prog)s create --platform x --pillar ceo_log --body "Built 14 tables tonight"
  %(prog)s create --platform linkedin --pillar educational --body "..." --scheduled-for "2026-03-20 09:00"
  %(prog)s create-multi --platforms x,linkedin,instagram --pillar quote_drop --body "..."
  %(prog)s edit abc123 --body "Revised copy" --status scheduled
  %(prog)s delete abc123
  %(prog)s view abc123
  %(prog)s due
  %(prog)s mark-posted abc123 --late-post-id lp_xyz
  %(prog)s templates list
  %(prog)s templates create --name "CEO Log" --platform x --pillar ceo_log --template "Day {{day}}. {{insight}}" --vars '["day","insight"]'
  %(prog)s templates render tmpl123 --vars '{"day": "47", "insight": "Shipped the content engine"}'
  %(prog)s stats --days 30
  %(prog)s week-plan

Platform limits: x=280 | threads=500 | instagram=2200 | linkedin=3000 | tiktok=4000
        """,
    )
    parser.add_argument("--json", dest="output_json", action="store_true",
                        help="Output raw JSON for agent consumption")

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # calendar
    p_cal = subparsers.add_parser("calendar", help="List content calendar entries")
    p_cal.add_argument("--status", choices=["draft", "scheduled", "posted"])
    p_cal.add_argument("--platform", choices=list(PLATFORM_LIMITS.keys()))
    p_cal.add_argument("--next", type=int, metavar="DAYS",
                       help="Only entries scheduled within the next N days")

    # create
    p_create = subparsers.add_parser("create", help="Create a single content entry")
    p_create.add_argument("--platform", required=True, choices=list(PLATFORM_LIMITS.keys()))
    p_create.add_argument("--pillar", required=True, choices=PILLARS)
    p_create.add_argument("--body", required=True)
    p_create.add_argument("--title")
    p_create.add_argument("--scheduled-for", dest="scheduled_for",
                          metavar="DATETIME", help="e.g. '2026-03-20 09:00'")
    p_create.add_argument("--hashtags", help="Comma-separated hashtags, no #")

    # create-multi
    p_cm = subparsers.add_parser("create-multi", help="Create one entry per platform (auto-truncates)")
    p_cm.add_argument("--platforms", required=True,
                      help="Comma-separated platforms: x,linkedin,instagram")
    p_cm.add_argument("--pillar", required=True, choices=PILLARS)
    p_cm.add_argument("--body", required=True)
    p_cm.add_argument("--title")
    p_cm.add_argument("--scheduled-for", dest="scheduled_for", metavar="DATETIME")
    p_cm.add_argument("--hashtags")

    # edit
    p_edit = subparsers.add_parser("edit", help="Edit a content entry")
    p_edit.add_argument("content_id", help="Content ID to edit")
    p_edit.add_argument("--body")
    p_edit.add_argument("--status", choices=["draft", "scheduled", "posted"])
    p_edit.add_argument("--scheduled-for", dest="scheduled_for", metavar="DATETIME")
    p_edit.add_argument("--title")
    p_edit.add_argument("--hashtags")

    # delete
    p_del = subparsers.add_parser("delete", help="Delete a content entry")
    p_del.add_argument("content_id", help="Content ID to delete")

    # view
    p_view = subparsers.add_parser("view", help="View a single content entry in full")
    p_view.add_argument("content_id", help="Content ID to view")

    # due
    subparsers.add_parser("due", help="Show content scheduled for today that is not yet posted")

    # mark-posted
    p_mp = subparsers.add_parser("mark-posted", help="Mark a content entry as posted")
    p_mp.add_argument("content_id", help="Content ID to mark posted")
    p_mp.add_argument("--late-post-id", dest="late_post_id", help="Late MCP post ID for cross-reference")

    # templates (sub-subcommand pattern)
    p_tmpl = subparsers.add_parser("templates", help="Manage content templates")
    tmpl_sub = p_tmpl.add_subparsers(dest="templates_command", help="Template operation")

    tmpl_sub.add_parser("list", help="List all templates")

    p_tc = tmpl_sub.add_parser("create", help="Create a new template")
    p_tc.add_argument("--name", required=True)
    p_tc.add_argument("--platform", required=True, choices=list(PLATFORM_LIMITS.keys()))
    p_tc.add_argument("--pillar", required=True, choices=PILLARS)
    p_tc.add_argument("--template", required=True,
                      help="Template body with {{variable}} placeholders")
    p_tc.add_argument("--vars", metavar="JSON_ARRAY",
                      help='Variable names as JSON array: \'["day_number", "insight"]\'')
    p_tc.add_argument("--example-output", dest="example_output")

    p_tr = tmpl_sub.add_parser("render", help="Render a template with variable substitution")
    p_tr.add_argument("template_id", help="Template ID to render")
    p_tr.add_argument("--vars", metavar="JSON_OBJECT",
                      help='Variable values as JSON: \'{"day_number": "47"}\'')

    # stats
    p_stats = subparsers.add_parser("stats", help="Aggregated stats by platform, pillar, status")
    p_stats.add_argument("--days", type=int, default=30, metavar="N",
                         help="Look back N days (default: 30)")

    # week-plan
    subparsers.add_parser("week-plan", help="Generate a 21-post draft week plan (3/day x 7 days)")

    return parser


# -- Entry point ---------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Propagate --json flag down into args namespace for sub-subcommand handlers
    args.output_json = getattr(args, "output_json", False)

    env_vars = load_env()
    client = get_client(env_vars)

    # Dispatch
    if args.command == "calendar":
        cmd_calendar(client, args)
    elif args.command == "create":
        cmd_create(client, args)
    elif args.command == "create-multi":
        cmd_create_multi(client, args)
    elif args.command == "edit":
        cmd_edit(client, args)
    elif args.command == "delete":
        cmd_delete(client, args)
    elif args.command == "view":
        cmd_view(client, args)
    elif args.command == "due":
        cmd_due(client, args)
    elif args.command == "mark-posted":
        cmd_mark_posted(client, args)
    elif args.command == "templates":
        if not hasattr(args, "templates_command") or not args.templates_command:
            print("Usage: content_engine.py templates [list|create|render]")
            sys.exit(1)
        elif args.templates_command == "list":
            cmd_templates_list(client, args)
        elif args.templates_command == "create":
            cmd_templates_create(client, args)
        elif args.templates_command == "render":
            cmd_templates_render(client, args)
    elif args.command == "stats":
        cmd_stats(client, args)
    elif args.command == "week-plan":
        cmd_week_plan(client, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
