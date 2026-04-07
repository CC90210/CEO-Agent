"""
Viral Content Generation Engine - Transforms draft placeholders into real posts.
Uses Anthropic Claude API to generate platform-appropriate content for CC's brand.
All credentials loaded from .env.agents (never hardcoded).

Keys required:
  ANTHROPIC_API_KEY
  BRAVO_SUPABASE_URL
  BRAVO_SUPABASE_SERVICE_ROLE_KEY

Usage:
  python scripts/content_generator.py generate-week [--json]
  python scripts/content_generator.py generate-one <content_id> [--json]
  python scripts/content_generator.py regenerate <content_id> [--json]
"""

import argparse
import json
import os
import sys
from pathlib import Path

# -- Platform limits -----------------------------------------------------------

CLAUDE_MODEL: str = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# -- Platform limits -----------------------------------------------------------

PLATFORM_LIMITS: dict[str, int] = {
    "x": 280,
    "threads": 500,
    "instagram": 2200,
    "linkedin": 3000,
    "tiktok": 4000,
}

# -- Pillar definitions --------------------------------------------------------

PILLAR_DESCRIPTIONS: dict[str, str] = {
    "sobriety_log": (
        "Raw, honest reflections on a sobriety journey. Introspective, 2am-conversation tone. "
        "Specific details beat vague feelings (say 'Day 47' not 'my journey'). "
        "About building something real after leaving that life behind."
    ),
    "quote_drop": (
        "Personal philosophy, ambition, and hard truths. Short, punchy, quotable. "
        "Never preachy — speak from experience, not from a pedestal. "
        "One sharp idea per post. No padding."
    ),
    "ceo_log": (
        "Business building updates from a 22-year-old founder in Collingwood, Ontario. "
        "Revenue milestones, strategy insights, wins and losses. "
        "Use specific numbers when possible (clients, dollars, days). "
        "Brand is OASIS AI Solutions — AI automation for local businesses."
    ),
    "educational": (
        "AI automation education for local business owners. Demystify AI. Show real ROI. "
        "Practical, specific, not theoretical. "
        "Audience is HVAC, wellness, and service businesses who fear AI is complicated."
    ),
    "promotional": (
        "OASIS AI Solutions offers — AI automation retainers for local service businesses. "
        "Value-first framing. Lead with the business owner's problem, not the product. "
        "Never sound salesy. Subtle and confident, not pushy."
    ),
}

# -- Example posts per pillar (used in the generation prompt) ------------------

PILLAR_EXAMPLES: dict[str, list[str]] = {
    "sobriety_log": [
        "Day 47. Woke up at 6am without an alarm for the first time in years. "
        "That's the thing nobody talks about — sobriety gives you your mornings back.",
        "Used to think the nights out were making me interesting. "
        "Turns out I was just loud. There's a difference.",
        "Some days are harder than others. Today wasn't hard. "
        "I'm going to write that down so I remember it existed.",
    ],
    "quote_drop": [
        "The goal isn't to be the smartest person in the room. "
        "It's to build the room.",
        "Most people quit right before it starts working. "
        "That's not pessimism — that's just pattern recognition.",
        "Clarity is a competitive advantage. "
        "Know exactly what you're building and why. Most people don't.",
    ],
    "ceo_log": [
        "Closed our 3rd retainer client this month. $900 USD/mo. "
        "Still 22, still figuring it out, but the math is starting to work.",
        "Spent 4 hours building an AI workflow that saves a client 6 hours a week. "
        "That's leverage. That's what we sell.",
        "MRR update: $2,691 USD. Original goal was $1,000. "
        "Adjusted the target. $5,000 by May 2026. Writing it here makes it real.",
    ],
    "educational": [
        "A local HVAC company asked me what AI actually does for them. "
        "I said: it answers your after-hours calls, qualifies leads, and books jobs. "
        "While you sleep. That's it.",
        "AI automation isn't replacing your staff. "
        "It's handling the stuff your staff hates doing — follow-ups, scheduling, reminders. "
        "The human stuff stays human.",
        "The business owners who figure out AI in 2025 will have an unfair advantage for the next decade. "
        "The barrier to entry is lower than you think.",
    ],
    "promotional": [
        "If your business loses leads after 5pm, that's a solvable problem. "
        "We build the system that catches them. DM me if you want to see it.",
        "Most of our clients see ROI in the first 30 days. "
        "Not because AI is magic — because they were losing money on follow-ups they never sent.",
        "OASIS AI does one thing: makes your business run when you're not running it. "
        "If that's interesting, let's talk.",
    ],
}

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


def get_anthropic_client(env_vars: dict[str, str]):
    """Create an Anthropic client using the API key from .env.agents."""
    try:
        import anthropic
    except ImportError:
        print("ERROR: 'anthropic' package not installed. Run: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    api_key = env_vars.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "ERROR: ANTHROPIC_API_KEY not found in .env.agents.\n"
            "Add it with: ANTHROPIC_API_KEY=sk-ant-...",
            file=sys.stderr,
        )
        sys.exit(1)

    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def get_supabase_client(env_vars: dict[str, str]):
    """Create a Supabase client for the Bravo project."""
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

    from supabase import create_client
    return create_client(url, key)


# -- Content generation --------------------------------------------------------

def build_prompt(pillar: str, platform: str) -> str:
    """Build the generation prompt for a given pillar and platform."""
    limit = PLATFORM_LIMITS.get(platform, 280)
    description = PILLAR_DESCRIPTIONS.get(pillar, "")
    examples = PILLAR_EXAMPLES.get(pillar, [])

    examples_text = "\n\n".join(f'"{ex}"' for ex in examples)

    use_emojis = "You may use emojis sparingly." if platform == "instagram" else "Do not use emojis."

    return f"""You are writing a social media post for Conaugh McKenna (CC), a 22-year-old founder from Collingwood, Ontario building OASIS AI Solutions.

PILLAR: {pillar}
PILLAR DESCRIPTION: {description}

TARGET PLATFORM: {platform}
CHARACTER LIMIT: {limit} characters (your post MUST be under this limit)

VOICE RULES:
- Write like talking to a friend at 2am — raw, honest, direct
- Never use hustle-culture jargon: no "grind", "hustle", "10x", "crush it", "level up"
- Never be preachy — state it, don't lecture
- Specific beats generic: "Day 47 sober" not "my sobriety journey", "$2,691 MRR" not "growing revenue"
- No hedging language ("kind of", "sort of", "maybe", "I think")
- End with "Only good things from now on." occasionally — only when it lands naturally
- {use_emojis}
- No hashtags — keep the post clean

EXAMPLE POSTS FOR THIS PILLAR (match this voice, do not copy):
{examples_text}

CTA RULE: End every post with a SOFT call-to-action. Rotate between these styles:
- "Free AI audit → cc-funnel.vercel.app"
- "DM me 'AUDIT' for a free business review"
- "Link in bio for your free automation assessment"

For LinkedIn/Instagram (longer platforms), you can expand the CTA to 2-3 sentences:
"I'm offering free AI automation audits for business owners this month. If you're spending 10+ hours/week on tasks that could be automated, I'll personally review your workflow. → cc-funnel.vercel.app"

Rules:
- CTA must be the LAST line of the post
- Never more than 1 CTA per post
- Keep it conversational, not salesy
- The CTA counts toward the character limit
- For sobriety_log posts, use a softer CTA: just "→ cc-funnel.vercel.app" or skip the CTA entirely if it breaks the tone

Write ONE post for {platform}. Output ONLY the post text. No labels, no explanation, no quotes around it."""


def generate_content(anthropic_client, pillar: str, platform: str) -> str:
    """Call Claude API and return the generated post text."""
    prompt = build_prompt(pillar, platform)

    message = anthropic_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text.strip()


def enforce_limit(body: str, platform: str) -> str:
    """Hard-truncate body to platform character limit with ellipsis."""
    limit = PLATFORM_LIMITS.get(platform)
    if limit is None or len(body) <= limit:
        return body
    return body[: limit - 3] + "..."


def is_draft(body: str) -> bool:
    """Return True if the body is an unfilled draft placeholder."""
    return (body or "").lstrip().startswith("[DRAFT")


# -- Commands ------------------------------------------------------------------

def cmd_generate_week(supabase_client, anthropic_client, args) -> None:
    """Find all draft placeholders and generate real content for each."""
    result = (
        supabase_client.table("content_calendar")
        .select("id,platform,pillar,body,scheduled_for,status")
        .eq("status", "draft")
        .execute()
    )
    rows = result.data or []
    drafts = [r for r in rows if is_draft(r.get("body", ""))]

    if not drafts:
        msg = "No draft placeholders found (looking for body starting with '[DRAFT')."
        if args.output_json:
            print(json.dumps({"generated": 0, "message": msg}))
        else:
            print(msg)
        return

    results: list[dict] = []

    for row in drafts:
        content_id = row["id"]
        platform = row.get("platform", "x")
        pillar = row.get("pillar", "ceo_log")

        if not args.output_json:
            print(f"  Generating [{pillar}] for {platform} (ID: {str(content_id)[:8]}...)  ", end="", flush=True)

        try:
            body = generate_content(anthropic_client, pillar, platform)
            body = enforce_limit(body, platform)

            supabase_client.table("content_calendar").update(
                {"body": body, "status": "scheduled"}
            ).eq("id", content_id).execute()

            results.append({
                "id": content_id,
                "platform": platform,
                "pillar": pillar,
                "chars": len(body),
                "limit": PLATFORM_LIMITS.get(platform, 0),
                "status": "ok",
                "preview": body[:80],
            })

            if not args.output_json:
                print(f"done ({len(body)} chars)")

        except Exception as exc:
            results.append({
                "id": content_id,
                "platform": platform,
                "pillar": pillar,
                "status": "error",
                "error": str(exc),
            })
            if not args.output_json:
                print(f"ERROR: {exc}")

    ok_count = sum(1 for r in results if r["status"] == "ok")
    err_count = len(results) - ok_count

    if args.output_json:
        print(json.dumps({
            "generated": ok_count,
            "errors": err_count,
            "results": results,
        }, indent=2, default=str))
        return

    print(f"\nGenerated {ok_count}/{len(drafts)} posts. {err_count} error(s).")
    if err_count:
        print("Re-run with generate-one <id> to retry failed entries.")


def cmd_generate_one(supabase_client, anthropic_client, args) -> None:
    """Generate content for a single draft entry."""
    content_id = args.content_id

    result = (
        supabase_client.table("content_calendar")
        .select("id,platform,pillar,body,scheduled_for,status")
        .eq("id", content_id)
        .execute()
    )

    if not result.data:
        print(f"ERROR: Content [{content_id}] not found.", file=sys.stderr)
        sys.exit(1)

    row = result.data[0]
    platform = row.get("platform", "x")
    pillar = row.get("pillar", "ceo_log")

    if not is_draft(row.get("body", "")):
        print(
            f"ERROR: Content [{content_id}] is not a draft placeholder. "
            "Use 'regenerate' to overwrite existing content.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.output_json:
        print(f"Generating [{pillar}] for {platform}...", flush=True)

    body = generate_content(anthropic_client, pillar, platform)
    body = enforce_limit(body, platform)

    supabase_client.table("content_calendar").update(
        {"body": body, "status": "scheduled"}
    ).eq("id", content_id).execute()

    if args.output_json:
        print(json.dumps({
            "id": content_id,
            "platform": platform,
            "pillar": pillar,
            "chars": len(body),
            "limit": PLATFORM_LIMITS.get(platform, 0),
            "body": body,
        }, indent=2))
        return

    limit = PLATFORM_LIMITS.get(platform, 0)
    print(f"\nGenerated ({len(body)}/{limit} chars):\n")
    print(body)


def cmd_regenerate(supabase_client, anthropic_client, args) -> None:
    """Regenerate content for an already-generated entry, preserving scheduled_for."""
    content_id = args.content_id

    result = (
        supabase_client.table("content_calendar")
        .select("id,platform,pillar,body,scheduled_for,status")
        .eq("id", content_id)
        .execute()
    )

    if not result.data:
        print(f"ERROR: Content [{content_id}] not found.", file=sys.stderr)
        sys.exit(1)

    row = result.data[0]
    platform = row.get("platform", "x")
    pillar = row.get("pillar", "ceo_log")

    if not args.output_json:
        old_preview = (row.get("body") or "")[:60]
        print(f"Regenerating [{pillar}] for {platform}...")
        print(f"  Replacing: {old_preview}...")

    body = generate_content(anthropic_client, pillar, platform)
    body = enforce_limit(body, platform)

    # Preserve scheduled_for and keep status as-is (don't reset a posted entry)
    update_payload: dict[str, object] = {"body": body}
    if row.get("status") == "draft":
        update_payload["status"] = "scheduled"

    supabase_client.table("content_calendar").update(update_payload).eq("id", content_id).execute()

    if args.output_json:
        print(json.dumps({
            "id": content_id,
            "platform": platform,
            "pillar": pillar,
            "chars": len(body),
            "limit": PLATFORM_LIMITS.get(platform, 0),
            "body": body,
        }, indent=2))
        return

    limit = PLATFORM_LIMITS.get(platform, 0)
    print(f"\nNew content ({len(body)}/{limit} chars):\n")
    print(body)


# -- Argument parser -----------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Viral Content Generation Engine — Claude-powered post generator for CC's brand",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s generate-week
  %(prog)s generate-week --json
  %(prog)s generate-one abc123-uuid
  %(prog)s regenerate abc123-uuid --json

Pillars: sobriety_log | quote_drop | ceo_log | educational | promotional
        """,
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="Output raw JSON for scheduler/agent consumption",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    p_week = subparsers.add_parser(
        "generate-week",
        help="Generate content for all draft placeholders in content_calendar",
    )
    p_week.add_argument("--json", dest="output_json", action="store_true", default=False)

    p_one = subparsers.add_parser(
        "generate-one",
        help="Generate content for a single draft entry by ID",
    )
    p_one.add_argument("content_id", help="UUID of the content_calendar row")
    p_one.add_argument("--json", dest="output_json", action="store_true", default=False)

    p_regen = subparsers.add_parser(
        "regenerate",
        help="Regenerate content for an already-generated entry (keeps scheduled_for)",
    )
    p_regen.add_argument("content_id", help="UUID of the content_calendar row")
    p_regen.add_argument("--json", dest="output_json", action="store_true", default=False)

    return parser


# -- Entry point ---------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Propagate --json to subcommand namespace
    args.output_json = getattr(args, "output_json", False)

    env_vars = load_env()
    supabase_client = get_supabase_client(env_vars)
    anthropic_client = get_anthropic_client(env_vars)

    if args.command == "generate-week":
        cmd_generate_week(supabase_client, anthropic_client, args)
    elif args.command == "generate-one":
        cmd_generate_one(supabase_client, anthropic_client, args)
    elif args.command == "regenerate":
        cmd_regenerate(supabase_client, anthropic_client, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
