"""
Skool Community Engine - Autonomous community management via Playwright browser automation.

Full-stack community automation for Agency Accelerants Skool community:
- Replies to community posts in CC's coaching voice
- Welcomes new paid members ($97/mo) with personal DMs
- Nurtures free members toward $97/month paid conversion
- Multi-turn DM conversations with rapport tracking
- Auto-responds to incoming DMs
- Daemon mode: runs continuously on configurable intervals
- Auto-starts on Windows boot via Task Scheduler

Usage:
  python scripts/skool_engine.py login              # One-time: manual Skool login
  python scripts/skool_engine.py scan-posts         # Reply to community posts
  python scripts/skool_engine.py auto               # Run scan once
  python scripts/skool_engine.py daemon             # Run continuously (default: 2min interval)
  python scripts/skool_engine.py daemon --interval 15  # Custom interval in minutes
  python scripts/skool_engine.py --dry-run auto     # Preview without posting
  python scripts/skool_engine.py --json auto        # JSON output

Requires: playwright, anthropic (pip install playwright anthropic)
Browser profile persists at tmp/skool-browser/ for session continuity.
"""

import argparse
import json
import sys
import os
import time
import signal
import logging
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
BROWSER_DIR = str(PROJECT_ROOT / "tmp" / "skool-browser")
TMP_DIR = PROJECT_ROOT / "tmp"
LOG_DIR = TMP_DIR / "logs"

# State files
REPLIED_POSTS_PATH = TMP_DIR / "skool_replied_posts.json"
DAEMON_PID_PATH = TMP_DIR / "skool_daemon.pid"
HEARTBEAT_PATH = TMP_DIR / "skool_daemon.heartbeat"

COMMUNITY_URL = "https://www.skool.com/agency-accelerants-6209"

SKOOL_DISABLED = False          # Global kill switch — False = engine runs
COMMUNITY_FEED_URL = COMMUNITY_URL
MAX_REPLIES_PER_CYCLE = 5            # Max post replies per scan cycle

sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from notify import notify
except ImportError:
    def notify(*a, **kw): return False


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = LOG_DIR / f"skool_{datetime.now().strftime('%Y-%m-%d')}.log"
    # Use UTF-8 for both file and stdout to handle emoji in Claude-generated messages
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setStream(open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))
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
# Credential / env loading
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# State persistence (with file locking to prevent concurrent access)
# ---------------------------------------------------------------------------

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
    # Write to temp file first, then atomic rename to prevent corruption
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    # Atomic replace (Windows: os.replace is atomic within same drive)
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Browser context
# ---------------------------------------------------------------------------

def get_browser_context(playwright):
    """Launch persistent Chromium context (maintains Skool login session)."""
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
    """Attempt automatic Skool login using credentials from .env.agents."""
    env = load_env()
    email = env.get("SKOOL_EMAIL", "")
    password = env.get("SKOOL_PASSWORD", "")
    if not email or not password:
        log.warning("No SKOOL_EMAIL/SKOOL_PASSWORD in .env.agents — cannot auto-login")
        return False

    log.info(f"Auto-login attempt as {email}...")
    page.goto("https://www.skool.com/login", wait_until="networkidle", timeout=60000)
    time.sleep(4)

    try:
        # Fill email — use #email ID selector (most reliable)
        email_input = page.locator("#email")
        email_input.click()
        email_input.fill(email)
        time.sleep(0.5)

        # Fill password — use #password ID selector
        pw_input = page.locator("#password")
        pw_input.click()
        pw_input.fill(password)
        time.sleep(1)

        # Click LOG IN submit button
        login_btn = page.locator('button[type="submit"]')
        login_btn.click()

        # Wait for login form to disappear (SPA navigation — URL may lag)
        for _ in range(15):
            time.sleep(1)
            still_has_form = page.locator("#email").count() > 0
            if not still_has_form:
                log.info("Auto-login successful")
                return True

        log.error("Auto-login failed — login form still present (check credentials)")
        return False
    except Exception as e:
        log.error(f"Auto-login error: {e}")
        return False


def is_logged_in(page) -> bool:
    """Check if we have an active Skool session. Auto-logins if credentials available."""
    page.goto(COMMUNITY_FEED_URL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)

    if "/login" in page.url or "/signup" in page.url:
        return _auto_login(page)

    # Check for authenticated user indicator (profile button or similar)
    is_authed = page.evaluate("""() => {
        const bodyText = document.body.textContent;
        // "Log In" button visible = not authenticated
        const btns = [...document.querySelectorAll('button, a')];
        for (const b of btns) {
            const t = b.textContent.trim();
            if (t === 'Log In' || t === 'Sign Up') return false;
        }
        // Check for authenticated indicators: user avatar, nav links, post elements
        return !!(document.querySelector('[class*="PostItem"]') ||
                  document.querySelector('[class*="PostList"]') ||
                  document.querySelectorAll('a[href*="/classroom"]').length > 0);
    }""")

    if not is_authed:
        log.info("Session appears expired — attempting auto-login...")
        return _auto_login(page)

    return True


# ---------------------------------------------------------------------------
# Claude API — voice generation
# ---------------------------------------------------------------------------

def _call_claude(system_prompt: str, user_msg: str, max_tokens: int = 200) -> str:
    """Shared Claude API caller. Returns reply text or empty string on failure."""
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
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        reply = response.content[0].text.strip()
        # Strip wrapping quotes
        if (reply.startswith('"') and reply.endswith('"')) or \
           (reply.startswith("'") and reply.endswith("'")):
            reply = reply[1:-1]
        return reply
    except Exception as e:
        log.error(f"Claude API call failed: {e}")
        return ""


def _strip_ai_slop(text: str) -> str:
    """Remove em dashes and other AI-sounding artifacts from generated text."""
    # Replace em dash (U+2014) and en dash (U+2013) with comma or period
    text = text.replace("\u2014", ",")   # em dash
    text = text.replace("\u2013", ",")   # en dash
    text = text.replace(" ,", ",")       # clean double space before comma
    text = text.replace(",,", ",")       # clean double commas
    return text


def generate_post_reply(post_title: str, post_content: str, author_name: str) -> str:
    """Generate a community post comment in CC's real coaching voice."""
    system = (
        "You are ghostwriting a Skool community comment as Conaugh McKenna (CC), "
        "a 22-year-old AI automation entrepreneur and admin/coach of the Agency Accelerants community. "
        "CC runs OASIS AI Solutions. He builds AI agent systems for local businesses and has closed "
        "$30k+ deals. He is NOT a yes-man. He is a real mentor who challenges his students.\n\n"
        "PERSONALITY (non-negotiable):\n"
        "- You are a CRITICAL THINKER first, cheerleader second.\n"
        "- If someone posts a valid point, agree and build on it with something they haven't considered.\n"
        "- If someone posts something generic or surface-level, push back respectfully. Ask them to go deeper.\n"
        "- If someone is stuck, don't just empathize. Give them a specific next step and tell them to execute.\n"
        "- You DEMAND growth. You care about these people which means you tell them the truth.\n"
        "- You challenge assumptions. If someone says 'whats the biggest bottleneck' you don't just list yours, "
        "you flip the frame and make them think harder about their own situation.\n"
        "- You are direct, opinionated, and confident. You've done the work.\n\n"
        "VOICE RULES (non-negotiable):\n"
        "- Write like a real person texting. Casual, lowercase is fine, short sentences.\n"
        "- 2-4 sentences max. No essays.\n"
        "- NEVER use em dashes (the long dash character). Use commas, periods, or just start a new sentence instead.\n"
        "- NEVER use hashtags. NEVER pitch services. NEVER be salesy.\n"
        "- Avoid generic AI phrases like 'great question', 'love this', 'absolutely', 'I couldn't agree more'.\n"
        "- Don't start with compliments. Lead with substance.\n"
        "- Use first name. Exclamation marks sparingly (max 1 per reply).\n"
        "- Sound like a friend who won't let you stay comfortable.\n\n"
        "Reply with ONLY the comment text. No quotes around it."
    )
    user = (
        f"Community member {author_name} posted:\n"
        f"Title: {post_title}\n"
        f"Content: {post_content[:800]}\n\n"
        f"Write a reply that challenges or adds real value:"
    )
    reply = _call_claude(system, user)
    if reply:
        reply = _strip_ai_slop(reply)
    return reply[:1000] if reply else ""


# ---------------------------------------------------------------------------
# Community feed scanning + replying
# ---------------------------------------------------------------------------

def cmd_scan_posts(args, page=None, ctx=None):
    """Scan community feed for new posts and reply to unreplied ones."""
    from playwright.sync_api import sync_playwright

    replied = _load_json(REPLIED_POSTS_PATH)
    results = {"scanned": 0, "replied": 0, "skipped": 0, "errors": []}
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
                // Find post-specific link (has slug path, not ?c= category link)
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

                // Author: second a[href*="/@"] has the actual name (first has level number)
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
                log.info(f"Hit reply limit ({MAX_REPLIES_PER_CYCLE}), stopping for this cycle")
                break

            slug = post.get("slug", "")
            if not slug or slug in replied:
                results["skipped"] += 1
                continue

            author = post.get("author", "")
            author_lower = author.lower().strip()
            if "conaugh" in author_lower or author_lower == "cc" or "bennett" in author_lower:
                replied[slug] = {"author": author, "skipped": "own_post", "ts": _now()}
                results["skipped"] += 1
                continue

            title = post.get("title", "")
            content = post.get("content", "")
            log.info(f"Processing post by {author}: {title[:60]}...")

            reply_text = generate_post_reply(title, content, author)
            if not reply_text:
                results["errors"].append(f"No reply for {slug}")
                continue

            log.info(f"  Reply: {reply_text[:80]}...")

            if args.dry_run:
                log.info("  [dry-run] Would post reply")
                replied[slug] = {"author": author, "dry_run": True, "ts": _now()}
                results["replied"] += 1
                reply_count += 1
                continue

            post_url = f"https://www.skool.com{post['href']}" if post["href"].startswith("/") else post["href"]
            page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            already_commented = page.evaluate("""() => {
                const links = document.querySelectorAll('a[href*="/@conaugh"]');
                return links.length > 1;
            }""")

            if already_commented:
                replied[slug] = {"author": author, "skipped": "already_commented", "ts": _now()}
                results["skipped"] += 1
                continue

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

    finally:
        if own_ctx:
            ctx.close()
            pw_mgr.stop()

    _save_json(REPLIED_POSTS_PATH, replied)
    return results


def _type_and_submit_comment(page, text: str) -> bool:
    """Type a comment into the Skool ProseMirror editor and submit it."""
    try:
        # Click on any comment box
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

        # Click comment/submit button
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
# Auto & Daemon modes
# ---------------------------------------------------------------------------
# NOTE: All DM outreach, welcome DMs, nurture DMs, and DM auto-reply code was
# deleted 2026-03-28 per CC's directive. The ONLY automation that runs is
# community post replies (cmd_scan_posts). CC handles all DMs personally.

def cmd_auto(args, page=None, ctx=None, **_kwargs):
    """Run community post scanning. Only post replies are active.

    All DM outreach, welcome DMs, nurture DMs, and DM auto-reply were removed
    2026-03-28. CC handles all DMs personally.
    """
    from playwright.sync_api import sync_playwright

    log.info("=== Skool Engine: Auto Scan (posts only) ===")
    log.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

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

    except Exception as e:
        log.error(f"Auto scan error: {e}")
        raise
    finally:
        if own_ctx:
            ctx.close()
            pw_mgr.stop()

    # Summary
    p = all_results.get("posts", {})
    log.info(f"\n=== Summary ===")
    log.info(f"Posts replied: {p.get('replied', 0)}/{p.get('scanned', 0)}")

    if p.get("replied", 0) > 0:
        notify(f"Skool scan: {p.get('replied', 0)} post replies", category="content")

    return all_results


def _is_daemon_running() -> bool:
    """Check if another daemon instance is already running via PID file.

    Uses heartbeat staleness to detect zombie processes that Windows won't release.
    If PID is alive but heartbeat is stale (>10 min), treat as zombie and allow takeover.
    """
    if not DAEMON_PID_PATH.exists():
        return False
    try:
        data = _load_json(DAEMON_PID_PATH)
        pid = data.get("pid")
        if not pid:
            return False

        # Check if the PID is actually alive (Windows-compatible)
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            # Process is dead — clean up stale PID file
            log.info(f"Stale PID file found (PID {pid} is dead). Cleaning up.")
            DAEMON_PID_PATH.unlink(missing_ok=True)
            return False
        kernel32.CloseHandle(handle)

        # PID is alive — but is it actually working? Check heartbeat staleness.
        if HEARTBEAT_PATH.exists():
            hb = _load_json(HEARTBEAT_PATH)
            hb_ts = hb.get("ts", "")
            if hb_ts:
                from datetime import datetime, timezone
                try:
                    last_beat = datetime.fromisoformat(hb_ts)
                    if last_beat.tzinfo is None:
                        last_beat = last_beat.replace(tzinfo=timezone.utc)
                    age_min = (datetime.now(timezone.utc) - last_beat).total_seconds() / 60
                    if age_min > 10:
                        log.warning(f"Zombie daemon detected: PID {pid} alive but heartbeat stale ({age_min:.0f} min). Taking over.")
                        DAEMON_PID_PATH.unlink(missing_ok=True)
                        HEARTBEAT_PATH.unlink(missing_ok=True)
                        return False
                except (ValueError, TypeError):
                    pass
        else:
            # PID alive but NO heartbeat file at all — zombie
            log.warning(f"Zombie daemon detected: PID {pid} alive but no heartbeat file. Taking over.")
            DAEMON_PID_PATH.unlink(missing_ok=True)
            return False

        return True
    except Exception:
        return False


def cmd_daemon(args):
    """Run continuously in daemon mode with persistent browser and configurable interval."""
    from playwright.sync_api import sync_playwright

    interval = getattr(args, "interval", 2) or 2

    # CRITICAL: Prevent multiple daemon instances (causes double-replies)
    if _is_daemon_running():
        existing = _load_json(DAEMON_PID_PATH)
        log.error(f"Another daemon is already running (PID {existing.get('pid')}, started {existing.get('started')})")
        log.error("Kill it first or use: taskkill /PID <pid> /F")
        sys.exit(1)

    log.info(f"=== Skool Engine: Daemon Mode (every {interval} min) ===")
    log.info("Mode: community post replies only (all DMs disabled)")
    log.info("Press Ctrl+C to stop")

    # Write PID file for tracking
    _save_json(DAEMON_PID_PATH, {"pid": os.getpid(), "started": _now(), "interval": interval})

    # Write initial heartbeat (watchdog checks this for liveness)
    _save_json(HEARTBEAT_PATH, {"pid": os.getpid(), "ts": _now(), "cycle": 0})

    # Handle graceful shutdown
    running = [True]

    def _shutdown(signum, frame):
        log.info("Shutdown signal received, stopping after current cycle...")
        running[0] = False

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    notify(f"Skool daemon started (every {interval} min)", category="system")

    cycle = 0
    consecutive_failures = 0
    max_consecutive_failures = 5  # Restart browser after 5 consecutive failures

    while running[0]:
        try:
            # Persistent browser context — reuse across cycles
            with sync_playwright() as pw:
                ctx = get_browser_context(pw)
                page = ctx.pages[0] if ctx.pages else ctx.new_page()

                # Verify login before entering the loop
                if not is_logged_in(page):
                    log.error("Not logged into Skool. Run: python scripts/skool_engine.py login")
                    ctx.close()
                    notify("Skool daemon: NOT LOGGED IN — run login command", category="system")
                    break

                # Inner loop with persistent browser
                while running[0]:
                    log.info(f"\n{'='*50}")
                    log.info(f"Cycle {cycle} at {datetime.now().strftime('%H:%M:%S')}")
                    log.info(f"{'='*50}")

                    # Update heartbeat every cycle so watchdog knows we're alive
                    try:
                        _save_json(HEARTBEAT_PATH, {"pid": os.getpid(), "ts": _now(), "cycle": cycle})
                    except Exception:
                        pass

                    try:
                        cmd_auto(args, page=page, ctx=ctx, cycle=cycle)
                        consecutive_failures = 0
                    except Exception as e:
                        consecutive_failures += 1
                        log.error(f"Cycle {cycle} failed ({consecutive_failures}/{max_consecutive_failures}): {e}")
                        notify(f"Skool daemon error (cycle {cycle}): {str(e)[:80]}", category="system")

                        if consecutive_failures >= max_consecutive_failures:
                            log.warning("Too many consecutive failures — restarting browser...")
                            break  # Break inner loop to restart browser

                    if not running[0]:
                        break

                    cycle += 1
                    log.info(f"Next cycle in {interval} minutes...")
                    for _ in range(interval * 6):  # 10-second increments
                        if not running[0]:
                            break
                        time.sleep(10)

                ctx.close()

        except Exception as e:
            log.error(f"Browser context crashed: {e}")
            notify(f"Skool daemon browser crash: {str(e)[:80]}", category="system")

        if not running[0]:
            break

        # If we got here from consecutive failures, wait a bit then retry
        if consecutive_failures >= max_consecutive_failures:
            consecutive_failures = 0
            log.info("Waiting 60s before restarting browser...")
            for _ in range(6):
                if not running[0]:
                    break
                time.sleep(10)

    # Cleanup PID + heartbeat files
    if DAEMON_PID_PATH.exists():
        DAEMON_PID_PATH.unlink()
    if HEARTBEAT_PATH.exists():
        HEARTBEAT_PATH.unlink()

    log.info("Daemon stopped gracefully.")
    notify("Skool daemon stopped", category="system")


# ---------------------------------------------------------------------------
# Login helper
# ---------------------------------------------------------------------------

def cmd_login(args):
    """Launch browser in headed mode for manual Skool login."""
    from playwright.sync_api import sync_playwright

    log.info("Launching browser for manual Skool login...")
    log.info("Log in to your Skool account, then close the browser window.")
    log.info(f"Session persists at: {BROWSER_DIR}")

    with sync_playwright() as pw:
        os.makedirs(BROWSER_DIR, exist_ok=True)
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DIR,
            headless=False,
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.skool.com/login", wait_until="domcontentloaded", timeout=60000)

        log.info("Waiting for you to log in... (close browser when done)")
        try:
            page.wait_for_event("close", timeout=300000)
        except Exception:
            pass
        ctx.close()

    log.info("Login session saved.")


# ---------------------------------------------------------------------------
# Status helper
# ---------------------------------------------------------------------------

def cmd_status(args):
    """Show current engine state."""
    replied_posts = _load_json(REPLIED_POSTS_PATH)
    total_posts_replied = sum(1 for p in replied_posts.values() if p.get("reply"))

    # Daemon status
    daemon_info = _load_json(DAEMON_PID_PATH)
    daemon_running = False
    if daemon_info.get("pid"):
        try:
            import subprocess
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {daemon_info['pid']}", "/NH"],
                capture_output=True, text=True, timeout=5
            )
            daemon_running = str(daemon_info["pid"]) in result.stdout
        except Exception:
            pass

    status = {
        "daemon": {"running": daemon_running, **daemon_info} if daemon_info else {"running": False},
        "posts_replied": total_posts_replied,
        "mode": "post replies only (DMs disabled 2026-03-28)",
    }

    if args.json:
        print(json.dumps(status, indent=2, default=str))
    else:
        safe_print(f"Daemon: {'RUNNING' if daemon_running else 'STOPPED'}")
        if daemon_running:
            safe_print(f"  PID: {daemon_info.get('pid')} | Interval: {daemon_info.get('interval')}min")
            safe_print(f"  Started: {daemon_info.get('started', 'unknown')}")
        safe_print(f"Posts replied: {total_posts_replied}")
        safe_print(f"Mode: post replies only (all DMs disabled)")

    return status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Skool Community Engine — Autonomous Community Management")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without posting")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("login", help="Launch browser for manual Skool login")
    sub.add_parser("scan-posts", help="Reply to community posts")
    sub.add_parser("auto", help="Run post scan once")
    sub.add_parser("status", help="Show engine status and stats")

    daemon_parser = sub.add_parser("daemon", help="Run continuously")
    daemon_parser.add_argument("--interval", type=int, default=2, help="Minutes between cycles (default: 2)")

    args = parser.parse_args()

    # Kill switch — refuse to run if disabled
    if SKOOL_DISABLED:
        msg = "Skool Engine is DISABLED (kill switch active since 2026-03-25). To re-enable, set SKOOL_DISABLED = False in skool_engine.py."
        log.warning(msg)
        if args.json if hasattr(args, 'json') else False:
            safe_print(json.dumps({"status": "disabled", "message": msg}))
        else:
            safe_print(msg)
        sys.exit(0)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "login": cmd_login,
        "scan-posts": cmd_scan_posts,
        "auto": cmd_auto,
        "daemon": cmd_daemon,
        "status": cmd_status,
    }

    handler = commands.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(1)

    result = handler(args)

    if args.json and result and args.command not in ("status",):
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
