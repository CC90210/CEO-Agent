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
import json
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

# Intent detection keyword sets
_BOOKING_KEYWORDS = {
    "book", "call", "meet", "schedule", "chat", "consultation",
    "demo", "appointment", "available", "time", "talk", "connect",
}
_PRICING_KEYWORDS = {
    "price", "cost", "how much", "rate", "pricing", "package", "afford",
}
_INFO_KEYWORDS = {
    "what do you", "how does", "tell me about", "what is", "services", "offer",
}
_GREETING_KEYWORDS = {"hey", "hi", "hello", "sup", "yo"}

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
        f"You're all set! I've booked us in for {display} (30 min).\n\n"
        f"Here's the Google Meet link: {meet_link}\n\n"
        f"Looking forward to chatting!"
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
    auto_replies = []
    skipped_replies = []

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

            # Also identify UNREPLIED conversations — last message NOT from "You:"
            # This catches DMs that lost their "Unread" badge when we opened the inbox
            unreplied = []
            for c in convos:
                preview = c.get("preview", "")
                preview_lower = preview.lower()
                is_from_other = (
                    not preview.startswith("You:")
                    and not preview.startswith("You ")
                    and "sent an attachment" not in preview_lower
                    and "liked a message" not in preview_lower
                    and "sent a gif" not in preview_lower
                    and "video chat" not in preview_lower
                    and "active today" not in preview_lower
                    and "you sent" not in preview_lower
                    and "you liked" not in preview_lower
                    and len(preview) > 3
                )
                if is_from_other:
                    c["needs_reply"] = True
                    unreplied.append(c)

            # Merge: process unread + unreplied (deduplicated)
            to_process = {c["username"]: c for c in unread}
            for c in unreplied:
                if c["username"] not in to_process:
                    to_process[c["username"]] = c
            actionable = list(to_process.values())

            if not actionable:
                result["message"] = "No DMs needing reply"
                if getattr(args, "output_json", False):
                    print(json.dumps(result, indent=2, default=str))
                return result

            # Process each actionable conversation — detect intent and auto-reply
            # Supports multi-turn booking: if user is in "awaiting_time" state,
            # parse their time, create a Google Calendar event, and send the Meet link.
            for convo in actionable:
                username = convo.get("username", "").strip()
                preview = convo.get("preview", "")[:100]
                if not username:
                    continue

                # Open the conversation to read the actual message
                convo_text = read_conversation_text(page, username)

                # Use the full conversation text to get the sender's last message
                signal_text = convo_text[-500:] if convo_text else preview

                # Check if this user is in a booking flow (awaiting time confirmation)
                user_booking = booking_state.get(username)
                if user_booking and user_booking.get("stage") == "awaiting_time":
                    # Try to parse a date/time from their response
                    parsed = parse_datetime_from_text(signal_text)
                    if parsed:
                        # Create Google Calendar event with Meet link
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
                        else:
                            skipped_replies.append({
                                "username": username,
                                "reason": "calendar_event_failed",
                            })
                            notify(
                                f"DM from {username}: tried to book {parsed['display']}"
                                f" but calendar event creation failed",
                                category="instagram",
                            )
                    else:
                        # Couldn't parse a time — ask again
                        reply_text = (
                            "I want to make sure I get the right time -- could you"
                            " send the day and time that works? For example:"
                            " \"Thursday at 2pm\" or \"March 27 at 10am\""
                        )
                        _send_dm_reply(page, reply_text)
                        auto_replies.append({
                            "username": username,
                            "intent": "BOOKING_REPROMPT",
                            "reply_preview": reply_text[:80],
                        })
                        notify(
                            f"DM from {username}: \"{preview}\" — couldn't parse"
                            f" time, asked again",
                            category="instagram",
                        )

                    # Navigate back to inbox
                    page.goto(
                        "https://www.instagram.com/direct/inbox/",
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )
                    time.sleep(4)
                    continue

                # --- Normal flow: new conversation ---
                intent = detect_intent(signal_text)

                should_reply = True
                skip_reason = None

                if already_replied_within_24h(replied_log, username):
                    should_reply = False
                    skip_reason = "replied_within_24h"
                elif intent == "UNKNOWN":
                    should_reply = False
                    skip_reason = "unknown_intent"

                if should_reply:
                    reply_text = build_reply(intent)

                    sent = _send_dm_reply(page, reply_text)
                    if sent:
                        # Track the reply
                        replied_log[username] = {
                            "replied_at": datetime.now(timezone.utc).isoformat(),
                            "intent": intent,
                        }
                        save_replied_log(replied_log)
                        log_auto_reply_to_supabase(env_vars, username, intent, reply_text)

                        # If booking/pricing/info intent, enter booking flow
                        if intent in ("BOOKING", "PRICING", "INFO"):
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
                        notify(
                            f"New IG DM from {username}: \"{preview}\"\n"
                            f"Auto-replied ({intent}): {reply_text[:80]}",
                            category="instagram",
                        )
                    else:
                        skip_reason = "no_input_found"
                        should_reply = False

                if not should_reply:
                    skipped_replies.append({"username": username, "reason": skip_reason})
                    if skip_reason not in ("replied_within_24h",):
                        notify(
                            f"New IG DM from {username}: \"{preview}\" "
                            f"(not auto-replied: {skip_reason})",
                            category="instagram",
                        )

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


# -- Auto-reply helpers -------------------------------------------------------

def detect_intent(text: str) -> str:
    """Classify message text into BOOKING / PRICING / INFO / GREETING / UNKNOWN.

    Multi-word phrases are checked with substring matching so that phrases like
    'how much' correctly score as PRICING even though they contain two words.
    Single-word sets are checked with whole-word tokenisation to reduce false
    positives (e.g. 'offer' inside 'buffer').
    Returns the highest-priority match: BOOKING > PRICING > INFO > GREETING > UNKNOWN.
    """
    lowered = text.lower()

    # Multi-word phrases first (substring check is correct here)
    multi_word_pricing = {"how much"}
    multi_word_info = {"what do you", "how does", "tell me about", "what is"}

    for phrase in multi_word_pricing:
        if phrase in lowered:
            return "PRICING"
    for phrase in multi_word_info:
        if phrase in lowered:
            return "INFO"

    # Single-word sets — tokenise so 'offer' in 'buffer' does not match
    import re
    tokens = set(re.findall(r"[a-z]+", lowered))

    single_booking = _BOOKING_KEYWORDS - {"how much"}
    single_pricing = _PRICING_KEYWORDS - {"how much"}
    single_info = _INFO_KEYWORDS - {"what do you", "how does", "tell me about", "what is"}

    if tokens & single_booking:
        return "BOOKING"
    if tokens & single_pricing:
        return "PRICING"
    if tokens & single_info:
        return "INFO"
    if tokens & _GREETING_KEYWORDS:
        return "GREETING"
    return "UNKNOWN"


def build_reply(intent: str, meet_link: str = "") -> str:
    """Return the appropriate auto-reply template for the given intent.

    BOOKING/PRICING/INFO replies now ask for a preferred date/time instead of
    sending a static Meet link. Once the person confirms a time, the follow-up
    handler creates a Google Calendar event with a fresh Meet link.
    """
    templates = {
        "BOOKING": (
            "Hey! I'd love to chat. I'm generally free weekdays between"
            " 9am-5pm ET -- what day and time works best for you?"
            " I'll send over a Google Meet link once we lock in a time"
        ),
        "PRICING": (
            "Great question! It really depends on what you need -- every"
            " business is different. Let's hop on a quick call so I can"
            " understand your situation. What day/time works for you?"
            " (I'm free weekdays 9-5 ET)"
        ),
        "INFO": (
            "Thanks for reaching out! I run OASIS AI Solutions -- we build"
            " AI automation systems for local businesses. Happy to walk you"
            " through it on a quick call. What day/time works best for you?"
        ),
        "GREETING": "Hey! Thanks for reaching out. What can I help you with?",
    }
    return templates.get(intent, "")


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
    """Extract a date and time from natural language text.

    Handles patterns like:
      - "tomorrow at 2pm", "Thursday 10am", "March 25 at 3:00"
      - "next Monday at 11", "this Friday 2:30pm"
      - "25th at 2pm", "the 26th at 10am"

    Returns {date: "YYYY-MM-DD", time: "HH:MM", display: "Thursday March 25 at 2:00 PM"}
    or None if no date/time found.
    """
    import re
    from datetime import date as date_type

    lowered = text.lower().strip()

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
        # Try 24h format: "at 14:00" or "at 14"
        time_24 = re.search(r'(?:at\s+)(\d{1,2})(?::(\d{2}))?(?!\s*(?:am|pm))', lowered)
        if time_24:
            hour = int(time_24.group(1))
            minute = int(time_24.group(2) or 0)
            if hour > 23:
                hour = None

    if hour is None:
        return None  # Can't book without a time

    # --- Extract date component ---
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/Toronto")
    now = datetime.now(et)
    today = now.date()
    target_date = None

    # "tomorrow"
    if "tomorrow" in lowered:
        target_date = today + timedelta(days=1)

    # "today"
    elif re.search(r'\btoday\b', lowered):
        target_date = today

    # Day of week: "monday", "this tuesday", "next wednesday"
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
                    days_ahead = 7  # Next week if same day
                if "next" in lowered:
                    days_ahead += 7 if days_ahead <= 7 else 0
                target_date = today + timedelta(days=days_ahead)
                break

    # Month + day: "march 25", "mar 25th", "april 2"
    if not target_date:
        month_names = {
            "jan": 1, "january": 1, "feb": 2, "february": 2,
            "mar": 3, "march": 3, "apr": 4, "april": 4,
            "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
            "aug": 8, "august": 8, "sep": 9, "september": 9,
            "oct": 10, "october": 10, "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }
        for name, month_num in month_names.items():
            m = re.search(rf'\b{name}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b', lowered)
            if m:
                day = int(m.group(1))
                year = today.year
                candidate = date_type(year, month_num, min(day, 28))
                if candidate < today:
                    candidate = date_type(year + 1, month_num, min(day, 28))
                target_date = candidate
                break

    # Ordinal day only: "the 25th", "on the 26th"
    if not target_date:
        ord_match = re.search(r'\b(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\b', lowered)
        if ord_match:
            day = int(ord_match.group(1))
            if 1 <= day <= 31:
                candidate = today.replace(day=min(day, 28))
                if candidate <= today:
                    # Next month
                    if today.month == 12:
                        candidate = date_type(today.year + 1, 1, min(day, 28))
                    else:
                        candidate = date_type(today.year, today.month + 1, min(day, 28))
                target_date = candidate

    # If still no date but we have a time, assume tomorrow if time has passed today
    if not target_date:
        if hour <= now.hour:
            target_date = today + timedelta(days=1)
        else:
            target_date = today

    # Build result
    time_str = f"{hour:02d}:{minute:02d}"
    display_dt = datetime.combine(target_date, datetime.strptime(time_str, "%H:%M").time())
    # Windows uses %#d instead of %-d for no-zero-pad
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
    except Exception:
        pass  # Supabase logging is best-effort; never crash the main flow


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

                reply_text = build_reply(intent)

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

                # Enter booking flow for booking/pricing/info intents
                if intent in ("BOOKING", "PRICING", "INFO"):
                    booking_state[username] = {
                        "stage": "awaiting_time",
                        "intent": intent,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                    }
                    save_booking_state(booking_state)

                # Log to Supabase (best-effort)
                log_auto_reply_to_supabase(env_vars, username, intent, reply_text)

                notify(
                    f"Auto-replied to @{username} (intent: {intent}): {reply_text[:80]}",
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
