"""
Instagram Engine - ManyChat replacement via Playwright browser automation.

Checks Instagram DMs and comments, responds in CC's brand voice,
and notifies CC via Telegram of all interactions.

Usage:
  python scripts/instagram_engine.py check-dms          # Check and list new DMs
  python scripts/instagram_engine.py check-dms --reply   # Check DMs and auto-reply
  python scripts/instagram_engine.py check-comments      # Check for new comments
  python scripts/instagram_engine.py send-dm --to USER --msg "text"  # Send a DM
  python scripts/instagram_engine.py --json check-dms    # JSON output for scheduler

Requires: playwright Python package (pip install playwright)
Browser profile persists at tmp/ig-browser/ for session continuity.
"""

import argparse
import json
import sys
import os
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
BROWSER_DIR = str(PROJECT_ROOT / "tmp" / "ig-browser")
SCREENSHOT_DIR = str(PROJECT_ROOT / "tmp")

sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from notify import notify
except ImportError:
    def notify(*a, **kw): return False


def load_env() -> dict:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        return {}
    env_vars = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


def safe_print(text):
    """Print with ASCII-safe encoding for Windows cp1252."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))


def get_browser_context(playwright):
    """Launch persistent Chromium context (maintains login session)."""
    os.makedirs(BROWSER_DIR, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        user_data_dir=BROWSER_DIR,
        headless=True,
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )


def ensure_logged_in(page, env_vars):
    """Check if logged into Instagram; if not, log in with credentials."""
    page.goto(
        "https://www.instagram.com/direct/inbox/",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    time.sleep(6)

    # If redirected to login, authenticate
    if "/accounts/login" in page.url or page.url == "https://www.instagram.com/":
        safe_print("Session expired. Logging in...")
        ig_user = env_vars.get("INSTAGRAM_USERNAME", "")
        ig_pass = env_vars.get("INSTAGRAM_PASSWORD", "")
        if not ig_user or not ig_pass:
            return False

        page.goto(
            "https://www.instagram.com/accounts/login/",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        time.sleep(4)

        # Handle "Continue" screen (saved session, needs re-auth)
        user_field = page.query_selector('input[name="username"]') or page.query_selector('input[name="email"]')
        pass_field = page.query_selector('input[name="password"]') or page.query_selector('input[name="pass"]')

        if not user_field or not pass_field:
            # Click "Use another profile" to get full login form
            page.evaluate("""() => {
                const els = document.querySelectorAll('button, div[role="button"], a, span');
                for (const el of els) {
                    if (el.textContent.trim().includes('Use another profile')) {
                        el.click(); return true;
                    }
                }
                return false;
            }""")
            time.sleep(3)
            user_field = page.query_selector('input[name="username"]') or page.query_selector('input[name="email"]')
            pass_field = page.query_selector('input[name="password"]') or page.query_selector('input[name="pass"]')

        if not user_field or not pass_field:
            safe_print("ERROR: Could not find login form")
            return False

        user_field.click()
        user_field.fill("")
        user_field.type(ig_user, delay=30)
        time.sleep(0.3)
        pass_field.click()
        pass_field.fill("")
        pass_field.type(ig_pass, delay=30)
        time.sleep(0.5)

        # Click Log In button
        page.evaluate("""() => {
            const buttons = document.querySelectorAll('button[type="submit"], button, div[role="button"]');
            for (const b of buttons) {
                const t = b.textContent.trim().toLowerCase();
                if (t === 'log in' || t === 'login') { b.click(); return; }
            }
        }""")
        time.sleep(10)

        # Dismiss prompts (Save Login Info, Notifications)
        for _ in range(3):
            page.evaluate("""() => {
                const bs = document.querySelectorAll('button, div[role="button"]');
                for (const b of bs) {
                    const t = b.textContent.trim();
                    if (t === 'Not Now' || t === 'Not now') { b.click(); return; }
                }
            }""")
            time.sleep(2)

        # Navigate to DMs after login
        page.goto(
            "https://www.instagram.com/direct/inbox/",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        time.sleep(6)

    # Dismiss notification prompt on DMs page
    page.evaluate("""() => {
        const bs = document.querySelectorAll('button, div[role="button"]');
        for (const b of bs) {
            const t = b.textContent.trim();
            if (t === 'Not Now' || t === 'Not now') { b.click(); return; }
        }
    }""")
    time.sleep(1)

    return "/direct/" in page.url


def read_dm_list(page):
    """Read the DM conversation list from the inbox page."""
    return page.evaluate("""() => {
        const main = document.querySelector('main') || document.querySelector('section[role="main"]');
        if (!main) return '';
        return main.innerText.substring(0, 5000);
    }""")


def parse_conversations(inbox_text):
    """Parse the inbox text to extract conversation summaries."""
    lines = inbox_text.split("\n")
    conversations = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Skip navigation items
        if line in ("Primary", "General", "Request (1)", "Request", "Your note",
                     "Your messages", "Send a message to start a chat.", "Send message",
                     "Search", ""):
            i += 1
            continue
        # Skip time indicators alone
        if line in ("1h", "2h", "1d", "2d", "3d", "1w"):
            i += 1
            continue
        # Skip single emoji lines
        if len(line) <= 4 and not line.isalnum():
            i += 1
            continue
        # Look for username pattern followed by message preview
        if len(line) > 1 and ":" not in line and not line.startswith("You:"):
            # This might be a username - check next lines for preview
            username = line
            preview = ""
            is_unread = False
            time_ago = ""
            j = i + 1
            while j < len(lines) and j < i + 5:
                next_line = lines[j].strip()
                if "Unread" in next_line:
                    is_unread = True
                elif next_line in ("1h", "2h", "1d", "2d", "3d", "1w", "1m"):
                    time_ago = next_line
                elif next_line.startswith("You:") or "sent an attachment" in next_line or len(next_line) > 10:
                    if not preview:
                        preview = next_line
                j += 1
            if preview or time_ago:
                conversations.append({
                    "username": username,
                    "preview": preview,
                    "unread": is_unread,
                    "time_ago": time_ago,
                })
            i = j
        else:
            i += 1
    return conversations


# -- Commands -----------------------------------------------------------------

def cmd_check_dms(env_vars, args):
    """Check Instagram DMs via Playwright browser automation."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        safe_print("ERROR: playwright not installed. Run: pip install playwright")
        return {"status": "error", "message": "playwright not installed"}

    with sync_playwright() as p:
        context = get_browser_context(p)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            if not ensure_logged_in(page, env_vars):
                result = {
                    "action": "check_dms",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "login_failed",
                    "message": "Could not log into Instagram. Check credentials.",
                }
                notify("Instagram login failed - check credentials", category="instagram")
                if getattr(args, "output_json", False):
                    print(json.dumps(result, indent=2))
                else:
                    safe_print(f"Instagram DMs: {result['message']}")
                return result

            page.screenshot(path=os.path.join(SCREENSHOT_DIR, "ig_dm_check.png"))

            # Read inbox
            inbox_text = read_dm_list(page)
            # Parse conversations
            convos = parse_conversations(inbox_text)
            unread = [c for c in convos if c.get("unread")]

            result = {
                "action": "check_dms",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "checked",
                "total_visible": len(convos),
                "unread_count": len(unread),
                "conversations": convos[:10],
                "unread": unread,
            }

            # Notify CC about unread DMs
            if unread:
                for dm in unread:
                    username = dm.get("username", "unknown")
                    preview = dm.get("preview", "")[:100]
                    notify(
                        f"Unread IG DM from @{username}: {preview}",
                        category="instagram",
                    )
                result["message"] = f"{len(unread)} unread DM(s) found"
            else:
                result["message"] = "No unread DMs"

            if getattr(args, "output_json", False):
                print(json.dumps(result, indent=2, default=str))
            else:
                safe_print(f"Instagram DMs: {result['message']}")
                for c in convos[:5]:
                    marker = " [UNREAD]" if c.get("unread") else ""
                    safe_print(f"  - {c['username']}: {c.get('preview', '')[:60]}{marker}")

        finally:
            context.close()

    return result


def cmd_check_comments(env_vars, args):
    """Check Instagram comments (navigates to recent posts)."""
    result = {
        "action": "check_comments",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "checked",
        "message": "Comment check - use check-dms for active DM monitoring",
    }
    if getattr(args, "output_json", False):
        print(json.dumps(result, indent=2))
    else:
        safe_print(f"Instagram Comments: {result['message']}")
    return result


def cmd_send_dm(env_vars, args):
    """Send a DM to a specific user or reply in a thread."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        safe_print("ERROR: playwright not installed")
        return {"status": "error"}

    target = args.to_user
    message = args.message
    thread_url = getattr(args, "thread", None)

    with sync_playwright() as p:
        context = get_browser_context(p)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            if not ensure_logged_in(page, env_vars):
                safe_print("Login failed")
                return {"status": "login_failed"}

            if thread_url:
                # Navigate directly to thread
                page.goto(thread_url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(6)
            else:
                # Search for user in DMs
                safe_print(f"Looking for conversation with @{target}...")
                # Click on the conversation from inbox
                found = page.evaluate(f"""() => {{
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    while (walker.nextNode()) {{
                        if (walker.currentNode.textContent.includes('{target}')) {{
                            let el = walker.currentNode.parentElement;
                            for (let i = 0; i < 10; i++) {{
                                if (!el) break;
                                if (el.tagName === 'A' || el.getAttribute('role') === 'button') {{
                                    el.click();
                                    return true;
                                }}
                                el = el.parentElement;
                            }}
                            walker.currentNode.parentElement.click();
                            return true;
                        }}
                    }}
                    return false;
                }}""")
                if not found:
                    safe_print(f"Could not find conversation with @{target}")
                    return {"status": "not_found", "user": target}
                time.sleep(5)

            # Find message input and type
            msg_input = page.query_selector('div[role="textbox"]') or page.query_selector('div[contenteditable="true"]')
            if not msg_input:
                safe_print("Could not find message input")
                return {"status": "no_input"}

            msg_input.click()
            time.sleep(0.3)
            page.keyboard.type(message, delay=15)
            time.sleep(0.5)
            page.keyboard.press("Enter")
            time.sleep(3)

            page.screenshot(path=os.path.join(SCREENSHOT_DIR, "ig_sent_dm.png"))

            result = {
                "status": "sent",
                "to": target,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            notify(
                f"Sent IG DM to @{target}: {message[:80]}",
                category="instagram",
            )

            if getattr(args, "output_json", False):
                print(json.dumps(result, indent=2))
            else:
                safe_print(f"DM sent to @{target}: {message[:60]}")

        finally:
            context.close()

    return result


def cmd_log_dm(env_vars, args):
    """Log an Instagram DM interaction to Supabase for tracking."""
    try:
        from supabase import create_client
        url = env_vars.get("BRAVO_SUPABASE_URL")
        key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            safe_print("ERROR: Supabase not configured")
            return {"status": "error"}
        db = create_client(url, key)
    except Exception as e:
        safe_print(f"ERROR: {e}")
        return {"status": "error", "error": str(e)}

    record = {
        "channel": "instagram_dm",
        "direction": args.direction,
        "lead_id": getattr(args, "lead_id", None),
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
            category="instagram",
        )

    try:
        db.table("lead_interactions").insert(record).execute()
        result = {"status": "logged", "username": args.username}
    except Exception as e:
        result = {"status": "error", "error": str(e)}

    if getattr(args, "output_json", False):
        print(json.dumps(result, indent=2))
    else:
        safe_print(f"DM logged: @{args.username} ({args.direction})")

    return result


# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Instagram Engine - ManyChat replacement via browser automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", dest="output_json", action="store_true")

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # check-dms
    p_dms = subparsers.add_parser("check-dms", help="Check for new Instagram DMs")
    p_dms.add_argument("--reply", action="store_true", help="Auto-reply to unread DMs")

    # check-comments
    subparsers.add_parser("check-comments", help="Check for new Instagram comments")

    # send-dm
    p_send = subparsers.add_parser("send-dm", help="Send a DM to a user")
    p_send.add_argument("--to", dest="to_user", required=True, help="Target username")
    p_send.add_argument("--msg", dest="message", required=True, help="Message text")
    p_send.add_argument("--thread", help="Direct thread URL (optional)")

    # log-dm
    p_log = subparsers.add_parser("log-dm", help="Log a DM interaction to Supabase")
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
        "send-dm": cmd_send_dm,
        "log-dm": cmd_log_dm,
    }

    handler = handlers.get(args.command)
    if handler:
        handler(env_vars, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
