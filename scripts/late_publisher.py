"""
Late Publisher — Autonomous content posting via Late SDK.

Reads due content from Supabase content_calendar, publishes via Late API,
marks as posted. Designed to run from scheduler (no MCP session needed).

Keys required in .env.agents:
  LATE_API_KEY, BRAVO_SUPABASE_URL, BRAVO_SUPABASE_SERVICE_ROLE_KEY

Usage:
  python scripts/late_publisher.py publish-due [--json] [--dry-run]
  python scripts/late_publisher.py publish-one <content_id> [--json]
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Platform name mapping: content_calendar uses shorthand, Late API uses full names
PLATFORM_MAP = {
    "x": "twitter",
    "twitter": "twitter",
    "instagram": "instagram",
    "ig": "instagram",
    "linkedin": "linkedin",
    "tiktok": "tiktok",
    "threads": "threads",
    "bluesky": "bluesky",
    "facebook": "facebook",
    "youtube": "youtube",
    "pinterest": "pinterest",
}

PLATFORM_LIMITS = {
    "twitter": 280,
    "threads": 500,
    "instagram": 2200,
    "linkedin": 3000,
    "tiktok": 4000,
}


def load_env() -> dict[str, str]:
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


def get_supabase_client(env_vars: dict):
    from supabase import create_client
    url = env_vars.get("BRAVO_SUPABASE_URL", "")
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("ERROR: BRAVO_SUPABASE_URL and BRAVO_SUPABASE_SERVICE_ROLE_KEY required", file=sys.stderr)
        sys.exit(1)
    return create_client(url, key)


def get_late_client(env_vars: dict):
    from late import Late
    api_key = env_vars.get("LATE_API_KEY", "")
    if not api_key:
        print("ERROR: LATE_API_KEY required in .env.agents", file=sys.stderr)
        sys.exit(1)
    return Late(api_key=api_key)


def get_late_accounts(client) -> list[dict]:
    """Fetch connected Late accounts as dicts."""
    try:
        response = client.accounts.list()
        if hasattr(response, "model_dump"):
            data = response.model_dump(by_alias=True)
        elif isinstance(response, dict):
            data = response
        else:
            data = {}
        return data.get("accounts", [])
    except Exception:
        try:
            raw = client._get("/v1/accounts")
            return raw.get("accounts", []) if isinstance(raw, dict) else []
        except Exception:
            return []


def publish_to_late(late_client, accounts: list[dict], platform: str, body: str, title: str = "") -> dict:
    """Publish content to a single platform via Late API. Returns {success, post_id, error}."""
    late_platform = PLATFORM_MAP.get(platform.lower(), platform.lower())

    # Validate character limit
    limit = PLATFORM_LIMITS.get(late_platform, 5000)
    if len(body) > limit:
        return {"success": False, "post_id": None, "error": f"Content too long: {len(body)}/{limit} chars"}

    # Find matching account
    matching = [a for a in accounts if (a.get("platform") or "").lower() == late_platform]
    if not matching:
        available = list({a.get("platform", "?") for a in accounts})
        return {"success": False, "post_id": None, "error": f"No {late_platform} account. Available: {', '.join(available)}"}

    account = matching[0]
    account_id = account.get("_id") or account.get("field_id") or "unknown"

    payload = {
        "content": body,
        "platforms": [{"platform": account.get("platform"), "accountId": account_id}],
        "publishNow": True,
    }
    if title:
        payload["title"] = title

    try:
        raw_response = late_client._post("/v1/posts", json=payload)
        if isinstance(raw_response, dict):
            post = raw_response.get("post", raw_response)
        elif hasattr(raw_response, "model_dump"):
            post = raw_response.model_dump(by_alias=True).get("post", {})
        else:
            post = {}
        post_id = post.get("_id") or post.get("field_id") or "unknown"
        return {"success": True, "post_id": post_id, "error": None}
    except Exception as e:
        return {"success": False, "post_id": None, "error": str(e)}


def cmd_publish_due(env_vars: dict, args) -> None:
    """Find all content due now or past-due, publish each, mark as posted."""
    sb = get_supabase_client(env_vars)
    now = datetime.now(timezone.utc)

    # Get content that's scheduled and due (scheduled_for <= now)
    result = (
        sb.table("content_calendar")
        .select("*")
        .eq("status", "scheduled")
        .lte("scheduled_for", now.isoformat())
        .order("scheduled_for", desc=False)
        .execute()
    )
    rows = result.data or []

    if not rows:
        if args.output_json:
            print(json.dumps({"published": 0, "results": []}, default=str))
        else:
            print("No content due for publishing.")
        return

    late_client = get_late_client(env_vars)
    accounts = get_late_accounts(late_client)
    if not accounts:
        msg = "No Late accounts connected — cannot publish"
        if args.output_json:
            print(json.dumps({"published": 0, "error": msg}))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return

    results = []
    published = 0

    for row in rows:
        content_id = row.get("id")
        platform = row.get("platform", "x")
        body = row.get("body", "")
        title = row.get("title", "")

        if not body.strip():
            results.append({"id": content_id, "status": "skipped", "reason": "empty body"})
            continue

        if args.dry_run:
            results.append({"id": content_id, "platform": platform, "status": "dry_run", "body_preview": body[:60]})
            published += 1
            continue

        pub_result = publish_to_late(late_client, accounts, platform, body, title)

        if pub_result["success"]:
            # Mark as posted in Supabase
            sb.table("content_calendar").update({
                "status": "posted",
                "posted_at": now.isoformat(),
                "late_post_id": pub_result["post_id"],
            }).eq("id", content_id).execute()

            results.append({
                "id": content_id,
                "platform": platform,
                "status": "published",
                "late_post_id": pub_result["post_id"],
            })
            published += 1
        else:
            results.append({
                "id": content_id,
                "platform": platform,
                "status": "failed",
                "error": pub_result["error"],
            })

    output = {"published": published, "total_due": len(rows), "results": results}

    if args.output_json:
        print(json.dumps(output, default=str))
    else:
        print(f"Published {published}/{len(rows)} post(s).")
        for r in results:
            status_icon = "+" if r.get("status") == "published" else "-" if r.get("status") == "failed" else "~"
            print(f"  [{status_icon}] {r.get('id', '?')[:8]}... [{r.get('platform', '?')}] — {r.get('status')}")
            if r.get("error"):
                print(f"      Error: {r['error']}")
            if r.get("late_post_id"):
                print(f"      Late ID: {r['late_post_id']}")


def cmd_publish_one(env_vars: dict, args) -> None:
    """Publish a single content_calendar entry by ID."""
    sb = get_supabase_client(env_vars)
    content_id = args.content_id

    result = sb.table("content_calendar").select("*").eq("id", content_id).execute()
    if not result.data:
        msg = f"Content [{content_id}] not found"
        if args.output_json:
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return

    row = result.data[0]
    if row.get("status") == "posted":
        msg = f"Content [{content_id}] already posted"
        if args.output_json:
            print(json.dumps({"error": msg}))
        else:
            print(msg)
        return

    late_client = get_late_client(env_vars)
    accounts = get_late_accounts(late_client)

    platform = row.get("platform", "x")
    body = row.get("body", "")
    title = row.get("title", "")

    pub_result = publish_to_late(late_client, accounts, platform, body, title)
    now = datetime.now(timezone.utc)

    if pub_result["success"]:
        sb.table("content_calendar").update({
            "status": "posted",
            "posted_at": now.isoformat(),
            "late_post_id": pub_result["post_id"],
        }).eq("id", content_id).execute()

    output = {
        "id": content_id,
        "platform": platform,
        "status": "published" if pub_result["success"] else "failed",
        "late_post_id": pub_result.get("post_id"),
        "error": pub_result.get("error"),
    }

    if args.output_json:
        print(json.dumps(output, default=str))
    else:
        if pub_result["success"]:
            print(f"Published [{content_id}] to {platform} — Late ID: {pub_result['post_id']}")
        else:
            print(f"Failed to publish [{content_id}]: {pub_result['error']}")


def main():
    parser = argparse.ArgumentParser(description="Late Publisher — autonomous content posting")
    parser.add_argument("--json", dest="output_json", action="store_true", help="JSON output")
    sub = parser.add_subparsers(dest="command")

    p_due = sub.add_parser("publish-due", help="Publish all due content")
    p_due.add_argument("--dry-run", dest="dry_run", action="store_true", help="Show what would be published without actually posting")

    p_one = sub.add_parser("publish-one", help="Publish a single content entry")
    p_one.add_argument("content_id", help="Content calendar ID")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    env_vars = load_env()

    if args.command == "publish-due":
        cmd_publish_due(env_vars, args)
    elif args.command == "publish-one":
        cmd_publish_one(env_vars, args)


if __name__ == "__main__":
    main()
