"""
Late SDK CLI — Social Media Publishing Tool
Uses Late SDK via inline Python (subprocess with uvx environment).
All credentials loaded from .env.agents (never hardcoded).

Usage (from any agent via terminal):
  python scripts/late_tool.py accounts
  python scripts/late_tool.py profiles
  python scripts/late_tool.py posts [--status draft|scheduled|published|failed] [--limit 10]
  python scripts/late_tool.py create --text "Post content" --account <account_id> [--schedule "2026-03-25T10:00:00Z"]
  python scripts/late_tool.py cross-post --text "Post content" --profile <profile_id>
  python scripts/late_tool.py delete <post_id>
  python scripts/late_tool.py publish <post_id>
  python scripts/late_tool.py failed
  python scripts/late_tool.py retry <post_id>
  python scripts/late_tool.py retry-all

All commands support --json flag for agent consumption.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def load_env():
    """Load .env.agents from project root."""
    env_path = Path(__file__).resolve().parent.parent / ".env.agents"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found", file=sys.stderr)
        sys.exit(1)

    env_vars = {}
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()
    return env_vars


def run_late_sdk(script_code):
    """Run Python code in uvx environment with late-sdk installed."""
    env = load_env()
    api_key = env.get("LATE_API_KEY")
    if not api_key:
        print("ERROR: LATE_API_KEY not found in .env.agents", file=sys.stderr)
        sys.exit(1)

    # Set env var and run via uvx
    run_env = os.environ.copy()
    run_env["LATE_API_KEY"] = api_key

    try:
        result = subprocess.run(
            ["uvx", "--from", "late-sdk[mcp]", "python", "-c", script_code],
            capture_output=True,
            text=True,
            timeout=30,
            env=run_env,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if stderr:
                print(f"ERROR: {stderr}", file=sys.stderr)
            sys.exit(1)
        return result.stdout.strip()
    except FileNotFoundError:
        print("ERROR: uvx not found. Install with: pip install uv", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("ERROR: Late SDK call timed out after 30s", file=sys.stderr)
        sys.exit(1)


SDK_PREAMBLE = """
import os, json

def safe_dump(obj):
    if hasattr(obj, 'model_dump'):
        return obj.model_dump(by_alias=True)
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, list):
        return [safe_dump(x) for x in obj]
    return obj

from late import Late
client = Late(api_key=os.environ['LATE_API_KEY'])
"""


def cmd_accounts(args):
    """List connected social media accounts."""
    code = SDK_PREAMBLE + """
result = client.accounts.list()
data = safe_dump(result)
accounts = data.get('accounts', data) if isinstance(data, dict) else data
print(json.dumps(accounts, indent=2, default=str))
"""
    output = run_late_sdk(code)
    if args.json:
        print(output)
    else:
        accounts = json.loads(output) if output else []
        print("Connected Accounts:\n")
        if isinstance(accounts, list):
            for acc in accounts:
                platform = acc.get("platform", "?")
                username = acc.get("username", acc.get("name", "?"))
                acc_id = acc.get("id", "?")
                print(f"  [{platform}] {username} — {acc_id}")
        else:
            print(json.dumps(accounts, indent=2, default=str))


def cmd_profiles(args):
    """List profiles."""
    code = SDK_PREAMBLE + """
result = client.profiles.list()
data = safe_dump(result)
profiles = data.get('profiles', data) if isinstance(data, dict) else data
print(json.dumps(profiles, indent=2, default=str))
"""
    output = run_late_sdk(code)
    if args.json:
        print(output)
    else:
        profiles = json.loads(output) if output else []
        print("Profiles:\n")
        if isinstance(profiles, list):
            for p in profiles:
                name = p.get("name", "?")
                pid = p.get("id", "?")
                print(f"  {name} — {pid}")
        else:
            print(json.dumps(profiles, indent=2, default=str))


def cmd_posts(args):
    """List posts."""
    status_filter = f", status='{args.status}'" if args.status else ""
    code = SDK_PREAMBLE + f"""
result = client.posts.list(limit={args.limit}{status_filter})
data = safe_dump(result)
posts = data.get('posts', data) if isinstance(data, dict) else data
print(json.dumps(posts, indent=2, default=str))
"""
    output = run_late_sdk(code)
    if args.json:
        print(output)
    else:
        posts = json.loads(output) if output else []
        print("Posts:\n")
        if isinstance(posts, list):
            for p in posts:
                text = (p.get("text", "")[:60] + "...") if len(p.get("text", "")) > 60 else p.get("text", "")
                status = p.get("status", "?")
                pid = p.get("id", "?")
                print(f"  [{status}] {pid} — {text}")
        else:
            print(json.dumps(posts, indent=2, default=str))


def cmd_create(args):
    """Create a post."""
    text_len = len(args.text)
    text_escaped = args.text.replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n')
    schedule = f", scheduled_at='{args.schedule}'" if args.schedule else ""

    code = SDK_PREAMBLE + f"""
result = client.posts.create(text="{text_escaped}", account_id="{args.account}"{schedule})
print(json.dumps(safe_dump(result), indent=2, default=str))
"""
    print(f"Post length: {text_len} chars")
    output = run_late_sdk(code)
    if args.json:
        print(output)
    else:
        print("Post Created:\n")
        print(output)


def cmd_cross_post(args):
    """Cross-post to profile."""
    text_escaped = args.text.replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n')

    code = SDK_PREAMBLE + f"""
result = client.posts.cross_post(text="{text_escaped}", profile_id="{args.profile}")
print(json.dumps(safe_dump(result), indent=2, default=str))
"""
    output = run_late_sdk(code)
    if args.json:
        print(output)
    else:
        print("Cross-Post Created:\n")
        print(output)


def cmd_delete(args):
    """Delete a post."""
    code = SDK_PREAMBLE + f"""
result = client.posts.delete(post_id="{args.post_id}")
print(json.dumps(safe_dump(result), indent=2, default=str))
"""
    output = run_late_sdk(code)
    print("Post Deleted." if not args.json else output)


def cmd_publish(args):
    """Publish now."""
    code = SDK_PREAMBLE + f"""
result = client.posts.publish_now(post_id="{args.post_id}")
print(json.dumps(safe_dump(result), indent=2, default=str))
"""
    output = run_late_sdk(code)
    print("Post Published." if not args.json else output)


def cmd_failed(args):
    """List failed posts."""
    code = SDK_PREAMBLE + """
result = client.posts.list_failed()
print(json.dumps(safe_dump(result), indent=2, default=str))
"""
    output = run_late_sdk(code)
    if args.json:
        print(output)
    else:
        print("Failed Posts:\n")
        print(output)


def cmd_retry(args):
    """Retry a failed post."""
    code = SDK_PREAMBLE + f"""
result = client.posts.retry(post_id="{args.post_id}")
print(json.dumps(safe_dump(result), indent=2, default=str))
"""
    output = run_late_sdk(code)
    print("Post Retried." if not args.json else output)


def cmd_retry_all(args):
    """Retry all failed posts."""
    code = SDK_PREAMBLE + """
result = client.posts.retry_all_failed()
print(json.dumps(safe_dump(result), indent=2, default=str))
"""
    output = run_late_sdk(code)
    print("All Failed Posts Retried." if not args.json else output)


def main():
    parser = argparse.ArgumentParser(
        description="Late SDK CLI — Social Media Publishing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON for agent consumption")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    sub.add_parser("accounts", help="List connected accounts")
    sub.add_parser("profiles", help="List profiles")

    posts_p = sub.add_parser("posts", help="List posts")
    posts_p.add_argument("--status", choices=["draft", "scheduled", "published", "failed"])
    posts_p.add_argument("--limit", type=int, default=10)

    create_p = sub.add_parser("create", help="Create a post")
    create_p.add_argument("--text", required=True, help="Post content")
    create_p.add_argument("--account", required=True, help="Account ID")
    create_p.add_argument("--schedule", help="ISO 8601 datetime for scheduling")

    xpost_p = sub.add_parser("cross-post", help="Cross-post to profile")
    xpost_p.add_argument("--text", required=True, help="Post content")
    xpost_p.add_argument("--profile", required=True, help="Profile ID")

    del_p = sub.add_parser("delete", help="Delete a post")
    del_p.add_argument("post_id", help="Post ID to delete")

    pub_p = sub.add_parser("publish", help="Publish a post now")
    pub_p.add_argument("post_id", help="Post ID to publish")

    sub.add_parser("failed", help="List failed posts")

    retry_p = sub.add_parser("retry", help="Retry a failed post")
    retry_p.add_argument("post_id", help="Post ID to retry")

    sub.add_parser("retry-all", help="Retry all failed posts")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "accounts": cmd_accounts,
        "profiles": cmd_profiles,
        "posts": cmd_posts,
        "create": cmd_create,
        "cross-post": cmd_cross_post,
        "delete": cmd_delete,
        "publish": cmd_publish,
        "failed": cmd_failed,
        "retry": cmd_retry,
        "retry-all": cmd_retry_all,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
