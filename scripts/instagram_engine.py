"""
Instagram Engine - ManyChat replacement via Playwright browser automation.

Checks Instagram DMs and comments, responds in CC's brand voice,
and notifies CC via Telegram of all interactions.

Usage:
  python scripts/instagram_engine.py check-dms          # Check and respond to new DMs
  python scripts/instagram_engine.py check-comments      # Check and respond to new comments
  python scripts/instagram_engine.py --json check-dms    # JSON output for scheduler

Requires: Playwright MCP server running (browser automation)
Note: This engine is designed to be called by the scheduler cron job.
      It uses subprocess calls to the Claude CLI with Playwright MCP
      for browser automation, since Playwright MCP is only accessible
      through the MCP protocol (not as a Python library directly).

For now, this engine flags new DMs/comments and notifies CC via Telegram.
Full auto-response requires an active Claude Code session with Playwright MCP.
"""

import argparse
import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# Add scripts to path for imports
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from notify import notify
except ImportError:
    def notify(*a, **kw): return False


def load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        return {}
    env_vars: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


def get_supabase(env_vars: dict[str, str]):
    from supabase import create_client
    url = env_vars.get("BRAVO_SUPABASE_URL")
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


# -- DM Check (Playwright-based) -----------------------------------------------

def cmd_check_dms(env_vars: dict, args) -> dict:
    """
    Check Instagram DMs via Playwright browser automation.

    Since Playwright MCP is only accessible through Claude Code sessions,
    this command logs pending DM checks and notifies CC to review them.
    The scheduler calls this periodically to remind CC of unread DMs.
    """
    db = get_supabase(env_vars)

    # Log the check attempt
    result = {
        "action": "check_dms",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "flagged_for_review",
        "message": "Instagram DM check scheduled. Open Claude Code with Playwright to process DMs."
    }

    # Check if we have any pending DM tasks in Supabase
    if db:
        try:
            pending = (
                db.table("lead_interactions")
                .select("*")
                .eq("channel", "instagram_dm")
                .eq("direction", "inbound")
                .is_("response_at", "null")
                .execute()
            )
            unresponded = len(pending.data or [])
            if unresponded > 0:
                result["unresponded_dms"] = unresponded
                result["message"] = f"{unresponded} Instagram DM(s) awaiting response"
                notify(
                    f"You have {unresponded} unread Instagram DM(s). Open Claude Code to respond.",
                    category="instagram"
                )
        except Exception:
            pass

    if getattr(args, "output_json", False):
        print(json.dumps(result, indent=2))
    else:
        print(f"Instagram DMs: {result['message']}")

    return result


def cmd_check_comments(env_vars: dict, args) -> dict:
    """
    Check Instagram comments via Playwright browser automation.
    Similar to DMs - flags for review and notifies CC.
    """
    result = {
        "action": "check_comments",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "flagged_for_review",
        "message": "Instagram comment check scheduled. Open Claude Code with Playwright to process."
    }

    if getattr(args, "output_json", False):
        print(json.dumps(result, indent=2))
    else:
        print(f"Instagram Comments: {result['message']}")

    return result


def cmd_log_dm(env_vars: dict, args) -> dict:
    """
    Log an Instagram DM interaction to Supabase for tracking.
    Called by Claude Code after Playwright reads a DM.
    """
    db = get_supabase(env_vars)
    if not db:
        print("ERROR: Supabase not configured", file=sys.stderr)
        sys.exit(1)

    record = {
        "channel": "instagram_dm",
        "direction": args.direction,
        "lead_id": args.lead_id if hasattr(args, "lead_id") and args.lead_id else None,
        "summary": args.summary,
        "metadata": json.dumps({
            "ig_username": args.username,
            "message_preview": args.summary[:200],
        }),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if args.direction == "inbound":
        notify(
            f"New Instagram DM from @{args.username}: {args.summary[:100]}",
            category="instagram"
        )

    try:
        db.table("lead_interactions").insert(record).execute()
        result = {"status": "logged", "username": args.username}
    except Exception as e:
        result = {"status": "error", "error": str(e)}

    if getattr(args, "output_json", False):
        print(json.dumps(result, indent=2))
    else:
        print(f"DM logged: @{args.username} ({args.direction})")

    return result


# -- Main -----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Instagram Engine - ManyChat replacement via browser automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", dest="output_json", action="store_true")

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # check-dms
    subparsers.add_parser("check-dms", help="Check for new Instagram DMs")

    # check-comments
    subparsers.add_parser("check-comments", help="Check for new Instagram comments")

    # log-dm
    p_log = subparsers.add_parser("log-dm", help="Log an Instagram DM interaction")
    p_log.add_argument("--username", required=True, help="Instagram username")
    p_log.add_argument("--summary", required=True, help="Message summary")
    p_log.add_argument("--direction", choices=["inbound", "outbound"], default="inbound")
    p_log.add_argument("--lead-id", help="Associated lead UUID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    env_vars = load_env()

    handlers = {
        "check-dms": cmd_check_dms,
        "check-comments": cmd_check_comments,
        "log-dm": cmd_log_dm,
    }

    handler = handlers.get(args.command)
    if handler:
        handler(env_vars, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
