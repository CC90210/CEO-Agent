"""
Content Repurposing Engine — Adapts posts from X to other platforms via Claude API.
All credentials loaded from .env.agents (never hardcoded).

Usage:
  python scripts/content_repurposer.py repurpose <content_id> --platforms linkedin,instagram,threads [--json]
  python scripts/content_repurposer.py repurpose-day 2026-03-20 --platforms linkedin,instagram [--json]
  python scripts/content_repurposer.py repurpose-week --platforms linkedin,instagram,threads [--json]
"""

import argparse
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

try:
    import anthropic
except ImportError:
    print("ERROR: 'anthropic' package not installed. Run: pip install anthropic", file=sys.stderr)
    sys.exit(1)

try:
    from supabase import create_client
except ImportError:
    print("ERROR: 'supabase' package not installed. Run: pip install supabase", file=sys.stderr)
    sys.exit(1)


# ── Platform configuration ─────────────────────────────────────────────────────

PLATFORM_RULES = {
    "x": {
        "max_chars": 280,
        "style": (
            "Ultra-punchy, one thought only. No hashtags in the body text. "
            "Get to the point in the first 5 words. Raw and direct."
        ),
    },
    "threads": {
        "max_chars": 500,
        "style": (
            "Slightly more conversational than X. One or two short paragraphs. "
            "1-2 hashtags are fine at the end. Still tight and punchy."
        ),
    },
    "instagram": {
        "max_chars": 2200,
        "style": (
            "Longer storytelling format. Open with a single hook line that stops the scroll. "
            "Then tell the story in short paragraphs with line breaks between each. "
            "End with a question or call to action. "
            "Add 5-10 relevant hashtags on a new line at the very end, separated by spaces."
        ),
    },
    "linkedin": {
        "max_chars": 3000,
        "style": (
            "Professional but still authentic — write like a founder reflecting, not a corporate memo. "
            "Put a line break after every 1-2 sentences for white-space readability. "
            "Business-focused angle: frame the lesson or story in terms of building, growing, or running a business. "
            "End with a takeaway or question to prompt comments. "
            "Add 3-5 professional hashtags on a new line at the end."
        ),
    },
    "tiktok": {
        "max_chars": 4000,
        "style": (
            "Caption style — hook in the first line to make people watch. "
            "Then add context in a casual, conversational tone. "
            "Hashtags can go inline or at the end. Keep it energetic."
        ),
    },
}

VALID_PLATFORMS = set(PLATFORM_RULES.keys())
CLAUDE_MODEL = "claude-sonnet-4-20250514"


# ── Credentials ────────────────────────────────────────────────────────────────

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


def get_supabase(env_vars: dict[str, str]):
    """Create a Supabase client using BRAVO credentials."""
    url = env_vars.get("BRAVO_SUPABASE_URL")
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print(
            "ERROR: BRAVO_SUPABASE_URL and BRAVO_SUPABASE_SERVICE_ROLE_KEY must be set in .env.agents",
            file=sys.stderr,
        )
        sys.exit(1)
    return create_client(url, key)


def get_anthropic(env_vars: dict[str, str]) -> anthropic.Anthropic:
    """Create an Anthropic client."""
    api_key = env_vars.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not found in .env.agents", file=sys.stderr)
        sys.exit(1)
    return anthropic.Anthropic(api_key=api_key)


# ── Claude adaptation ──────────────────────────────────────────────────────────

def build_prompt(source_body: str, target_platform: str) -> str:
    rules = PLATFORM_RULES[target_platform]
    return (
        f"You are adapting a social media post for {target_platform.upper()}.\n\n"
        f"ORIGINAL POST:\n{source_body}\n\n"
        f"TARGET PLATFORM RULES:\n"
        f"- Max {rules['max_chars']} characters\n"
        f"- Style: {rules['style']}\n\n"
        f"VOICE: Write like talking to a friend at 2am — raw and honest, no hustle-culture jargon, "
        f"no phrases like 'Unlock the power of' or 'Transform your'. "
        f"Sound like a real person building something, not a LinkedIn influencer.\n\n"
        f"Output ONLY the adapted post text, nothing else. No labels, no explanations."
    )


def adapt_post(claude: anthropic.Anthropic, source_body: str, target_platform: str) -> str:
    """Call Claude to adapt source_body for target_platform. Returns the adapted text."""
    prompt = build_prompt(source_body, target_platform)
    message = claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


# ── Supabase helpers ───────────────────────────────────────────────────────────

def fetch_post(db, content_id: str) -> dict:
    """Fetch a single post from content_calendar by id."""
    result = db.table("content_calendar").select("*").eq("id", content_id).execute()
    if not result.data:
        print(f"ERROR: No post found with id '{content_id}'", file=sys.stderr)
        sys.exit(1)
    return result.data[0]


def fetch_posts_for_date(db, date_str: str) -> list[dict]:
    """Fetch all posts scheduled on a given date (YYYY-MM-DD).

    scheduled_for is stored as UTC in the DB. We interpret the requested date
    in America/Toronto (ET) so that e.g. '2026-03-20' covers posts scheduled
    between 04:00 UTC and 04:00 UTC the next day (during EDT, UTC-4).
    """
    et = ZoneInfo("America/Toronto")
    year, month, day = (int(p) for p in date_str.split("-"))
    day_start_et = datetime(year, month, day, 0, 0, 0, tzinfo=et)
    day_end_et = day_start_et + timedelta(days=1)
    result = (
        db.table("content_calendar")
        .select("*")
        .gte("scheduled_for", day_start_et.isoformat())
        .lt("scheduled_for", day_end_et.isoformat())
        .execute()
    )
    return result.data or []


def fetch_x_posts_next_week(db) -> list[dict]:
    """Fetch X-only posts scheduled in the next 7 days with status scheduled or draft."""
    now = datetime.now(timezone.utc)
    week_end = now + timedelta(days=7)
    result = (
        db.table("content_calendar")
        .select("*")
        .eq("platform", "x")
        .in_("status", ["scheduled", "draft"])
        .gte("scheduled_for", now.isoformat())
        .lte("scheduled_for", week_end.isoformat())
        .execute()
    )
    return result.data or []


def duplicate_exists(db, platform: str, scheduled_for: str) -> bool:
    """Return True if a post already exists for this platform + scheduled_for time."""
    result = (
        db.table("content_calendar")
        .select("id")
        .eq("platform", platform)
        .eq("scheduled_for", scheduled_for)
        .execute()
    )
    return bool(result.data)


def create_repurposed_post(db, source: dict, platform: str, adapted_body: str) -> dict:
    """Insert a new content_calendar row for the repurposed post. Returns the created row."""
    new_row = {
        "id": str(uuid.uuid4()),
        "platform": platform,
        "content_type": source.get("content_type"),
        "pillar": source.get("pillar"),
        "title": source.get("title"),
        "body": adapted_body,
        "media_url": source.get("media_url"),
        "hashtags": source.get("hashtags"),
        "scheduled_for": source.get("scheduled_for"),
        "status": "draft",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = db.table("content_calendar").insert(new_row).execute()
    return result.data[0] if result.data else new_row


# ── Core repurpose logic ───────────────────────────────────────────────────────

def repurpose_one(
    db,
    claude: anthropic.Anthropic,
    source: dict,
    target_platforms: list[str],
    verbose: bool = True,
) -> list[dict]:
    """
    Repurpose a single source post to the requested target platforms.
    Returns a list of result dicts (one per platform).
    Skips platforms that already have a post at the same scheduled_for time.
    """
    results = []
    source_body: str = source.get("body") or ""
    if not source_body.strip():
        if verbose:
            print(f"  SKIP {source['id']} — empty body", file=sys.stderr)
        return results

    scheduled_for: str = source.get("scheduled_for") or ""

    for platform in target_platforms:
        if platform == source.get("platform"):
            # Never repurpose onto the same platform the source is already on
            results.append({"platform": platform, "status": "skipped", "reason": "same as source"})
            continue

        if scheduled_for and duplicate_exists(db, platform, scheduled_for):
            results.append(
                {
                    "platform": platform,
                    "status": "skipped",
                    "reason": f"post already exists for {platform} at {scheduled_for}",
                }
            )
            if verbose:
                print(f"  SKIP {platform} — duplicate at {scheduled_for}")
            continue

        if verbose:
            print(f"  Adapting for {platform}...")
        try:
            adapted = adapt_post(claude, source_body, platform)
            # Enforce platform character limit before DB insert
            limit = PLATFORM_RULES[platform]["max_chars"]
            if len(adapted) > limit:
                adapted = adapted[: limit - 3] + "..."
            created = create_repurposed_post(db, source, platform, adapted)
            results.append(
                {
                    "platform": platform,
                    "status": "created",
                    "id": created.get("id"),
                    "chars": len(adapted),
                    "max_chars": PLATFORM_RULES[platform]["max_chars"],
                }
            )
            if verbose:
                char_count = len(adapted)
                limit = PLATFORM_RULES[platform]["max_chars"]
                flag = " WARNING: over limit" if char_count > limit else ""
                print(f"  OK {platform} — {char_count}/{limit} chars{flag}")
        except Exception as exc:
            results.append({"platform": platform, "status": "error", "error": str(exc)})
            if verbose:
                print(f"  ERROR {platform} — {exc}", file=sys.stderr)

    return results


def parse_platforms(platforms_arg: str) -> list[str]:
    """Parse a comma-separated platform string, validate each, return cleaned list."""
    requested = [p.strip().lower() for p in platforms_arg.split(",") if p.strip()]
    invalid = [p for p in requested if p not in VALID_PLATFORMS]
    if invalid:
        print(
            f"ERROR: Unknown platform(s): {invalid}. Valid options: {sorted(VALID_PLATFORMS)}",
            file=sys.stderr,
        )
        sys.exit(1)
    return requested


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_repurpose(db, claude: anthropic.Anthropic, args) -> None:
    target_platforms = parse_platforms(args.platforms)
    source = fetch_post(db, args.content_id)

    if not args.output_json:
        print(f"Repurposing post {args.content_id}")
        print(f"  Source platform : {source.get('platform', 'unknown')}")
        print(f"  Scheduled for   : {source.get('scheduled_for', 'N/A')}")
        print(f"  Target platforms: {target_platforms}\n")

    results = repurpose_one(db, claude, source, target_platforms, verbose=not args.output_json)

    summary = {
        "source_id": args.content_id,
        "source_platform": source.get("platform"),
        "results": results,
        "created": sum(1 for r in results if r["status"] == "created"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "errors": sum(1 for r in results if r["status"] == "error"),
    }

    if args.output_json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\nDone — {summary['created']} created, {summary['skipped']} skipped, {summary['errors']} errors")


def cmd_repurpose_day(db, claude: anthropic.Anthropic, args) -> None:
    target_platforms = parse_platforms(args.platforms)
    posts = fetch_posts_for_date(db, args.date)

    if not posts:
        msg = f"No posts found for {args.date}"
        if args.output_json:
            print(json.dumps({"date": args.date, "message": msg, "results": []}))
        else:
            print(msg)
        return

    if not args.output_json:
        print(f"Found {len(posts)} post(s) on {args.date}")
        print(f"Target platforms: {target_platforms}\n")

    all_results = []
    for post in posts:
        if not args.output_json:
            print(f"Post {post['id']} [{post.get('platform', '?')}]: {(post.get('title') or post.get('body', ''))[:60]}...")
        platform_results = repurpose_one(db, claude, post, target_platforms, verbose=not args.output_json)
        all_results.append({"source_id": post["id"], "results": platform_results})
        if not args.output_json:
            print()

    total_created = sum(
        sum(1 for r in entry["results"] if r["status"] == "created") for entry in all_results
    )
    total_skipped = sum(
        sum(1 for r in entry["results"] if r["status"] == "skipped") for entry in all_results
    )
    total_errors = sum(
        sum(1 for r in entry["results"] if r["status"] == "error") for entry in all_results
    )

    summary = {
        "date": args.date,
        "posts_processed": len(posts),
        "results": all_results,
        "total_created": total_created,
        "total_skipped": total_skipped,
        "total_errors": total_errors,
    }

    if args.output_json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Done — {total_created} created, {total_skipped} skipped, {total_errors} errors across {len(posts)} post(s)")


def cmd_repurpose_week(db, claude: anthropic.Anthropic, args) -> None:
    target_platforms = parse_platforms(args.platforms)
    posts = fetch_x_posts_next_week(db)

    if not posts:
        msg = "No X posts found scheduled in the next 7 days with status scheduled/draft"
        if args.output_json:
            print(json.dumps({"message": msg, "results": []}))
        else:
            print(msg)
        return

    if not args.output_json:
        print(f"Found {len(posts)} X post(s) in the next 7 days")
        print(f"Target platforms: {target_platforms}\n")

    all_results = []
    for post in posts:
        if not args.output_json:
            print(f"Post {post['id']} [{post.get('scheduled_for', '?')[:10]}]: {(post.get('title') or post.get('body', ''))[:60]}...")
        platform_results = repurpose_one(db, claude, post, target_platforms, verbose=not args.output_json)
        all_results.append({"source_id": post["id"], "results": platform_results})
        if not args.output_json:
            print()

    total_created = sum(
        sum(1 for r in entry["results"] if r["status"] == "created") for entry in all_results
    )
    total_skipped = sum(
        sum(1 for r in entry["results"] if r["status"] == "skipped") for entry in all_results
    )
    total_errors = sum(
        sum(1 for r in entry["results"] if r["status"] == "error") for entry in all_results
    )

    summary = {
        "posts_processed": len(posts),
        "results": all_results,
        "total_created": total_created,
        "total_skipped": total_skipped,
        "total_errors": total_errors,
    }

    if args.output_json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Done — {total_created} created, {total_skipped} skipped, {total_errors} errors across {len(posts)} post(s)")


# ── Argument parsing & entry point ────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Content Repurposing Engine — Adapts posts from X to other platforms via Claude",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s repurpose abc123 --platforms linkedin,instagram,threads
  %(prog)s repurpose abc123 --platforms linkedin --json
  %(prog)s repurpose-day 2026-03-20 --platforms linkedin,instagram
  %(prog)s repurpose-week --platforms linkedin,instagram,threads
  %(prog)s repurpose-week --platforms linkedin --json

Valid platforms: x, threads, instagram, linkedin, tiktok
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # repurpose
    p_one = subparsers.add_parser("repurpose", help="Repurpose a single post by ID")
    p_one.add_argument("content_id", help="UUID of the source post in content_calendar")
    p_one.add_argument(
        "--platforms",
        required=True,
        help="Comma-separated target platforms (e.g. linkedin,instagram,threads)",
    )
    p_one.add_argument("--json", dest="output_json", action="store_true", help="Output JSON for scheduler integration")

    # repurpose-day
    p_day = subparsers.add_parser("repurpose-day", help="Repurpose all posts scheduled on a given date")
    p_day.add_argument("date", help="Date in YYYY-MM-DD format")
    p_day.add_argument(
        "--platforms",
        required=True,
        help="Comma-separated target platforms",
    )
    p_day.add_argument("--json", dest="output_json", action="store_true", help="Output JSON for scheduler integration")

    # repurpose-week
    p_week = subparsers.add_parser(
        "repurpose-week", help="Repurpose all X-only posts scheduled in the next 7 days"
    )
    p_week.add_argument(
        "--platforms",
        required=True,
        help="Comma-separated target platforms",
    )
    p_week.add_argument("--json", dest="output_json", action="store_true", help="Output JSON for scheduler integration")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    env_vars = load_env()
    db = get_supabase(env_vars)
    claude = get_anthropic(env_vars)

    dispatch = {
        "repurpose": cmd_repurpose,
        "repurpose-day": cmd_repurpose_day,
        "repurpose-week": cmd_repurpose_week,
    }
    handler = dispatch.get(args.command)
    if handler is None:
        print(f"ERROR: Unknown command '{args.command}'. Valid commands: {list(dispatch.keys())}", file=sys.stderr)
        parser.print_help()
        sys.exit(1)
    handler(db, claude, args)


if __name__ == "__main__":
    main()
