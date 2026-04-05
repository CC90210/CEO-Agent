"""
Late Publisher — Automated Social Media Publishing from Content Calendar
Reads due content from Supabase `content_calendar` and publishes via late_tool.py.
All credentials loaded from .env.agents (never hardcoded).

Keys required: BRAVO_SUPABASE_URL, BRAVO_SUPABASE_SERVICE_ROLE_KEY, LATE_API_KEY

Usage:
    python scripts/late_publisher.py publish-due          # Publish all scheduled posts due now
    python scripts/late_publisher.py publish-one <id>     # Publish a specific content entry
    python scripts/late_publisher.py status               # Show counts by status
    python scripts/late_publisher.py --json publish-due   # JSON output for agents/scheduler

Called by scheduler.py:
    run_script("late_publisher.py", ["--json", "publish-due"], timeout=120)

Platform character limits:
    x=280 | threads=500 | instagram=2200 | linkedin=3000 | tiktok=4000
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# ── Constants ─────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
PYTHON = sys.executable

PLATFORM_LIMITS: dict[str, int] = {
    "x": 280,
    "threads": 500,
    "instagram": 2200,
    "linkedin": 3000,
    "tiktok": 4000,
}

# Cached at runtime via _get_account_map(); never hardcoded.
_account_map_cache: dict[str, str] | None = None


# ── Credential loading ────────────────────────────────────────────────────────

def load_env() -> dict[str, str]:
    """Load .env.agents from project root."""
    env_path = PROJECT_ROOT / ".env.agents"
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
        print(
            "ERROR: Missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY in .env.agents",
            file=sys.stderr,
        )
        sys.exit(1)
    return create_client(url, key)


# ── Notification (graceful fallback) ─────────────────────────────────────────

try:
    from notify import notify
except ImportError:
    def notify(message: str, category: str = "system", **kwargs) -> bool:  # type: ignore[misc]
        return False


# ── Account discovery ─────────────────────────────────────────────────────────

def _get_account_map() -> dict[str, str]:
    """
    Fetch connected Late accounts and build a platform → account_id map.
    Results are cached for the lifetime of the process.
    Returns e.g. {"x": "acc_abc123", "linkedin": "acc_def456"}.
    """
    global _account_map_cache
    if _account_map_cache is not None:
        return _account_map_cache

    try:
        result = subprocess.run(
            [PYTHON, str(SCRIPTS_DIR / "late_tool.py"), "--json", "accounts"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            cwd=str(PROJECT_ROOT),
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
        if result.returncode != 0:
            print(
                f"WARNING: late_tool.py accounts failed: {result.stderr.strip()[:200]}",
                file=sys.stderr,
            )
            _account_map_cache = {}
            return _account_map_cache

        accounts = json.loads(result.stdout.strip()) if result.stdout.strip() else []
        mapping: dict[str, str] = {}
        if isinstance(accounts, list):
            for acc in accounts:
                platform = (acc.get("platform") or "").lower().strip()
                acc_id = acc.get("_id") or acc.get("id") or acc.get("accountId") or ""
                if platform and acc_id:
                    mapping[platform] = acc_id
        # Alias: content_calendar uses "x" but Late API uses "twitter"
        if "twitter" in mapping and "x" not in mapping:
            mapping["x"] = mapping["twitter"]
        _account_map_cache = mapping
        return _account_map_cache

    except subprocess.TimeoutExpired:
        print("WARNING: Timed out fetching Late accounts.", file=sys.stderr)
        _account_map_cache = {}
        return _account_map_cache
    except Exception as exc:
        print(f"WARNING: Could not fetch Late accounts: {exc}", file=sys.stderr)
        _account_map_cache = {}
        return _account_map_cache


def resolve_account_id(platform: str) -> str | None:
    """
    Return the Late account ID for the given platform name, or None if unmapped.
    Normalises platform to lowercase before lookup.
    """
    account_map = _get_account_map()
    return account_map.get(platform.lower().strip())


# ── Character limit validation ────────────────────────────────────────────────

def validate_length(text: str, platform: str) -> tuple[bool, int, int]:
    """
    Returns (ok, actual_length, limit).
    ok is True when length is within the platform limit (or platform is unknown).
    """
    limit = PLATFORM_LIMITS.get(platform.lower().strip())
    if limit is None:
        return True, len(text), 0
    return len(text) <= limit, len(text), limit


# ── Late publishing via subprocess ───────────────────────────────────────────

def publish_via_late(text: str, account_id: str) -> tuple[bool, str, str]:
    """
    Call late_tool.py create to publish a post immediately.
    Returns (success, late_post_id_or_empty, error_message_or_empty).
    """
    cmd = [
        PYTHON,
        str(SCRIPTS_DIR / "late_tool.py"),
        "--json",
        "create",
        "--text", text,
        "--account", account_id,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            cwd=str(PROJECT_ROOT),
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip()
            return False, "", error[:500]

        raw = result.stdout.strip()
        if not raw:
            return True, "", ""

        try:
            data = json.loads(raw)
            # Late API returns {"post": {"_id": "...", ...}} — extract the post ID.
            post_obj = data.get("post", data) if isinstance(data, dict) else data
            post_id = (
                (post_obj.get("_id") if isinstance(post_obj, dict) else None)
                or data.get("_id")
                or data.get("id")
                or data.get("postId")
                or data.get("post_id")
                or ""
            )
            return True, str(post_id), ""
        except json.JSONDecodeError:
            # Non-JSON success output (e.g. "Post Created:") is still a success.
            return True, "", ""

    except subprocess.TimeoutExpired:
        return False, "", "late_tool.py timed out after 60s"
    except Exception as exc:
        return False, "", str(exc)


# ── Supabase update helpers ───────────────────────────────────────────────────

def mark_posted(client, content_id: str, late_post_id: str) -> None:
    """Update content_calendar row to status='posted'."""
    updates: dict[str, object] = {
        "status": "posted",
        "posted_at": datetime.now(timezone.utc).isoformat(),
    }
    if late_post_id:
        updates["late_post_id"] = late_post_id
    client.table("content_calendar").update(updates).eq("id", content_id).execute()


def mark_failed(client, content_id: str, error: str = "") -> None:
    """Update content_calendar row to status='failed'."""
    updates: dict[str, object] = {
        "status": "failed",
        "posted_at": None,
    }
    client.table("content_calendar").update(updates).eq("id", content_id).execute()


# ── Core publish logic ────────────────────────────────────────────────────────

def _publish_row(client, row: dict, as_json: bool) -> dict:
    """
    Attempt to publish one content_calendar row.
    Returns a result dict with keys: id, platform, status, late_post_id, error.
    """
    content_id = str(row.get("id", ""))
    platform = (row.get("platform") or "").lower().strip()
    body = (row.get("body") or "").strip()
    title = row.get("title")

    # Build the final post text. Title is prepended when present.
    post_text = f"{title}\n\n{body}" if title else body

    # 1. Validate character limit.
    ok, actual, limit = validate_length(post_text, platform)
    if not ok:
        error_msg = f"Exceeds {platform} limit: {actual}/{limit} chars"
        if not as_json:
            print(f"  SKIP [{content_id}] {platform}: {error_msg}", file=sys.stderr)
        mark_failed(client, content_id, error_msg)
        notify(
            f"Content publish skipped [{content_id}]: {error_msg}",
            category="content",
        )
        return {"id": content_id, "platform": platform, "status": "failed", "late_post_id": "", "error": error_msg}

    # 2. Resolve Late account ID.
    account_id = resolve_account_id(platform)
    if not account_id:
        error_msg = f"No Late account mapped for platform '{platform}'"
        if not as_json:
            print(f"  SKIP [{content_id}] {platform}: {error_msg}", file=sys.stderr)
        mark_failed(client, content_id, error_msg)
        notify(
            f"Content publish failed [{content_id}]: {error_msg}",
            category="content",
        )
        return {"id": content_id, "platform": platform, "status": "failed", "late_post_id": "", "error": error_msg}

    # 3. Publish.
    success, late_post_id, error_msg = publish_via_late(post_text, account_id)

    if success:
        mark_posted(client, content_id, late_post_id)
        if not as_json:
            chars_info = f"{actual}/{limit}" if limit else str(actual)
            print(f"  OK  [{content_id}] {platform} — {chars_info} chars — late_post_id={late_post_id or 'n/a'}")
        return {"id": content_id, "platform": platform, "status": "posted", "late_post_id": late_post_id, "error": ""}
    else:
        mark_failed(client, content_id, error_msg)
        if not as_json:
            print(f"  ERR [{content_id}] {platform}: {error_msg}", file=sys.stderr)
        notify(
            f"Content publish failed [{content_id}] on {platform}: {error_msg}",
            category="content",
        )
        return {"id": content_id, "platform": platform, "status": "failed", "late_post_id": "", "error": error_msg}


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_publish_due(client, as_json: bool) -> None:
    """Find all scheduled content due now and publish each one."""
    now = datetime.now(timezone.utc).isoformat()

    try:
        result = (
            client.table("content_calendar")
            .select("*")
            .eq("status", "scheduled")
            .lte("scheduled_for", now)
            .order("scheduled_for", desc=False)
            .execute()
        )
        rows = result.data or []
    except Exception as exc:
        output = {"error": f"content_calendar query failed: {exc}", "published": [], "failed": [], "total_due": 0}
        if as_json:
            print(json.dumps(output))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if not rows:
        if as_json:
            print(json.dumps({"published": [], "failed": [], "total_due": 0}))
        else:
            print("No content due for publishing.")
        return

    if not as_json:
        print(f"Publishing {len(rows)} due post(s):\n")

    published: list[dict] = []
    failed: list[dict] = []

    for row in rows:
        result_entry = _publish_row(client, row, as_json)
        if result_entry["status"] == "posted":
            published.append(result_entry)
        else:
            failed.append(result_entry)

    summary = {
        "total_due": len(rows),
        "published": published,
        "failed": failed,
    }

    if as_json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\nDone: {len(published)} published, {len(failed)} failed out of {len(rows)} due.")
        if failed:
            for f in failed:
                print(f"  FAILED [{f['id']}] {f['platform']}: {f['error']}")


def cmd_publish_one(client, content_id: str, as_json: bool) -> None:
    """Publish a specific content entry by ID, regardless of its scheduled time."""
    try:
        result = (
            client.table("content_calendar")
            .select("*")
            .eq("id", content_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
    except Exception as exc:
        output = {"error": f"content_calendar query failed: {exc}"}
        if as_json:
            print(json.dumps(output))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if not rows:
        msg = f"Content [{content_id}] not found."
        if as_json:
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        sys.exit(1)

    row = rows[0]
    current_status = row.get("status", "")
    if current_status == "posted":
        msg = f"Content [{content_id}] is already posted. Aborting."
        if as_json:
            print(json.dumps({"error": msg, "status": "posted"}))
        else:
            print(f"WARN: {msg}")
        return

    if not as_json:
        platform = row.get("platform", "?")
        body_preview = (row.get("body") or "")[:60].replace("\n", " ")
        print(f"Publishing [{content_id}] [{platform}]: {body_preview}...")

    result_entry = _publish_row(client, row, as_json)

    if as_json:
        print(json.dumps(result_entry, indent=2))
    else:
        if result_entry["status"] == "posted":
            print(f"Published [{content_id}] — late_post_id={result_entry['late_post_id'] or 'n/a'}")
        else:
            print(f"Failed [{content_id}]: {result_entry['error']}", file=sys.stderr)
            sys.exit(1)


def cmd_status(client, as_json: bool) -> None:
    """Show counts of content by status, and how many scheduled are now due."""
    now = datetime.now(timezone.utc).isoformat()

    try:
        all_result = client.table("content_calendar").select("id, status, scheduled_for").execute()
        rows = all_result.data or []
    except Exception as exc:
        output = {"error": str(exc)}
        if as_json:
            print(json.dumps(output))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    counts: dict[str, int] = {}
    due_count = 0

    for row in rows:
        status = row.get("status") or "unknown"
        counts[status] = counts.get(status, 0) + 1

        if status == "scheduled":
            scheduled_for = row.get("scheduled_for") or ""
            if scheduled_for and scheduled_for <= now:
                due_count += 1

    stats = {
        "by_status": counts,
        "scheduled_due_now": due_count,
        "total": len(rows),
    }

    if as_json:
        print(json.dumps(stats, indent=2))
    else:
        print("Content Calendar Status:\n")
        for s, count in sorted(counts.items()):
            print(f"  {s:12s}: {count}")
        print(f"\n  Due now (scheduled + past schedule_for): {due_count}")
        print(f"  Total rows: {len(rows)}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="late_publisher.py",
        description="Late Publisher — publish due content from Supabase content_calendar",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  publish-due              Publish all scheduled posts with scheduled_for <= now()
  publish-one <id>         Publish a single content entry by its UUID
  status                   Show counts by status and how many are due

Examples:
  python scripts/late_publisher.py publish-due
  python scripts/late_publisher.py --json publish-due
  python scripts/late_publisher.py publish-one abc-123-def
  python scripts/late_publisher.py status
  python scripts/late_publisher.py --json status
        """,
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="Machine-readable JSON output (used by scheduler.py)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("publish-due", help="Publish all due scheduled posts")

    p_one = subparsers.add_parser("publish-one", help="Publish a specific content entry")
    p_one.add_argument("content_id", help="UUID of the content_calendar row to publish")

    subparsers.add_parser("status", help="Show content counts by status")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    env_vars = load_env()
    client = get_client(env_vars)

    if args.command == "publish-due":
        cmd_publish_due(client, as_json=args.output_json)
    elif args.command == "publish-one":
        cmd_publish_one(client, args.content_id, as_json=args.output_json)
    elif args.command == "status":
        cmd_status(client, as_json=args.output_json)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
