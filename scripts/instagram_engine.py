"""
Instagram Engine - ManyChat replacement via Playwright browser automation.

Checks Instagram DMs and comments, responds in CC's brand voice,
and notifies CC via Telegram of all interactions.

Usage:
  python scripts/instagram_engine.py check-dms          # Check and list new DMs
  python scripts/instagram_engine.py check-dms --reply   # Check DMs and auto-reply
  python scripts/instagram_engine.py check-comments      # Check for new comments
  python scripts/instagram_engine.py send-dm --to USER --msg "text"  # Send a DM
  python scripts/instagram_engine.py log-dm --username USER --summary "text"
  python scripts/instagram_engine.py auto-reply          # Detect intent + auto-reply
  python scripts/instagram_engine.py --json auto-reply   # JSON output for scheduler

Requires: playwright Python package (pip install playwright)
Browser profile persists at tmp/ig-browser/ for session continuity.
"""

import argparse
import calendar
import json
import subprocess
import sys
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
BROWSER_DIR = str(PROJECT_ROOT / "tmp" / "ig-browser")
SCREENSHOT_DIR = str(PROJECT_ROOT / "tmp")
DM_REPLIED_PATH = PROJECT_ROOT / "tmp" / "dm_replied.json"
BOOKING_STATE_PATH = PROJECT_ROOT / "tmp" / "dm_booking_state.json"
NOTIFIED_PATH = PROJECT_ROOT / "tmp" / "dm_notified.json"

# Intent detection — only trigger booking when they EXPLICITLY ask for a call/meeting
# Everything else gets a genuine conversational reply
_EXPLICIT_BOOKING_PHRASES = {
    "book a call", "schedule a call", "set up a call", "hop on a call",
    "jump on a call", "get on a call", "book a meeting", "schedule a meeting",
    "can we call", "can we meet", "let's call", "lets call", "want to call",
    "when can we", "when are you free", "when works", "what time works",
    "book a demo", "schedule a demo", "set up a meeting",
}
_BOOKING_SIGNAL_WORDS = {
    "book", "schedule", "appointment", "consultation", "demo",
}
_PRICING_KEYWORDS = {
    "price", "cost", "how much", "rate", "pricing", "package", "afford",
}
_INFO_KEYWORDS = {
    "what do you", "how does", "tell me about", "what is", "services", "offer",
}
_GREETING_KEYWORDS = {"hey", "hi", "hello", "sup", "yo", "what's good", "whats good"}

_PAYMENT_PHRASES = {
    "how do i pay", "ready to pay", "where do i pay", "how to pay",
    "send payment", "take my money", "sign me up", "payment link",
    "e-transfer", "etransfer", "e transfer", "wire transfer", "interac",
    "venmo", "zelle", "paypal", "can i pay", "want to pay",
    "send you money", "send the money", "how do i send",
}

sys.path.insert(0, str(SCRIPTS_DIR))

# Intents that signal business interest — trigger CRM lead capture
_CRM_INTEREST_INTENTS = {"BOOKING", "PRICING", "PAYMENT", "INFO"}

try:
    from notify import notify
except ImportError:
    def notify(*a, **kw): return False


def capture_lead_to_crm(username: str, intent: str, message_text: str):
    """Insert an Instagram DM lead into the CRM if not already there.

    Runs lead_engine.py add as a subprocess — fire-and-forget, never blocks
    the DM reply flow. Notifies CC via Telegram on successful capture.
    """
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "lead_engine.py"),
                "add",
                "--name", f"@{username}",
                "--source", "instagram_dm",
                "--notes", f"Intent: {intent} | DM: {message_text[:200]}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
        if result.returncode == 0:
            notify(
                f"\U0001f3af IG lead captured: @{username} ({intent})",
                category="lead",
            )
            return True
    except Exception as exc:
        safe_print(f"CRM capture failed for @{username}: {exc}")
    return False


def _read_config_model(key: str, fallback: str) -> str:
    """Read a model name from .agents/config.toml."""
    config_path = PROJECT_ROOT / ".agents" / "config.toml"
    if not config_path.exists():
        return fallback
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}") and "=" in line:
                    _, _, val = line.partition("=")
                    val = val.strip().strip('"').strip("'")
                    if val:
                        return val
    except OSError:
        pass
    return fallback


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
    """Read the DM conversation list by extracting structured data from DOM buttons.

    Instagram renders each conversation as a div[role='button'] containing:
        Line 0: Username/display name
        Line 1: Message preview (or 'You: ...' or 'X sent an attachment.')
        Line 2: '·' (separator dot)
        Line 3: Time ago (8m, 1h, 1d, 1w, etc.)
        Line 4: 'Unread' (if unread)
    Returns a JSON string of parsed conversation objects.
    """
    return page.evaluate("""() => {
        const btns = document.querySelectorAll('div[role="button"]');
        const results = [];
        for (const btn of btns) {
            const text = btn.innerText.trim();
            if (text.length < 10 || text.length > 500) continue;
            if (text.includes('Instagram') || text.includes('Send message')) continue;
            const lines = text.split(String.fromCharCode(10)).map(l => l.trim()).filter(l => l.length > 0);
            if (lines.length >= 2) {
                results.push(lines);
            }
        }
        return JSON.stringify(results);
    }""")


def parse_conversations(inbox_data):
    """Parse conversation data from read_dm_list (JSON string of line arrays).

    Each conversation button yields an array of lines:
        [0] Username/display name
        [1] Message preview
        [2] '·' (dot separator — may be absent)
        [3] Time ago (8m, 1h, 1d, 1w, etc. — may be absent)
        [4] 'Unread' (if unread — may be absent)
    """
    import re
    TIME_PATTERN = re.compile(r"^\d{1,3}[mhdw]$|^\d{1,2}(mo|w)$")
    SKIP_NAMES = {"Your note", "First note of the week...", "OPEN MIC", "Send message"}

    # Parse the JSON string from read_dm_list
    try:
        raw_convos = json.loads(inbox_data) if isinstance(inbox_data, str) else inbox_data
    except (json.JSONDecodeError, TypeError):
        return []

    conversations = []
    for lines in raw_convos:
        if not isinstance(lines, list) or len(lines) < 2:
            continue

        username = lines[0]
        if username in SKIP_NAMES:
            continue

        # Filter out dot separators and find preview, time, unread
        preview = ""
        time_ago = ""
        is_unread = False

        for line in lines[1:]:
            if line == "\u00b7" or line == "·":
                continue  # dot separator
            elif line == "Unread":
                is_unread = True
            elif TIME_PATTERN.match(line):
                time_ago = line
            elif not preview:
                preview = line

        conversations.append({
            "username": username,
            "preview": preview,
            "unread": is_unread,
            "time_ago": time_ago,
        })

    return conversations


# -- DM Helpers ---------------------------------------------------------------

def _send_dm_reply(page, reply_text: str) -> bool:
    """Type and send a reply in the currently open DM conversation.

    Returns True if the message was sent, False if the input wasn't found.
    """
    msg_input = (
        page.query_selector('div[role="textbox"]')
        or page.query_selector('div[contenteditable="true"]')
    )
    if not msg_input:
        return False
    msg_input.click()
    time.sleep(0.3)
    page.keyboard.type(reply_text, delay=15)
    time.sleep(0.5)
    page.keyboard.press("Enter")
    time.sleep(3)
    return True


def _handle_booking_confirmation(
    env_vars: dict,
    page,
    username: str,
    parsed_time: dict,
    booking_state: dict,
) -> str | None:
    """Create a Google Calendar event and send the Meet link as a DM reply.

    Returns the reply text if successful, None on failure.
    """
    try:
        from scripts.google_calendar import create_event
    except ImportError:
        try:
            from google_calendar import create_event
        except ImportError:
            return None

    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/Toronto")

    start_dt = datetime.combine(
        datetime.strptime(parsed_time["date"], "%Y-%m-%d").date(),
        datetime.strptime(parsed_time["time"], "%H:%M").time(),
        tzinfo=et,
    )

    result = create_event(
        env_vars,
        title=f"Call with {username}",
        start_dt=start_dt,
        duration_minutes=30,
        description=f"Booked via Instagram DM auto-reply — @{username}",
    )

    if not result["success"]:
        return None

    meet_link = result["meet_link"]
    display = parsed_time["display"]

    reply_text = (
        f"locked in for {display}. "
        f"here's the meet link: {meet_link}"
    )

    sent = _send_dm_reply(page, reply_text)
    if not sent:
        return None

    # Update booking state to confirmed
    booking_state[username] = {
        "stage": "confirmed",
        "date": parsed_time["date"],
        "time": parsed_time["time"],
        "display": display,
        "meet_link": meet_link,
        "event_id": result["event_id"],
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }
    save_booking_state(booking_state)

    return reply_text


# -- Commands -----------------------------------------------------------------

def cmd_check_dms(env_vars, args):
    """Check Instagram DMs and auto-reply to unread messages in one atomic pass.

    This is the ONLY DM handler that runs on cron. It:
    1. Opens inbox, reads conversations
    2. For each unread DM: opens it, reads last message, detects intent
    3. Sends auto-reply if appropriate (respects 24h cooldown + CC manual reply check)
    4. Notifies CC on Telegram with the username AND what action was taken
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        safe_print("ERROR: playwright not installed. Run: pip install playwright")
        return {"status": "error", "message": "playwright not installed"}

    replied_log = load_replied_log()
    booking_state = load_booking_state()
    notified_log = load_notified_log()
    auto_replies = []
    skipped_replies = []
    result = {"action": "check_dms", "status": "error", "message": "Unknown error"}

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

            # Read inbox
            inbox_text = read_dm_list(page)
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
                "auto_replies": [],
            }

            # ONLY process conversations Instagram marks as "Unread"
            # Do NOT auto-reply to every unreplied conversation — CC handles
            # personal conversations himself. The bot only responds to genuinely
            # new, unread DMs that CC hasn't seen yet.
            actionable = list(unread)

            if not actionable:
                result["message"] = "No DMs needing reply"
                if getattr(args, "output_json", False):
                    print(json.dumps(result, indent=2, default=str))
                return result

            # Process each actionable conversation — detect intent and auto-reply.
            #
            # NOTIFICATION RULES (non-negotiable):
            #   - ONLY notify CC on Telegram when we SUCCESSFULLY auto-reply
            #   - ONLY notify CC on Telegram when a booking is CONFIRMED
            #   - NEVER notify about skips, errors, unknown intents, or failures
            #   - NEVER re-notify about the same DM preview we already reported
            #
            for convo in actionable:
                username = convo.get("username", "").strip()
                preview = convo.get("preview", "")[:100]
                if not username:
                    continue

                # Skip group chats — they contain "and" in the preview or
                # have "Active" as username with multi-person previews
                if " and " in preview and username == "Active":
                    skipped_replies.append({"username": username, "reason": "group_chat"})
                    continue

                # Skip if we already notified about this exact DM preview
                if already_notified(notified_log, username, preview):
                    skipped_replies.append({"username": username, "reason": "already_notified"})
                    continue

                # Open the conversation to read the actual messages
                convo_text = read_conversation_text(page, username)
                # Extract just the LAST message from the other person
                last_msg = extract_last_incoming_message(convo_text)
                if not last_msg:
                    last_msg = preview  # Fallback to inbox preview

                # --- Multi-turn booking flow ---
                user_booking = booking_state.get(username)
                if user_booking and user_booking.get("stage") == "awaiting_time":
                    # ONLY parse the last incoming message — NOT the whole convo
                    parsed = parse_datetime_from_text(last_msg)
                    if parsed:
                        reply_text = _handle_booking_confirmation(
                            env_vars, page, username, parsed, booking_state,
                        )
                        if reply_text:
                            auto_replies.append({
                                "username": username,
                                "intent": "BOOKING_CONFIRMED",
                                "reply_preview": reply_text[:80],
                            })
                            notify(
                                f"Booking confirmed! {username} — {parsed['display']}\n"
                                f"Sent Meet link via DM",
                                category="instagram",
                            )
                            mark_notified(notified_log, username, preview)
                            save_notified_log(notified_log)
                        else:
                            skipped_replies.append({
                                "username": username,
                                "reason": "calendar_error",
                            })
                    else:
                        # Their message doesn't contain a date/time — respond
                        # conversationally instead of robotically re-asking
                        intent = detect_intent(last_msg)
                        if intent == "CONVO":
                            reply_text = build_reply("CONVO", last_msg=last_msg, convo_context=convo_text)
                        else:
                            reply_text = (
                                "just lmk a day and time that works, "
                                "like \"thursday at 2pm\" or something"
                            )
                        _send_dm_reply(page, reply_text)
                        auto_replies.append({
                            "username": username,
                            "intent": "BOOKING_FOLLOWUP",
                            "reply_preview": reply_text[:80],
                        })
                        mark_notified(notified_log, username, preview)
                        save_notified_log(notified_log)

                    page.goto(
                        "https://www.instagram.com/direct/inbox/",
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )
                    time.sleep(4)
                    continue

                # --- Normal flow ---
                intent = detect_intent(last_msg)

                should_reply = True
                skip_reason = None

                if already_replied_within_24h(replied_log, username):
                    should_reply = False
                    skip_reason = "replied_within_24h"
                elif intent == "UNKNOWN":
                    should_reply = False
                    skip_reason = "unknown_intent"

                if should_reply:
                    reply_text = build_reply(intent, last_msg=last_msg, convo_context=convo_text)
                    if not reply_text:
                        should_reply = False
                        skip_reason = "empty_reply"
                    else:
                        sent = _send_dm_reply(page, reply_text)
                        if sent:
                            replied_log[username] = {
                                "replied_at": datetime.now(timezone.utc).isoformat(),
                                "intent": intent,
                            }
                            save_replied_log(replied_log)
                            log_auto_reply_to_supabase(env_vars, username, intent, reply_text)

                            # Capture business-interest DMs as CRM leads
                            if intent in _CRM_INTEREST_INTENTS:
                                capture_lead_to_crm(username, intent, last_msg)

                            # Only enter booking flow on EXPLICIT booking intent
                            if intent == "BOOKING":
                                booking_state[username] = {
                                    "stage": "awaiting_time",
                                    "intent": intent,
                                    "started_at": datetime.now(timezone.utc).isoformat(),
                                }
                                save_booking_state(booking_state)

                            auto_replies.append({
                                "username": username,
                                "intent": intent,
                                "reply_preview": reply_text[:80],
                            })
                            # Only notify CC on Telegram for BOOKING intents
                            # (not every routine auto-reply — that's spam)
                            if intent == "BOOKING":
                                notify(
                                    f"IG DM from {username}: \"{last_msg[:60]}\"\n"
                                    f"Auto-replied ({intent}): {reply_text[:80]}",
                                    category="instagram",
                                )
                            mark_notified(notified_log, username, preview)
                            save_notified_log(notified_log)
                        else:
                            skip_reason = "no_input_found"
                            should_reply = False

                if not should_reply:
                    skipped_replies.append({"username": username, "reason": skip_reason})
                    mark_notified(notified_log, username, preview)
                    save_notified_log(notified_log)

                # Navigate back to inbox for next conversation
                page.goto(
                    "https://www.instagram.com/direct/inbox/",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                time.sleep(4)

            result["auto_replies"] = auto_replies
            result["skipped_replies"] = skipped_replies
            result["actionable_count"] = len(actionable)
            result["message"] = (
                f"{len(actionable)} DM(s) needing reply — "
                f"{len(auto_replies)} auto-replied, "
                f"{len(skipped_replies)} skipped"
            )

            if getattr(args, "output_json", False):
                print(json.dumps(result, indent=2, default=str))
            else:
                safe_print(f"Instagram DMs: {result['message']}")
                for a in auto_replies:
                    safe_print(f"  -> @{a['username']} [{a['intent']}]: {a['reply_preview']}")
                for s in skipped_replies:
                    safe_print(f"  -- @{s['username']}: {s['reason']}")

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
    result = {"status": "error", "to": target, "message": "Unknown error"}

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
                safe_target = target.replace("\\", "\\\\").replace("'", "\\'")
                found = page.evaluate(f"""() => {{
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    while (walker.nextNode()) {{
                        if (walker.currentNode.textContent.includes('{safe_target}')) {{
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


# -- Auto-reply helpers -------------------------------------------------------

def extract_last_incoming_message(convo_text: str) -> str:
    """Pull out the last message that ISN'T from CC (i.e. not starting with 'You').

    The conversation text contains interleaved messages. We want the most recent
    message from the OTHER person to understand what they actually said.

    For story replies, Instagram shows "Replied to your story" as metadata then
    the actual reply text — we grab both and concatenate so context is preserved.
    """
    if not convo_text:
        return ""
    lines = [l.strip() for l in convo_text.split("\n") if l.strip()]
    # Walk backwards, skip timestamps/metadata, find last non-You message
    skip_patterns = {"seen", "delivered", "active", "typing", "liked a message",
                     "liked a photo", "sent an attachment"}
    # Story-related metadata that should be INCLUDED as context (not skipped)
    story_patterns = {"replied to your story", "reacted to your story",
                      "mentioned you in their story"}
    import re
    time_pattern = re.compile(r"^\d{1,2}:\d{2}\s*(am|pm)?$|^\d{1,2}[mhdw]$|^just now$|^yesterday$", re.I)

    # Collect up to 3 recent incoming lines to get context (story reply + actual text)
    incoming_lines = []
    for line in reversed(lines):
        lower = line.lower()
        # Skip metadata
        if lower in skip_patterns or time_pattern.match(lower):
            continue
        if len(line) < 2:
            continue
        # Skip CC's own messages — stop collecting (we've passed the boundary)
        if lower.startswith("you:") or lower.startswith("you ") or lower == "you":
            break
        incoming_lines.append(line)
        # If this line is story metadata, keep going to grab the actual reply
        if any(p in lower for p in story_patterns):
            continue
        # Otherwise we have enough context
        if len(incoming_lines) >= 2:
            break

    # Reverse to get chronological order and join
    incoming_lines.reverse()
    return " ".join(incoming_lines).strip()


def detect_intent(text: str) -> str:
    """Classify the OTHER person's message into an intent.

    BOOKING: Only when they EXPLICITLY ask for a call/meeting/demo.
    PRICING: Asking about cost/pricing.
    PAYMENT: Ready to pay, asking how to pay, or mentioning non-Stripe payment methods.
    INFO: Asking what you do or how it works.
    GREETING: Simple hello/hey/yo.
    CONVO: General conversation that doesn't fit above — respond naturally.
    UNKNOWN: Can't understand or too short to act on.

    Key change from V1: "CONVO" is the new default instead of UNKNOWN.
    Most messages deserve a genuine response, not silence.
    """
    lowered = text.lower().strip()

    # Too short to do anything with
    if len(lowered) < 2:
        return "UNKNOWN"

    # Check for explicit booking phrases first (high confidence)
    for phrase in _EXPLICIT_BOOKING_PHRASES:
        if phrase in lowered:
            return "BOOKING"

    # Check for payment intent — someone ready to pay or mentioning non-Stripe methods
    for phrase in _PAYMENT_PHRASES:
        if phrase in lowered:
            return "PAYMENT"
    # Single-word payment signals with context
    if any(w in lowered for w in ("invoice", "checkout")) and any(w in lowered for w in ("send", "ready", "want", "need", "can")):
        return "PAYMENT"

    # Multi-word checks
    if "how much" in lowered or "what's the price" in lowered or "what do you charge" in lowered:
        return "PRICING"
    for phrase in ("what do you do", "how does", "tell me about", "what is your", "what services"):
        if phrase in lowered:
            return "INFO"

    # Single-word tokenization
    import re
    tokens = set(re.findall(r"[a-z']+", lowered))

    # Only trigger BOOKING on very explicit signal words + context
    booking_signals = tokens & _BOOKING_SIGNAL_WORDS
    if booking_signals and any(w in lowered for w in ("call", "meeting", "demo", "appointment")):
        return "BOOKING"

    if tokens & _PRICING_KEYWORDS:
        return "PRICING"

    # Short reactive messages (thank you, lol, haha, emoji-like) — treat as CONVO
    # so _build_convo_reply can match "thank you" properly instead of greeting them
    if any(w in lowered for w in ("thank", "thanks", "appreciate", "thx", "lol", "haha", "lmao", "nice", "dope", "fire")):
        return "CONVO"

    # Pure greetings (short messages that are ONLY a hello — nothing else)
    if len(tokens) <= 4 and tokens & _GREETING_KEYWORDS:
        return "GREETING"

    # If the message has substance (>3 words), it's a conversation — respond to it
    if len(tokens) >= 3:
        return "CONVO"

    # Very short but not a greeting — still try to respond contextually
    if len(tokens) <= 2:
        return "CONVO"

    return "CONVO"


def build_reply(intent: str, last_msg: str = "", convo_context: str = "") -> str:
    """Generate a reply that sounds like CC — short, casual, genuine.

    Voice rules:
    - Text like you're talking to a friend. Short sentences.
    - Use lowercase mostly. No "I'd love to" or "Thanks for reaching out."
    - No multiple exclamation marks. No corporate pleasantries.
    - Can use slang: "ya", "nah", "for sure", "lowkey", "honestly", "bet"
    - Be helpful and real, not salesy.
    - DON'T force every conversation toward booking a call.
    - Match the energy of what they said.
    """
    import random

    if intent == "BOOKING":
        return random.choice([
            "ya for sure lets do it. when works for you this week? i'm usually free 9-5",
            "bet lets hop on a call. what day works best? im pretty open this week",
            "down. when are you thinking? im free most days 9-5 eastern",
        ])

    if intent == "PAYMENT":
        return _build_payment_reply(last_msg, convo_context)

    if intent == "PRICING":
        return random.choice([
            "honestly it depends on what you need — every business is different. "
            "what kind of stuff are you looking to set up?",
            "ya so pricing really depends on the scope. "
            "some clients pay 400/mo, some pay more depending on what we build. "
            "what's your situation?",
            "it varies a lot — depends on what you need automated and how complex it is. "
            "what are you working with right now?",
        ])

    if intent == "INFO":
        return random.choice([
            "ya so basically i build AI automation systems for local businesses — "
            "stuff like auto follow-ups, booking, lead capture, review management. "
            "been doing it for a while now, it's pretty sick what you can automate these days",
            "i run an AI automation company called OASIS. we set up systems that handle "
            "the repetitive stuff — follow-ups, scheduling, lead gen, all that. "
            "honestly it's been a wild ride building it",
            "short version — i help businesses automate their ops with AI. "
            "most of my clients are local service businesses. pretty much anything "
            "repetitive, we can build a system for it",
        ])

    if intent == "GREETING":
        return random.choice([
            "yo what's good",
            "hey what's up",
            "yo whats good",
            "hey! how's it going",
        ])

    if intent == "CONVO":
        # For general conversation, build a contextual reply
        return _build_convo_reply(last_msg, convo_context)

    return ""


def _resolve_payment_links(reply: str) -> str:
    """Find [GENERATE_PAYMENT_LINK:amount:label] tokens and replace with real Stripe URLs."""
    import re

    pattern = r'\[GENERATE_PAYMENT_LINK:(\d+):([^\]]+)\]'

    def _replace_link(match):
        amount_cents = int(match.group(1))
        label = match.group(2).strip()
        try:
            from stripe_tool import generate_payment_link
            result = generate_payment_link(
                amount_cents=amount_cents,
                label=label,
                currency="cad",
            )
            return result["url"]
        except Exception as e:
            safe_print(f"[stripe] Payment link generation failed: {e}")
            return "(payment link coming — i'll send it in a sec)"

    return re.sub(pattern, _replace_link, reply)


def _build_payment_reply(last_msg: str, convo_context: str) -> str:
    """Generate a payment-related reply using Claude, then resolve any payment link tokens."""
    reply = _generate_reply_via_claude(last_msg, convo_context, payment_context=True)
    if reply:
        return _resolve_payment_links(reply)

    # Fallback if Claude API is down
    return (
        "ya for sure — i'll send you a payment link right now. "
        "all payments go through stripe so its secure and easy"
    )


def _build_convo_reply(last_msg: str, convo_context: str) -> str:
    """Generate a contextual reply using Claude API.

    Sends the person's message (and recent conversation context) to Claude
    with CC's voice rules. Returns a genuine, conversational response that
    actually addresses what they said — not canned keyword templates.

    Falls back to simple templates only if the API call fails.
    """
    import random

    # Try Claude API first — this is the real reply engine
    reply = _generate_reply_via_claude(last_msg, convo_context)
    if reply:
        return _resolve_payment_links(reply)

    # Fallback: bare minimum templates if API is down
    lower = last_msg.lower().strip()
    if any(w in lower for w in ("thank", "thanks", "appreciate", "thx")):
        return "ya no worries"
    if any(w in lower for w in ("replied to your story", "your story")):
        return "appreciate that fr"
    if "?" in last_msg:
        return "good question, honestly it depends on the situation"
    return "ya for sure"


def _generate_reply_via_claude(last_msg: str, convo_context: str, payment_context: bool = False) -> str:
    """Call Claude API to generate a contextual DM reply in CC's voice.

    Returns the reply text, or empty string on failure.
    """
    try:
        import anthropic
    except ImportError:
        return ""

    env_vars = load_env()
    api_key = env_vars.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""

    # Build the prompt with conversation context
    context_block = ""
    if convo_context:
        context_block = f"\nRecent conversation:\n{convo_context[-1000:]}\n"

    if payment_context:
        context_block += (
            "\nCONTEXT: This person is asking about payment or how to pay. "
            "If a price was previously discussed or agreed in the conversation, "
            "include a [GENERATE_PAYMENT_LINK:amount_cents:label] token in your reply "
            "(e.g., [GENERATE_PAYMENT_LINK:25000:OASIS AI Monthly]). "
            "If no price was agreed yet, ask what service they want first.\n"
        )

    system_prompt = (
        "You are ghostwriting an Instagram DM reply as Conaugh McKenna (CC), "
        "a 22-year-old AI automation entrepreneur from Collingwood, Ontario. "
        "CC runs OASIS AI Solutions — he builds AI systems for local businesses.\n\n"
        "VOICE RULES (non-negotiable):\n"
        "- Text like you're talking to a friend at 2am. Short sentences.\n"
        "- Lowercase mostly. No 'I'd love to' or 'Thanks for reaching out.'\n"
        "- No exclamation marks spam. No corporate pleasantries. No emojis.\n"
        "- Can use: ya, nah, for sure, lowkey, honestly, bet, fr, lol\n"
        "- Be genuine and real. Match their energy.\n"
        "- NEVER pitch, sell, or push toward a call unless they ask.\n"
        "- NEVER use hashtags or marketing language.\n"
        "- If they said something about your story, acknowledge the story content.\n"
        "- If they said thank you, just be chill about it.\n"
        "- Keep it to 1-3 sentences max. DMs are short.\n"
        "- Respond to WHAT THEY ACTUALLY SAID. Read their message carefully.\n\n"
        "PAYMENT RULES (non-negotiable):\n"
        "- ALL payments go through Stripe. NEVER suggest e-transfer, wire transfer, "
        "Interac, Venmo, Zelle, PayPal, cash, or any other payment method.\n"
        "- If they ask how to pay or mention any non-Stripe method, say: "
        "'all payments go through stripe — super easy and secure, i'll send you a link'\n"
        "- If a specific dollar amount has been AGREED upon and they want to pay, "
        "include this exact token in your reply (it will be replaced with a real link):\n"
        "  [GENERATE_PAYMENT_LINK:<amount_in_cents_CAD>:<short description>]\n"
        "  Example: 'here's your link [GENERATE_PAYMENT_LINK:50000:OASIS AI Retainer]'\n"
        "- Only include the payment link token when a price is AGREED. Not for general pricing questions.\n"
        "- Currency is always CAD.\n\n"
        "Reply with ONLY the message text. No quotes, no labels, nothing else."
    )

    user_msg = f"{context_block}Their message: \"{last_msg}\"\n\nYour reply:"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=_read_config_model("fast_model", "claude-sonnet-4-6"),
            max_tokens=150,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        reply = response.content[0].text.strip()

        # Safety: strip any quotes the model might wrap the reply in
        if reply.startswith('"') and reply.endswith('"'):
            reply = reply[1:-1]
        if reply.startswith("'") and reply.endswith("'"):
            reply = reply[1:-1]

        # Safety: reject if too long for a DM (something went wrong)
        if len(reply) > 500:
            return reply[:500]

        return reply
    except Exception as e:
        safe_print(f"[claude-api] Reply generation failed: {e}")
        return ""


def load_replied_log() -> dict:
    """Load the dm_replied.json tracking file.  Returns {} if absent or corrupt."""
    if not DM_REPLIED_PATH.exists():
        return {}
    try:
        with open(DM_REPLIED_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_replied_log(log: dict) -> None:
    """Persist the dm_replied.json tracking file."""
    DM_REPLIED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DM_REPLIED_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


def load_notified_log() -> dict:
    """Load the dm_notified.json file — tracks which DM previews we already
    sent a Telegram notification about so we never spam CC with the same
    conversation on every cron cycle."""
    if not NOTIFIED_PATH.exists():
        return {}
    try:
        with open(NOTIFIED_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_notified_log(log: dict) -> None:
    NOTIFIED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(NOTIFIED_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


def already_notified(log: dict, username: str, preview: str) -> bool:
    """Return True if we already sent CC a Telegram notification for this
    exact username + preview combo. Prevents the same DM from generating
    a notification on every 5-minute cron cycle."""
    entry = log.get(username)
    if not entry:
        return False
    return entry.get("preview", "") == preview


def mark_notified(log: dict, username: str, preview: str) -> None:
    """Record that we notified CC about this DM."""
    log[username] = {
        "preview": preview,
        "notified_at": datetime.now(timezone.utc).isoformat(),
    }


def load_booking_state() -> dict:
    """Load the multi-turn booking state tracker. Returns {} if absent."""
    if not BOOKING_STATE_PATH.exists():
        return {}
    try:
        with open(BOOKING_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_booking_state(state: dict) -> None:
    """Persist the booking state tracker."""
    BOOKING_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BOOKING_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def parse_datetime_from_text(text: str) -> dict | None:
    """Extract a date and time from a SHORT, SPECIFIC scheduling message.

    STRICT RULES — only parse if the message is clearly a scheduling response:
      - Must contain a recognizable time (2pm, 10:30am, at 14:00)
      - Must contain a recognizable date signal (tomorrow, Thursday, March 25)
      - Message should be SHORT (scheduling responses are typically <50 words)
      - If the message is long/rambling, it's probably NOT a scheduling response

    Returns {date: "YYYY-MM-DD", time: "HH:MM", display: "Thursday March 25 at 2:00 PM"}
    or None if this doesn't look like a scheduling message.
    """
    import re
    from datetime import date as date_type

    # GUARD: Only parse SHORT messages that look like scheduling responses.
    # "trapped is not the mic rib sea story Thursday" is NOT a scheduling msg.
    # Real scheduling messages: "thursday at 2pm", "tomorrow 10am", "march 25 3pm"
    lowered = text.lower().strip()
    words = lowered.split()
    if len(words) > 30:
        return None  # Too long to be a time/date response
    if len(words) < 2:
        return None  # Too short — just one word isn't a date

    # GUARD: Must contain an explicit time marker (am/pm or "at X:XX")
    has_time_marker = bool(re.search(r'\d{1,2}\s*(am|pm|a\.m\.|p\.m\.)', lowered))
    has_at_time = bool(re.search(r'at\s+\d{1,2}', lowered))
    if not has_time_marker and not has_at_time:
        return None

    # GUARD: Must contain a date signal
    date_signals = (
        "tomorrow", "today", "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday", "mon", "tue", "wed", "thu", "fri",
        "sat", "sun", "next", "this", "jan", "feb", "mar", "apr", "may",
        "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    )
    has_date_signal = any(sig in lowered for sig in date_signals)
    # Also check for ordinals: "the 25th"
    has_ordinal = bool(re.search(r'\b\d{1,2}(?:st|nd|rd|th)\b', lowered))
    if not has_date_signal and not has_ordinal:
        return None

    # --- Extract time component ---
    time_match = re.search(
        r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)',
        lowered,
    )
    hour, minute = None, 0
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        ampm = time_match.group(3).replace(".", "")
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
    else:
        time_24 = re.search(r'(?:at\s+)(\d{1,2})(?::(\d{2}))?(?!\s*(?:am|pm))', lowered)
        if time_24:
            hour = int(time_24.group(1))
            minute = int(time_24.group(2) or 0)
            if hour > 23:
                hour = None

    if hour is None:
        return None
    # Sanity check: business hours only (7am - 9pm)
    if hour < 7 or hour > 21:
        return None

    # --- Extract date component ---
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/Toronto")
    now = datetime.now(et)
    today = now.date()
    target_date = None

    if "tomorrow" in lowered:
        target_date = today + timedelta(days=1)
    elif re.search(r'\btoday\b', lowered):
        target_date = today

    day_names = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
        "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3,
        "thurs": 3, "fri": 4, "sat": 5, "sun": 6,
    }
    if not target_date:
        for name, dow in day_names.items():
            if re.search(rf'\b{name}\b', lowered):
                days_ahead = (dow - today.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                if "next" in lowered:
                    days_ahead += 7
                target_date = today + timedelta(days=days_ahead)
                break

    month_names = {
        "jan": 1, "january": 1, "feb": 2, "february": 2,
        "mar": 3, "march": 3, "apr": 4, "april": 4,
        "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "september": 9,
        "oct": 10, "october": 10, "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }
    if not target_date:
        for name, month_num in month_names.items():
            m = re.search(rf'\b{name}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b', lowered)
            if m:
                day = int(m.group(1))
                year = today.year
                candidate = date_type(year, month_num, min(day, calendar.monthrange(year, month_num)[1]))
                if candidate < today:
                    candidate = date_type(year + 1, month_num, min(day, calendar.monthrange(year + 1, month_num)[1]))
                target_date = candidate
                break

    if not target_date and has_ordinal:
        ord_match = re.search(r'\b(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\b', lowered)
        if ord_match:
            day = int(ord_match.group(1))
            if 1 <= day <= 31:
                candidate = today.replace(day=min(day, calendar.monthrange(today.year, today.month)[1]))
                if candidate <= today:
                    if today.month == 12:
                        candidate = date_type(today.year + 1, 1, min(day, calendar.monthrange(today.year + 1, 1)[1]))
                    else:
                        candidate = date_type(today.year, today.month + 1, min(day, calendar.monthrange(today.year, today.month + 1)[1]))
                target_date = candidate

    # If we have a time but no date, DON'T guess — ask them to clarify
    if not target_date:
        return None

    time_str = f"{hour:02d}:{minute:02d}"
    display_dt = datetime.combine(target_date, datetime.strptime(time_str, "%H:%M").time())
    display = display_dt.strftime("%A %B %#d at %#I:%M %p")

    return {
        "date": target_date.isoformat(),
        "time": time_str,
        "display": display,
    }


def already_replied_within_24h(log: dict, username: str) -> bool:
    """Return True if we auto-replied to this username in the last 24 hours."""
    entry = log.get(username)
    if not entry:
        return False
    last_ts = datetime.fromisoformat(entry["replied_at"])
    now = datetime.now(timezone.utc)
    # Make last_ts timezone-aware if it came back naive (defensive)
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=timezone.utc)
    return (now - last_ts).total_seconds() < 86400


def read_conversation_text(page, username: str) -> str:
    """Open a DM conversation by clicking the matching button in the inbox list
    and return the visible message text (last ~3000 chars).

    Uses the same div[role='button'] approach as read_dm_list to reliably
    find and click the correct conversation.
    """
    # Escape single quotes in username for JS string
    safe_name = username.replace("'", "\\'").replace("\\", "\\\\")
    found = page.evaluate(f"""() => {{
        const btns = document.querySelectorAll('div[role="button"]');
        for (const btn of btns) {{
            const text = btn.innerText.trim();
            const firstLine = text.split(String.fromCharCode(10))[0].trim();
            if (firstLine === '{safe_name}') {{
                btn.click();
                return true;
            }}
        }}
        // Fallback: partial match (display names can be truncated)
        for (const btn of btns) {{
            const text = btn.innerText.trim();
            const firstLine = text.split(String.fromCharCode(10))[0].trim();
            if (firstLine.includes('{safe_name}') || '{safe_name}'.includes(firstLine)) {{
                btn.click();
                return true;
            }}
        }}
        return false;
    }}""")
    if not found:
        return ""
    time.sleep(5)

    # Scrape ONLY the conversation thread (right panel), NOT the sidebar.
    # The sidebar contains "You: ..." previews from other conversations
    # that cause false positives in reply-detection logic.
    raw = page.evaluate("""() => {
        // Strategy: find the message textbox, then walk up to the conversation
        // panel container — this excludes the left sidebar entirely.
        const textbox = document.querySelector('div[role="textbox"]');
        if (textbox) {
            let el = textbox;
            // Walk up to find the conversation panel (stops at a large container
            // that is narrower than the full page — i.e. the right panel)
            for (let i = 0; i < 12; i++) {
                if (!el.parentElement) break;
                el = el.parentElement;
                const rect = el.getBoundingClientRect();
                const bodyWidth = document.body.getBoundingClientRect().width;
                // Right panel is typically 50-75% of page width
                if (rect.width > 350 && rect.height > 300 && rect.width < bodyWidth * 0.85) {
                    return el.innerText.slice(-3000);
                }
            }
        }
        // Fallback: if we can't isolate the panel, get full page but take
        // a larger slice from the end (conversation content is at the end).
        const main = document.querySelector('main') || document.body;
        return main.innerText.slice(-3000);
    }""")
    return raw or ""


def cc_has_replied(conversation_text: str) -> bool:
    """Return True if CC's most recent message is AFTER the last incoming message.

    We check the last ~500 chars of the conversation text. If the very last
    message block starts with 'You' or 'You:' or 'You sent', CC already replied
    to the most recent incoming message — no auto-reply needed.
    """
    if not conversation_text:
        return False
    # Look at just the tail of the conversation
    tail = conversation_text[-500:]
    lines = [l.strip() for l in tail.split("\n") if l.strip()]
    if not lines:
        return False
    # Walk backwards from the end to find the last actual message line
    # (skip time stamps, empty lines, emoji-only lines)
    import re
    time_pat = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)?$|^\d{1,3}[mhdw]$|^(Yesterday|Today)$", re.IGNORECASE)
    for line in reversed(lines):
        if time_pat.match(line):
            continue
        if len(line) <= 2:
            continue
        # Check if this last message is from CC
        if line.startswith("You") or line.startswith("you"):
            return True
        # If the last real message is from someone else, CC hasn't replied
        return False
    return False


def log_auto_reply_to_supabase(env_vars: dict, username: str, intent: str, reply: str) -> None:
    """Write the auto-reply event to Supabase dm_interactions table.
    Fails silently so it never blocks the send flow."""
    try:
        from supabase import create_client
        url = env_vars.get("BRAVO_SUPABASE_URL")
        key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            return
        db = create_client(url, key)
        db.table("dm_interactions").insert({
            "channel": "instagram_dm",
            "direction": "outbound",
            "ig_username": username,
            "intent": intent,
            "reply_preview": reply[:200],
            "auto_replied": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        safe_print(f"[supabase] dm_interactions insert failed: {e}")


def cmd_auto_reply(env_vars, args):
    """Check unread DMs, detect intent, and send templated auto-replies.

    Safety rules enforced here:
    - Never reply to the same person more than once per 24 h (dm_replied.json).
    - Never reply if CC has already manually replied in that thread.
    - All auto-replies are logged to Supabase dm_interactions.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        safe_print("ERROR: playwright not installed. Run: pip install playwright")
        return {"status": "error", "message": "playwright not installed"}

    replied_log = load_replied_log()
    booking_state = load_booking_state()
    actions_taken = []
    skipped = []

    with sync_playwright() as p:
        context = get_browser_context(p)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            if not ensure_logged_in(page, env_vars):
                result = {
                    "action": "auto_reply",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "login_failed",
                    "message": "Could not log into Instagram. Check credentials.",
                }
                notify("Instagram login failed - auto-reply aborted", category="instagram")
                if getattr(args, "output_json", False):
                    print(json.dumps(result, indent=2))
                else:
                    safe_print(f"auto-reply: {result['message']}")
                return result

            # Step 1: Read the inbox list
            inbox_text = read_dm_list(page)
            convos = parse_conversations(inbox_text)
            unread = [c for c in convos if c.get("unread")]

            if not unread:
                result = {
                    "action": "auto_reply",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "ok",
                    "message": "No unread DMs",
                    "replied": [],
                    "skipped": [],
                }
                if getattr(args, "output_json", False):
                    print(json.dumps(result, indent=2))
                else:
                    safe_print("auto-reply: No unread DMs to process")
                return result

            # Step 2: Process each unread conversation
            for convo in unread:
                username = convo.get("username", "").strip()
                if not username:
                    continue

                # Safety check 1: already replied in last 24 h?
                if already_replied_within_24h(replied_log, username):
                    skipped.append({"username": username, "reason": "replied_within_24h"})
                    continue

                # Open conversation and read full thread text
                convo_text = read_conversation_text(page, username)

                # NOTE: cc_has_replied() check removed — it was returning false
                # positives because main.innerText includes sidebar previews
                # ("You: ...") from OTHER conversations. The inbox preview check
                # (unread detection) already filters correctly. 24h cooldown
                # prevents double-replying.

                # Detect intent from the last message in the thread
                # Use the preview from the inbox list as the signal text; fall
                # back to the tail of the full conversation if the preview is empty.
                signal_text = convo.get("preview", "") or convo_text[-500:]
                last_msg = extract_last_incoming_message(convo_text) or signal_text
                intent = detect_intent(signal_text)

                if intent == "UNKNOWN":
                    skipped.append({"username": username, "reason": "unknown_intent"})
                    page.goto(
                        "https://www.instagram.com/direct/inbox/",
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )
                    time.sleep(4)
                    continue

                reply_text = build_reply(intent, last_msg=last_msg, convo_context=convo_text)

                sent = _send_dm_reply(page, reply_text)
                if not sent:
                    skipped.append({"username": username, "reason": "no_input_found"})
                    page.goto(
                        "https://www.instagram.com/direct/inbox/",
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )
                    time.sleep(4)
                    continue

                # Record the reply in the local tracking file
                replied_log[username] = {
                    "replied_at": datetime.now(timezone.utc).isoformat(),
                    "intent": intent,
                }
                save_replied_log(replied_log)

                # Only enter booking flow on EXPLICIT booking intent
                # (not PRICING or INFO — those are conversational, no CTA)
                if intent == "BOOKING":
                    booking_state[username] = {
                        "stage": "awaiting_time",
                        "intent": intent,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                    }
                    save_booking_state(booking_state)

                # Log to Supabase (best-effort)
                log_auto_reply_to_supabase(env_vars, username, intent, reply_text)

                # Notify CC on Telegram for booking and payment intents
                if intent == "BOOKING":
                    notify(
                        f"IG DM from @{username}: \"{last_msg[:60]}\"\n"
                        f"Auto-replied (BOOKING): {reply_text[:80]}",
                        category="instagram",
                    )
                elif intent == "PAYMENT":
                    notify(
                        f"IG DM from @{username}: \"{last_msg[:60]}\"\n"
                        f"Auto-replied (PAYMENT): {reply_text[:80]}",
                        category="instagram",
                    )

                actions_taken.append({
                    "username": username,
                    "intent": intent,
                    "reply_preview": reply_text[:100],
                })

                # Navigate back to inbox for the next conversation
                page.goto(
                    "https://www.instagram.com/direct/inbox/",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                time.sleep(4)
                # Re-read the list so stale refs don't cause issues
                inbox_text = read_dm_list(page)

        finally:
            context.close()

    result = {
        "action": "auto_reply",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "unread_processed": len(unread) if unread else 0,
        "replied": actions_taken,
        "skipped": skipped,
        "message": (
            f"Replied to {len(actions_taken)} conversation(s), "
            f"skipped {len(skipped)}"
        ),
    }

    if getattr(args, "output_json", False):
        print(json.dumps(result, indent=2, default=str))
    else:
        safe_print(f"auto-reply: {result['message']}")
        for a in actions_taken:
            safe_print(f"  -> @{a['username']} [{a['intent']}]: {a['reply_preview']}")
        for s in skipped:
            safe_print(f"  -- skipped @{s['username']}: {s['reason']}")

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

    # auto-reply
    subparsers.add_parser(
        "auto-reply",
        help="Detect intent in unread DMs and send templated auto-replies",
    )

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
        "auto-reply": cmd_auto_reply,
    }

    handler = handlers.get(args.command)
    if handler:
        handler(env_vars, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
