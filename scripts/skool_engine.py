"""
Skool Community Engine V2.1 — Autonomous community management via Playwright.

Features:
- Replies to community posts in CC's coaching voice
- Replies to COMMENTS inside posts (V2.1 — added 2026-04-11)
- When CC has already top-level commented on a post, Bravo's comment replies are
  brief and complementary (never step on CC's voice)
- Detects posts/comments needing CC's personal attention (crisis, hot leads, direct
  @-mentions, explicit coaching asks) and escalates via Telegram instead of auto-replying
- DMs DISABLED (2026-04-01) — CC handles DMs manually

Usage:
  python scripts/skool_engine.py login              # One-time: manual Skool login
  python scripts/skool_engine.py scan-posts         # Reply to community posts + comments
  python scripts/skool_engine.py auto               # Run post+comment scan
  python scripts/skool_engine.py daemon             # Run continuously (default: 5min)
  python scripts/skool_engine.py daemon --interval 5
  python scripts/skool_engine.py status             # Show engine status
  python scripts/skool_engine.py --dry-run auto     # Preview without posting
  python scripts/skool_engine.py --json auto        # JSON output

Requires: playwright, anthropic (pip install playwright anthropic)
Browser profile persists at tmp/skool-browser/ for session continuity.
"""

import argparse
import json
import sys
import os
import re
import time
import signal
import logging
import subprocess
import msvcrt
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
BROWSER_DIR = str(PROJECT_ROOT / "tmp" / "skool-browser")
TMP_DIR = PROJECT_ROOT / "tmp"
LOG_DIR = TMP_DIR / "logs"

# State files
REPLIED_POSTS_PATH = TMP_DIR / "skool_replied_posts.json"
REPLIED_COMMENTS_PATH = TMP_DIR / "skool_replied_comments.json"  # V2.1: comment reply state
ESCALATED_PATH = TMP_DIR / "skool_escalated.json"  # V2.1: posts/comments sent to CC's Telegram
DM_STATE_PATH = TMP_DIR / "skool_dm_state.json"
MEMBER_STATE_PATH = TMP_DIR / "skool_member_state.json"
DAEMON_PID_PATH = TMP_DIR / "skool_daemon.pid"
HEARTBEAT_PATH = TMP_DIR / "skool_daemon.heartbeat"

COMMUNITY_URL = "https://www.skool.com/agency-accelerants-6209"
ABOUT_URL = "https://www.skool.com/agency-accelerants-6209/about"

SKOOL_DISABLED = False  # Kill switch — set True to stop everything

# ===== DM KILL SWITCH — 2026-04-02 =====
# CC directive: DMs are DISABLED permanently. Only community post replies run.
# CC handles all DMs manually. DO NOT change this to False.
DM_DISABLED = True
# ========================================

COMMUNITY_FEED_URL = COMMUNITY_URL
MAX_REPLIES_PER_CYCLE = 5   # Max post replies per scan
MAX_DM_REPLIES_PER_CYCLE = 0  # DMs disabled — was 5

# V2.1 — Comment engagement tier
COMMENT_REPLIES_ENABLED = True          # Master switch for comment replies
MAX_COMMENT_REPLIES_PER_CYCLE = 8       # Max comment replies per full daemon cycle
MAX_COMMENT_REPLIES_PER_POST = 3        # Max comment replies on any one post per cycle
COMMENT_BRIEF_CHAR_LIMIT = 180          # Hard cap when CC already top-level commented

# Escalation signals — these phrases/conditions trigger a Telegram alert instead of auto-reply.
# Reason: Bravo should never auto-reply to a crisis, a hot lead, or a direct @-mention of CC.
# Those are moments that need CC's real voice, not a ghostwriter.
ESCALATION_KEYWORDS = [
    # Direct mentions of CC
    "@conaugh", "@cc", "@coach",
    # Explicit help / coaching asks
    "need help", "help me", "can anyone help", "stuck on", "don't know what to do",
    "quitting", "giving up", "burned out", "burning out", "can't do this",
    "about to quit",
    # Crisis / emotional
    "crisis", "emergency", "panic", "desperate",
    "angry", "furious", "losing it", "i'm done",
    # Money / account issues
    "refund", "cancel my membership", "want my money back", "want out",
    # Hot wins that deserve CC's personal note (not an auto-reply)
    "closed my first", "signed my first", "won my first", "just closed a",
    "got my first client", "first retainer", "big client",
    # Explicit asks to talk
    "dm me", "can we talk", "can we hop on a call", "can we jump on a call",
    "need a call",
]

# Exclusive lock file — prevents multiple daemon instances
LOCK_FILE_PATH = TMP_DIR / "skool_daemon.lock"


class DaemonLock:
    """Windows file lock using msvcrt.locking. Only ONE daemon can hold this."""

    def __init__(self):
        self._fh = None

    def acquire(self) -> bool:
        """Try to acquire exclusive lock. Returns True if successful."""
        os.makedirs(TMP_DIR, exist_ok=True)
        try:
            # Create file if needed, then open without truncating
            if not LOCK_FILE_PATH.exists():
                LOCK_FILE_PATH.write_text("")
            self._fh = open(LOCK_FILE_PATH, "r+b")
            # Write a byte so msvcrt has something to lock
            self._fh.write(b"\x00")
            self._fh.flush()
            self._fh.seek(0)
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except (OSError, IOError):
            if self._fh:
                try:
                    self._fh.close()
                except Exception:
                    pass
                self._fh = None
            return False

    def release(self):
        if self._fh:
            try:
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                self._fh.close()
            except Exception:
                pass
            self._fh = None
        LOCK_FILE_PATH.unlink(missing_ok=True)

# CC's availability for calls (Eastern Time)
CALL_AVAILABILITY = {
    "days": [0, 1, 2, 3, 4],  # Mon-Fri (0=Monday)
    "start_hour": 10,  # 10 AM ET
    "end_hour": 18,    # 6 PM ET
    "duration_minutes": 30,
    "timezone": "America/Toronto",
    "buffer_minutes": 15,  # Buffer between events
}

sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from notify import notify
except ImportError:
    def notify(*a, **kw):
        return False


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = LOG_DIR / f"skool_{datetime.now().strftime('%Y-%m-%d')}.log"
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setStream(
        open(sys.stdout.fileno(), mode="w", encoding="utf-8", closefd=False)
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            stdout_handler,
        ],
    )
    return logging.getLogger("skool")


log = setup_logging()


# ---------------------------------------------------------------------------
# Env / State helpers
# ---------------------------------------------------------------------------

def _read_config_model(key: str, fallback: str) -> str:
    """Read a model name from .agents/config.toml. Falls back to hardcoded default."""
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


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_json(path: Path, data: dict):
    os.makedirs(path.parent, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))


# ---------------------------------------------------------------------------
# Browser context + login
# ---------------------------------------------------------------------------

def get_browser_context(playwright):
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


def _auto_login(page) -> bool:
    env = load_env()
    email = env.get("SKOOL_EMAIL", "")
    password = env.get("SKOOL_PASSWORD", "")
    if not email or not password:
        log.warning("No SKOOL_EMAIL/SKOOL_PASSWORD in .env.agents")
        return False

    log.info(f"Auto-login attempt as {email}...")
    page.goto("https://www.skool.com/login", wait_until="networkidle", timeout=60000)
    time.sleep(4)

    try:
        page.locator("#email").click()
        page.locator("#email").fill(email)
        time.sleep(0.5)
        page.locator("#password").click()
        page.locator("#password").fill(password)
        time.sleep(1)
        page.locator('button[type="submit"]').click()

        for _ in range(15):
            time.sleep(1)
            if page.locator("#email").count() == 0:
                log.info("Auto-login successful")
                return True

        log.error("Auto-login failed — login form still present")
        return False
    except Exception as e:
        log.error(f"Auto-login error: {e}")
        return False


def is_logged_in(page) -> bool:
    page.goto(COMMUNITY_FEED_URL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)

    if "/login" in page.url or "/signup" in page.url:
        return _auto_login(page)

    is_authed = page.evaluate("""() => {
        const btns = [...document.querySelectorAll('button, a')];
        for (const b of btns) {
            const t = b.textContent.trim();
            if (t === 'Log In' || t === 'Sign Up') return false;
        }
        return !!(document.querySelector('[class*="PostItem"]') ||
                  document.querySelector('[class*="PostList"]') ||
                  document.querySelectorAll('a[href*="/classroom"]').length > 0);
    }""")

    if not is_authed:
        log.info("Session expired — attempting auto-login...")
        return _auto_login(page)

    return True


# ---------------------------------------------------------------------------
# Claude API
# ---------------------------------------------------------------------------

def _call_claude_vision(system_prompt: str, user_msg: str, image_data: list = None, max_tokens: int = 300) -> str:
    """Call Claude with optional image attachments (base64-encoded)."""
    try:
        import anthropic
    except ImportError:
        log.error("anthropic package not installed")
        return ""

    env_vars = load_env()
    api_key = env_vars.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log.error("ANTHROPIC_API_KEY not found in .env.agents")
        return ""

    try:
        client = anthropic.Anthropic(api_key=api_key)

        # Build content blocks: text + images
        content = []
        if image_data:
            for img in image_data:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.get("media_type", "image/png"),
                        "data": img["data"],
                    }
                })
            content.append({"type": "text", "text": user_msg})
        else:
            content = user_msg

        response = client.messages.create(
            model=_read_config_model("fast_model", "claude-sonnet-4-6"),
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
        )
        reply = response.content[0].text.strip()
        if (reply.startswith('"') and reply.endswith('"')) or \
           (reply.startswith("'") and reply.endswith("'")):
            reply = reply[1:-1]
        return reply
    except Exception as e:
        log.error(f"Claude vision call failed: {e}")
        return ""


def _call_claude(system_prompt: str, user_msg: str, max_tokens: int = 300) -> str:
    try:
        import anthropic
    except ImportError:
        log.error("anthropic package not installed")
        return ""

    env_vars = load_env()
    api_key = env_vars.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log.error("ANTHROPIC_API_KEY not found in .env.agents")
        return ""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=_read_config_model("fast_model", "claude-sonnet-4-6"),
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        reply = response.content[0].text.strip()
        if (reply.startswith('"') and reply.endswith('"')) or \
           (reply.startswith("'") and reply.endswith("'")):
            reply = reply[1:-1]
        return reply
    except Exception as e:
        log.error(f"Claude API call failed: {e}")
        return ""


def _strip_ai_slop(text: str) -> str:
    text = text.replace("\u2014", ",")
    text = text.replace("\u2013", ",")
    text = text.replace(" ,", ",")
    text = text.replace(",,", ",")
    return text


def _strip_pricing_language(text: str) -> str:
    """Hard filter: remove ANY pricing, upsell, dollar-amount, or fabricated URL language.

    Applied to ALL DM replies regardless of paid/free status.
    The bot should NEVER mention specific prices, upsell, or invent links.
    """
    # Remove sentences containing dollar amounts ($XX, $XXX, $X,XXX)
    text = re.sub(r'[^.!?\n]*\$\d[\d,]*[^.!?\n]*[.!?]?\s*', '', text)
    # Remove sentences mentioning price/pricing/upgrade/upsell keywords
    text = re.sub(
        r'[^.!?\n]*\b(price\s+(?:jumps?|goes?\s+up|is\s+going\s+up|increase|rising|changing)|'
        r'prices?\s+(?:increase|go\s+up|going\s+up|will\s+go)|'
        r'lock(?:ed|ing)?\s+(?:you\s+)?in|upgrad(?:e|ing|ed)|upsell|'
        r'before\s+(?:the\s+)?price|current\s+price|special\s+(?:price|offer|deal)|'
        r'limited\s+time|act\s+(?:fast|now|quickly)|hurry|'
        r'now.s\s+a\s+good\s+time|good\s+time\s+to\s+(?:jump|join|get)|'
        r'paid\s+(?:plan|tier|membership)|join\s+(?:the\s+)?paid)\b[^.!?\n]*[.!?]?\s*',
        '', text, flags=re.IGNORECASE
    )
    # Remove sentences containing Calendly links (hallucinated)
    text = re.sub(r'[^.!?\n]*calendly\.com[^.!?\n]*[.!?]?\s*', '', text, flags=re.IGNORECASE)
    # Remove any fabricated URLs that aren't Google Meet links
    # (Google Meet links are real — they come from the booking system)
    text = re.sub(
        r'[^.!?\n]*(?:https?://(?!meet\.google\.com)\S+)[^.!?\n]*[.!?]?\s*',
        '', text, flags=re.IGNORECASE
    )
    # Clean up leftover whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


# ---------------------------------------------------------------------------
# Member status detection
# ---------------------------------------------------------------------------

def check_member_status(page, member_slug: str) -> dict:
    """Visit a member's Skool profile and detect paid vs free status.

    Returns: {"is_paid": bool, "level": str, "name": str}

    On Skool, paid members show a level badge (Level 1+) and have access
    indicators. Free members show Level 0 or no level badge.
    We also check our local member_state.json as a cache.
    """
    # Check local cache first
    member_state = _load_json(MEMBER_STATE_PATH)
    if member_slug in member_state:
        cached = member_state[member_slug]
        return {
            "is_paid": cached.get("is_paid", False),
            "level": cached.get("level", "unknown"),
            "name": cached.get("name", member_slug),
        }

    # Visit profile page to scrape status
    profile_url = f"https://www.skool.com/agency-accelerants-6209/@{member_slug}"
    try:
        page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        info = page.evaluate("""() => {
            const body = document.body.textContent || '';
            // Look for level indicator — paid members have Level 1+
            const levelMatch = body.match(/Level\\s+(\\d+)/i);
            const level = levelMatch ? parseInt(levelMatch[1]) : 0;

            // Get display name
            const nameEl = document.querySelector('h1, [class*="ProfileName"]');
            const name = nameEl ? nameEl.textContent.trim() : '';

            // Check for paid indicators
            const isPaid = level >= 1;

            return { level: level, name: name, is_paid: isPaid };
        }""")

        # Cache the result
        member_state[member_slug] = {
            "name": info.get("name", member_slug),
            "is_paid": info.get("is_paid", False),
            "level": str(info.get("level", 0)),
            "checked_at": _now(),
        }
        _save_json(MEMBER_STATE_PATH, member_state)

        log.info(f"Member {member_slug}: paid={info.get('is_paid')}, level={info.get('level')}")
        return info

    except Exception as e:
        log.error(f"Failed to check member status for {member_slug}: {e}")
        return {"is_paid": True, "level": "unknown", "name": member_slug}


# ---------------------------------------------------------------------------
# Google Calendar integration
# ---------------------------------------------------------------------------

def _run_google_tool(args: list, timeout: int = 30) -> str:
    """Run google_tool.py and return stdout."""
    cmd = [sys.executable, str(SCRIPTS_DIR / "google_tool.py")] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            timeout=timeout, cwd=str(PROJECT_ROOT),
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
        return result.stdout.strip()
    except Exception as e:
        log.error(f"google_tool.py failed: {e}")
        return ""


def get_calendar_events(days_ahead: int = 7) -> list:
    """Fetch upcoming calendar events as JSON."""
    output = _run_google_tool(["calendar", "list", "--json"])
    if not output:
        return []
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return []


def find_available_slot() -> dict | None:
    """Find the next available 30-minute slot on CC's calendar.

    Returns: {"start": ISO datetime, "end": ISO datetime} or None
    """
    events = get_calendar_events(days_ahead=7)
    avail = CALL_AVAILABILITY
    duration = timedelta(minutes=avail["duration_minutes"])
    buffer = timedelta(minutes=avail["buffer_minutes"])

    # Build list of busy periods from calendar
    busy_periods = []
    for ev in events:
        start_info = ev.get("start", {})
        end_info = ev.get("end", {})
        start_str = start_info.get("dateTime", start_info.get("date", ""))
        end_str = end_info.get("dateTime", end_info.get("date", ""))
        if start_str and end_str:
            try:
                busy_start = datetime.fromisoformat(start_str)
                busy_end = datetime.fromisoformat(end_str)
                busy_periods.append((busy_start, busy_end))
            except ValueError:
                continue

    busy_periods.sort(key=lambda x: x[0])

    # Try each day for the next 7 days
    now = datetime.now().astimezone()
    for day_offset in range(7):
        check_date = now.date() + timedelta(days=day_offset)

        # Skip weekends
        if check_date.weekday() not in avail["days"]:
            continue

        # Build candidate slots for this day
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(avail["timezone"])
        day_start = datetime(
            check_date.year, check_date.month, check_date.day,
            avail["start_hour"], 0, 0, tzinfo=tz
        )
        day_end = datetime(
            check_date.year, check_date.month, check_date.day,
            avail["end_hour"], 0, 0, tzinfo=tz
        )

        # Don't offer past slots
        if day_offset == 0:
            # Round up to next 30-min boundary + buffer
            earliest = now + buffer
            minutes = earliest.minute
            if minutes % 30 != 0:
                earliest = earliest.replace(
                    minute=(minutes // 30 + 1) * 30 % 60,
                    second=0, microsecond=0
                )
                if (minutes // 30 + 1) * 30 >= 60:
                    earliest += timedelta(hours=1)
                    earliest = earliest.replace(minute=0)
            day_start = max(day_start, earliest)

        # Try each 30-min slot
        slot_start = day_start
        while slot_start + duration <= day_end:
            slot_end = slot_start + duration

            # Check if this slot conflicts with any busy period
            conflict = False
            for busy_start, busy_end in busy_periods:
                # Add buffer around existing events
                if slot_start < (busy_end + buffer) and slot_end > (busy_start - buffer):
                    conflict = True
                    break

            if not conflict:
                return {
                    "start": slot_start.isoformat(),
                    "end": slot_end.isoformat(),
                    "display": slot_start.strftime("%A %B %d at %I:%M %p ET"),
                }

            slot_start += timedelta(minutes=30)

    return None


def book_meeting(member_name: str, member_email: str = "") -> dict:
    """Book a 30-min Google Meet on CC's calendar.

    Returns: {"success": bool, "meet_link": str, "display_time": str, "error": str}
    """
    slot = find_available_slot()
    if not slot:
        return {
            "success": False,
            "meet_link": "",
            "display_time": "",
            "error": "No available slots in the next 7 days",
        }

    title = f"Skool Call — {member_name}"
    description = (
        f"30-minute call with {member_name} from the prior community Skool community.\n"
        f"Booked automatically by Bravo."
    )

    args = [
        "calendar", "create",
        "--title", title,
        "--start", slot["start"],
        "--end", slot["end"],
        "--meet",
        "--description", description,
        "--timezone", CALL_AVAILABILITY["timezone"],
        "--json",
    ]
    if member_email:
        args.extend(["--attendees", member_email])

    output = _run_google_tool(args, timeout=30)

    if not output:
        return {
            "success": False,
            "meet_link": "",
            "display_time": slot["display"],
            "error": "Failed to create calendar event",
        }

    try:
        event_data = json.loads(output)
        meet_link = event_data.get("hangoutLink", "")
        if not meet_link:
            conf = event_data.get("conferenceData", {})
            for ep in conf.get("entryPoints", []):
                if ep.get("entryPointType") == "video":
                    meet_link = ep.get("uri", "")
                    break
    except json.JSONDecodeError:
        # Non-JSON output — try to extract meet link
        meet_match = re.search(r"https://meet\.google\.com/[\w-]+", output)
        meet_link = meet_match.group(0) if meet_match else ""

    log.info(f"Booked meeting: {title} at {slot['display']} — {meet_link}")
    notify(f"Skool call booked: {member_name} at {slot['display']}", category="booking")

    return {
        "success": True,
        "meet_link": meet_link,
        "display_time": slot["display"],
        "error": "",
    }


# ---------------------------------------------------------------------------
# DM response generation
# ---------------------------------------------------------------------------

def _detect_booking_intent(message: str) -> bool:
    """Check if a DM message is asking to book a call."""
    booking_keywords = [
        r"\bcall\b", r"\bmeeting\b",
        r"\bbook\b", r"\bschedule\b", r"\b1[:\-]1\b",
        r"\bone.on.one\b", r"\bhopping on\b", r"\bjump on\b",
        r"\bset up a call\b", r"\bsetup a call\b", r"\btime to talk\b",
        r"\bcan we talk\b", r"\bwanna talk\b", r"\bwant to talk\b",
        r"\bshow you more\b", r"\bshow u more\b",
        r"\blet'?s connect\b", r"\blets connect\b",
        r"\bjump on a.{0,10}(call|chat|meet)\b",
        r"\bdo a call\b", r"\bhop on a call\b",
    ]
    msg_lower = message.lower()
    return any(re.search(kw, msg_lower) for kw in booking_keywords)


def generate_dm_reply(
    member_name: str,
    member_message: str,
    conversation_history: str,
    is_paid: bool,
    booking_result: dict | None = None,
) -> str:
    """Generate a DM reply using Claude. Tone-adaptive based on the query."""

    # Build context about booking if applicable
    booking_context = ""
    if booking_result:
        if booking_result["success"]:
            booking_context = (
                f"\nIMPORTANT: A call has been booked for this member. Details:\n"
                f"- Time: {booking_result['display_time']}\n"
                f"- Google Meet link: {booking_result['meet_link']}\n"
                f"Include these details naturally in your reply. "
                f"Make it feel seamless, not robotic.\n"
            )
        else:
            booking_context = (
                f"\nThe member asked for a call but no slots are available: "
                f"{booking_result['error']}. Let them know CC will reach out "
                f"personally to find a time.\n"
            )

    # Paid status context
    paid_context = (
        "This member is a PAID member. "
        "They are already fully invested. Treat them as a valued insider."
        if is_paid
        else "This member is on the FREE tier. "
        "Do NOT mention pricing or plans unless they explicitly ask how to upgrade."
    )

    system = (
        "You are ghostwriting a Skool DM as Conaugh McKenna (CC), "
        "a 22-year-old AI automation entrepreneur and admin of the the prior community "
        "Skool community. CC runs OASIS AI Solutions.\n\n"
        "HARD RULES (violation = failure — these override everything):\n"
        "1. NEVER mention dollar amounts, prices, plans, upgrades, upsells, discounts, "
        "deals, or anything about cost/payment/pricing. No exceptions.\n"
        "2. NEVER mention or link to Calendly, calendly.com, or any scheduling tool. "
        "If a call was booked, the booking details are provided below. Use ONLY those.\n"
        "3. NEVER invent URLs, links, or information. Only reference info given in this prompt.\n"
        "4. NEVER use em dashes (—). Use commas, periods, or new sentences instead.\n"
        "5. NEVER use emojis except a single thumbs up or fire occasionally.\n"
        "6. Output must be a SINGLE message. No line breaks. Everything on one line.\n\n"
        f"MEMBER STATUS: {paid_context}\n"
        f"{booking_context}\n"
        "SITUATION HANDLING:\n"
        "- Technical question: be helpful, give a clear next step.\n"
        "- Frustrated or venting: listen, validate their feelings, show you care. "
        "Ask what specifically went wrong so you can help fix it.\n"
        "- Wants to cancel or refund: DO NOT give refund instructions. Instead, "
        "ask what's not working for them. Show empathy. Offer to hop on a call "
        "to work through it together. Make them feel heard and valued. Your goal "
        "is to understand their frustration and help solve their problem.\n"
        "- Excited or sharing a win: match their energy, celebrate, push them forward.\n"
        "- Booking a call: confirm the details from the booking info provided.\n"
        "- Payment timing: just acknowledge, be supportive, no pressure.\n\n"
        "VOICE:\n"
        "- Text like a friend. Casual, lowercase fine, short sentences.\n"
        "- 2-4 sentences max, all on one line. No paragraphs.\n"
        "- Use their first name. Be genuine. Sound like an equal.\n\n"
        "Reply with ONLY the message text. No quotes. No line breaks."
    )

    user = (
        f"Member: {member_name}\n"
        f"Their message: {member_message}\n"
    )
    if conversation_history:
        user = (
            f"Member: {member_name}\n"
            f"Recent conversation:\n{conversation_history[-800:]}\n\n"
            f"Their latest message: {member_message}\n"
        )

    reply = _call_claude(system, user, max_tokens=250)
    if reply:
        reply = _strip_ai_slop(reply)
        reply = _strip_pricing_language(reply)
    return reply[:1000] if reply else ""


# ---------------------------------------------------------------------------
# Web research for informed replies
# ---------------------------------------------------------------------------

def _web_search(query: str, max_results: int = 3) -> str:
    """Search the web via DuckDuckGo and return a brief summary of results."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return ""
        snippets = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            snippets.append(f"- {title}: {body[:200]}")
        return "\n".join(snippets)
    except Exception as e:
        log.warning(f"Web search failed for '{query}': {e}")
        return ""


def _identify_research_topics(post_title: str, post_content: str) -> list[str]:
    """Use Claude to identify specific tools, products, or concepts in a post that need research."""
    system = (
        "You analyze Skool community posts to identify specific tools, products, frameworks, "
        "companies, methodologies, or technical concepts mentioned that would benefit from a "
        "quick web search to ensure an informed reply.\n\n"
        "Rules:\n"
        "- Only return terms that are SPECIFIC (named tools, products, frameworks, people)\n"
        "- Do NOT return generic terms like 'AI', 'automation', 'business'\n"
        "- Return 0-3 search queries, one per line\n"
        "- If the post only discusses common/generic topics, return NONE\n"
        "- Each query should be a concise web search query (3-6 words)\n"
        "- Return ONLY the search queries, nothing else"
    )
    user = f"Post title: {post_title}\nPost content: {post_content[:600]}"
    result = _call_claude(system, user, max_tokens=100)
    if not result or result.strip().upper() == "NONE":
        return []
    queries = [q.strip().lstrip("- ").strip() for q in result.strip().split("\n") if q.strip() and q.strip().upper() != "NONE"]
    return queries[:3]


def _research_post(post_title: str, post_content: str) -> str:
    """Research any specific topics mentioned in a post before replying."""
    topics = _identify_research_topics(post_title, post_content)
    if not topics:
        return ""

    log.info(f"  Researching {len(topics)} topic(s): {topics}")
    research_parts = []
    for query in topics:
        result = _web_search(query)
        if result:
            research_parts.append(f"Research on '{query}':\n{result}")

    return "\n\n".join(research_parts) if research_parts else ""


# ---------------------------------------------------------------------------
# Post reply generation (V2 — research-enhanced)
# ---------------------------------------------------------------------------

def _capture_post_images(page, max_images: int = 3) -> list:
    """Capture images from the current post page as base64 for Claude vision."""
    import base64
    images = []
    try:
        # Find all images in the post content area
        img_elements = page.query_selector_all('img[src*="skool"], img[src*="amazonaws"], img[src*="cloudfront"], img[src*="uploads"]')

        # Also check for images in the main content area
        if not img_elements:
            img_elements = page.query_selector_all('[class*="PostContent"] img, [class*="Content"] img, .ProseMirror img')

        for img_el in img_elements[:max_images]:
            try:
                # Screenshot the image element directly
                img_bytes = img_el.screenshot(timeout=5000)
                if img_bytes and len(img_bytes) > 500:  # Skip tiny/broken images
                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                    images.append({"data": b64, "media_type": "image/png"})
                    log.info(f"  Captured image ({len(img_bytes)} bytes)")
            except Exception as e:
                log.debug(f"  Image capture failed: {e}")
    except Exception as e:
        log.debug(f"Image extraction failed: {e}")
    return images


def generate_post_reply(post_title: str, post_content: str, author_name: str, images: list = None) -> str:
    # Step 1: Research any specific topics mentioned in the post
    research_context = _research_post(post_title, post_content)

    system = (
        "You are ghostwriting a Skool community comment as Conaugh McKenna (CC), "
        "a 22-year-old AI automation entrepreneur and admin/coach of the the prior community community. "
        "CC runs OASIS AI Solutions. He builds AI agent systems for local businesses and has closed "
        "$30k+ deals. He's a real mentor who wants every member to succeed.\n\n"
        "PERSONALITY:\n"
        "- You are CONSTRUCTIVE and PROGRESSIVE. You build people up while pushing them forward.\n"
        "- If someone shares work (screenshots, code, websites), acknowledge what they built first, then suggest improvements.\n"
        "- If someone is early stage or learning, meet them where they are. Encourage the effort, guide the direction.\n"
        "- If someone posts something incomplete, ask clarifying questions instead of dismissing it.\n"
        "- Give specific, actionable next steps. Not vague advice.\n"
        "- You're direct but never condescending. You remember what it felt like to start.\n"
        "- You genuinely care about each person's progress.\n\n"
        "IMAGE HANDLING:\n"
        "- If images are attached, LOOK AT THEM CAREFULLY. Describe what you see and respond to the actual content.\n"
        "- Screenshots of code, websites, dashboards, tools = comment on the specific work shown.\n"
        "- If an image is unclear or broken, say something like 'the image didn't load fully on my end, can you drop the link or repost it?'\n"
        "- NEVER ignore images. NEVER respond as if you can't see them when they're provided.\n\n"
        "KNOWLEDGE RULES:\n"
        "- NEVER say 'I don't know' or admit ignorance. CC stays on top of every tool and trend.\n"
        "- If research context is provided, USE IT.\n"
        "- Connect topics back to practical AI automation, business systems, or execution.\n\n"
        "VOICE RULES:\n"
        "- Write like a real person texting. Casual, lowercase is fine, short sentences.\n"
        "- 2-4 sentences max. No essays.\n"
        "- NEVER use em dashes. Use commas, periods, or new sentences.\n"
        "- NEVER use hashtags. NEVER pitch services.\n"
        "- Avoid generic phrases like 'great question', 'love this', 'absolutely'.\n"
        "- Use first name. Sound like a supportive friend who also pushes you to level up.\n\n"
        "Reply with ONLY the comment text. No quotes around it."
    )

    user_parts = [
        f"Community member {author_name} posted:",
        f"Title: {post_title}",
    ]

    if post_content.strip():
        user_parts.append(f"Content: {post_content[:800]}")
    else:
        user_parts.append("Content: (no text, check the images)")

    if images:
        user_parts.append(f"\n[{len(images)} image(s) attached — LOOK AT THEM and respond to what you see]")

    if research_context:
        user_parts.append(f"\n--- RESEARCH CONTEXT ---\n{research_context[:1200]}")
    user_parts.append("\nWrite a constructive reply:")

    user = "\n".join(user_parts)

    # Use vision API if images are present, regular API otherwise
    if images:
        reply = _call_claude_vision(system, user, image_data=images, max_tokens=250)
    else:
        reply = _call_claude(system, user, max_tokens=250)

    if reply:
        reply = _strip_ai_slop(reply)
    return reply[:1000] if reply else ""


# ---------------------------------------------------------------------------
# V2.1 — Comment-tier engagement helpers
# ---------------------------------------------------------------------------

def _needs_coach_attention(title: str, content: str, author: str = "") -> tuple[bool, str]:
    """Rule-based check: does this post/comment need CC's personal attention instead of auto-reply?

    Returns (needs_attention, reason). Errs on the side of escalation — a false positive
    costs one Telegram ping; a false negative costs trust with the community.
    """
    # Never escalate moderators' own posts/comments to themselves.
    author_lower = (author or "").lower()
    if "conaugh" in author_lower or author_lower == "cc" or "primary_retainer" in author_lower:
        return False, ""

    text = f"{title} {content}".lower()
    for kw in ESCALATION_KEYWORDS:
        if kw in text:
            return True, f"keyword: '{kw}'"
    # Long emotional content (>600 chars) with question marks is often a venting post
    if len(content) > 600 and content.count("?") >= 3:
        return True, "long venting post w/ multiple questions"
    return False, ""


def _escalate_to_cc(post_url: str, author: str, snippet: str, reason: str, kind: str = "post"):
    """Send a Telegram alert to CC via notify() — do NOT auto-reply to this item."""
    try:
        msg = (
            f"[Skool — coach attention] {kind} by {author}\n"
            f"Reason: {reason}\n"
            f"Excerpt: {snippet[:160]}...\n"
            f"Link: {post_url}"
        )
        notify(msg, category="skool-escalation")
    except Exception as e:
        log.warning(f"Escalation notify failed: {e}")

    try:
        escalated = _load_json(ESCALATED_PATH)
        key = f"{kind}:{post_url}:{author}"
        escalated[key] = {"reason": reason, "ts": _now(), "snippet": snippet[:200]}
        _save_json(ESCALATED_PATH, escalated)
    except Exception as e:
        log.warning(f"Escalation log failed: {e}")


def _extract_comments_on_post(page) -> list:
    """Extract the comment list on the currently loaded post page.

    Returns a list of dicts: [{idx, author, content, is_cc, is_primary_retainer}, ...]
    Resilient to selector drift — tries multiple strategies. Degrades to empty list
    on failure (never raises).
    """
    try:
        comments = page.evaluate(r"""() => {
            // Try multiple comment wrapper selector patterns (Skool changes these periodically)
            const selectors = [
                '[class*="CommentItem"]',
                '[class*="Comment-sc-"]',
                '[class*="commentWrapper"]',
                'div[data-comment-id]',
                '[class*="CommentThread"] > div',
            ];

            let wrappers = [];
            for (const sel of selectors) {
                const found = document.querySelectorAll(sel);
                if (found.length > 0) {
                    wrappers = Array.from(found);
                    break;
                }
            }
            if (!wrappers.length) return [];

            const results = [];
            let idx = 0;
            for (const w of wrappers) {
                idx++;

                // Author
                const authorLink = w.querySelector('a[href*="/@"]');
                const author = authorLink ? (authorLink.textContent || '').trim() : '';
                if (!author) continue;

                // Content — try several selectors
                const contentSels = [
                    '[class*="CommentContent"]',
                    '[class*="CommentBody"]',
                    '[class*="CommentText"]',
                    '.ProseMirror',
                    '[class*="Content"]',
                ];
                let content = '';
                for (const cs of contentSels) {
                    const el = w.querySelector(cs);
                    if (el && (el.textContent || '').trim().length > 3) {
                        content = (el.textContent || '').trim();
                        break;
                    }
                }
                if (!content || content.length < 5) continue;

                // Skip items that are the comment composer itself
                if (content.toLowerCase().includes('write a comment')) continue;

                // V2.1 2026-04-11: Tight is_cc matching — old code used
                // .includes('conaugh') which false-matched names like
                // "CC Funnel Bot" or "Conaugh's Assistant". Now we match:
                //   - exact 'cc' / 'conaugh' (case-insensitive, trimmed)
                //   - 'conaugh mckenna' (full name)
                //   - name starting with 'conaugh ' (word boundary)
                // Nothing else. Members named "CC Funnel Bot" are treated
                // as regular members who can receive engagement.
                const authorTrimmed = (author || '').trim().toLowerCase();
                const isCC = (
                    authorTrimmed === 'cc'
                    || authorTrimmed === 'conaugh'
                    || authorTrimmed === 'conaugh mckenna'
                    || authorTrimmed.startsWith('conaugh ')
                );
                const isprimary retainer = (
                    authorTrimmed === 'primary_retainer'
                    || authorTrimmed === 'primary_retainer spooner'
                    || authorTrimmed.startsWith('primary_retainer ')
                );

                results.push({
                    idx: idx,
                    author: author,
                    content: content.substring(0, 500),
                    is_cc: isCC,
                    is_primary_retainer: isprimary retainer,
                });
            }
            return results;
        }""")
        return comments or []
    except Exception as e:
        log.warning(f"Failed to extract comments: {e}")
        return []


def generate_comment_reply(
    post_title: str,
    post_content: str,
    comment_text: str,
    comment_author: str,
    cc_commented_on_parent: bool,
) -> str:
    """Generate a reply to a community member's comment.

    If cc_commented_on_parent=True, the reply is BRIEF (<=180 chars) and complementary —
    Bravo never steps on CC's coaching voice when CC has already weighed in on the post.
    Otherwise, full coaching-voice response (2-4 sentences).
    """
    if cc_commented_on_parent:
        length_rule = (
            "CRITICAL CONSTRAINT: CC (Conaugh McKenna) has ALREADY left a top-level comment "
            "on this post. Your reply must be BRIEF (absolute max 180 characters, ideally 120), "
            "complementary to CC's voice, and NEVER restate or contradict what a coach would say. "
            "You are a supportive second voice — a quick validating ack, a tactical micro-observation, "
            "or an encouraging nod. Do NOT give full coaching advice — that is CC's lane on this post. "
            "Examples of good brief replies:\n"
            "- 'This. The messaging reframe is 80% of it.'\n"
            "- 'Agreed — tested this myself last month and the response rate doubled.'\n"
            "- 'The discovery question in step 2 is the unlock for me.'"
        )
        max_tokens = 80
    else:
        length_rule = (
            "Write a constructive, specific reply in 2 to 4 sentences. Reference the specific thing "
            "the commenter said. Coaching voice: direct, honest, no hype. If they asked a question, "
            "answer it concretely. If they shared a win, acknowledge the specific thing they did right. "
            "If they shared a problem, offer one concrete next step."
        )
        max_tokens = 200

    system = (
        "You are ghostwriting a Skool community COMMENT REPLY as Conaugh McKenna (CC), founder of "
        "OASIS AI Solutions and head coach of the the prior community community. The community is "
        "for people building AI automation agencies.\n\n"
        "Voice rules:\n"
        "- Direct, specific, no hype language ('game-changer', 'revolutionary', 'unlock the power')\n"
        "- Never preachy — no 'you should'\n"
        "- First person when relevant, conversational\n"
        "- Never mention pricing or promote OASIS services\n"
        "- Never admit ignorance — if you don't know a specific tool, pivot to broader principles\n\n"
        f"{length_rule}\n\n"
        "Output ONLY the reply text. No quotes, no line breaks, no preamble."
    )

    user = (
        f"ORIGINAL POST TITLE: {post_title}\n"
        f"ORIGINAL POST (excerpt): {post_content[:400]}\n\n"
        f"COMMENT by {comment_author}:\n{comment_text[:400]}\n\n"
        f"Write the reply now:"
    )

    reply = _call_claude(system, user, max_tokens=max_tokens)
    if not reply:
        return ""

    reply = _strip_ai_slop(reply)
    reply = _strip_pricing_language(reply)

    # Hard enforce brevity when CC already commented
    if cc_commented_on_parent and len(reply) > COMMENT_BRIEF_CHAR_LIMIT:
        trimmed = reply[:COMMENT_BRIEF_CHAR_LIMIT]
        # Cut at last sentence or word boundary
        for end in ('. ', '? ', '! '):
            if end in trimmed:
                trimmed = trimmed.rsplit(end, 1)[0] + end.strip()
                break
        else:
            trimmed = trimmed.rsplit(' ', 1)[0] + '.'
        reply = trimmed

    return reply[:500]


def _type_and_submit_reply_to_comment(page, comment_idx: int, text: str) -> bool:
    """Click the Reply button on the comment at position `comment_idx` (1-based) and submit text.

    Reuses the same selector strategy as _extract_comments_on_post to stay consistent.
    Returns True on success, False on any failure (never raises).
    """
    try:
        click_result = page.evaluate(r"""(idx) => {
            const selectors = [
                '[class*="CommentItem"]',
                '[class*="Comment-sc-"]',
                '[class*="commentWrapper"]',
                'div[data-comment-id]',
                '[class*="CommentThread"] > div',
            ];
            let wrappers = [];
            for (const sel of selectors) {
                const found = document.querySelectorAll(sel);
                if (found.length > 0) {
                    wrappers = Array.from(found);
                    break;
                }
            }
            if (!wrappers.length || wrappers.length < idx) return 'no_wrapper';

            const w = wrappers[idx - 1];
            // Scroll into view so Skool renders the reply affordances
            w.scrollIntoView({ block: 'center' });

            const clickables = w.querySelectorAll('button, a, span[role="button"]');
            for (const b of clickables) {
                const t = (b.textContent || '').trim().toLowerCase();
                if (t === 'reply' || t === 'respond') {
                    b.click();
                    return 'clicked';
                }
            }
            return 'no_button';
        }""", comment_idx)

        if click_result != 'clicked':
            log.warning(f"  Comment {comment_idx}: reply click failed ({click_result})")
            return False

        time.sleep(1.5)

        # Focus the editor that just opened — prefer the last visible editable ProseMirror
        focused = page.evaluate("""() => {
            const editors = document.querySelectorAll('.ProseMirror[contenteditable="true"]');
            const visible = Array.from(editors).filter(e => {
                const r = e.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            });
            if (!visible.length) return false;
            const target = visible[visible.length - 1];
            target.click();
            return true;
        }""")
        if not focused:
            log.warning(f"  Comment {comment_idx}: reply editor not found after click")
            return False

        time.sleep(0.5)
        page.keyboard.type(text, delay=12)
        time.sleep(1)

        submitted = page.evaluate("""() => {
            const btns = [...document.querySelectorAll('button')];
            for (const btn of btns) {
                const txt = (btn.textContent || '').trim().toLowerCase();
                if ((txt === 'reply' || txt === 'comment' || txt === 'post' || txt === 'send')
                    && !btn.disabled) {
                    btn.click();
                    return 'clicked';
                }
            }
            return 'no_button';
        }""")

        if submitted == 'no_button':
            page.keyboard.press('Control+Enter')

        time.sleep(2)
        return True
    except Exception as e:
        log.error(f"  Comment {comment_idx}: submission failed: {e}")
        return False


def _process_post_comments(
    page,
    post_slug: str,
    post_title: str,
    post_content: str,
    cc_commented_on_parent: bool,
    replied_comments: dict,
    global_comment_budget: int,
    dry_run: bool,
) -> tuple[int, int, list]:
    """Scan the comment section on the currently-loaded post page and reply where appropriate.

    Returns (replies_posted, errors_count, escalations_list).
    Mutates `replied_comments` in place. Respects both per-post and global budgets.

    V2.1 2026-04-11: Page health check before extraction. If Playwright lost
    the post page (500 error, network glitch), retry once with a page.reload
    before giving up. Budget is now checked per-comment, not per-post, so an
    exception mid-iteration can't accidentally bypass the cap.
    """
    if not COMMENT_REPLIES_ENABLED:
        return 0, 0, []

    if global_comment_budget <= 0:
        return 0, 0, []

    # Page health check — verify the post page is still loaded
    try:
        page_ok = page.evaluate("""() => {
            const body = document.body;
            if (!body) return 'no_body';
            const text = body.innerText || '';
            if (text.length < 50) return 'empty';
            if (text.includes('Something went wrong')
                || text.includes('Page not found')
                || text.includes('500')) return 'error_page';
            return 'ok';
        }""")
    except Exception as e:
        log.warning(f"  Page health check failed for {post_slug}: {e}")
        page_ok = 'exception'

    if page_ok != 'ok':
        log.warning(f"  Page unhealthy ({page_ok}) for {post_slug} — attempting reload")
        try:
            page.reload(wait_until='domcontentloaded', timeout=30000)
            time.sleep(3)
        except Exception as e:
            log.error(f"  Reload failed for {post_slug}: {e} — skipping comment tier")
            return 0, 1, []

    comments = _extract_comments_on_post(page)
    if not comments:
        log.info(f"  No comments extracted for {post_slug}")
        return 0, 0, []

    log.info(f"  Found {len(comments)} comment(s) on {post_slug}")

    posted = 0
    errors = 0
    escalations = []

    for c in comments:
        # V2.1 fix: check both caps BEFORE each comment reply (not at loop
        # start) so the global budget is honored even if an exception
        # short-circuits the normal decrement flow.
        if posted >= MAX_COMMENT_REPLIES_PER_POST:
            break
        if posted >= global_comment_budget:
            break

        author = c.get("author", "")
        content = c.get("content", "")
        idx = c.get("idx", 0)

        # Never reply to CC, primary retainer, or empty comments
        if c.get("is_cc") or c.get("is_primary_retainer"):
            continue
        if not content or not author:
            continue

        comment_key = f"{post_slug}::{idx}::{author}::{content[:40]}"
        if comment_key in replied_comments:
            continue

        # Escalation check — if this comment deserves CC's personal attention, ping Telegram and skip auto-reply
        needs_coach, reason = _needs_coach_attention(post_title, content, author)
        if needs_coach:
            post_url = f"https://www.skool.com/agency-accelerants-6209/{post_slug}"
            _escalate_to_cc(post_url, author, content, reason, kind="comment")
            escalations.append({"slug": post_slug, "author": author, "reason": reason})
            replied_comments[comment_key] = {
                "escalated": True,
                "reason": reason,
                "ts": _now(),
            }
            continue

        try:
            reply_text = generate_comment_reply(
                post_title=post_title,
                post_content=post_content,
                comment_text=content,
                comment_author=author,
                cc_commented_on_parent=cc_commented_on_parent,
            )
        except Exception as e:
            log.error(f"  generate_comment_reply failed for {author}: {e}")
            errors += 1
            continue

        if not reply_text:
            errors += 1
            continue

        log.info(f"  -> Comment reply to {author}: {reply_text[:80]}")

        if dry_run:
            replied_comments[comment_key] = {
                "author": author,
                "reply": reply_text,
                "dry_run": True,
                "brief": cc_commented_on_parent,
                "ts": _now(),
            }
            posted += 1
            continue

        try:
            ok = _type_and_submit_reply_to_comment(page, idx, reply_text)
        except Exception as e:
            log.error(f"  Submit failed for {author}: {e}")
            errors += 1
            ok = False

        if ok:
            replied_comments[comment_key] = {
                "author": author,
                "reply": reply_text,
                "brief": cc_commented_on_parent,
                "ts": _now(),
            }
            posted += 1
            notify(
                f"Skool comment reply to {author} on {post_slug}: {reply_text[:80]}",
                category="content",
            )
            time.sleep(3)  # Pace between comment submissions
        else:
            errors += 1

    return posted, errors, escalations


# ---------------------------------------------------------------------------
# Community post scanning + replying
# ---------------------------------------------------------------------------

def cmd_scan_posts(args, page=None, ctx=None):
    from playwright.sync_api import sync_playwright

    replied = _load_json(REPLIED_POSTS_PATH)
    replied_comments = _load_json(REPLIED_COMMENTS_PATH)
    results = {
        "scanned": 0,
        "replied": 0,
        "skipped": 0,
        "errors": [],
        # V2.1 — comment tier + escalation counters
        "comment_replies": 0,
        "comment_errors": 0,
        "escalations": 0,
    }
    # Global comment-reply budget for the whole scan (respects daily/per-cycle cap)
    comment_budget_remaining = MAX_COMMENT_REPLIES_PER_CYCLE if COMMENT_REPLIES_ENABLED else 0
    own_ctx = page is None

    pw_mgr = None
    if own_ctx:
        pw_mgr = sync_playwright().start()
        ctx = get_browser_context(pw_mgr)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if not is_logged_in(page):
            log.error("Not logged into Skool. Run: python scripts/skool_engine.py login")
            ctx.close()
            pw_mgr.stop()
            return results

    try:
        page.goto(COMMUNITY_FEED_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)

        for _ in range(3):
            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(1.5)

        posts = page.evaluate("""() => {
            const wrappers = document.querySelectorAll('[class*="PostItemWrapper-sc-e4ns84"]');
            const results = [];
            const seen = new Set();
            for (const w of wrappers) {
                const allLinks = w.querySelectorAll('a[href*="/agency-accelerants-6209/"]');
                let postLink = null;
                for (const a of allLinks) {
                    const h = a.getAttribute('href');
                    if (h && !h.includes('?c=') && h !== '/agency-accelerants-6209/' && h.split('/').length > 2) {
                        postLink = a;
                        break;
                    }
                }
                if (!postLink) continue;

                const href = postLink.getAttribute('href');
                const slug = href.split('/').pop().split('?')[0] || href;
                if (!slug || seen.has(slug)) continue;
                seen.add(slug);

                const authorLinks = w.querySelectorAll('a[href*="/@"]');
                const author = authorLinks.length >= 2 ? authorLinks[1].textContent.trim() :
                               (authorLinks[0] ? authorLinks[0].textContent.trim() : 'Unknown');

                const contentEl = w.querySelector('[class*="PostItemContent"], [class*="ContentWrapper"]');
                const content = contentEl ? contentEl.textContent.trim() : '';

                results.push({ slug, href, author, title: slug, content: content.substring(0, 500) });
            }
            return results;
        }""")

        log.info(f"Found {len(posts)} posts in feed")
        results["scanned"] = len(posts)

        reply_count = 0
        for post in posts:
            if reply_count >= MAX_REPLIES_PER_CYCLE:
                break

            slug = post.get("slug", "")
            if not slug or slug in replied:
                results["skipped"] += 1
                continue

            author = post.get("author", "")
            author_lower = author.lower().strip()
            if "conaugh" in author_lower or author_lower == "cc" or "primary_retainer" in author_lower:
                replied[slug] = {"author": author, "skipped": "own_post", "ts": _now()}
                results["skipped"] += 1
                continue

            title = post.get("title", "")
            content = post.get("content", "")
            log.info(f"Processing post by {author}: {title[:60]}...")

            # Navigate to the post page FIRST (to get full content + images)
            post_url = f"https://www.skool.com{post['href']}" if post["href"].startswith("/") else post["href"]
            page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            # V2.1: detect whether CC has already top-level commented on this post.
            # DO NOT skip — flag it so comment replies can be tone-adjusted (brief + complementary).
            cc_commented_on_parent = page.evaluate("""() => {
                const links = document.querySelectorAll('a[href*="/@conaugh"]');
                return links.length > 1;
            }""")

            # Read the full post content from the page
            full_content = page.evaluate("""() => {
                const el = document.querySelector('[class*="PostContent"], [class*="Content"], .ProseMirror');
                return el ? el.innerText.trim() : '';
            }""")
            if full_content:
                content = full_content[:800]

            # V2.1: escalation check on the post itself. If this post needs CC's personal
            # attention (crisis, hot lead, direct @-mention, explicit coaching ask),
            # Telegram-ping CC and SKIP the auto-reply — let CC respond in his real voice.
            needs_coach, escalation_reason = _needs_coach_attention(title, content, author)
            if needs_coach:
                log.info(f"  ⚠️  Escalating to CC (post): {escalation_reason}")
                _escalate_to_cc(post_url, author, content, escalation_reason, kind="post")
                replied[slug] = {
                    "author": author,
                    "escalated": True,
                    "reason": escalation_reason,
                    "ts": _now(),
                }
                results["escalations"] += 1
                # Still scan comments — members may have replied with something worth engaging
                c_posted, c_errors, c_escalations = _process_post_comments(
                    page=page,
                    post_slug=slug,
                    post_title=title,
                    post_content=content,
                    cc_commented_on_parent=cc_commented_on_parent,
                    replied_comments=replied_comments,
                    global_comment_budget=comment_budget_remaining,
                    dry_run=args.dry_run,
                )
                results["comment_replies"] += c_posted
                results["comment_errors"] += c_errors
                results["escalations"] += len(c_escalations)
                comment_budget_remaining = max(0, comment_budget_remaining - c_posted)
                continue

            # Capture any images from the post for vision analysis
            post_images = _capture_post_images(page)
            if post_images:
                log.info(f"  Captured {len(post_images)} image(s) for vision analysis")

            # TOP-LEVEL REPLY — only if CC hasn't already commented and post budget allows
            if cc_commented_on_parent:
                log.info("  CC already commented top-level — skipping Bravo top-level reply, "
                         "proceeding to comment-tier engagement")
                replied[slug] = {
                    "author": author,
                    "cc_already_commented": True,
                    "ts": _now(),
                }
            else:
                # Generate reply with full content + images
                reply_text = generate_post_reply(title, content, author, images=post_images)
                if not reply_text:
                    results["errors"].append(f"No reply for {slug}")
                    # Still try to engage comments even if top-level failed
                    reply_text = None

                if reply_text:
                    log.info(f"  Reply: {reply_text[:80]}...")

                    if args.dry_run:
                        log.info("  [dry-run] Would post reply")
                        replied[slug] = {"author": author, "dry_run": True, "ts": _now()}
                        results["replied"] += 1
                        reply_count += 1
                    else:
                        posted = _type_and_submit_comment(page, reply_text)
                        if posted:
                            log.info("  Comment posted")
                            replied[slug] = {"author": author, "reply": reply_text, "ts": _now()}
                            results["replied"] += 1
                            reply_count += 1
                            notify(f"Skool reply to {author}: {reply_text[:80]}...", category="content")
                        else:
                            results["errors"].append(f"Failed to comment on {slug}")

                time.sleep(3)

            # V2.1: COMMENT-TIER ENGAGEMENT — scan and reply to other members' comments
            # on this post. Tone adjusts automatically based on cc_commented_on_parent.
            if comment_budget_remaining > 0:
                # Scroll to the comment section to make sure Skool has rendered it
                try:
                    page.evaluate("window.scrollBy(0, 1200)")
                    time.sleep(2)
                except Exception:
                    pass

                c_posted, c_errors, c_escalations = _process_post_comments(
                    page=page,
                    post_slug=slug,
                    post_title=title,
                    post_content=content,
                    cc_commented_on_parent=cc_commented_on_parent,
                    replied_comments=replied_comments,
                    global_comment_budget=comment_budget_remaining,
                    dry_run=args.dry_run,
                )
                results["comment_replies"] += c_posted
                results["comment_errors"] += c_errors
                results["escalations"] += len(c_escalations)
                comment_budget_remaining = max(0, comment_budget_remaining - c_posted)

                if c_posted or c_escalations:
                    log.info(
                        f"  Comment tier: {c_posted} replies, "
                        f"{len(c_escalations)} escalations, "
                        f"{comment_budget_remaining} budget remaining"
                    )

    finally:
        if own_ctx:
            ctx.close()
            pw_mgr.stop()

    _save_json(REPLIED_POSTS_PATH, replied)
    _save_json(REPLIED_COMMENTS_PATH, replied_comments)
    return results


def _type_and_submit_comment(page, text: str) -> bool:
    try:
        page.evaluate("""() => {
            const editors = document.querySelectorAll('.ProseMirror[contenteditable="true"]');
            for (const ed of editors) {
                if (!ed.closest('[class*="PostBody"]')) {
                    ed.click();
                    return true;
                }
            }
            const placeholders = document.querySelectorAll('p[data-placeholder]');
            for (const p of placeholders) {
                if (p.getAttribute('data-placeholder')?.toLowerCase().includes('comment') ||
                    p.getAttribute('data-placeholder')?.toLowerCase().includes('your')) {
                    p.click();
                    return true;
                }
            }
            return false;
        }""")
        time.sleep(1)

        page.keyboard.type(text, delay=12)
        time.sleep(1)

        submitted = page.evaluate("""() => {
            const btns = [...document.querySelectorAll('button')];
            for (const btn of btns) {
                const txt = btn.textContent.trim().toLowerCase();
                if ((txt === 'comment' || txt === 'reply' || txt === 'post' || txt === 'send')
                    && !btn.disabled) {
                    btn.click();
                    return 'clicked';
                }
            }
            return 'no_button';
        }""")

        if submitted == "no_button":
            page.keyboard.press("Control+Enter")

        time.sleep(2)
        return True
    except Exception as e:
        log.error(f"Comment submission failed: {e}")
        return False


# ---------------------------------------------------------------------------
# DM scanning + replying
# ---------------------------------------------------------------------------

def cmd_scan_dms(args, page=None, ctx=None):
    """DISABLED 2026-04-02 — CC handles DMs manually. Returns empty results immediately."""
    if DM_DISABLED:
        log.info("DMs DISABLED (DM_DISABLED=True). Skipping entirely.")
        return {"scanned": 0, "replied": 0, "skipped": 0, "booked": 0, "errors": []}

    # Everything below is dead code — kept for reference only
    from playwright.sync_api import sync_playwright

    dm_state = _load_json(DM_STATE_PATH)
    results = {"scanned": 0, "replied": 0, "skipped": 0, "booked": 0, "errors": []}
    own_ctx = page is None

    pw_mgr = None
    if own_ctx:
        pw_mgr = sync_playwright().start()
        ctx = get_browser_context(pw_mgr)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if not is_logged_in(page):
            log.error("Not logged into Skool. Run: python scripts/skool_engine.py login")
            ctx.close()
            pw_mgr.stop()
            return results

    try:
        # Navigate to community page and open chat panel via top nav icon
        page.goto(COMMUNITY_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)

        # Click the chat icon button in the top navbar
        chat_opened = page.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                if ((b.className || '').toString().includes('ChatNotific')) {
                    b.click();
                    return true;
                }
            }
            return false;
        }""")

        if not chat_opened:
            log.error("Could not find chat button in top nav")
            results["errors"].append("Chat button not found")
            if own_ctx:
                ctx.close()
                pw_mgr.stop()
            return results

        time.sleep(4)

        # Parse thread list from the chat popover
        # Each thread is an <a> with class "ChildrenLink" pointing to /chat?ch=<id>
        # Text format: "MemberName• TimePreview text..."
        threads = page.evaluate(r"""() => {
            const popover = document.querySelector('[class*="PopoverItems"]');
            if (!popover) return [];

            const anchors = popover.querySelectorAll('a[class*="ChildrenLink"]');
            const results = [];
            const seen = new Set();

            for (const a of anchors) {
                const href = a.getAttribute('href') || '';
                if (!href.includes('/chat?')) continue;

                const text = a.textContent.trim().replace(/\s+/g, ' ');
                if (!text || text.length < 5) continue;

                const bulletIdx = text.indexOf('\u2022');
                if (bulletIdx < 0) continue;

                const name = text.substring(0, bulletIdx).trim();
                if (!name || name.length > 60 || seen.has(name)) continue;
                seen.add(name);

                const afterBullet = text.substring(bulletIdx + 1).trim();
                const timeMatch = afterBullet.match(/^(\d+[hmd])/);
                const timeAgo = timeMatch ? timeMatch[1] : '';
                const preview = timeMatch
                    ? afterBullet.substring(timeMatch[0].length).trim()
                    : afterBullet;

                const slug = name.toLowerCase()
                    .replace(/[^\w\s-]/g, '')
                    .replace(/\s+/g, '-')
                    .trim();

                // Chat URL for direct navigation
                const chatUrl = href.startsWith('/') ? 'https://www.skool.com' + href : href;

                results.push({ name, slug, timeAgo, preview: preview.substring(0, 120), chatUrl });
            }
            return results;
        }""")

        log.info(f"Found {len(threads)} DM threads in chat panel")
        results["scanned"] = len(threads)

        # Identify threads needing a reply.
        # Skool chat popover shows unread threads with bold/notification indicators.
        # We detect unread via CSS weight classes on the thread anchor.
        unread_threads = [t for t in threads if t.get("hasUnread")]
        if not unread_threads:
            # No unread indicators found — check up to MAX threads.
            # The in-conversation anti-spam check (reads actual messages) is the
            # real guard. This limit just prevents opening 30 threads per cycle.
            unread_threads = threads[:MAX_DM_REPLIES_PER_CYCLE]
        log.info(f"Threads to check: {len(unread_threads)} (of {len(threads)})")

        reply_count = 0
        for thread_idx, thread in enumerate(unread_threads):
            if reply_count >= MAX_DM_REPLIES_PER_CYCLE:
                log.info(f"Hit DM reply limit ({MAX_DM_REPLIES_PER_CYCLE})")
                break

            member_name = thread.get("name", "")
            member_slug = thread.get("slug", "")

            # Skip own conversations
            if "conaugh" in member_name.lower():
                results["skipped"] += 1
                continue

            log.info(f"Opening DM with {member_name} ({member_slug})...")

            # Navigate directly to the chat URL
            chat_url = thread.get("chatUrl", "")
            if not chat_url:
                log.warning(f"No chat URL for {member_name}")
                results["errors"].append(f"No chat URL: {member_name}")
                continue

            try:
                page.goto(chat_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(4)
                thread_opened = True
            except Exception as e:
                log.warning(f"Failed to navigate to chat: {e}")
                thread_opened = False

            if not thread_opened:
                log.warning(f"Could not open thread with {member_name}")
                results["errors"].append(f"Could not open thread: {member_name}")
                continue

            time.sleep(3)

            # Read the conversation — get last few messages
            # Skool chat bubbles use class "ChatBubble-sc-" and contain:
            # "SenderNameTimestampMessage text" all concatenated
            messages = page.evaluate("""() => {
                const msgs = [];
                const bubbles = document.querySelectorAll('[class*="ChatBubble"]');

                // Junk patterns: leaderboard data, system messages, feed snippets
                const JUNK_PATTERNS = [
                    /^Leaderboard/i,
                    /^[0-9]+[A-Z][a-z]+ [A-Z]/,  // "1Lourenço Abreu+47" etc
                    /broke the ice/i,
                    /joined the group/i,
                    /started a conversation/i,
                ];

                for (const b of bubbles) {
                    const fullText = b.textContent.trim();
                    if (!fullText || fullText.length > 2000) continue;

                    // Extract sender name — it's the first text node or first child
                    // The bubble format is: "SenderName HH:MMam/pm MessageText"
                    const isFromCC = fullText.startsWith('Conaugh') || fullText.startsWith('CC');

                    // Strip the sender name and timestamp to get just the message
                    // Pattern: "Name TimeMessage" — time is like "10:03pm", "6:14pm"
                    const timeMatch = fullText.match(/\\d{1,2}:\\d{2}(?:am|pm)/);
                    let messageText = fullText;
                    if (timeMatch) {
                        const timeEnd = fullText.indexOf(timeMatch[0]) + timeMatch[0].length;
                        messageText = fullText.substring(timeEnd).trim();
                    }

                    if (!messageText) continue;

                    // Filter out junk: leaderboard data, system messages, etc.
                    let isJunk = false;
                    for (const pat of JUNK_PATTERNS) {
                        if (pat.test(messageText)) { isJunk = true; break; }
                    }
                    if (isJunk) continue;

                    msgs.push({
                        text: messageText.substring(0, 500),
                        from: isFromCC ? 'CC' : 'member',
                    });
                }
                return msgs;
            }""")

            if not messages:
                log.info(f"  No messages found in thread with {member_name}")
                results["skipped"] += 1
                continue

            # RESPONSE-ONLY GUARD: The bot NEVER initiates conversations.
            # There must be at least one genuine message FROM the member.
            has_member_message = any(m.get("from") == "member" for m in messages)
            if not has_member_message:
                log.info(f"  No member messages in thread — skipping (response-only)")
                dm_state[member_slug] = {
                    "last_checked": _now(),
                    "last_from": "CC",
                    "skipped": "no_member_msgs",
                }
                results["skipped"] += 1
                continue

            # ANTI-SPAM CHECK: If the last message is from CC, do NOT reply
            last_message = messages[-1]
            if last_message.get("from") == "CC":
                log.info(f"  Last message is from CC — skipping (anti-spam)")
                dm_state[member_slug] = {
                    "last_checked": _now(),
                    "last_from": "CC",
                    "skipped": "anti_spam",
                }
                results["skipped"] += 1
                continue

            member_message = last_message.get("text", "")
            log.info(f"  Member says: {member_message[:80]}...")

            # Build conversation history
            history = "\n".join(
                f"{'CC' if m['from'] == 'CC' else member_name}: {m['text']}"
                for m in messages[-6:]
            )

            # Check member paid/free status
            member_info = check_member_status(page, member_slug)
            is_paid = member_info.get("is_paid", True)

            # Navigate back to the chat thread after profile check
            page.goto(chat_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)

            # Check for booking intent
            booking_result = None
            if _detect_booking_intent(member_message):
                log.info(f"  Booking intent detected — finding available slot...")
                booking_result = book_meeting(member_name)
                if booking_result["success"]:
                    results["booked"] += 1
                    log.info(f"  Booked: {booking_result['display_time']}")

            # Generate reply
            reply_text = generate_dm_reply(
                member_name=member_name,
                member_message=member_message,
                conversation_history=history,
                is_paid=is_paid,
                booking_result=booking_result,
            )

            if not reply_text:
                results["errors"].append(f"No reply generated for {member_name}")
                continue

            log.info(f"  Reply: {reply_text[:80]}...")

            if args.dry_run:
                log.info("  [dry-run] Would send DM reply")
                dm_state[member_slug] = {
                    "last_checked": _now(),
                    "last_reply": reply_text,
                    "dry_run": True,
                }
                results["replied"] += 1
                reply_count += 1
                continue

            # PRE-SEND VERIFICATION: Re-read the conversation to confirm
            # the last message is STILL from the member (not from CC/bot).
            # This is the final guard against double-texting.
            presend_messages = page.evaluate("""() => {
                const msgs = [];
                const JUNK = [/^Leaderboard/i, /^\\d+[A-Z]/, /broke the ice/i, /joined/i];
                const bubbles = document.querySelectorAll('[class*="ChatBubble"]');
                for (const b of bubbles) {
                    const fullText = b.textContent.trim();
                    if (!fullText || fullText.length > 2000) continue;
                    const isFromCC = fullText.startsWith('Conaugh') || fullText.startsWith('CC');
                    const timeMatch = fullText.match(/\\d{1,2}:\\d{2}(?:am|pm)/);
                    let msg = fullText;
                    if (timeMatch) msg = fullText.substring(fullText.indexOf(timeMatch[0]) + timeMatch[0].length).trim();
                    let junk = false;
                    for (const p of JUNK) { if (p.test(msg)) { junk = true; break; } }
                    if (junk) continue;
                    msgs.push({ from: isFromCC ? 'CC' : 'member' });
                }
                return msgs;
            }""")

            if presend_messages and presend_messages[-1].get("from") == "CC":
                log.warning(f"  PRE-SEND BLOCK: Last message is now from CC — another instance already replied. Skipping.")
                dm_state[member_slug] = {
                    "last_checked": _now(),
                    "last_from": "CC",
                    "skipped": "presend_block",
                }
                results["skipped"] += 1
                continue

            # Type and send the DM
            sent = _type_and_send_dm(page, reply_text)
            if sent:
                log.info(f"  DM sent to {member_name}")
                dm_state[member_slug] = {
                    "last_checked": _now(),
                    "last_reply": reply_text,
                    "last_from": "CC",
                    "is_paid": is_paid,
                    "booking": booking_result["display_time"] if booking_result and booking_result["success"] else None,
                }
                results["replied"] += 1
                reply_count += 1
                notify(f"Skool DM to {member_name}: {reply_text[:80]}...", category="content")
            else:
                results["errors"].append(f"Failed to send DM to {member_name}")

            time.sleep(3)

    finally:
        if own_ctx:
            ctx.close()
            pw_mgr.stop()

    _save_json(DM_STATE_PATH, dm_state)
    return results


def _type_and_send_dm(page, text: str) -> bool:
    """Type a message into the Skool DM chat input and send it."""
    try:
        # Find the chat input field
        focused = page.evaluate("""() => {
            // Look for ProseMirror editor in DM area
            const editors = document.querySelectorAll('.ProseMirror[contenteditable="true"]');
            for (const ed of editors) {
                ed.click();
                ed.focus();
                return 'editor';
            }
            // Look for textarea or input
            const inputs = document.querySelectorAll('textarea, input[type="text"]');
            for (const inp of inputs) {
                if (inp.placeholder?.toLowerCase().includes('message') ||
                    inp.placeholder?.toLowerCase().includes('type') ||
                    inp.closest('[class*="chat"], [class*="Chat"], [class*="dm"], [class*="DM"]')) {
                    inp.click();
                    inp.focus();
                    return 'input';
                }
            }
            // Look for contenteditable divs
            const editables = document.querySelectorAll('[contenteditable="true"]');
            for (const ed of editables) {
                if (ed.closest('[class*="chat"], [class*="Chat"], [class*="dm"], [class*="DM"]')) {
                    ed.click();
                    ed.focus();
                    return 'editable';
                }
            }
            return 'none';
        }""")

        if focused == "none":
            log.error("Could not find DM input field")
            return False

        time.sleep(0.5)

        # CRITICAL: Strip ALL newlines before typing.
        # Skool DMs use Enter to send — any \n in the text triggers
        # a premature send, splitting one reply into multiple messages.
        clean_text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        clean_text = re.sub(r"  +", " ", clean_text).strip()

        page.keyboard.type(clean_text, delay=15)
        time.sleep(1)

        # Send with Enter (Skool DMs use Enter to send)
        page.keyboard.press("Enter")
        time.sleep(2)
        return True

    except Exception as e:
        log.error(f"DM send failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Auto & Daemon modes
# ---------------------------------------------------------------------------

def cmd_auto(args, page=None, ctx=None, **_kwargs):
    """Run full scan: community post replies only. DMs disabled 2026-04-01."""
    from playwright.sync_api import sync_playwright

    log.info("=== Skool Engine V2: Auto Scan ===")
    log.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log.info("Mode: post replies ONLY (DMs disabled — CC handles DMs manually)")

    all_results = {}
    own_ctx = page is None

    if own_ctx:
        pw_mgr = sync_playwright().start()
        ctx = get_browser_context(pw_mgr)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

    try:
        if not is_logged_in(page):
            log.error("Not logged into Skool. Run: python scripts/skool_engine.py login")
            return all_results

        log.info("\n--- Scanning community posts ---")
        all_results["posts"] = cmd_scan_posts(args, page=page, ctx=ctx)

        # DMs disabled 2026-04-01 — CC handles DMs manually
        all_results["dms"] = {"scanned": 0, "replied": 0, "booked": 0}

    except Exception as e:
        log.error(f"Auto scan error: {e}")
        raise
    finally:
        if own_ctx:
            ctx.close()
            pw_mgr.stop()

    p = all_results.get("posts", {})
    log.info(f"\n=== Summary ===")
    log.info(f"Posts replied: {p.get('replied', 0)}/{p.get('scanned', 0)}")
    log.info(f"Comment replies: {p.get('comment_replies', 0)}  errors: {p.get('comment_errors', 0)}")
    log.info(f"Escalations to CC: {p.get('escalations', 0)}")

    total_engagements = p.get("replied", 0) + p.get("comment_replies", 0)
    escalations = p.get("escalations", 0)

    if total_engagements > 0 or escalations > 0:
        parts = []
        if p.get("replied", 0):
            parts.append(f"{p.get('replied', 0)} post replies")
        if p.get("comment_replies", 0):
            parts.append(f"{p.get('comment_replies', 0)} comment replies")
        if escalations:
            parts.append(f"{escalations} ESCALATIONS to CC")
        notify("Skool scan: " + ", ".join(parts), category="content")

    return all_results


# ---------------------------------------------------------------------------
# Daemon
# ---------------------------------------------------------------------------

def _is_daemon_running() -> bool:
    if not DAEMON_PID_PATH.exists():
        return False
    try:
        data = _load_json(DAEMON_PID_PATH)
        pid = data.get("pid")
        if not pid:
            return False

        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, int(pid))
        if not handle:
            DAEMON_PID_PATH.unlink(missing_ok=True)
            return False
        kernel32.CloseHandle(handle)

        if HEARTBEAT_PATH.exists():
            hb = _load_json(HEARTBEAT_PATH)
            hb_ts = hb.get("ts", "")
            if hb_ts:
                try:
                    last_beat = datetime.fromisoformat(hb_ts)
                    if last_beat.tzinfo is None:
                        last_beat = last_beat.replace(tzinfo=timezone.utc)
                    age_min = (datetime.now(timezone.utc) - last_beat).total_seconds() / 60
                    if age_min > 10:
                        log.warning(f"Zombie daemon: PID {pid} alive but heartbeat stale ({age_min:.0f}m)")
                        DAEMON_PID_PATH.unlink(missing_ok=True)
                        HEARTBEAT_PATH.unlink(missing_ok=True)
                        return False
                except (ValueError, TypeError):
                    pass
        else:
            DAEMON_PID_PATH.unlink(missing_ok=True)
            return False

        return True
    except Exception:
        return False


def cmd_daemon(args):
    from playwright.sync_api import sync_playwright

    interval = getattr(args, "interval", 5) or 5

    # EXCLUSIVE LOCK — only ONE daemon process can hold this lock.
    # If another daemon is already running, we exit immediately.
    lock = DaemonLock()
    if not lock.acquire():
        log.error("BLOCKED: Another skool_engine daemon holds the lock. Exiting.")
        sys.exit(1)

    log.info(f"=== Skool Engine V2: Daemon Mode (every {interval} min) ===")
    log.info(f"Exclusive lock acquired (PID {os.getpid()})")
    log.info("Mode: post replies ONLY (DMs disabled 2026-04-01)")
    log.info("Press Ctrl+C to stop")

    _save_json(DAEMON_PID_PATH, {"pid": os.getpid(), "started": _now(), "interval": interval})
    _save_json(HEARTBEAT_PATH, {"pid": os.getpid(), "ts": _now(), "cycle": 0})

    running = [True]

    def _shutdown(_signum, _frame):
        log.info("Shutdown signal received...")
        running[0] = False

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    notify(f"Skool V2 daemon started (every {interval} min)", category="system")

    cycle = 0
    consecutive_failures = 0

    while running[0]:
        try:
            with sync_playwright() as pw:
                ctx = get_browser_context(pw)
                page = ctx.pages[0] if ctx.pages else ctx.new_page()

                if not is_logged_in(page):
                    log.error("Not logged into Skool")
                    ctx.close()
                    notify("Skool daemon: NOT LOGGED IN", category="system")
                    break

                while running[0]:
                    log.info(f"\n{'='*50}")
                    log.info(f"Cycle {cycle} at {datetime.now().strftime('%H:%M:%S')}")

                    try:
                        _save_json(HEARTBEAT_PATH, {"pid": os.getpid(), "ts": _now(), "cycle": cycle})
                    except Exception:
                        pass

                    try:
                        cmd_auto(args, page=page, ctx=ctx)
                        consecutive_failures = 0
                    except Exception as e:
                        consecutive_failures += 1
                        log.error(f"Cycle {cycle} failed ({consecutive_failures}/5): {e}")
                        if consecutive_failures >= 5:
                            log.warning("Too many failures — restarting browser...")
                            break

                    if not running[0]:
                        break

                    cycle += 1
                    log.info(f"Next cycle in {interval} minutes...")
                    for _ in range(interval * 6):
                        if not running[0]:
                            break
                        time.sleep(10)

                ctx.close()

        except Exception as e:
            log.error(f"Browser crashed: {e}")

        if not running[0]:
            break

        if consecutive_failures >= 5:
            consecutive_failures = 0
            log.info("Waiting 60s before restart...")
            for _ in range(6):
                if not running[0]:
                    break
                time.sleep(10)

    DAEMON_PID_PATH.unlink(missing_ok=True)
    HEARTBEAT_PATH.unlink(missing_ok=True)
    lock.release()
    log.info("Daemon stopped. Lock released.")
    notify("Skool V2 daemon stopped", category="system")


# ---------------------------------------------------------------------------
# Login / Status
# ---------------------------------------------------------------------------

def cmd_login(args):
    from playwright.sync_api import sync_playwright

    log.info("Launching browser for manual Skool login...")
    with sync_playwright() as pw:
        os.makedirs(BROWSER_DIR, exist_ok=True)
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DIR,
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.skool.com/login", wait_until="domcontentloaded", timeout=60000)
        log.info("Log in, then close browser window.")
        try:
            page.wait_for_event("close", timeout=300000)
        except Exception:
            pass
        ctx.close()
    log.info("Login session saved.")


def cmd_status(args):
    replied_posts = _load_json(REPLIED_POSTS_PATH)
    dm_state = _load_json(DM_STATE_PATH)
    total_posts = sum(1 for p in replied_posts.values() if isinstance(p, dict) and p.get("reply"))
    total_dms = sum(1 for d in dm_state.values() if isinstance(d, dict) and d.get("last_reply"))

    daemon_info = _load_json(DAEMON_PID_PATH)
    daemon_running = False
    if daemon_info.get("pid"):
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, int(daemon_info["pid"]))
            if handle:
                kernel32.CloseHandle(handle)
                daemon_running = True
        except Exception:
            pass

    status = {
        "daemon": {"running": daemon_running, **daemon_info} if daemon_info else {"running": False},
        "posts_replied": total_posts,
        "dms_replied": total_dms,
        "mode": "V2: post replies ONLY (DMs disabled 2026-04-01)",
        "kill_switch": SKOOL_DISABLED,
    }

    if getattr(args, "json", False):
        print(json.dumps(status, indent=2, default=str))
    else:
        safe_print(f"Kill switch: {'ON (engine disabled)' if SKOOL_DISABLED else 'OFF (engine active)'}")
        safe_print(f"Daemon: {'RUNNING' if daemon_running else 'STOPPED'}")
        if daemon_running:
            safe_print(f"  PID: {daemon_info.get('pid')} | Interval: {daemon_info.get('interval')}min")
        safe_print(f"Posts replied (all time): {total_posts}")
        safe_print(f"DMs replied (historical): {total_dms}")
        safe_print(f"Mode: V2 — post replies ONLY (DMs disabled 2026-04-01)")

    return status


# ---------------------------------------------------------------------------
# SKOOL METRICS SCRAPER — reads dashboard, updates revenue DB
# ---------------------------------------------------------------------------

def cmd_metrics(args, page=None, ctx=None):
    """Scrape Skool dashboard for community metrics and update revenue database."""
    from playwright.sync_api import sync_playwright

    own_browser = page is None
    pw = None

    try:
        if own_browser:
            pw = sync_playwright().start()
            ctx = get_browser_context(pw)
            page = ctx.new_page()

        # Navigate to Skool dashboard
        safe_print("Scraping Skool dashboard...")
        page.goto("https://www.skool.com/agency-accelerants/about", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # Check if logged in (dashboard shows "Dashboard" link when logged in)
        try:
            page.wait_for_selector('a[href*="/about"]', timeout=5000)
        except Exception:
            safe_print("Not logged in to Skool. Run: python scripts/skool_engine.py login")
            return {"ok": False, "error": "Not logged in to Skool"}

        # Navigate to admin dashboard for metrics
        page.goto("https://www.skool.com/agency-accelerants/settings", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # Try to extract metrics from the page
        metrics = page.evaluate("""() => {
            const text = document.body.innerText;
            const result = {};

            // Extract numbers near key labels
            const memberMatch = text.match(/(\\d+)\\s*Members/i);
            if (memberMatch) result.members = parseInt(memberMatch[1]);

            const mrrMatch = text.match(/\\$([\\d,]+)\\s*MRR/i);
            if (mrrMatch) result.mrr = parseFloat(mrrMatch[1].replace(',', ''));

            const engMatch = text.match(/(\\d+)%\\s*Engagement/i);
            if (engMatch) result.engagement = parseInt(engMatch[1]);

            const retMatch = text.match(/(\\d+)%\\s*Retention/i);
            if (retMatch) result.retention = parseInt(retMatch[1]);

            return result;
        }""")

        # If metrics extraction failed from settings, try the main about page
        if not metrics.get("members"):
            page.goto("https://www.skool.com/agency-accelerants", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            metrics = page.evaluate("""() => {
                const text = document.body.innerText;
                const result = {};
                const memberMatch = text.match(/(\\d[\\d,]*)\\s*(?:Members|members)/);
                if (memberMatch) result.members = parseInt(memberMatch[1].replace(',', ''));
                return result;
            }""")

        safe_print(f"Skool metrics: {json.dumps(metrics)}")

        # Update revenue database if MRR found
        if metrics.get("mrr"):
            skool_mrr = metrics["mrr"]
            rev_share = round(skool_mrr * 0.15, 2)
            total_primary_retainer = 2500 + rev_share
            members = metrics.get("members", "?")
            engagement = metrics.get("engagement", "?")
            retention = metrics.get("retention", "?")

            # Update Supabase
            update_note = (f"primary retainer: $2500 flat + 15% of ${skool_mrr} Skool MRR (${rev_share}). "
                          f"{members} members, {engagement}% engagement, {retention}% retention. "
                          f"Auto-updated {datetime.now().strftime('%Y-%m-%d %H:%M')}.")

            try:
                result = subprocess.run(
                    [sys.executable, "scripts/supabase_tool.py", "update", "revenue_events",
                     json.dumps({"amount_usd": total_primary_retainer, "metadata": json.dumps({"notes": update_note})}),
                     "--project", "bravo",
                     "--match", json.dumps({"client_name": "primary retainer Agency Accelerator", "type": "subscription_start"})],
                    capture_output=True, text=True, timeout=15,
                    creationflags=0x08000000 if sys.platform == "win32" else 0,
                    cwd=str(PROJECT_ROOT)
                )
                if "Updated 1 row" in result.stdout:
                    safe_print(f"Revenue updated: primary retainer → ${total_primary_retainer}/mo")
                    metrics["revenue_updated"] = True
                    metrics["total_primary_retainer"] = total_primary_retainer
                else:
                    safe_print(f"Revenue update issue: {result.stdout[:200]}")
            except Exception as e:
                safe_print(f"Revenue update failed: {e}")

        return {"ok": True, "metrics": metrics}

    except Exception as e:
        log.error(f"Metrics scrape failed: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        if own_browser:
            try:
                ctx.close()
                pw.stop()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Skool Community Engine V2")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--dry-run", action="store_true", help="Preview without posting")

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("login", help="Launch browser for Skool login")
    sub.add_parser("scan-posts", help="Reply to community posts")
    sub.add_parser("scan-dms", help="Reply to incoming DMs")
    sub.add_parser("auto", help="Full scan (posts + DMs)")
    sub.add_parser("status", help="Show engine status")
    sub.add_parser("metrics", help="Scrape Skool dashboard metrics and update revenue")

    daemon_parser = sub.add_parser("daemon", help="Run continuously")
    daemon_parser.add_argument("--interval", type=int, default=5, help="Minutes between cycles (default: 5)")

    args = parser.parse_args()

    if SKOOL_DISABLED:
        msg = "Skool Engine is DISABLED (kill switch active). Set SKOOL_DISABLED = False in skool_engine.py to re-enable."
        log.warning(msg)
        safe_print(msg)
        sys.exit(0)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "login": cmd_login,
        "scan-posts": cmd_scan_posts,
        "scan-dms": cmd_scan_dms,
        "auto": cmd_auto,
        "daemon": cmd_daemon,
        "status": cmd_status,
        "metrics": cmd_metrics,
    }

    handler = commands.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(1)

    result = handler(args)
    if getattr(args, "json", False) and result and args.command not in ("status",):
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
