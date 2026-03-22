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
  python scripts/skool_engine.py scan-dms           # Reply to incoming DMs
  python scripts/skool_engine.py engage-members     # DM members (welcome paid, nurture free)
  python scripts/skool_engine.py auto               # Run all scans once
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
MEMBER_STATE_PATH = TMP_DIR / "skool_member_state.json"
DM_CONVERSATIONS_PATH = TMP_DIR / "skool_dm_conversations.json"
DAEMON_PID_PATH = TMP_DIR / "skool_daemon.pid"

COMMUNITY_URL = "https://www.skool.com/agency-accelerants-6209"
COMMUNITY_FEED_URL = COMMUNITY_URL
MEMBERS_URL = f"{COMMUNITY_URL}/-/members"

# Engagement intervals (hours) — how long between follow-up DMs
FREE_MEMBER_FOLLOWUP_HOURS = 48      # Nurture free members every 48h
PAID_MEMBER_FOLLOWUP_HOURS = 168     # Check in with paid members weekly
DM_REPLY_COOLDOWN_HOURS = 1          # Don't auto-reply to same person within 1h
MAX_DMS_PER_CYCLE = 3                # Max DMs per scan cycle (avoid spam flags)
MAX_REPLIES_PER_CYCLE = 5            # Max post replies per scan cycle (avoid API overload)
ENGAGEMENT_EVERY_N_CYCLES = 5        # Member engagement runs every Nth cycle (~10 min at 2-min interval)

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
# State persistence
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
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


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
# Member extraction from Skool DOM
# ---------------------------------------------------------------------------

def _extract_members_from_page(page) -> list[dict]:
    """Extract members from the currently loaded members page."""
    # Scroll to ensure all members on this page are rendered
    for _ in range(8):
        page.evaluate("window.scrollBy(0, 800)")
        time.sleep(0.6)

    return page.evaluate(r"""() => {
        const wrappers = document.querySelectorAll('.styled__MemberItemWrapper-sc-qwyv4g-0');
        const members = [];
        for (const w of wrappers) {
            const text = w.textContent;
            const linkEl = w.querySelector('a[href*="/@"]');
            const href = linkEl?.getAttribute('href') || '';
            const username = href.split('/@').pop()?.split('?')[0] || '';
            if (!username) continue;

            // Name: find the first /@-link whose text is longer than 2 chars (skips level number)
            const allNameLinks = w.querySelectorAll('a[href*="/@"]');
            let name = '';
            for (const a of allNameLinks) {
                const t = a.textContent.trim();
                if (t.length > 2) { name = t; break; }
            }

            const isPaid = text.includes('$97/month');
            const isFree = text.includes('Free');
            const joinedMatch = text.match(/Joined ([\w\s,]+?\d{4})/);
            const joined = joinedMatch ? joinedMatch[1] : '';
            const activeMatch = text.match(/(Active \w+ ago)/);
            const active = activeMatch ? activeMatch[1] : '';
            const sourceMatch = text.match(/Joined from (\w+)/);
            const source = sourceMatch ? sourceMatch[1] : '';
            const levelMatch = text.match(/^(\d+)/);
            const level = levelMatch ? parseInt(levelMatch[1]) : 0;

            members.push({ username, name, isPaid, isFree, joined, active, source, level });
        }
        return members;
    }""")


def extract_members(page) -> list[dict]:
    """Extract all members across all paginated pages with paid/free status."""
    page.goto(MEMBERS_URL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)

    all_members = []
    seen_usernames = set()
    max_pages = 10  # Safety limit

    for page_num in range(1, max_pages + 1):
        page_members = _extract_members_from_page(page)
        new_count = 0
        for m in page_members:
            if m["username"] not in seen_usernames:
                seen_usernames.add(m["username"])
                all_members.append(m)
                new_count += 1

        log.info(f"Members page {page_num}: {new_count} new members ({len(all_members)} total)")

        if new_count == 0:
            break

        # Click "Next" button to go to the next page
        has_next = page.evaluate(r"""() => {
            const btns = [...document.querySelectorAll('button')];
            const nextBtn = btns.find(b => b.textContent.trim() === 'Next' && !b.disabled);
            if (nextBtn) { nextBtn.click(); return true; }
            return false;
        }""")

        if not has_next:
            log.info("No more pages — all members extracted")
            break

        time.sleep(3)
        # Scroll back to top for the new page
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(1)

    log.info(f"Total members extracted: {len(all_members)} "
             f"({sum(1 for m in all_members if m.get('isPaid'))} paid, "
             f"{sum(1 for m in all_members if m.get('isFree'))} free)")
    return all_members


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


def generate_post_reply(post_title: str, post_content: str, author_name: str) -> str:
    """Generate a community post comment in CC's coaching voice."""
    system = (
        "You are ghostwriting a Skool community comment as Conaugh McKenna (CC), "
        "a 22-year-old AI automation entrepreneur and admin/coach of the Agency Accelerants community. "
        "CC runs OASIS AI Solutions — he builds AI systems for local businesses.\n\n"
        "VOICE RULES (non-negotiable):\n"
        "- You are a COACH. Excited, enthusiastic, optimistic for the builders.\n"
        "- Celebrate their wins. Acknowledge their effort. Push them to keep going.\n"
        "- Be genuine and warm but not cheesy. No corporate speak.\n"
        "- Write like a friend who genuinely cares.\n"
        "- Can use: 'lets go', 'this is fire', 'huge', 'love this', 'honestly', 'for real'\n"
        "- Keep it to 2-4 sentences. Punchy, not essays.\n"
        "- If they're sharing a win → hype them authentically.\n"
        "- If they're asking a question → direct helpful answer.\n"
        "- If they're sharing a struggle → empathetic + one actionable tip.\n"
        "- NEVER use hashtags. NEVER pitch services. NEVER be salesy.\n"
        "- Use exclamation marks sparingly. Address them by first name.\n\n"
        "Reply with ONLY the comment text."
    )
    user = (
        f"Community member {author_name} posted:\n"
        f"Title: {post_title}\n"
        f"Content: {post_content[:800]}\n\n"
        f"Write a coaching reply:"
    )
    reply = _call_claude(system, user)
    return reply[:1000] if reply else ""


def generate_welcome_dm(member_name: str, is_paid: bool) -> str:
    """Generate a welcome DM — different tone for paid vs free members."""
    if is_paid:
        system = (
            "You are ghostwriting a Skool DM as Conaugh McKenna (CC), admin of Agency Accelerants. "
            "A new PAID member ($97/month) just joined.\n\n"
            "VOICE RULES:\n"
            "- Warm, excited, personal. They invested in themselves — acknowledge that.\n"
            "- 2-3 sentences max. Lowercase, casual, genuine.\n"
            "- Tell them you're stoked they joined, ask what they're working on or what made them join.\n"
            "- Mention they now have full access to coaching calls and the course.\n"
            "- NEVER sound like a template.\n"
            "- Address them by first name.\n\n"
            "Reply with ONLY the message text."
        )
    else:
        system = (
            "You are ghostwriting a Skool DM as Conaugh McKenna (CC), admin of Agency Accelerants. "
            "A new FREE member just joined the community.\n\n"
            "VOICE RULES:\n"
            "- Warm and welcoming. You're genuinely glad they're here.\n"
            "- 2-3 sentences max. Lowercase, casual, genuine.\n"
            "- Ask what brought them to the community and what they're building.\n"
            "- Be curious about THEM — don't pitch the paid plan yet. Just build rapport.\n"
            "- NEVER mention pricing, paid plans, or upgrades in the first message.\n"
            "- Address them by first name.\n\n"
            "Reply with ONLY the message text."
        )

    user = f"New member name: {member_name}\nMembership: {'Paid $97/mo' if is_paid else 'Free'}\n\nWrite a welcome DM:"
    reply = _call_claude(system, user, max_tokens=100)
    if not reply:
        first = member_name.split()[0] if member_name else "hey"
        return f"hey {first}! welcome to the community, really glad you're here. what are you working on?"
    return reply


def generate_nurture_dm(member_name: str, convo_history: str, interaction_count: int) -> str:
    """Generate a follow-up nurture DM for free members to build rapport and eventually convert."""
    stage_context = ""
    if interaction_count <= 1:
        stage_context = (
            "STAGE: First follow-up. You've already said hello. Now go deeper — "
            "ask about their business, what challenges they're facing, what they want to achieve. "
            "Be genuinely curious. NO selling."
        )
    elif interaction_count <= 3:
        stage_context = (
            "STAGE: Building rapport. You've chatted a couple times. Share a quick insight or tip "
            "related to what they're working on. Mention something helpful from the community "
            "(a post, a lesson, a coaching call topic). Be a resource, not a salesman."
        )
    elif interaction_count <= 5:
        stage_context = (
            "STAGE: Value demonstration. You've built some rapport. Now naturally mention something "
            "exclusive to paid members (like the coaching calls, the full course content, or a specific "
            "lesson that would help with their exact problem). Frame it as 'hey thought of you, this "
            "might help' — not a pitch. Soft, authentic, value-first."
        )
    else:
        stage_context = (
            "STAGE: Gentle nudge. You've been chatting for a while. If they haven't upgraded yet, "
            "give them a genuine reason to consider it — like 'honestly the coaching calls alone "
            "are worth it, we covered [relevant topic] last week and it was exactly the kind of thing "
            "you were asking about'. No pressure, just real talk."
        )

    system = (
        "You are ghostwriting a Skool DM as Conaugh McKenna (CC), admin of Agency Accelerants. "
        "You're having an ongoing conversation with a FREE member, building rapport toward them "
        "eventually seeing the value in the $97/month paid plan.\n\n"
        f"{stage_context}\n\n"
        "VOICE RULES:\n"
        "- Warm, genuine, coaching energy. You care about their success.\n"
        "- 1-3 sentences. Short and natural.\n"
        "- Lowercase, casual. Can use: ya, honestly, for real, lets go, thats sick\n"
        "- NEVER be pushy, salesy, or use marketing language.\n"
        "- If they haven't responded to a previous message, don't double-text the same energy. "
        "Try a different angle or share something valuable.\n\n"
        "Reply with ONLY the message text."
    )

    user = f"Conversation history with {member_name}:\n{convo_history[-1000:]}\n\nWrite your next message:"
    reply = _call_claude(system, user, max_tokens=150)
    return reply[:500] if reply else ""


def generate_dm_reply(member_name: str, their_message: str, convo_context: str = "",
                      is_paid: bool = True) -> str:
    """Generate a DM reply to an incoming message."""
    paid_context = (
        "This is a PAID member ($97/month). They have full access to coaching calls and courses. "
        "Be supportive, helpful, and make them feel the value of their investment."
        if is_paid else
        "This is a FREE member. Be helpful and build rapport. If they ask about courses or "
        "coaching calls, let them know those are available with the paid membership — but only "
        "if THEY bring it up first. Never push."
    )

    context_block = ""
    if convo_context:
        context_block = f"\nRecent conversation:\n{convo_context[-800:]}\n"

    system = (
        "You are ghostwriting a Skool DM reply as Conaugh McKenna (CC), "
        "admin of the Agency Accelerants Skool community.\n\n"
        f"{paid_context}\n\n"
        "VOICE RULES:\n"
        "- Friendly, warm, coaching energy. Genuinely care about their success.\n"
        "- Short and direct — 1-3 sentences.\n"
        "- Lowercase mostly. No corporate speak.\n"
        "- Can use: ya, for sure, honestly, lets go, thats sick, love that\n"
        "- Be helpful. Answer questions directly.\n"
        "- NEVER use hashtags.\n\n"
        "Reply with ONLY the message text."
    )

    user = f"{context_block}{member_name} says: \"{their_message}\"\n\nYour reply:"
    reply = _call_claude(system, user, max_tokens=150)
    return reply[:500] if reply else ""


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
# Member engagement (welcome + nurture)
# ---------------------------------------------------------------------------

def cmd_engage_members(args, page=None, ctx=None):
    """Engage all members: welcome new ones, nurture free ones toward conversion."""
    from playwright.sync_api import sync_playwright

    member_state = _load_json(MEMBER_STATE_PATH)
    convos = _load_json(DM_CONVERSATIONS_PATH)
    results = {"scanned": 0, "welcomed": 0, "nurtured": 0, "skipped": 0, "errors": []}
    dm_count = 0
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
        members = extract_members(page)
        free_count = sum(1 for m in members if m.get("isFree"))
        paid_count = sum(1 for m in members if m.get("isPaid"))
        log.info(f"Found {len(members)} members ({paid_count} paid, {free_count} free)")
        results["scanned"] = len(members)

        # FREE members FIRST — they're the conversion targets
        # Sort: free+never-contacted first, then free+contacted, then paid
        def _engage_priority(m):
            is_free = m.get("isFree", not m.get("isPaid", False))
            username = m.get("username", "")
            interaction_count = member_state.get(username, {}).get("interaction_count", 0)
            # Lower = higher priority: (0=free, 1=paid), interaction_count
            return (0 if is_free else 1, interaction_count)

        members.sort(key=_engage_priority)

        for member in members:
            if dm_count >= MAX_DMS_PER_CYCLE:
                log.info(f"Hit DM limit ({MAX_DMS_PER_CYCLE}), stopping for this cycle")
                break

            username = member.get("username", "")
            name = member.get("name", "") or username
            is_free = member.get("isFree", not member.get("isPaid", False))
            is_paid = not is_free

            if not username:
                continue

            # Skip self and admins
            skip_names = {"conaugh", "bennett", "eric-scott", "christian-mb"}
            if any(s in username.lower() for s in skip_names):
                results["skipped"] += 1
                continue

            state = member_state.get(username, {})
            interaction_count = state.get("interaction_count", 0)
            last_dm_ts = state.get("last_dm_ts", "")

            # Check timing
            if last_dm_ts:
                try:
                    last_dt = datetime.fromisoformat(last_dm_ts)
                    hours_since = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
                    cooldown = PAID_MEMBER_FOLLOWUP_HOURS if is_paid else FREE_MEMBER_FOLLOWUP_HOURS

                    # First message has no cooldown (welcome DM)
                    if interaction_count > 0 and hours_since < cooldown:
                        results["skipped"] += 1
                        continue
                except ValueError:
                    pass

            # Determine action
            if interaction_count == 0:
                # First contact — welcome DM
                log.info(f"Welcoming {'paid' if is_paid else 'free'} member {name} (@{username})")
                message = generate_welcome_dm(name, is_paid)
                action = "welcome"
            elif not is_paid:
                # Free member — nurture toward conversion
                convo_history = convos.get(username, {}).get("history", "")
                log.info(f"Nurturing free member {name} (@{username}) [interaction #{interaction_count + 1}]")
                message = generate_nurture_dm(name, convo_history, interaction_count)
                action = "nurture"
            else:
                # Paid member — periodic check-in (only if they haven't been active)
                active_str = member.get("active", "")
                if "1d" not in active_str and "h" not in active_str:
                    convo_history = convos.get(username, {}).get("history", "")
                    log.info(f"Checking in with paid member {name} (@{username})")
                    message = generate_nurture_dm(name, convo_history, interaction_count)
                    action = "checkin"
                else:
                    results["skipped"] += 1
                    continue

            if not message:
                results["errors"].append(f"No message for @{username}")
                continue

            log.info(f"  Message: {message[:80]}...")

            if args.dry_run:
                log.info(f"  [dry-run] Would send {action} DM")
                if action == "welcome":
                    results["welcomed"] += 1
                else:
                    results["nurtured"] += 1
                dm_count += 1
                continue

            # Send the DM via member profile Chat button
            sent = _send_dm_to_member(page, username, message)
            if sent:
                log.info(f"  DM sent ({action})")
                now = _now()

                # Update member state
                member_state[username] = {
                    "name": name,
                    "is_paid": is_paid,
                    "interaction_count": interaction_count + 1,
                    "last_dm_ts": now,
                    "last_action": action,
                    "source": member.get("source", ""),
                    "joined": member.get("joined", ""),
                }

                # Track conversation history
                if username not in convos:
                    convos[username] = {"history": "", "messages": []}
                convos[username]["history"] += f"\nCC: {message}"
                convos[username]["messages"].append({
                    "from": "CC", "text": message, "ts": now, "action": action
                })

                if action == "welcome":
                    results["welcomed"] += 1
                else:
                    results["nurtured"] += 1

                dm_count += 1
                category = "content"
                notify(f"Skool {action} DM to {name}: {message[:60]}...", category=category)
            else:
                results["errors"].append(f"Failed to DM @{username}")

            time.sleep(3)

    finally:
        if own_ctx:
            ctx.close()
            pw_mgr.stop()

    _save_json(MEMBER_STATE_PATH, member_state)
    _save_json(DM_CONVERSATIONS_PATH, convos)
    return results


def _send_dm_to_member(page, username: str, message: str) -> bool:
    """Navigate to member profile, click Chat, type and send a DM."""
    try:
        # Must include ?g= group context for the Chat button to appear
        profile_url = f"https://www.skool.com/@{username}?g=agency-accelerants-6209"
        page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)

        # Click the Chat button on their profile sidebar
        chat_clicked = page.evaluate("""() => {
            const btns = [...document.querySelectorAll('button')];
            for (const btn of btns) {
                const txt = btn.textContent?.trim();
                if (txt === 'Chat' || txt === 'chat' || txt === 'Message') {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")

        if not chat_clicked:
            log.warning(f"Chat button not found for @{username}")
            return False

        time.sleep(3)

        # Type and send
        return _type_and_send_dm(page, message)
    except Exception as e:
        log.error(f"DM to @{username} failed: {e}")
        return False


def _type_and_send_dm(page, text: str) -> bool:
    """Type a DM into the chat input and send it (profile Chat button flow)."""
    try:
        # Find and click chat input
        page.evaluate("""() => {
            const inputs = document.querySelectorAll('[contenteditable="true"], textarea, .ProseMirror');
            for (const inp of inputs) {
                if (inp.closest('[class*="Chat"]') || inp.closest('[class*="Message"]') ||
                    inp.closest('[class*="Dm"]') || inp.closest('[class*="Conversation"]')) {
                    inp.click();
                    inp.focus();
                    return true;
                }
            }
            // Fallback — any contenteditable
            const ce = document.querySelector('[contenteditable="true"]');
            if (ce) { ce.click(); ce.focus(); return true; }
            return false;
        }""")
        time.sleep(0.5)

        page.keyboard.type(text, delay=12)
        time.sleep(0.5)

        page.keyboard.press("Enter")
        time.sleep(2)
        return True
    except Exception as e:
        log.error(f"DM send failed: {e}")
        return False


def _type_and_send_chat(page, member_name: str, text: str) -> bool:
    """Type a reply into the Skool chat conversation textbox and send it.

    The chat page has a textbox with aria-label "Message <Name>" at the bottom.
    """
    try:
        # Try to find the textbox by aria-label first
        textbox = page.get_by_role("textbox", name=f"Message {member_name}")
        if textbox.count() == 0:
            # Fallback: any textbox on the page
            textbox = page.get_by_role("textbox")

        textbox.first.click()
        time.sleep(0.3)
        textbox.first.fill("")  # Clear any existing text
        page.keyboard.type(text, delay=12)
        time.sleep(0.5)
        page.keyboard.press("Enter")
        time.sleep(2)
        return True
    except Exception as e:
        log.error(f"Chat send to {member_name} failed: {e}")
        # Fallback to the old method
        return _type_and_send_dm(page, text)



# ---------------------------------------------------------------------------
# DM scanning (auto-reply to incoming)
# ---------------------------------------------------------------------------

def _open_chat_sidebar(page) -> bool:
    """Click the chat icon button in the top nav bar to open the chat sidebar.

    The chat button is an unnamed icon-only button in the top-right nav bar,
    next to the notification bell and user avatar. It contains only an <img>.
    After clicking, a sidebar panel appears with "Chats" header and conversation links.
    """
    pos = page.evaluate(r"""() => {
        const allBtns = [...document.querySelectorAll('button')];
        const navSvgBtns = allBtns.filter(b => {
            const hasSvg = b.querySelector('svg') !== null;
            const hasImg = b.querySelector('img') !== null;
            const text = b.textContent.trim();
            const rect = b.getBoundingClientRect();
            return hasSvg && !hasImg && text.length === 0 &&
                   rect.top >= 0 && rect.top < 60 && rect.left > 500;
        });
        navSvgBtns.sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);
        if (navSvgBtns.length > 0) {
            const r = navSvgBtns[0].getBoundingClientRect();
            return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
        }
        return null;
    }""")
    if pos:
        page.mouse.click(pos["x"], pos["y"])
        time.sleep(3)
    else:
        log.error("Chat sidebar button not found in nav bar")
        return False

    # Verify sidebar opened by checking for "Chats" text
    has_sidebar = page.evaluate(r"""() => {
        return document.body.innerText.includes('Chats') &&
               !!document.querySelector('a[href*="/chat?ch="]');
    }""")
    return has_sidebar


def _get_chat_conversations(page) -> list[dict]:
    """Extract conversation list from the open chat sidebar.

    Returns list of {name, href, channelId, lastMessage, lastMessageTime}.
    Filters to only Agency Accelerants community conversations.
    """
    return page.evaluate(r"""() => {
        // Chat sidebar conversations are links with href pattern /chat?ch=<id>&clr=<id>
        const links = document.querySelectorAll('a[href*="/chat?ch="]');
        const convos = [];
        const seen = new Set();
        for (const link of links) {
            const href = link.getAttribute('href') || '';
            if (seen.has(href)) continue;
            seen.add(href);

            // Extract name from link text — skip timestamps and short text
            const textNodes = link.querySelectorAll('*');
            let name = '';
            for (const el of textNodes) {
                const t = el.textContent?.trim() || '';
                // Name is usually the longest meaningful text that's not a timestamp
                if (t.length > 2 && t.length < 50 && !t.match(/^\d+[smhd]$/) &&
                    !t.match(/^\d{1,2}:\d{2}/) && !t.includes('ago') &&
                    t !== 'All' && t !== 'Chats') {
                    if (t.length > name.length) name = t;
                }
            }

            // Get last message preview
            const allText = link.textContent || '';
            const lastMsg = allText.replace(name, '').trim().substring(0, 100);

            // Check for unread indicator (bold text or badge)
            const hasUnread = !!(link.querySelector('[class*="unread"], [class*="Unread"], [class*="badge"], [class*="Badge"]') ||
                                 link.querySelector('strong, b'));

            const chMatch = href.match(/ch=([^&]+)/);
            const channelId = chMatch ? chMatch[1] : '';

            if (name && channelId) {
                convos.push({ name, href, channelId, lastMessage: lastMsg, hasUnread });
            }
        }
        return convos;
    }""")


def _read_conversation_messages(page) -> dict | None:
    """Read messages from the currently open chat conversation.

    Detects incoming vs outgoing by checking profile links:
    - Links containing /@conaugh-mckenna = outgoing (CC's messages)
    - Any other profile link = incoming (their messages)

    Returns {lastIncoming, needsReply, context} or None.
    """
    try:
        # Wait for chat messages to load
        page.wait_for_selector('a[href*="/@"]', timeout=8000)
    except Exception:
        return None

    return page.evaluate(r"""() => {
        // Find all profile links — each represents a message sender
        const profileLinks = [...document.querySelectorAll('a[href*="/@"]')];
        if (!profileLinks.length) return null;

        // Each message block: profile link (sender) + surrounding text (message)
        // Walk profile links and extract message data
        const entries = [];
        const processed = new Set();

        for (const link of profileLinks) {
            const href = link.getAttribute('href') || '';
            if (!href.includes('/@')) continue;
            const isMine = href.includes('/@conaugh-mckenna');

            // Find the message container — walk up to find a meaningful parent
            let container = link.parentElement;
            // Walk up max 5 levels to find a container with substantial text
            for (let i = 0; i < 5 && container; i++) {
                const text = container.textContent || '';
                if (text.length > 20 && !processed.has(container)) break;
                container = container.parentElement;
            }
            if (!container || processed.has(container)) continue;
            processed.add(container);

            // Extract message text: full container text minus the sender name and timestamps
            const fullText = container.textContent?.trim() || '';
            const linkText = link.textContent?.trim() || '';
            let msgText = fullText;
            // Remove sender name
            if (linkText) msgText = msgText.replace(linkText, '');
            // Remove timestamps
            msgText = msgText.replace(/\d{1,2}:\d{2}\s*(AM|PM)?/gi, '').trim();
            msgText = msgText.replace(/\d+[smhd]\s+ago/gi, '').trim();
            msgText = msgText.replace(/^[\s•·]+/, '').trim();

            if (msgText.length > 1) {
                entries.push({ isMine, text: msgText.substring(0, 300) });
            }
        }

        if (!entries.length) return null;

        const recent = entries.slice(-10);
        const context = recent.map(e => (e.isMine ? 'CC: ' : 'Them: ') + e.text).join('\n');
        const lastEntry = recent[recent.length - 1];

        // Find the most recent incoming message
        let lastIncoming = null;
        for (let i = recent.length - 1; i >= 0; i--) {
            if (!recent[i].isMine) { lastIncoming = recent[i].text; break; }
        }

        return {
            lastIncoming,
            needsReply: !lastEntry.isMine,
            context
        };
    }""")


def cmd_scan_dms(args, page=None, ctx=None):
    """Check for incoming Skool DMs and auto-reply (closed-loop).

    Flow:
    1. Navigate to community feed
    2. Open chat sidebar via chat icon button
    3. Extract conversation list
    4. For each conversation where the last message is from THEM (not CC):
       a. Navigate to /chat?ch=<id>
       b. Read message history, detect incoming vs outgoing via profile links
       c. Generate reply via Claude API
       d. Type into message textbox and send
    5. Filter to Agency Accelerants members only (cross-ref member state)
    """
    from playwright.sync_api import sync_playwright

    member_state = _load_json(MEMBER_STATE_PATH)
    convos = _load_json(DM_CONVERSATIONS_PATH)
    results = {"checked": 0, "replied": 0, "skipped": 0, "errors": []}
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
        # Step 1: Ensure we're on the community feed page
        current = page.url or ""
        if "agency-accelerants" not in current:
            page.goto(COMMUNITY_FEED_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)
        else:
            time.sleep(2)

        # Step 2: Open chat sidebar (retry up to 2 times)
        sidebar_open = False
        for attempt in range(2):
            if _open_chat_sidebar(page):
                sidebar_open = True
                break
            log.info(f"Chat sidebar attempt {attempt + 1} failed, retrying...")
            time.sleep(2)

        if not sidebar_open:
            log.warning("Could not open chat sidebar — trying direct /chat URL")
            page.goto("https://www.skool.com/chat", wait_until="networkidle", timeout=30000)
            time.sleep(4)

        # Step 3: Extract conversations
        chat_items = _get_chat_conversations(page)
        log.info(f"Found {len(chat_items)} DM conversations in sidebar")
        results["checked"] = len(chat_items)

        # Build set of known community members for filtering
        known_members = set(member_state.keys())

        reply_count = 0
        for item in chat_items:
            if reply_count >= MAX_REPLIES_PER_CYCLE:
                log.info(f"Hit DM reply limit ({MAX_REPLIES_PER_CYCLE}), stopping")
                break

            name = item.get("name", "Unknown")
            href = item.get("href", "")

            # Try to match conversation to a known community member
            name_slug = name.lower().replace(" ", "-")
            # Match against known member usernames (fuzzy — name slug may differ from username)
            matched_username = None
            for uname in known_members:
                # Match if the name slug is a prefix of the username or vice versa
                if name_slug in uname or uname.startswith(name_slug.split("-")[0]):
                    matched_username = uname
                    break

            # Check cooldown
            state = member_state.get(matched_username or name_slug, {})
            last_ts = state.get("last_dm_ts", "")
            if last_ts:
                try:
                    hours_ago = (datetime.now(timezone.utc) - datetime.fromisoformat(last_ts)).total_seconds() / 3600
                    if hours_ago < DM_REPLY_COOLDOWN_HOURS:
                        results["skipped"] += 1
                        continue
                except ValueError:
                    pass

            # Step 4: Open conversation to read messages
            chat_url = f"https://www.skool.com{href}" if href.startswith("/") else href
            page.goto(chat_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            # Read message history and detect if reply is needed
            msg_data = _read_conversation_messages(page)

            if not msg_data or not msg_data.get("needsReply"):
                results["skipped"] += 1
                continue

            their_msg = msg_data.get("lastIncoming", "")
            if not their_msg:
                results["skipped"] += 1
                continue

            context = msg_data.get("context", "")
            is_paid = state.get("is_paid", False)
            username = matched_username or name_slug

            log.info(f"  Unreplied DM from {name}: {their_msg[:80]}...")

            reply = generate_dm_reply(name, their_msg, context, is_paid)
            if not reply:
                results["errors"].append(f"No reply generated for {name}")
                continue

            log.info(f"  Reply: {reply[:80]}...")

            if args.dry_run:
                results["replied"] += 1
                reply_count += 1
                continue

            # Type reply into the message textbox
            sent = _type_and_send_chat(page, name, reply)
            if sent:
                log.info(f"  DM reply sent to {name}")
                now = _now()

                # Update conversation tracking
                if username not in convos:
                    convos[username] = {"history": "", "messages": []}
                convos[username]["history"] += f"\nThem: {their_msg}\nCC: {reply}"
                convos[username]["messages"].append({"from": "Them", "text": their_msg, "ts": now})
                convos[username]["messages"].append({"from": "CC", "text": reply, "ts": now})

                # Update member state
                if username in member_state:
                    member_state[username]["last_dm_ts"] = now
                    member_state[username]["interaction_count"] = state.get("interaction_count", 0) + 1
                else:
                    member_state[username] = {
                        "name": name, "is_paid": is_paid,
                        "interaction_count": 1, "last_dm_ts": now,
                        "last_action": "dm_reply",
                    }

                results["replied"] += 1
                reply_count += 1
                notify(f"Skool DM reply to {name}: {reply[:60]}...", category="content")
            else:
                results["errors"].append(f"Failed to send reply to {name}")

            time.sleep(2)

    finally:
        if own_ctx:
            ctx.close()
            pw_mgr.stop()

    _save_json(MEMBER_STATE_PATH, member_state)
    _save_json(DM_CONVERSATIONS_PATH, convos)
    return results


# ---------------------------------------------------------------------------
# Auto & Daemon modes
# ---------------------------------------------------------------------------

def cmd_auto(args, page=None, ctx=None, cycle=0):
    """Run all scans in sequence with shared browser context.

    Args:
        page/ctx: Optional pre-existing browser page/context (daemon mode reuses these).
        cycle: Current daemon cycle number. Member engagement only runs every
               ENGAGEMENT_EVERY_N_CYCLES cycles (0 = always run, for standalone use).
    """
    from playwright.sync_api import sync_playwright

    log.info("=== Skool Engine: Auto Scan ===")
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

        # Member engagement is heavier (DMs) — only run every Nth cycle
        run_engagement = (cycle == 0) or (cycle % ENGAGEMENT_EVERY_N_CYCLES == 1)
        if run_engagement:
            log.info("\n--- Engaging members ---")
            all_results["members"] = cmd_engage_members(args, page=page, ctx=ctx)
        else:
            log.info(f"\n--- Skipping member engagement (cycle {cycle}, next at cycle {cycle + (ENGAGEMENT_EVERY_N_CYCLES - (cycle - 1) % ENGAGEMENT_EVERY_N_CYCLES)}) ---")
            all_results["members"] = {}

        log.info("\n--- Scanning DMs ---")
        all_results["dms"] = cmd_scan_dms(args, page=page, ctx=ctx)

    except Exception as e:
        log.error(f"Auto scan error: {e}")
        raise
    finally:
        if own_ctx:
            ctx.close()
            pw_mgr.stop()

    # Summary
    p = all_results.get("posts", {})
    m = all_results.get("members", {})
    d = all_results.get("dms", {})
    total = p.get("replied", 0) + m.get("welcomed", 0) + m.get("nurtured", 0) + d.get("replied", 0)

    log.info(f"\n=== Summary ===")
    log.info(f"Posts replied: {p.get('replied', 0)}/{p.get('scanned', 0)}")
    log.info(f"Members welcomed: {m.get('welcomed', 0)} | Nurtured: {m.get('nurtured', 0)}")
    log.info(f"DMs replied: {d.get('replied', 0)}/{d.get('checked', 0)}")
    log.info(f"Total actions: {total}")

    if total > 0:
        notify(
            f"Skool scan: {p.get('replied', 0)} post replies, "
            f"{m.get('welcomed', 0)} welcomes, {m.get('nurtured', 0)} nurtures, "
            f"{d.get('replied', 0)} DM replies",
            category="content",
        )

    return all_results


def cmd_daemon(args):
    """Run continuously in daemon mode with persistent browser and configurable interval."""
    from playwright.sync_api import sync_playwright

    interval = getattr(args, "interval", 2) or 2
    log.info(f"=== Skool Engine: Daemon Mode (every {interval} min) ===")
    log.info(f"Member engagement every {ENGAGEMENT_EVERY_N_CYCLES} cycles (~{interval * ENGAGEMENT_EVERY_N_CYCLES} min)")
    log.info("Press Ctrl+C to stop")

    # Write PID file for tracking
    _save_json(DAEMON_PID_PATH, {"pid": os.getpid(), "started": _now(), "interval": interval})

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

    # Cleanup PID file
    if DAEMON_PID_PATH.exists():
        DAEMON_PID_PATH.unlink()

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
    """Show current engine state and member stats."""
    member_state = _load_json(MEMBER_STATE_PATH)
    convos = _load_json(DM_CONVERSATIONS_PATH)
    replied_posts = _load_json(REPLIED_POSTS_PATH)

    total_members = len(member_state)
    paid = sum(1 for m in member_state.values() if m.get("is_paid"))
    free = total_members - paid
    total_interactions = sum(m.get("interaction_count", 0) for m in member_state.values())
    total_convos = len(convos)
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
        "members_tracked": total_members,
        "paid_members": paid,
        "free_members": free,
        "total_interactions": total_interactions,
        "active_conversations": total_convos,
        "posts_replied": total_posts_replied,
    }

    if args.json:
        print(json.dumps(status, indent=2, default=str))
    else:
        safe_print(f"Daemon: {'RUNNING' if daemon_running else 'STOPPED'}")
        if daemon_running:
            safe_print(f"  PID: {daemon_info.get('pid')} | Interval: {daemon_info.get('interval')}min")
            safe_print(f"  Started: {daemon_info.get('started', 'unknown')}")
        safe_print(f"Members tracked: {total_members} ({paid} paid, {free} free)")
        safe_print(f"Total interactions: {total_interactions}")
        safe_print(f"Active conversations: {total_convos}")
        safe_print(f"Posts replied: {total_posts_replied}")

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
    sub.add_parser("scan-dms", help="Reply to incoming DMs")
    sub.add_parser("engage-members", help="Welcome + nurture members")
    sub.add_parser("auto", help="Run all scans once")
    sub.add_parser("status", help="Show engine status and stats")

    daemon_parser = sub.add_parser("daemon", help="Run continuously")
    daemon_parser.add_argument("--interval", type=int, default=2, help="Minutes between cycles (default: 2)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "login": cmd_login,
        "scan-posts": cmd_scan_posts,
        "scan-dms": cmd_scan_dms,
        "engage-members": cmd_engage_members,
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
