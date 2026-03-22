"""
Bravo Notification System - Telegram alerts for all engine actions.

Every engine imports this module to send CC real-time updates.
Usage:
    from notify import notify
    notify("New lead booked a call for Tuesday 3pm")
    notify("Revenue update: $2,871 MRR", category="revenue")

Categories: lead, email, booking, content, revenue, outreach, instagram, system

FILTERING: Only high-signal categories reach CC's Telegram.
- ALWAYS SEND: lead, booking, revenue, error
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


# Category prefix map (using basic chars for Windows compatibility)
CATEGORY_PREFIX = {
    "lead": "[LEAD]",
    "email": "[EMAIL]",
    "booking": "[BOOKING]",
    "content": "[CONTENT]",
    "revenue": "[REVENUE]",
    "outreach": "[OUTREACH]",
    "instagram": "[IG]",
    "system": "[SYSTEM]",
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
    chat_id = env.get("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()

    if not token or not chat_id:
        return False

    try:
        import requests
    except ImportError:
        return False

    prefix = CATEGORY_PREFIX.get(category, "[BRAVO]")
    timestamp = datetime.now().strftime("%H:%M")
    full_message = f"{prefix} {message}\n-- {timestamp}"
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
            timeout=10,
        )
        return resp.json().get("ok", False)
    except Exception:
        return False


def notify_error(engine: str, error: str) -> bool:
    """Send an error alert - always with sound."""
    return notify(f"{engine} error: {error}", category="system", silent=False)


# Quick test
if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Bravo notification system online."
    result = notify(msg, category="system")
    print(f"Sent: {result}")
