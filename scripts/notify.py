"""
Bravo Notification System - Telegram alerts for CC.

V3 (2026-04-12): Human-readable format. No brackets. No JSON. No system status.
Every message must pass the "3-second glance test": CC should understand it
immediately on his phone without decoding anything.

Usage:
    from notify import notify
    notify("New lead: John from Acme HVAC just submitted the funnel form", category="lead")
    notify("Stripe: $800 payment received from Bennett Agency", category="revenue")

Categories: lead, email, booking, content, revenue, outreach, instagram, system, skool-escalation

FILTERING: Only high-signal categories reach CC's Telegram.
- ALWAYS SEND (with sound): lead, booking, revenue, skool-escalation
- SILENT (no sound): email, outreach
- BLOCKED (never send): content, instagram, system
Override via NOTIFY_BLOCKED_CATEGORIES in .env.agents (comma-separated).
"""

import sys
from pathlib import Path
from datetime import datetime

# Load .env.agents
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env.agents"

_env_cache: dict[str, str] = {}

# Categories that are blocked from Telegram by default.
# CC only wants: new leads, DMs needing attention, booked meetings, errors.
DEFAULT_BLOCKED = {"content", "instagram", "system"}
# Categories that send silently (no notification sound)
DEFAULT_SILENT = {"email", "outreach"}


def _load_env() -> dict[str, str]:
    global _env_cache
    if _env_cache:
        return _env_cache
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    _env_cache[key.strip()] = value.strip()
    return _env_cache


def _get_blocked_categories() -> set[str]:
    env = _load_env()
    override = env.get("NOTIFY_BLOCKED_CATEGORIES", "")
    if override:
        return {c.strip().lower() for c in override.split(",") if c.strip()}
    return DEFAULT_BLOCKED


# V3 2026-04-12: Human-readable category labels. No brackets, no all-caps.
# CC's feedback: "the format is gross, I don't know what [REVENUE] means,
# it goes over my head." New format: clean emoji + plain English label.
CATEGORY_PREFIX = {
    "lead": "New Lead",
    "email": "Email",
    "booking": "Booking",
    "content": "Content",
    "revenue": "Revenue",
    "outreach": "Outreach",
    "instagram": "Instagram",
    "system": "System",
    "skool-escalation": "Skool (needs you)",
}


def notify(message: str, category: str = "system", silent: bool = False, force: bool = False) -> bool:
    """
    Send a Telegram notification to CC.

    Args:
        message: The notification text
        category: One of lead/email/booking/content/revenue/outreach/instagram/system
        silent: If True, send without sound (disable_notification=True)
        force: If True, bypass category filtering (for critical alerts)

    Returns:
        True if sent successfully, False otherwise
    """
    # Block noisy categories unless forced
    if not force and category in _get_blocked_categories():
        return False

    # Auto-silence low-priority categories
    if category in DEFAULT_SILENT:
        silent = True

    env = _load_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    # V2.1 2026-04-11: Guarded chat_id parsing. Old code used
    # `.split(",")[0].strip()` which returned "" on empty/whitespace env
    # and silently failed at Telegram send. Now we filter valid IDs and
    # log a visible error when none are found.
    raw_users = env.get("TELEGRAM_ALLOWED_USERS", "")
    chat_ids = [c.strip() for c in raw_users.split(",") if c.strip()]

    if not token:
        print("[notify] TELEGRAM_BOT_TOKEN missing in .env.agents", file=sys.stderr)
        return False
    if not chat_ids:
        print("[notify] TELEGRAM_ALLOWED_USERS empty or malformed in .env.agents", file=sys.stderr)
        return False
    chat_id = chat_ids[0]

    try:
        import requests
    except ImportError:
        return False

    # V3 2026-04-12: Clean human-readable format.
    # Old: "[REVENUE] Stripe Revenue Sync: Stripe sync complete.\n  Inserted: 0 new event(s)\n  Skipped: 4 duplicate(s)\n-- 17:34"
    # New: "Revenue\n$800 payment from Bennett Agency\n\n12:34 PM"
    prefix = CATEGORY_PREFIX.get(category, "Bravo")
    timestamp = datetime.now().strftime("%#I:%M %p")  # 12-hour format, no leading zero
    full_message = f"{prefix}\n{message}\n\n{timestamp}"
    if len(full_message) > 4096:
        full_message = full_message[:4093] + "..."

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": full_message,
                "parse_mode": "HTML",
                "disable_notification": silent,
            },
            timeout=5,  # V2 2026-04-11: 10s -> 5s to prevent scheduler loop stalls
        )
        ok = resp.json().get("ok", False)
        if not ok:
            # Log to stderr so scheduler's PM2 logs surface delivery failures
            # (e.g., 403 bot blocked, 429 rate limit). Fail-closed visibility.
            err_info = resp.json().get("description", f"HTTP {resp.status_code}")
            print(f"[notify] Telegram send failed: {err_info}", file=sys.stderr)
        return ok
    except Exception as exc:
        # Visible failure beats silent failure. PM2 logs catch this.
        print(f"[notify] Telegram send exception: {exc}", file=sys.stderr)
        return False


def notify_error(engine: str, error: str) -> bool:
    """Send an error alert - always with sound."""
    return notify(f"{engine} error: {error}", category="system", silent=False)


# Quick test
if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Bravo notification system online."
    result = notify(msg, category="system")
    print(f"Sent: {result}")
