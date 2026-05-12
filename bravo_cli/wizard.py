"""Bravo interactive setup wizard — Agent Factory onboarding.

Walks a new user through:
  1. Profile picker (Bravo / Atlas / Maven / Aura / Hermes / Custom)
  2. AI provider keys (required providers depend on the selected profile)
  3. Chat bridges (Telegram, Discord, Slack, WhatsApp/Twilio)
  4. Domain integrations (per profile: finance / marketing / home / client)
  5. Final summary + optional `bravo doctor` run

Writes secrets DIRECTLY to <repo>/.env.agents (0600 on POSIX) — that is
exactly where the 73 scripts in scripts/ load env from, so every key works
the instant it is saved. ~/.bravo/ is still used for profiles / sessions /
logs / cache, but NOT for env anymore (simpler, no mirror step).

Zero external dependencies — stdlib only (urllib, getpass, json, re).
"""

from __future__ import annotations

import getpass
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env.agents"          # Single source of truth.
BRAVO_HOME = Path(os.path.expanduser("~/.bravo"))  # Still used for profiles / sessions.

# Tracks which keys the user saved in this session (for final summary).
_SAVED_THIS_SESSION: list[str] = []
_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,120}$")
_ENV_EXCLUDE_PATTERNS = [
    ".env",
    ".env.*",
    "*.env",
    ".env.agents",
    ".env.agents.local",
]

# Force UTF-8 output on Windows.
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Terminal feature detection ────────────────────────────────────────────────

_TTY = sys.stdout.isatty()
_NO_COLOR = os.environ.get("NO_COLOR") is not None
_COLOR = _TTY and not _NO_COLOR

def _supports_hyperlinks() -> bool:
    if _NO_COLOR or not _TTY:
        return False
    # Windows Terminal, iTerm2, VS Code, Ghostty, Kitty, WezTerm, modern gnome-terminal
    if os.environ.get("WT_SESSION"):
        return True
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    if term_program in {"iterm.app", "vscode", "ghostty", "wezterm", "mintty"}:
        return True
    term = os.environ.get("TERM", "").lower()
    if any(t in term for t in ("kitty", "ghostty", "wezterm")):
        return True
    # Git Bash uses mintty
    if "MSYSTEM" in os.environ:
        return True
    return False

_HYPERLINKS = _supports_hyperlinks()

def _supports_unicode() -> bool:
    enc = (sys.stdout.encoding or "").lower()
    return "utf" in enc

_UNICODE = _supports_unicode()

# ── Style helpers ─────────────────────────────────────────────────────────────

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text

BOLD    = lambda t: _c("1", t)
DIM     = lambda t: _c("2", t)
ITALIC  = lambda t: _c("3", t)
GREEN   = lambda t: _c("32", t)
YELLOW  = lambda t: _c("33", t)
RED     = lambda t: _c("31", t)
CYAN    = lambda t: _c("36", t)
MAGENTA = lambda t: _c("35", t)
BRIGHT_BLUE = lambda t: _c("94", t)
BG_CYAN = lambda t: _c("46;30", t)

OK = "✓" if _UNICODE else "+"
FAIL = "✗" if _UNICODE else "X"
WARN = "○" if _UNICODE else "o"
ARROW = "→" if _UNICODE else "->"

def link(url: str, text: str | None = None) -> str:
    """Clickable URL in modern terminals (OSC 8); plain fallback elsewhere."""
    display = text or url
    if _HYPERLINKS:
        return f"\033]8;;{url}\033\\{CYAN(display)}\033]8;;\033\\"
    if display != url:
        return f"{CYAN(display)} {DIM(f'({url})')}"
    return CYAN(url)

# ── Banner + branding ─────────────────────────────────────────────────────────

# Primary wordmark. Shown on wizard open. Thick ANSI Shadow block letters.
_OASIS_BANNER_UNICODE = r"""
╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║    ██████╗  █████╗ ███████╗██╗███████╗    █████╗ ██╗               ║
║   ██╔═══██╗██╔══██╗██╔════╝██║██╔════╝   ██╔══██╗██║               ║
║   ██║   ██║███████║███████╗██║███████╗   ███████║██║               ║
║   ██║   ██║██╔══██║╚════██║██║╚════██║   ██╔══██║██║               ║
║   ╚██████╔╝██║  ██║███████║██║███████║   ██║  ██║██║               ║
║    ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝╚══════╝   ╚═╝  ╚═╝╚═╝               ║
║                                                                    ║
║    Agent Factory · Business-in-a-Box                               ║
║    oasisai.work                                                    ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝
"""

_OASIS_BANNER_ASCII = r"""
+====================================================================+
|                                                                    |
|    ######   #####  ######  ####  ######    ####  ####              |
|   ##   ## ##   ## ##       ##   ##        ##  ## ##  ##            |
|   ##   ## ####### ######   ##   ######    ###### ##  ##            |
|   ##   ## ##   ##     ##   ##       ##    ##  ## ##  ##            |
|    #####  ##   ## ######  ####  ######    ##  ## ##  ##            |
|                                                                    |
|    Agent Factory * Business-in-a-Box                               |
|    oasisai.work                                                    |
|                                                                    |
+====================================================================+
"""

# Per-agent block-letter wordmarks. Shown AFTER the user picks a profile,
# in that agent's color. Each one is ANSI Shadow style for consistency.
_AGENT_FIGLETS_UNICODE = {
    "bravo": r"""
██████╗ ██████╗  █████╗ ██╗   ██╗ ██████╗
██╔══██╗██╔══██╗██╔══██╗██║   ██║██╔═══██╗
██████╔╝██████╔╝███████║██║   ██║██║   ██║
██╔══██╗██╔══██╗██╔══██║╚██╗ ██╔╝██║   ██║
██████╔╝██║  ██║██║  ██║ ╚████╔╝ ╚██████╔╝
╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝   ╚═════╝""",
    "atlas": r"""
 █████╗ ████████╗██╗      █████╗ ███████╗
██╔══██╗╚══██╔══╝██║     ██╔══██╗██╔════╝
███████║   ██║   ██║     ███████║███████╗
██╔══██║   ██║   ██║     ██╔══██║╚════██║
██║  ██║   ██║   ███████╗██║  ██║███████║
╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝╚══════╝""",
    "maven": r"""
███╗   ███╗ █████╗ ██╗   ██╗███████╗███╗   ██╗
████╗ ████║██╔══██╗██║   ██║██╔════╝████╗  ██║
██╔████╔██║███████║██║   ██║█████╗  ██╔██╗ ██║
██║╚██╔╝██║██╔══██║╚██╗ ██╔╝██╔══╝  ██║╚██╗██║
██║ ╚═╝ ██║██║  ██║ ╚████╔╝ ███████╗██║ ╚████║
╚═╝     ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝  ╚═══╝""",
    "aura": r"""
 █████╗ ██╗   ██╗██████╗  █████╗
██╔══██╗██║   ██║██╔══██╗██╔══██╗
███████║██║   ██║██████╔╝███████║
██╔══██║██║   ██║██╔══██╗██╔══██║
██║  ██║╚██████╔╝██║  ██║██║  ██║
╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝""",
    "hermes": r"""
██╗  ██╗███████╗██████╗ ███╗   ███╗███████╗███████╗
██║  ██║██╔════╝██╔══██╗████╗ ████║██╔════╝██╔════╝
███████║█████╗  ██████╔╝██╔████╔██║█████╗  ███████╗
██╔══██║██╔══╝  ██╔══██╗██║╚██╔╝██║██╔══╝  ╚════██║
██║  ██║███████╗██║  ██║██║ ╚═╝ ██║███████╗███████║
╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚══════╝""",
    "custom": r"""
 ██████╗██╗   ██╗███████╗████████╗ ██████╗ ███╗   ███╗
██╔════╝██║   ██║██╔════╝╚══██╔══╝██╔═══██╗████╗ ████║
██║     ██║   ██║███████╗   ██║   ██║   ██║██╔████╔██║
██║     ██║   ██║╚════██║   ██║   ██║   ██║██║╚██╔╝██║
╚██████╗╚██████╔╝███████║   ██║   ╚██████╔╝██║ ╚═╝ ██║
 ╚═════╝ ╚═════╝ ╚══════╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝""",
}

# ASCII fallback figlets (same shape, `#` characters).
_AGENT_FIGLETS_ASCII = {
    "bravo":  "\n######  ######   ####   ##  ##   #####\n##   ## ##   ## ##  ##  ##  ##  ##   ##\n######  ######  ######  ##  ##  ##   ##\n##   ## ##   ## ##  ##   ####   ##   ##\n######  ##  ## ##  ##    ##     #####",
    "atlas":  "\n #####  ######## ##       #####   #####\n##   ##    ##    ##      ##   ## ##\n#######    ##    ##      ####### ######\n##   ##    ##    ##      ##   ##      ##\n##   ##    ##    ####### ##   ## ######",
    "maven":  "\n###   ###  #####  ##   ## ####### ###   ##\n####  ###  ##  ## ##   ## ##      ####  ##\n## #### ## ######  ##   ## #####   ## ## ##\n##  ##  ## ##  ##  ## ##   ##      ##  ####\n##      ## ##  ##    ###    ####### ##   ###",
    "aura":   "\n #####  ##   ## ######   #####\n##   ## ##   ## ##   ## ##   ##\n####### ##   ## ######  #######\n##   ## ##   ## ##   ## ##   ##\n##   ##  #####  ##   ## ##   ##",
    "hermes": "\n##   ## ####### ######  ###   ### ####### #######\n##   ## ##      ##   ## ####  ### ##      ##\n####### #####   ######  ## #### # #####   #######\n##   ## ##      ##   ## ##  ##  # ##           ##\n##   ## ####### ##   ## ##      # ####### #######",
    "custom": "\n #####  ##   ## ####### ####### ####### ###   ###\n##      ##   ## ##         ##   ##   ## ####  ###\n##      ##   ## #######    ##   ##   ## ## #### #\n##      ##   ##      ##    ##   ##   ## ##  ##  #\n ######  #####  #######    ##    #####  ##      #",
}

def _agent_figlet(slug: str) -> str:
    """Return the agent's ASCII art, Unicode or plain depending on terminal."""
    src = _AGENT_FIGLETS_UNICODE if _UNICODE else _AGENT_FIGLETS_ASCII
    return src.get(slug, "")

def banner() -> str:
    return _OASIS_BANNER_UNICODE if _UNICODE else _OASIS_BANNER_ASCII

OASIS_URL = "https://oasisai.work"

def print_banner() -> None:
    """Primary wordmark shown when the wizard opens. Brand-first."""
    print(CYAN(banner()))
    print(f"  {DIM('version:')} {BOLD('V1.4')}  "
          f"{DIM('|')}  {DIM('home:')} {link(OASIS_URL, 'oasisai.work')}  "
          f"{DIM('|')}  {DIM('press Ctrl+C anytime')}")
    print()

# ── Profiles ──────────────────────────────────────────────────────────────────

# Integration slugs that each profile walks through (chat_core is shared).
PROFILES: dict[str, dict] = {
    "bravo": {
        "name": "Bravo",
        "icon": "◆" if _UNICODE else "#",
        "color": CYAN,
        "role": "CEO · Business operations brain",
        "tagline": "Strategy · revenue · clients · orchestration",
        "required": ["anthropic"],
        "ai": ["anthropic", "openai", "google_ai"],
        "chat": ["telegram", "discord", "slack", "whatsapp"],
        "business": ["stripe", "supabase", "n8n"],
        "extra": [],
    },
    "atlas": {
        "name": "Atlas",
        "icon": "$" if not _UNICODE else "$",
        "color": GREEN,
        "role": "CFO · Finance, tax, trading, budgeting",
        "tagline": "Money · markets · compliance · wealth",
        "required": ["anthropic"],
        "ai": ["anthropic", "openai"],
        "chat": ["telegram", "discord", "slack"],
        "business": ["stripe", "plaid", "ccxt"],
        "extra": [],
    },
    "maven": {
        "name": "Maven",
        "icon": "★" if _UNICODE else "*",
        "color": MAGENTA,
        "role": "CMO · Content, ads, funnel, brand",
        "tagline": "Content · ads · social · funnel",
        "required": ["anthropic"],
        "ai": ["anthropic", "openai", "google_ai"],
        "chat": ["telegram", "discord", "slack", "whatsapp"],
        "business": ["stripe"],
        "extra": ["meta_ads", "google_ads", "late_zernio", "linkedin", "x_twitter"],
    },
    "aura": {
        "name": "Aura",
        "icon": "⌂" if _UNICODE else "H",
        "color": YELLOW,
        "role": "Life/Home agent · Ambient, habits, routines",
        "tagline": "Home · health · habits · ambient",
        "required": ["anthropic"],
        "ai": ["anthropic", "openai"],
        "chat": ["telegram"],
        "business": [],
        "extra": ["home_assistant", "elevenlabs"],
    },
    "hermes": {
        "name": "Hermes",
        "icon": "⚡" if _UNICODE else "^",
        "color": BRIGHT_BLUE,  # differentiated from Bravo's cyan
        "role": "Wholesale commerce + EDI compliance agent",
        "tagline": "PO → POS → invoice · ASN · chargeback prevention · A2000 takeover",
        "required": [],
        "ai": ["anthropic", "openai"],  # cloud LLM for PO parsing — DPA-bound, no-storage
        "chat": ["telegram"],
        "business": [],
        "extra": [],
    },
    "sunbiz": {
        "name": "Solara",
        "icon": "☀" if _UNICODE else "S",
        "color": YELLOW,
        "role": "Sun Biz funding · digital employee for lead intake + follow-up",
        "tagline": "Leads · renewals · text follow-up · funded deals",
        "required": ["anthropic"],
        "ai": ["anthropic", "openai"],
        "chat": ["telegram"],
        "business": ["stripe", "supabase", "twilio", "n8n"],
        "extra": [],
    },
    "suga_sean": {
        "name": "Suga",
        "icon": "♛" if _UNICODE else "K",
        "color": MAGENTA,
        "role": "Suga Sean O'Malley · fan ops + brand agent",
        "tagline": "Fans · merch · social · sponsorship",
        "required": ["anthropic"],
        "ai": ["anthropic", "openai"],
        "chat": ["telegram", "discord"],
        "business": ["stripe"],
        "extra": ["late_zernio", "x_twitter"],
    },
    "custom": {
        "name": "Custom",
        "icon": "+" if not _UNICODE else "◇",
        "color": DIM,
        "role": "Forge a new agent from scratch",
        "tagline": "You pick the tools — we'll scaffold the rest after setup",
        "required": ["anthropic"],
        "ai": ["anthropic", "openai", "google_ai"],
        "chat": ["telegram", "discord", "slack", "whatsapp"],
        "business": [],
        "extra": [],
    },
}

# ── Per-agent GitHub repos ────────────────────────────────────────────────────

AGENT_REPOS: dict[str, dict] = {
    "bravo":  {"url": "https://github.com/CC90210/CEO-Agent.git",        "dir": "~/bravo-repo"},
    "atlas":  {"url": "https://github.com/CC90210/CFO-Agent.git",        "dir": "~/atlas-repo"},
    "maven":  {"url": "https://github.com/CC90210/CMO-Agent.git",        "dir": "~/maven-repo"},
    "aura":   {"url": "https://github.com/CC90210/Aura-Home-Agent.git",  "dir": "~/aura-repo"},
    "hermes": {"url": "https://github.com/CC90210/hermes.git",           "dir": "~/hermes-repo"},
    "sunbiz": {"url": "https://github.com/CC90210/SunBiz-Agent.git",     "dir": "~/sunbiz-repo"},
    "custom": None,  # No repo — scaffolded via `bravo agent create` after setup.
}

# ── Per-agent dynamic questions ───────────────────────────────────────────────
#
# Each entry is a dict with:
#   key      — ENV_KEY the answer gets written to
#   prompt   — what the user sees
#   type     — "text" | "choice" | "yesno"
#   default  — value used when user presses Enter
#   choices  — for type=choice, the menu options
#   secret   — True to hide input (getpass)

PROFILE_QUESTIONS: dict[str, list[dict]] = {
    "bravo": [
        {"key": "BRAVO_NORTH_STAR_METRIC", "prompt": "North-star metric",
         "type": "choice", "choices": ["MRR", "ARR", "Revenue", "Users", "Other"], "default": "MRR"},
        {"key": "BRAVO_TARGET",      "prompt": "Target (e.g., $5,000 MRR by 2026-05-15)",
         "type": "text", "default": "$5,000 MRR"},
        {"key": "BRAVO_TIMEZONE",    "prompt": "Timezone (e.g., America/Toronto)",
         "type": "text", "default": "America/Toronto"},
        {"key": "BRAVO_WORKING_HOURS", "prompt": "Working hours (e.g., 09:00-18:00)",
         "type": "text", "default": "09:00-18:00"},
        {"key": "BRAVO_CHECKIN_CADENCE", "prompt": "How often should Bravo check in?",
         "type": "choice", "choices": ["hourly", "daily", "weekly", "on-demand"], "default": "daily"},
        {"key": "BRAVO_PRIMARY_BRAND", "prompt": "Primary business / brand name",
         "type": "text", "default": "OASIS AI"},
    ],
    "atlas": [
        {"key": "ATLAS_TAX_REGION",   "prompt": "Tax region",
         "type": "choice", "choices": ["CA", "US", "UK", "EU", "AU", "OTHER"], "default": "CA"},
        {"key": "ATLAS_BASE_CURRENCY", "prompt": "Base currency",
         "type": "choice", "choices": ["USD", "CAD", "EUR", "GBP", "AUD"], "default": "USD"},
        {"key": "ATLAS_FISCAL_YEAR_START", "prompt": "Fiscal year start (MM-DD)",
         "type": "text", "default": "01-01"},
        {"key": "ATLAS_RISK_TOLERANCE", "prompt": "Investment risk tolerance",
         "type": "choice", "choices": ["conservative", "moderate", "aggressive"], "default": "moderate"},
        {"key": "ATLAS_TRADING_ENABLED", "prompt": "Allow Atlas to place live trades? (REQUIRES explicit approval per trade either way)",
         "type": "yesno", "default": False},
        {"key": "ATLAS_BUDGET_REVIEW_CADENCE", "prompt": "Budget review cadence",
         "type": "choice", "choices": ["weekly", "bi-weekly", "monthly", "quarterly"], "default": "monthly"},
        {"key": "ATLAS_FIRE_TARGET_CAD", "prompt": "FIRE / wealth target (CAD, or blank to skip)",
         "type": "text", "default": ""},
    ],
    "maven": [
        {"key": "MAVEN_BRAND_VOICE", "prompt": "Brand voice",
         "type": "choice", "choices": ["professional", "casual", "provocative", "educational", "friendly"], "default": "casual"},
        {"key": "MAVEN_PRIMARY_PLATFORM", "prompt": "Primary publishing platform",
         "type": "choice", "choices": ["linkedin", "x", "instagram", "tiktok", "youtube", "skool"], "default": "linkedin"},
        {"key": "MAVEN_POSTING_FREQUENCY", "prompt": "Posting frequency",
         "type": "choice", "choices": ["daily", "weekdays", "3x-week", "weekly", "varies"], "default": "daily"},
        {"key": "MAVEN_CONTENT_TYPES", "prompt": "Content types (comma-separated: video,image,text,audio)",
         "type": "text", "default": "video,text"},
        {"key": "MAVEN_PRIMARY_CTA", "prompt": "Primary CTA URL (booking / lead magnet / product)",
         "type": "text", "default": "https://calendar.app.google/"},
        {"key": "MAVEN_TARGET_AUDIENCE", "prompt": "Target audience (one sentence)",
         "type": "text", "default": "solo founders building with AI"},
        {"key": "MAVEN_APPROVAL_BEFORE_PUBLISH", "prompt": "Require approval before publishing?",
         "type": "yesno", "default": True},
    ],
    "aura": [
        {"key": "AURA_RESIDENCE_CITY", "prompt": "Primary residence city",
         "type": "text", "default": "Collingwood"},
        {"key": "AURA_HOME_PLATFORM", "prompt": "Smart-home platform",
         "type": "choice", "choices": ["home-assistant", "homekit", "google-home", "alexa", "none"], "default": "home-assistant"},
        {"key": "AURA_WAKE_TIME", "prompt": "Target wake time (HH:MM)",
         "type": "text", "default": "07:00"},
        {"key": "AURA_SLEEP_TIME", "prompt": "Target sleep time (HH:MM)",
         "type": "text", "default": "23:00"},
        {"key": "AURA_PRIVACY_MODE", "prompt": "Processing mode",
         "type": "choice", "choices": ["on-device", "hybrid", "cloud"], "default": "on-device"},
        {"key": "AURA_VOICE_ENABLED", "prompt": "Enable voice interaction?",
         "type": "yesno", "default": True},
        {"key": "AURA_APPROVAL_FOR_PHYSICAL_DEVICES", "prompt": "Require approval before triggering locks/cameras/alarms?",
         "type": "yesno", "default": True},
    ],
    "hermes": [
        {"key": "HERMES_CLIENT_NAME", "prompt": "Client/company name Hermes will operate for",
         "type": "text", "default": "Lowinger Distribution", "required": True},
        {"key": "HERMES_CLIENT_INDUSTRY", "prompt": "Client/company industry",
         "type": "choice",
         "choices": ["wholesale-apparel", "wholesale-other", "ecommerce", "retail", "distribution", "services", "other"],
         "default": "wholesale-apparel"},
        {"key": "HERMES_POS_SYSTEM", "prompt": "POS / ERP system Hermes integrates with",
         "type": "choice",
         "choices": ["a2000-gcs", "shopify", "stripe", "square", "woocommerce", "netsuite", "sap-business-one", "custom"],
         "default": "a2000-gcs"},
        {"key": "A2000_MODE", "prompt": "How does Hermes drive the POS? (mock for trial; desktop = pywinauto on A2000.exe; edi = X12 850 to VAN)",
         "type": "choice", "choices": ["mock", "desktop", "edi", "api", "playwright"], "default": "mock"},
        {"key": "HERMES_PRIMARY_BUYER", "prompt": "Primary retail buyer (drives compliance: Walgreens, CVS, Target, etc.)",
         "type": "text", "default": "Walgreens"},
        {"key": "HERMES_EDI_VAN", "prompt": "EDI VAN / broker (if any)",
         "type": "choice", "choices": ["none", "sps-commerce", "truecommerce", "crossbridge", "other"], "default": "none"},
        {"key": "HERMES_ORDER_VOLUME_MONTHLY", "prompt": "Rough monthly PO volume",
         "type": "choice", "choices": ["<50", "50-500", "500-5000", "5000+"], "default": "500-5000"},
        {"key": "HERMES_INVENTORY_TRACKING", "prompt": "Does Hermes need to manage inventory positions?",
         "type": "yesno", "default": True},
        {"key": "HERMES_SUPPORT_CHANNELS", "prompt": "Customer support channels (comma-separated: email,chat,sms)",
         "type": "text", "default": "email"},
        {"key": "HERMES_APPROVAL_FOR_REFUNDS", "prompt": "Require approval before issuing refunds?",
         "type": "yesno", "default": True},
        {"key": "HERMES_PO_PARSER", "prompt": "PO parser backend (cloud is DPA-bound and no-storage; ollama is fully local)",
         "type": "choice", "choices": ["ollama-local", "auto", "cloud-anthropic", "cloud-openai"], "default": "ollama-local"},
    ],
    "sunbiz": [
        {"key": "SUNBIZ_PRIMARY_MARKET", "prompt": "Primary funding lane",
         "type": "choice", "choices": ["mca", "term-loan", "equipment-finance", "line-of-credit", "mixed"], "default": "mixed"},
        {"key": "SUNBIZ_RENEWAL_WINDOW_DAYS", "prompt": "Renewal-warning window (days)",
         "type": "text", "default": "30"},
        {"key": "SUNBIZ_DOC_CHASE_STYLE", "prompt": "Document-chase style",
         "type": "choice", "choices": ["agent-assisted", "manual-review", "auto-reminders"], "default": "agent-assisted"},
        {"key": "SUNBIZ_SMS_TONE", "prompt": "SMS tone",
         "type": "choice", "choices": ["professional", "direct", "friendly", "urgent"], "default": "professional"},
        {"key": "SUNBIZ_APPROVAL_BEFORE_SEND", "prompt": "Require approval before outbound sends?",
         "type": "yesno", "default": True},
    ],
    "suga_sean": [
        {"key": "SUGA_PRIMARY_PLATFORM", "prompt": "Primary platform",
         "type": "choice", "choices": ["instagram", "x", "youtube", "tiktok", "email"], "default": "instagram"},
        {"key": "SUGA_REVENUE_FOCUS", "prompt": "Primary revenue focus",
         "type": "choice", "choices": ["merch", "sponsorships", "content", "affiliate", "mixed"], "default": "mixed"},
        {"key": "SUGA_POSTING_CADENCE", "prompt": "Posting cadence",
         "type": "choice", "choices": ["daily", "fight-week", "3x-week", "weekly", "launch-only"], "default": "daily"},
        {"key": "SUGA_MERCH_STACK", "prompt": "Merch stack",
         "type": "choice", "choices": ["shopify", "woocommerce", "gumroad", "none", "other"], "default": "shopify"},
        {"key": "SUGA_APPROVAL_BEFORE_PUBLISH", "prompt": "Require approval before publishing?",
         "type": "yesno", "default": True},
    ],
    "custom": [
        {"key": "CUSTOM_AGENT_NAME", "prompt": "Name for your new agent",
         "type": "text", "default": ""},
        {"key": "CUSTOM_AGENT_ROLE", "prompt": "Role (one line)",
         "type": "text", "default": ""},
        {"key": "CUSTOM_AGENT_DOMAIN", "prompt": "Domain / industry",
         "type": "text", "default": ""},
        {"key": "CUSTOM_AGENT_PRIMARY_OUTCOME", "prompt": "Primary outcome this agent should drive",
         "type": "text", "default": ""},
    ],
}

# ── Shared "about your business" block (asked for business-y agents) ──────────
#
# Deep, not extensive. Five questions that transform a general-purpose agent
# (CEO/CFO/CMO/commerce) into one tailored to the user's actual business.
# Example: answering "real estate agent" in the industry question turns Maven
# from a generic CMO into a real-estate marketing operator.

USER_IDENTITY_QUESTIONS: list[dict] = [
    {"key": "USER_FULL_NAME",
     "prompt": "User's full name (who is using this agent?)",
     "type": "text", "default": "", "required": True},
    {"key": "USER_PREFERRED_NAME",
     "prompt": "What should the agent call you?",
     "type": "text", "default": ""},
    {"key": "USER_BUSINESS_NAME",
     "prompt": "Your business / brand name",
     "type": "text", "default": ""},
    {"key": "USER_ROLE",
     "prompt": "Your role or title",
     "type": "text", "default": ""},
]

BUSINESS_CONTEXT_QUESTIONS: list[dict] = [
    {"key": "USER_INDUSTRY",
     "prompt": "Your business / operator type",
     "type": "choice",
     "choices": ["real-estate", "saas", "agency", "ecommerce", "consulting",
                 "content-creator", "services", "coaching", "finance",
                 "healthcare", "education", "other"],
     "default": "services"},
    {"key": "USER_PRIMARY_METRIC",
     "prompt": "The ONE metric that matters to you right now",
     "type": "text", "default": ""},
    {"key": "USER_DAILY_WORK",
     "prompt": "What you actually do day-to-day (one sentence)",
     "type": "text", "default": ""},
    {"key": "USER_FIRST_WORKFLOW_TARGET",
     "prompt": "First workflow you want this agent to automate",
     "type": "text", "default": ""},
    {"key": "USER_OFF_LIMITS",
     "prompt": "Anything this agent should NEVER do (e.g., post without approval)",
     "type": "text", "default": ""},
]

# Profiles that get the shared business-context block in addition to their
# per-agent questions. Aura is lifestyle, Custom is user-defined — both skip.
BUSINESS_CONTEXT_PROFILES = {"bravo", "atlas", "maven", "hermes", "sunbiz", "suga_sean"}

COMMON_CONTEXT_KEYS = [
    "USER_FULL_NAME",
    "USER_PREFERRED_NAME",
    "USER_BUSINESS_NAME",
    "USER_ROLE",
    "USER_INDUSTRY",
    "USER_PRIMARY_METRIC",
    "USER_DAILY_WORK",
    "USER_FIRST_WORKFLOW_TARGET",
    "USER_OFF_LIMITS",
]

PROFILE_CONTEXT_PREFIXES = {
    "bravo": ["BRAVO_"],
    "atlas": ["ATLAS_"],
    "maven": ["MAVEN_"],
    "aura": ["AURA_"],
    "hermes": ["HERMES_"],
    "sunbiz": ["SUNBIZ_"],
    "suga_sean": ["SUGA_"],
    "custom": ["CUSTOM_"],
}

PRIVATE_VALUE_MARKERS = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "WEBHOOK",
    "DSN",
    "PRIVATE",
)

# ── Integrations ──────────────────────────────────────────────────────────────

# Each integration: {env_key, label, url, format, instructions, validator}
# validator(value) -> (ok: bool, detail: str)

INTEGRATIONS: dict[str, dict] = {
    # AI providers
    "anthropic": {
        "env_key": "ANTHROPIC_API_KEY",
        "label": "Anthropic (Claude)",
        "tagline": "Primary reasoning engine",
        "url": "https://console.anthropic.com/settings/keys",
        "format": "sk-ant-api03-...",
        "secret": True,
        "instructions": [
            "Sign in to console.anthropic.com",
            "Settings -> API Keys -> Create Key",
            "Copy the full key (starts with sk-ant-)",
        ],
        "cli_auth": {
            "cmd": "claude",
            "mode_key": "ANTHROPIC_AUTH_MODE",
            "mode_value": "claude_code_cli",
            "label": "Claude Code CLI (OS keychain auth)",
        },
    },
    "openai": {
        "env_key": "OPENAI_API_KEY",
        "label": "OpenAI",
        "tagline": "Codex delegation + fallback provider",
        "url": "https://platform.openai.com/api-keys",
        "format": "sk-...",
        "secret": True,
        "instructions": [
            "Sign in to platform.openai.com",
            "API keys -> Create new secret key",
        ],
        "cli_auth": {
            "cmd": "codex",
            "mode_key": "OPENAI_AUTH_MODE",
            "mode_value": "codex_cli",
            "label": "Codex CLI (OS keychain auth)",
        },
    },
    "google_ai": {
        "env_key": "GOOGLE_AI_API_KEY",
        "label": "Google AI Studio (Gemini)",
        "tagline": "Free tier available — good fallback",
        "url": "https://aistudio.google.com/app/apikey",
        "format": "AIza...",
        "secret": True,
        "instructions": [
            "Sign in to aistudio.google.com",
            "Get API Key -> Create API key",
        ],
        "cli_auth": {
            "cmd": "gemini",
            "mode_key": "GOOGLE_AI_AUTH_MODE",
            "mode_value": "gemini_cli",
            "label": "Gemini CLI (OS keychain auth)",
        },
    },
    # Chat bridges
    "telegram": {
        "env_key": "TELEGRAM_BOT_TOKEN",
        "label": "Telegram bridge",
        "tagline": "Remote control for your agent from your phone",
        "url": "https://t.me/BotFather",
        "format": "123456:ABC-DEF...",
        "secret": True,
        "instructions": [
            "Open Telegram, message @BotFather",
            "Send /newbot, pick a name, pick a username ending in 'bot'",
            "BotFather replies with a token — paste it here",
        ],
        "interactive": "telegram",
    },
    "discord": {
        "env_key": "DISCORD_BOT_TOKEN",
        "label": "Discord bridge",
        "tagline": "Send & receive commands in a Discord channel",
        "url": "https://discord.com/developers/applications",
        "format": "MTA...{long}",
        "secret": True,
        "instructions": [
            "Go to discord.com/developers/applications",
            "New Application -> give it a name",
            "Left sidebar -> Bot -> Reset Token -> Copy",
            "Enable 'MESSAGE CONTENT INTENT' under Privileged Gateway Intents",
        ],
    },
    "slack": {
        "env_key": "SLACK_BOT_TOKEN",
        "label": "Slack bridge",
        "tagline": "Bridge agent to your workspace",
        "url": "https://api.slack.com/apps",
        "format": "xoxb-...",
        "secret": True,
        "instructions": [
            "Go to api.slack.com/apps",
            "Create New App -> From scratch",
            "OAuth & Permissions -> add scopes: chat:write, channels:read",
            "Install to workspace -> copy Bot User OAuth Token (xoxb-...)",
        ],
    },
    "whatsapp": {
        "env_key": "TWILIO_ACCOUNT_SID",
        "label": "WhatsApp (via Twilio)",
        "tagline": "Business WhatsApp without full Meta verification",
        "url": "https://console.twilio.com/",
        "format": "AC...",
        "secret": True,
        "instructions": [
            "Sign up at twilio.com (free trial available)",
            "Console -> Account SID (public) — paste here",
            "Next step will ask for Auth Token (secret)",
            "WhatsApp sandbox: Messaging -> Try it out -> Send a WhatsApp message",
        ],
        "followup_key": "TWILIO_AUTH_TOKEN",
        "followup_label": "Twilio Auth Token",
    },
    "twilio": {
        "env_key": "TWILIO_ACCOUNT_SID",
        "label": "Text Torrent",
        "tagline": "Lead texting + follow-up lane for Solara",
        "url": "https://console.twilio.com/",
        "format": "AC...",
        "secret": True,
        "instructions": [
            "Open the Text Torrent workspace (or the linked Twilio console)",
            "Copy the Account SID first",
            "On the next prompt, paste the Auth Token so Solara can send follow-ups",
        ],
        "followup_key": "TWILIO_AUTH_TOKEN",
        "followup_label": "Text Torrent Auth Token",
        "followup_secret": True,
    },
    # Business ops
    "stripe": {
        "env_key": "STRIPE_SECRET_KEY",
        "label": "Stripe",
        "tagline": "Revenue sync, MRR, subscriptions",
        "url": "https://dashboard.stripe.com/apikeys",
        "format": "sk_live_... or sk_test_...",
        "secret": True,
        "instructions": [
            "Sign in to dashboard.stripe.com",
            "Developers -> API keys -> Reveal secret key",
            "Use 'sk_test_' during setup, switch to 'sk_live_' for production",
        ],
    },
    "supabase": {
        "env_key": "BRAVO_SUPABASE_URL",
        "label": "Supabase",
        "tagline": "Persistent state + CRM + memory store",
        "url": "https://supabase.com/dashboard/projects",
        "format": "https://<project>.supabase.co",
        "secret": False,
        "instructions": [
            "Go to supabase.com/dashboard/projects",
            "Pick your project -> Settings -> API",
            "Copy the Project URL here; service_role key on the next prompt",
            "(service_role is needed for server-side scripts to bypass RLS)",
        ],
        "followup_key": "BRAVO_SUPABASE_SERVICE_ROLE_KEY",
        "followup_label": "Supabase service_role key (NOT the anon key)",
        "followup_secret": True,
    },
    "n8n": {
        "env_key": "N8N_API_URL",
        "label": "n8n (workflow automation)",
        "tagline": "Triggers, schedules, integrations",
        "url": "https://docs.n8n.io/api/authentication/",
        "format": "https://n8n.example.com",
        "secret": False,
        "instructions": [
            "From your n8n instance: Settings -> API",
            "Copy the base URL (e.g. https://n8n.example.com)",
            "Then create an API key and paste it in the next prompt",
        ],
        "followup_key": "N8N_API_KEY",
        "followup_label": "n8n API key",
        "followup_secret": True,
    },
    # Finance (Atlas)
    "plaid": {
        "env_key": "PLAID_CLIENT_ID",
        "label": "Plaid (bank accounts)",
        "tagline": "Read-only bank + credit card balances",
        "url": "https://dashboard.plaid.com/team/keys",
        "format": "client_id (public)",
        "secret": False,
        "instructions": [
            "Sign up at plaid.com (sandbox is free)",
            "Team Settings -> Keys -> Client ID",
        ],
        "followup_key": "PLAID_SECRET",
        "followup_label": "Plaid secret (sandbox or production)",
        "followup_secret": True,
    },
    "ccxt": {
        "env_key": "EXCHANGE_API_KEY",
        "label": "Crypto exchange (via CCXT)",
        "tagline": "Binance / Coinbase / Kraken etc. — read-only recommended",
        "url": "https://github.com/ccxt/ccxt#supported-exchanges",
        "format": "exchange-specific",
        "secret": True,
        "instructions": [
            "Exchange -> API Management -> Create Key",
            "Enable READ ONLY unless trading from this machine",
            "Paste the API key here, secret on next prompt",
        ],
        "followup_key": "EXCHANGE_API_SECRET",
        "followup_label": "Exchange API secret",
        "followup_secret": True,
    },
    # Marketing (Maven)
    "meta_ads": {
        "env_key": "META_ACCESS_TOKEN",
        "label": "Meta Ads (Facebook/Instagram)",
        "tagline": "Ad creation, audience insights, spend tracking",
        "url": "https://developers.facebook.com/tools/explorer/",
        "format": "long opaque token",
        "secret": True,
        "instructions": [
            "Meta for Developers -> Tools -> Graph API Explorer",
            "Generate User Access Token with ads_management permission",
            "For production use: exchange for a long-lived system user token",
        ],
    },
    "google_ads": {
        "env_key": "GOOGLE_ADS_DEVELOPER_TOKEN",
        "label": "Google Ads",
        "tagline": "Campaign management, keyword reporting",
        "url": "https://ads.google.com/aw/apicenter",
        "format": "developer token",
        "secret": True,
        "instructions": [
            "Google Ads -> Tools -> API Center",
            "Apply for a developer token (approval can take 24-48h)",
        ],
    },
    "late_zernio": {
        "env_key": "LATE_API_KEY",
        "label": "Late / Zernio (social scheduling)",
        "tagline": "Cross-platform content scheduling",
        "url": "https://zernio.com",
        "format": "opaque token",
        "secret": True,
        "instructions": [
            "Sign in to zernio.com",
            "Settings -> API -> Generate key",
        ],
    },
    "linkedin": {
        "env_key": "LINKEDIN_EMAIL",
        "label": "LinkedIn",
        "tagline": "Automation via account credentials (read-only browser session)",
        "url": "https://www.linkedin.com",
        "format": "your LinkedIn email",
        "secret": False,
        "instructions": [
            "Enter the LinkedIn account credentials used by Maven's automation",
            "We store these locally only — never committed to git",
            "Password comes next (hidden input)",
        ],
        "followup_key": "LINKEDIN_PASSWORD",
        "followup_label": "LinkedIn password",
        "followup_secret": True,
    },
    "x_twitter": {
        "env_key": "TWITTER_BEARER_TOKEN",
        "label": "X / Twitter",
        "tagline": "Tweet scheduling, mentions, DMs",
        "url": "https://developer.twitter.com/en/portal/dashboard",
        "format": "Bearer token (API v2)",
        "secret": True,
        "instructions": [
            "Developer portal -> Projects & Apps -> your app",
            "Keys and tokens -> Bearer Token -> Generate",
        ],
    },
    # Home (Aura)
    "home_assistant": {
        "env_key": "HOME_ASSISTANT_URL",
        "label": "Home Assistant",
        "tagline": "Lights, sensors, locks, devices",
        "url": "https://www.home-assistant.io/docs/authentication/",
        "format": "http://homeassistant.local:8123",
        "secret": False,
        "instructions": [
            "On your Home Assistant instance:",
            "Profile (bottom-left) -> Long-Lived Access Tokens -> Create Token",
            "Paste the base URL here; token on the next prompt",
        ],
        "followup_key": "HOME_ASSISTANT_TOKEN",
        "followup_label": "Home Assistant Long-Lived Token",
        "followup_secret": True,
    },
    "elevenlabs": {
        "env_key": "ELEVENLABS_API_KEY",
        "label": "ElevenLabs (voice)",
        "tagline": "Premium voice synthesis for agent replies",
        "url": "https://elevenlabs.io/app/settings/api-keys",
        "format": "opaque",
        "secret": True,
        "instructions": [
            "Sign in to elevenlabs.io",
            "Profile -> API Keys -> Create New Key",
        ],
    },
}

# ── Env file I/O ──────────────────────────────────────────────────────────────

def _git_run(args: list[str], cwd: Path, timeout: int = 10) -> subprocess.CompletedProcess[str] | None:
    """Small git wrapper for safety checks. Returns None when git is absent."""
    if not shutil.which("git"):
        return None
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except Exception:
        return None


def _git_root_for(path: Path) -> Path | None:
    """Return the containing git root for path, if any."""
    cwd = path if path.is_dir() else path.parent
    if not cwd.exists():
        return None
    result = _git_run(["rev-parse", "--show-toplevel"], cwd)
    if not result or result.returncode != 0:
        return None
    root = result.stdout.strip()
    return Path(root).resolve() if root else None


def _git_rel(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def _git_file_is_tracked(root: Path, rel: str) -> bool:
    result = _git_run(["ls-files", "--error-unmatch", "--", rel], root)
    return bool(result and result.returncode == 0)


def _git_file_is_ignored(root: Path, rel: str) -> bool:
    result = _git_run(["check-ignore", "-q", "--", rel], root)
    return bool(result and result.returncode == 0)


def _git_info_exclude(root: Path) -> Path | None:
    result = _git_run(["rev-parse", "--git-path", "info/exclude"], root)
    if not result or result.returncode != 0:
        return None
    raw = result.stdout.strip()
    return (root / raw).resolve() if raw else None


def _ensure_env_is_git_safe(path: Path) -> None:
    """Guarantee the env file cannot be accidentally committed."""
    root = _git_root_for(path)
    if not root:
        return
    rel = _git_rel(path, root)
    if not rel:
        return
    if _git_file_is_tracked(root, rel):
        raise RuntimeError(
            f"Refusing to write secrets because {rel} is tracked by git. "
            "Remove it from git history/index before running setup."
        )
    if _git_file_is_ignored(root, rel):
        return

    exclude = _git_info_exclude(root)
    if not exclude:
        raise RuntimeError(f"Could not locate .git/info/exclude for {root}")
    exclude.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude.read_text(encoding="utf-8", errors="ignore") if exclude.exists() else ""
    existing_lines = {line.strip() for line in existing.splitlines()}
    additions = [p for p in [rel, *_ENV_EXCLUDE_PATTERNS] if p not in existing_lines]
    if additions:
        prefix = "" if not existing or existing.endswith("\n") else "\n"
        block = prefix + "\n# Bravo local secrets\n" + "\n".join(additions) + "\n"
        exclude.write_text(existing + block, encoding="utf-8")

    if not _git_file_is_ignored(root, rel):
        raise RuntimeError(f"Could not git-ignore secret env file: {path}")


def _chmod_secret_file(path: Path) -> None:
    """Tighten ACLs on a credential file so only the owner can read it.

    POSIX: chmod 0o600.
    Windows: icacls /inheritance:r + grant the current user Full Control.
    Disabling inheritance removes any inherited ACEs from a parent
    directory that might grant other Users group members read access.
    """
    if os.name == "nt":
        try:
            import subprocess
            user = os.environ.get("USERNAME") or os.environ.get("USER")
            if not user:
                return
            # /inheritance:r removes all existing ACLs (including inherited
            # ACEs from %USERPROFILE% which may include the Users group).
            # /grant:r replaces (not appends) any ACE for the current user.
            for argv in (
                ["icacls", str(path), "/inheritance:r"],
                ["icacls", str(path), "/grant:r", f"{user}:F"],
            ):
                subprocess.run(argv, capture_output=True, timeout=10,
                               check=False)
        except Exception:
            # icacls is built-in on every supported Windows version; if it
            # fails we silently fall back to default ACLs rather than
            # blocking the wizard. The user's HOME usually inherits an
            # owner-only ACL anyway.
            pass
        return
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _clean_env_value(key: str, value: str) -> str:
    if not _ENV_KEY_RE.fullmatch(key):
        raise ValueError(f"Invalid env key: {key!r}")
    if any(ch in value for ch in ("\n", "\r", "\x00")):
        raise ValueError(f"Refusing to write multiline/env-breaking value for {key}")
    return value.strip()


def ensure_env_file() -> None:
    # Home directory for sessions/profiles (not for env anymore).
    BRAVO_HOME.mkdir(parents=True, exist_ok=True)
    # .env.agents lives in the repo; create if absent.
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ensure_env_is_git_safe(ENV_PATH)
    if not ENV_PATH.exists():
        ENV_PATH.write_text(
            "# Bravo .env.agents — managed by `bravo setup`.\n"
            "# One KEY=value per line. Never commit this file.\n"
            "# Scripts in scripts/ load directly from here.\n\n",
            encoding="utf-8",
        )
    _chmod_secret_file(ENV_PATH)

def write_env(key: str, value: str, announce: bool = True) -> None:
    """Write KEY=value to the repo's .env.agents.

    Rewrites the file line-by-line so duplicate keys get collapsed to a
    single occurrence holding the latest value. Comments and blank lines
    are preserved in place. Never clobbers OTHER keys.
    """
    ensure_env_file()
    value = _clean_env_value(key, value)
    text = ENV_PATH.read_text(encoding="utf-8", errors="ignore")
    out_lines: list[str] = []
    replaced = False
    for raw in text.splitlines():
        s = raw.strip()
        # Preserve comments and blanks as-is.
        if not s or s.startswith("#"):
            out_lines.append(raw)
            continue
        if "=" not in s:
            out_lines.append(raw)
            continue
        k = s.split("=", 1)[0].strip()
        if k == key:
            if replaced:
                # Drop any duplicate occurrences after the first replacement.
                continue
            out_lines.append(f"{key}={value}")
            replaced = True
            continue
        out_lines.append(raw)
    if not replaced:
        # Key didn't exist — append it.
        out_lines.append(f"{key}={value}")
    # Rejoin; keep a single trailing newline.
    new_text = "\n".join(out_lines).rstrip() + "\n"
    tmp_path = ENV_PATH.with_name(f"{ENV_PATH.name}.tmp")
    tmp_path.write_text(new_text, encoding="utf-8")
    _chmod_secret_file(tmp_path)
    tmp_path.replace(ENV_PATH)
    _chmod_secret_file(ENV_PATH)
    if key not in _SAVED_THIS_SESSION:
        _SAVED_THIS_SESSION.append(key)
    if announce:
        print(f"    {GREEN(OK)} Saved {BOLD(key)} "
              f"{DIM('→ ' + str(ENV_PATH))}")

def read_env(key: str) -> str | None:
    if not ENV_PATH.exists():
        return None
    for raw in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = raw.strip()
        if s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        if k.strip() == key:
            return v.strip()
    return None


def _read_env_map() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    values: dict[str, str] = {}
    for raw in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, value = s.partition("=")
        key = key.strip()
        value = value.strip()
        if key and value:
            values[key] = value
    return values


def _public_context_values(profile: str) -> dict[str, str]:
    values = _read_env_map()
    prefixes = PROFILE_CONTEXT_PREFIXES.get(profile, [])
    allowed = set(COMMON_CONTEXT_KEYS)
    for key in values:
        if any(key.startswith(prefix) for prefix in prefixes):
            allowed.add(key)
    safe: dict[str, str] = {}
    for key in sorted(allowed):
        value = values.get(key)
        if not value:
            continue
        if any(marker in key for marker in PRIVATE_VALUE_MARKERS):
            continue
        safe[key] = value
    return safe


def _write_setup_profile(profile: str) -> Path:
    """Persist non-secret setup context under ~/.bravo/profiles/."""
    BRAVO_HOME.mkdir(parents=True, exist_ok=True)
    profiles_dir = BRAVO_HOME / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    context = _public_context_values(profile)
    payload = {
        "schema": "oasis.agent_setup.v1",
        "profile": profile,
        "profile_name": PROFILES[profile]["name"],
        "role": PROFILES[profile]["role"],
        "env_file": str(ENV_PATH),
        "written_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "operator": {
            "full_name": context.get("USER_FULL_NAME", ""),
            "preferred_name": context.get("USER_PREFERRED_NAME", ""),
            "business_name": context.get("USER_BUSINESS_NAME", ""),
            "role": context.get("USER_ROLE", ""),
        },
        "context": context,
    }
    path = profiles_dir / f"{profile}.setup.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _chmod_secret_file(path)
    return path


def _set_active_profile(profile: str) -> Path:
    """Make `bravo` open on the agent the user just configured."""
    BRAVO_HOME.mkdir(parents=True, exist_ok=True)
    config_path = BRAVO_HOME / "config.toml"
    text = config_path.read_text(encoding="utf-8", errors="ignore") if config_path.exists() else ""
    if re.search(r"^\s*active\s*=", text, flags=re.MULTILINE):
        text = re.sub(r'^\s*active\s*=\s*".*?"',
                      f'active = "{profile}"', text,
                      flags=re.MULTILINE, count=1)
    elif "[profile]" in text:
        text = text.replace("[profile]", f'[profile]\nactive = "{profile}"', 1)
    else:
        text = f'[profile]\nactive = "{profile}"\n' + text
    config_path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return config_path

# (mirror_to_repo_env removed — ENV_PATH is already the repo file.)

# ── I/O helpers ───────────────────────────────────────────────────────────────

def hr(char: str = "─", width: int = 64) -> None:
    print(DIM(char * width))

def step_header(number: int, total: int, title: str, subtitle: str = "") -> None:
    print()
    bar = f"[{number}/{total}]"
    print(f"{BG_CYAN(f' {bar} ')}  {BOLD(title)}")
    if subtitle:
        print(f"{' ' * (len(bar) + 4)}{DIM(subtitle)}")
    hr()

def prompt(label: str, default: str | None = None, required: bool = False) -> str:
    # "Enter to skip" hint when there's no default and it's optional — this
    # makes the long question flow feel lighter; you can power through with
    # Enter on anything you don't want to answer now.
    if default:
        hint = f" [{default}]"
    elif required:
        hint = f" {DIM('(needed)')}"
    else:
        hint = f" {DIM('(Enter to skip)')}"
    while True:
        try:
            raw = input(f"  {label}{hint}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(130)
        if raw:
            return raw
        if default is not None:
            return default
        if not required:
            return ""
        print(f"  {YELLOW('Required. Please try again.')}")

def yes_no(label: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        raw = input(f"  {label} [{hint}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(130)
    if not raw:
        return default
    return raw in {"y", "yes"}

def secret_prompt(label: str) -> str:
    try:
        return getpass.getpass(f"  {label}: ").strip()
    except Exception:
        print(f"  {YELLOW('(input will be visible)')}")
        return input(f"  {label}: ").strip()

# ── Validators (optional; return (ok, detail)) ────────────────────────────────

def _http_get(url: str, headers: dict[str, str] | None = None,
              timeout: int = 10) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return e.code, body
    except Exception as e:  # noqa: BLE001
        return 0, str(e)

def validate_anthropic(key: str) -> tuple[bool, str]:
    if not key.startswith("sk-ant-"):
        return False, "expected prefix sk-ant-"
    # Tiny POST to /v1/messages — valid key returns 200 or 400 with usage
    data = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data, method="POST",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
            r.read()
            return True, "accepted"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "unauthorized (401)"
        if e.code in (400, 429):
            return True, f"reachable (HTTP {e.code})"
        return False, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:80]

def validate_openai(key: str) -> tuple[bool, str]:
    # `status == 0` means the HTTP helper caught an exception (DNS / TLS /
    # connect refused / timeout). Treat that as "cannot verify", not "ok".
    status, _ = _http_get("https://api.openai.com/v1/models",
                          {"Authorization": f"Bearer {key}"})
    if status == 200:
        return True, "accepted"
    if status == 401:
        return False, "unauthorized"
    if status == 0:
        return False, "network error — could not reach OpenAI"
    return False, f"HTTP {status}"

def validate_google_ai(key: str) -> tuple[bool, str]:
    status, _ = _http_get(
        f"https://generativelanguage.googleapis.com/v1beta/models?key={key}")
    if status == 200:
        return True, "accepted"
    if status in (401, 403):
        return False, "unauthorized"
    if status == 0:
        return False, "network error — could not reach Google AI"
    return False, f"HTTP {status}"

def validate_stripe(key: str) -> tuple[bool, str]:
    status, _ = _http_get("https://api.stripe.com/v1/balance",
                          {"Authorization": f"Bearer {key}"})
    if status == 200:
        return True, "accepted"
    if status == 401:
        return False, "unauthorized"
    if status == 0:
        return False, "network error — could not reach Stripe"
    return False, f"HTTP {status}"

def validate_slack(token: str) -> tuple[bool, str]:
    status, body = _http_get("https://slack.com/api/auth.test",
                             {"Authorization": f"Bearer {token}"})
    if status != 200:
        return False, f"HTTP {status}"
    try:
        data = json.loads(body)
        if data.get("ok"):
            return True, f"team: {data.get('team', '?')}"
        return False, data.get("error", "rejected")
    except Exception:
        return False, "unparseable response"

def validate_discord(token: str) -> tuple[bool, str]:
    status, body = _http_get("https://discord.com/api/v10/users/@me",
                             {"Authorization": f"Bot {token}"})
    if status == 200:
        try:
            data = json.loads(body)
            return True, f"bot: {data.get('username', '?')}"
        except Exception:
            return True, "accepted"
    if status == 401:
        return False, "unauthorized"
    return False, f"HTTP {status}"

VALIDATORS: dict[str, Callable[[str], tuple[bool, str]]] = {
    "ANTHROPIC_API_KEY":  validate_anthropic,
    "OPENAI_API_KEY":     validate_openai,
    "GOOGLE_AI_API_KEY":  validate_google_ai,
    "STRIPE_SECRET_KEY":  validate_stripe,
    "SLACK_BOT_TOKEN":    validate_slack,
    "DISCORD_BOT_TOKEN":  validate_discord,
}

# ── Telegram-specific flow (end-to-end test message) ──────────────────────────

def _tg_api(token: str, method: str, params: dict | None = None,
            timeout: int = 15) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "bravo-wizard"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8"))

def tg_validate(token: str) -> dict | None:
    try:
        r = _tg_api(token, "getMe")
    except urllib.error.HTTPError as e:
        print(f"  {RED('HTTP')} {e.code}: {e.reason}")
        return None
    except Exception as e:  # noqa: BLE001
        print(f"  {RED('Request failed:')} {e}")
        return None
    if not r.get("ok"):
        print(f"  {RED('Telegram rejected token:')} {r.get('description')}")
        return None
    return r["result"]

def tg_wait_for_chat_id(token: str, timeout: int = 120) -> int | None:
    deadline = time.time() + timeout
    last_update = 0
    while time.time() < deadline:
        try:
            r = _tg_api(token, "getUpdates",
                        {"offset": last_update + 1, "timeout": 0})
        except Exception as e:  # noqa: BLE001
            print(f"  {YELLOW('Poll error')}: {e}")
            time.sleep(2)
            continue
        for upd in r.get("result", []):
            last_update = max(last_update, upd.get("update_id", 0))
            msg = upd.get("message") or upd.get("edited_message") or {}
            chat = msg.get("chat") or {}
            cid = chat.get("id")
            if cid:
                return int(cid)
        time.sleep(2)
    return None

def tg_send(token: str, chat_id: int, text: str) -> bool:
    try:
        r = _tg_api(token, "sendMessage", {"chat_id": chat_id, "text": text})
        return bool(r.get("ok"))
    except Exception:
        return False

def telegram_flow(profile_name: str) -> bool:
    print(f"  {ITALIC('Telegram is the easiest remote control — set it up in 60 seconds.')}")
    print(f"  {ITALIC('We will: validate your bot token, find your chat, and send you a test message.')}")
    print()
    print(f"  {BOLD('1.')} Open Telegram and message {link('https://t.me/BotFather', '@BotFather')}")
    print(f"  {BOLD('2.')} Send {CYAN('/newbot')}, pick a name, pick a username ending in 'bot'")
    print(f"  {BOLD('3.')} BotFather replies with a token like {DIM('123456:ABC-DEF_ghi...')}")
    print()
    for attempt in range(3):
        token = secret_prompt("Paste BOT_TOKEN")
        if not token:
            print(f"  {DIM('Skipped.')}")
            return False
        if not re.match(r"^\d+:[A-Za-z0-9_\-]{30,}$", token):
            print(f"  {YELLOW('Format looks off. Expected like 123456:ABC...')}")
            if not yes_no("Try again?", default=True):
                return False
            continue
        print(f"  {DIM(ARROW + ' Validating via getMe...')}")
        me = tg_validate(token)
        if me:
            print(f"  {GREEN(OK)} Connected to {BOLD('@' + me.get('username', '?'))} "
                  f"({me.get('first_name', '?')})")
            write_env("TELEGRAM_BOT_TOKEN", token)
            break
        if attempt < 2:
            print(f"  {YELLOW('Token rejected. Try again.')}")
    else:
        print(f"  {RED('Gave up after 3 attempts.')}")
        return False

    print()
    print(f"  {BOLD('Now link your chat:')}")
    print(f"  {BOLD('4.')} Open Telegram, find {BOLD('@' + me.get('username', 'your_bot'))}")
    print(f"  {BOLD('5.')} Press {CYAN('Start')} or send any message (like {CYAN('hi')})")
    print(f"  {BOLD('6.')} Come back here — the wizard detects your chat automatically")
    print()
    # Flush any pending updates from before the user messaged the bot — this
    # stops a stale backlog from binding the wrong chat_id.
    try:
        _tg_api(token, "getUpdates", {"offset": -1})
    except Exception:
        pass
    input(f"  {DIM('Press Enter once you have messaged your bot...')} ")
    print(f"  {DIM(ARROW + ' Listening for a fresh message (up to 120s)...')}")
    chat_id = tg_wait_for_chat_id(token, timeout=120)
    if chat_id is None:
        print(f"  {YELLOW('No message detected.')} Re-run {CYAN('bravo setup')} later.")
        return False
    print(f"  {GREEN(OK)} Detected chat_id {BOLD(str(chat_id))}")
    # Explicit operator confirmation — Codex self-review surfaced this: if
    # multiple people chat the bot during setup, the first one "wins" the
    # bridge without the user noticing.
    if not yes_no(f"Is {BOLD(str(chat_id))} YOUR chat (the one you just messaged from)?",
                  default=True):
        print(f"  {YELLOW('Not bound.')} Re-run {CYAN('bravo setup')} "
              f"when your bot has no backlog.")
        return False
    write_env("TELEGRAM_CHAT_ID", str(chat_id))
    # telegram_agent.js + funnel_nurture.py read TELEGRAM_ALLOWED_USERS for
    # outbound messages. Keep them in sync so the bridge works end-to-end.
    write_env("TELEGRAM_ALLOWED_USERS", str(chat_id))
    test_msg = (f"✅ {profile_name} is connected to Telegram. "
                "You will get updates here. Reply /help anytime.")
    if tg_send(token, chat_id, test_msg):
        print(f"  {GREEN(OK)} Test message sent — check Telegram.")
    else:
        print(f"  {YELLOW('Test message failed, but token + chat_id are saved.')}")
    return True

# ── Generic integration prompt ────────────────────────────────────────────────

def integration_step(slug: str, required: bool) -> bool:
    """Prompt for one integration's env_key(s). Returns True if saved."""
    spec = INTEGRATIONS[slug]
    existing = read_env(spec["env_key"])
    header = f"{BOLD(spec['label'])}  {DIM('· ' + spec['tagline'])}"
    if existing:
        mark = GREEN(OK + " set")
        print(f"  {header}  {mark}")
        if not yes_no("Replace?", default=False):
            return True
    else:
        req_mark = RED(" (required)") if required else DIM(" (optional)")
        print(f"  {header}{req_mark}")
        if not required and not yes_no("Add it now?", default=False):
            print(f"  {DIM('Skipped.')}")
            return False

    # ── Offer CLI-based auth as an alternative to a raw API key ─────────────
    # Companion CLIs (Claude Code / Codex / Gemini CLI) manage auth in the OS
    # secure credential store. More private than a raw key in .env.agents.
    # BUT: today only a subset of downstream scripts respect the _AUTH_MODE
    # marker. Default is "No" so the safe path (raw key — every script works)
    # is one-Enter. Opt in only if you know what you're doing.
    cli = spec.get("cli_auth")
    if cli and shutil.which(cli["cmd"]):
        print(f"    {GREEN(OK)} Detected {BOLD(cli['label'])} on PATH.")
        print(f"    {DIM('CLI auth stays in your OS keychain — no raw key on disk.')}")
        print(f"    {YELLOW(WARN)} {DIM('Beta: existing scripts still expect a raw key. If unsure, say No.')}")
        if yes_no(f"Use {cli['label']} anyway?", default=False):
            write_env(cli["mode_key"], cli["mode_value"])
            print(f"    {DIM('Marker written. Wire scripts to read ' + cli['mode_key'] + ' over time.')}")
            print()
            return True
        print(f"    {DIM('Good call — raw key is the reliable path today.')}")

    # Tell user where to get it
    print(f"    {DIM('Get it:')} {link(spec['url'])}")
    if spec.get("format"):
        print(f"    {DIM('Format:')} {DIM(spec['format'])}")
    for i, line in enumerate(spec.get("instructions", []), start=1):
        print(f"    {DIM(str(i) + '.')} {DIM(line)}")
    print()

    # Primary key
    value = (secret_prompt(f"Paste {spec['env_key']}")
             if spec.get("secret") else prompt(spec["env_key"]))
    if not value:
        if required:
            print(f"  {RED('Required — cannot skip.')}")
            return False
        print(f"  {DIM('Skipped.')}")
        return False
    # Validate if we can
    validator = VALIDATORS.get(spec["env_key"])
    if validator:
        print(f"    {DIM(ARROW + ' Validating...')}")
        ok, detail = validator(value)
        if ok:
            print(f"    {GREEN(OK)} {detail}")
        else:
            print(f"    {YELLOW(WARN)} {detail}")
            if not yes_no("Save anyway?", default=True):
                return False
    write_env(spec["env_key"], value)

    # Follow-up key (e.g., SUPABASE service_role, N8N_API_KEY, TWILIO token)
    if spec.get("followup_key"):
        fkey = spec["followup_key"]
        flabel = spec.get("followup_label", fkey)
        fsecret = spec.get("followup_secret", True)
        fval = (secret_prompt(f"Paste {flabel}")
                if fsecret else prompt(flabel))
        if fval:
            write_env(fkey, fval)
    print()
    return True

# ── Steps ─────────────────────────────────────────────────────────────────────

def _dashboard_url() -> str:
    return (
        os.environ.get("BRAVO_DASHBOARD_URL")
        or read_env("BRAVO_DASHBOARD_URL")
        or "https://agent-dashboard-cc90210.vercel.app"
    ).rstrip("/")


def _bridge_token_path() -> Path:
    return Path.home() / ".oasis" / "bridge_token"


def _bridge_token() -> str:
    try:
        return _bridge_token_path().read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _post_bridge_services(dashboard_url: str, services: dict[str, dict]) -> bool:
    token = _bridge_token()
    if not token or not services:
        return False
    req = urllib.request.Request(
        f"{dashboard_url}/api/bridge/ping",
        method="POST",
        data=json.dumps({"services": services}).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
            payload = json.loads(r.read().decode("utf-8"))
        return bool(payload.get("ok"))
    except Exception:
        return False


def step_welcome() -> None:
    print_banner()
    print(f"  {BOLD('Welcome.')} We're onboarding your new digital employee.")
    print(f"  {DIM('Pick the agent you want to hire, then we will connect the tools it needs behind the scenes.')}")
    print(f"  {DIM('Keys go to')} {CYAN(str(ENV_PATH))}  {DIM('(0600 on POSIX)')}.")
    print(f"  {DIM('Nothing is uploaded; you stay in full control.')}")
    print()
    try:
        input(f"  {BOLD('Press Enter when ready...')} ")
    except (EOFError, KeyboardInterrupt):
        sys.exit(130)

def step_profile() -> str:
    # Header is deliberately unnumbered — step count depends on which agent
    # they pick, so "[1/9]" would be a lie for Bravo (where total is 8) or
    # Custom (5). Numbered progress starts after the pick.
    print()
    print(f"{BG_CYAN('  Choose an agent profile  ')}")
    print(f"    {DIM('Each agent has different tools for its role.')}")
    hr()
    print()
    slugs = list(PROFILES.keys())
    for idx, slug in enumerate(slugs, start=1):
        p = PROFILES[slug]
        icon = p["icon"]
        colored_name = p["color"](BOLD(p["name"]))
        print(f"  {DIM(str(idx) + '.')}  {colored_name}  {DIM('—')} {p['role']}")
        print(f"       {DIM(p['tagline'])}  "
              f"{DIM('(' + icon + ')')}")
        print()
    while True:
        raw = prompt(f"Pick an agent (1-{len(slugs)})", required=True).strip()
        try:
            n = int(raw)
            if 1 <= n <= len(slugs):
                chosen = slugs[n - 1]
                _confirm_profile(chosen)
                return chosen
        except ValueError:
            pass
        print(f"  {RED('Enter a number 1-' + str(len(slugs)))}")


def _confirm_profile(slug: str) -> None:
    """Big, impossible-to-miss confirmation. Shows the agent's block-letter
    figlet in the agent's color, plus role + tagline."""
    p = PROFILES[slug]
    color = p["color"]
    figlet = _agent_figlet(slug)
    print()
    print(f"  {color('━' * 62)}")
    if figlet:
        # Indent each line of the figlet for alignment.
        for line in figlet.splitlines():
            if line.strip():
                print(f"  {color(line)}")
    print()
    print(f"  {color(OK)}  {BOLD(color('SELECTED: ' + p['name'].upper()))}")
    print(f"     {DIM('Role:')}   {p['role']}")
    print(f"     {DIM('Focus:')}  {p['tagline']}")
    print(f"  {color('━' * 62)}")
    print()
    try:
        input(f"  {DIM('Press Enter to continue with ' + BOLD(p['name']) + '...')} ")
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(130)


# ── Dynamic questions + repo clone steps ──────────────────────────────────────

def _ask_one(q: dict) -> str:
    """Ask a single question from a PROFILE_QUESTIONS / BUSINESS_CONTEXT entry.

    Env-var override: if the question's `key` is already set in the
    environment (e.g. via the /configure pre-signup flow exporting
    OASIS_OPERATOR_NAME → USER_FULL_NAME), skip the prompt and return
    that value. Falls through to interactive prompt otherwise.

    Aliases below map the public-facing OASIS_* env names (set by
    /configure's generated install one-liner) onto the wizard's internal
    question keys.
    """
    OASIS_ALIASES = {
        "USER_FULL_NAME": "OASIS_OPERATOR_NAME",
        "USER_PREFERRED_NAME": "OASIS_OPERATOR_NICKNAME",
        "USER_BUSINESS_NAME": "OASIS_BRAND",
        "BRAVO_PRIMARY_BRAND": "OASIS_BRAND",
        "BRAVO_NORTH_STAR_METRIC": "OASIS_NORTH_STAR",
        "USER_PRIMARY_METRIC": "OASIS_NORTH_STAR",
    }
    key = q.get("key", "")
    pre = os.environ.get(key, "").strip()
    if not pre and key in OASIS_ALIASES:
        pre = os.environ.get(OASIS_ALIASES[key], "").strip()
    if pre:
        # Use the pre-set value directly. Echo so the operator sees what
        # got skipped — matches the rest of the wizard's chatty UX.
        print(f"  {GREEN(OK)} {q['prompt']}: {CYAN(pre)} {DIM('(from env)')}")
        return pre

    qtype = q.get("type", "text")
    label = q["prompt"]
    default = q.get("default")
    required = bool(q.get("required", False))
    if qtype == "choice":
        choices = q["choices"]
        print(f"  {label}  {DIM('(' + '/'.join(choices) + ')')}")
        default_str = default if default in choices else choices[0]
        # Case-insensitive map so choices like ["MRR","ARR"] or ["CA","US"]
        # work when the user types "mrr" OR "MRR" OR presses Enter to accept
        # a default like "MRR". Canonical stored value is whatever is in
        # the choices list; we always return that exact form.
        canon = {c.lower(): c for c in choices}
        while True:
            raw = prompt(f"  answer", default=str(default_str)).strip().lower()
            if raw in canon:
                return canon[raw]
            # Partial match — "con" -> "consulting", "ca" -> "CA".
            hits = [canon[k] for k in canon if k.startswith(raw)]
            if len(hits) == 1:
                return hits[0]
            print(f"  {RED('Pick one of:')} {', '.join(choices)}")
    if qtype == "yesno":
        return "true" if yes_no(label, default=bool(default)) else "false"
    # text (default)
    if q.get("secret"):
        val = secret_prompt(label)
    else:
        val = prompt(label, default=str(default) if default else None,
                     required=required)
    return val


def _business_context_questions(profile: str) -> list[dict]:
    """Return shared context questions, with profile-specific de-duplication."""
    if profile == "hermes":
        # Hermes asks for the client/company industry in its own focused block.
        # Asking USER_INDUSTRY first felt like the same question twice.
        return [q for q in BUSINESS_CONTEXT_QUESTIONS
                if q["key"] != "USER_INDUSTRY"]
    return BUSINESS_CONTEXT_QUESTIONS


def step_user_identity(profile: str, step_num: int, total: int) -> None:
    """Capture who the agent works for before any domain-specific setup."""
    step_header(step_num, total, "About you",
                "This teaches the agent who is using it and where to save that memory.")
    for q in USER_IDENTITY_QUESTIONS:
        ans = _ask_one(q)
        if ans:
            write_env(q["key"], ans)


def step_business_context(profile: str, step_num: int, total: int) -> None:
    """Deep, not extensive. Five shared questions that turn any general-purpose
    agent (CEO/CFO/CMO/commerce) into one tailored to the user's actual
    business. A real-estate agent and a SaaS founder get different behavior
    from the same Maven install because the ANSWERS differ."""
    if profile not in BUSINESS_CONTEXT_PROFILES:
        return
    questions = _business_context_questions(profile)
    step_header(step_num, total, "Operating context",
                f"{len(questions)} questions. Press Enter to skip anything you'd rather come back to.")
    for q in questions:
        ans = _ask_one(q)
        if ans:
            write_env(q["key"], ans)


def step_agent_questions(profile: str, step_num: int, total: int) -> None:
    """Per-agent targeted questions — north star, fiscal year, brand voice,
    residence city, client industry, etc."""
    qs = PROFILE_QUESTIONS.get(profile, [])
    if not qs:
        return
    p = PROFILES[profile]
    title = (f"Tune {p['name']} to the client operation"
             if profile == "hermes"
             else f"Tune {p['name']} to how you operate")
    step_header(step_num, total, title,
                f"{len(qs)} questions. Defaults are good — press Enter to accept.")
    for q in qs:
        ans = _ask_one(q)
        if ans:
            write_env(q["key"], ans)


def _reroot_env_path(target: Path) -> None:
    """Point subsequent write_env() calls at the cloned agent's repo.

    Without this, every key the user enters after picking Atlas/Maven/Aura/
    Hermes would still land in the LAUNCHER repo (whichever repo ships the
    wizard), leaving the cloned agent's .env.agents empty. Codex V1.4 review
    flagged this as a high-severity launch blocker.
    """
    global ENV_PATH
    ENV_PATH = target / ".env.agents"


def _activate_env_destination(target: Path) -> bool:
    """Switch env writes to target/.env.agents and harden that destination."""
    _reroot_env_path(target)
    try:
        ensure_env_file()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  {RED('Secret-file safety check failed:')} {exc}")
        sys.exit(1)


def _clone_one_repo(url: str, target: Path, label: str) -> bool:
    """Shallow-clone one repo. Idempotent — skips if already cloned.
    Returns True on success (or if already present)."""
    if target.exists() and (target / ".git").exists():
        print(f"    {GREEN(OK)} {label}: already at {CYAN(str(target))}")
        return True
    if not shutil.which("git"):
        print(f"    {RED('git missing — cannot clone ' + label)}")
        return False
    print(f"    {DIM(ARROW + ' cloning ' + label + '...')}")
    try:
        r = subprocess.run(["git", "clone", "--depth", "10", url, str(target)],
                           capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            print(f"    {GREEN(OK)} {label} -> {CYAN(str(target))}")
            return True
        print(f"    {RED('FAIL')} {label}: {r.stderr.strip()[:160]}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"    {RED('ERROR')} {label}: {exc}")
        return False


def step_clone_agent_repo(profile: str, step_num: int, total: int) -> None:
    """Offer to clone the selected agent's own GitHub repo into ~/.

    The OASIS AI wizard is ONE entry point for all five agents. If someone
    picks Atlas, we fetch CFO-Agent; Maven -> CMO-Agent; etc. All five
    sibling repos are public on github.com/CC90210.

    Bravo is special: it's the orchestrator. Bravo users often want
    Atlas/Maven/Aura/Hermes also cloned for cross-agent workflows, so we
    offer that as a batch at this step.

    On successful clone (or when an existing clone is detected), we re-root
    the wizard's ENV_PATH to the cloned repo so all subsequent key writes
    land where that agent's scripts will read them.
    """
    repo_info = AGENT_REPOS.get(profile)
    if not repo_info:
        # Custom — no repo to clone; user scaffolds via `bravo agent create`.
        return
    p = PROFILES[profile]
    target = Path(repo_info["dir"]).expanduser()
    step_header(step_num, total, f"Clone the {p['name']} repo",
                f"Grabs {repo_info['url']} into {target}")

    if target.exists() and (target / ".git").exists():
        print(f"  {GREEN(OK)} Already cloned at {CYAN(str(target))}")
        if _activate_env_destination(target):
            print(f"  {GREEN(OK)} Config will save to {CYAN(str(ENV_PATH))}")
        return
    if not yes_no(f"Clone {p['name']} to {target}?", default=True):
        print(f"  {YELLOW(WARN)} Skipped clone — config will save to the launcher repo")
        print(f"     {DIM('(' + str(ENV_PATH) + ')')}")
        print(f"  {DIM('For a clean ' + p['name'] + ' install, re-run and accept the clone.')}")
        return
    if not shutil.which("git"):
        print(f"  {RED('git not on PATH. Install Git, then re-run.')}")
        return
    print(f"  {DIM(ARROW + ' Cloning... (shallow, depth 10)')}")
    try:
        r = subprocess.run(["git", "clone", "--depth", "10",
                            repo_info["url"], str(target)],
                           capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            print(f"  {GREEN(OK)} Cloned to {CYAN(str(target))}")
            if _activate_env_destination(target):
                print(f"  {GREEN(OK)} Config will save to {CYAN(str(ENV_PATH))}")
        else:
            err_msg = r.stderr.strip()[:200] or "unknown error"
            print(f"  {RED('Clone failed:')} {err_msg}")
            print(f"  {YELLOW(WARN)} Continuing with launcher repo as config destination.")
    except Exception as exc:
        print(f"  {RED('Clone error:')} {exc}")
        print(f"  {YELLOW(WARN)} Continuing with launcher repo as config destination.")

    # Bravo-only: offer to clone siblings too for full C-Suite orchestration.
    # Gap-2 fix — without this, picking Bravo leaves Atlas/Maven/Aura/Hermes
    # repos unclonedand cross-agent workflows silently fail later.
    if profile == "bravo":
        sibling_slugs = ["atlas", "maven", "aura", "hermes"]
        missing = [s for s in sibling_slugs
                   if not (Path(AGENT_REPOS[s]["dir"]).expanduser() / ".git").exists()]
        if not missing:
            return
        print()
        print(f"  {BOLD('Bravo orchestrates the whole C-Suite.')} "
              f"{DIM(str(len(missing)) + ' sibling repo(s) missing locally:')}")
        for s in missing:
            sp = PROFILES[s]
            print(f"    {sp['color'](sp['name']):18s} {DIM(AGENT_REPOS[s]['url'])}")
        print()
        if yes_no(f"Clone all {len(missing)} siblings too? (shallow, ~20 MB total)",
                  default=True):
            for s in missing:
                info = AGENT_REPOS[s]
                target_s = Path(info["dir"]).expanduser()
                _clone_one_repo(info["url"], target_s, PROFILES[s]["name"])
        else:
            print(f"  {DIM('Skipped — clone any time with:')}")
            for s in missing:
                print(f"    {DIM('git clone --depth 10 ' + AGENT_REPOS[s]['url'] + ' ' + AGENT_REPOS[s]['dir'])}")


def step_ai(profile: str, step_num: int, total: int) -> None:
    p = PROFILES[profile]
    required_names = [
        INTEGRATIONS[slug]["label"]
        for slug in p["ai"]
        if slug in p["required"]
    ]
    subtitle = (
        f"{', '.join(required_names)} required. Others are backup options."
        if required_names
        else "Optional cloud providers. Skip these for local-first installs."
    )
    step_header(step_num, total, "AI providers", subtitle)
    for slug in p["ai"]:
        required = slug in p["required"]
        integration_step(slug, required=required)

def step_chat(profile: str, step_num: int, total: int) -> None:
    p = PROFILES[profile]
    step_header(step_num, total, "Chat bridges",
                "Remote control from any messenger. Telegram is fastest.")
    for slug in p["chat"]:
        spec = INTEGRATIONS[slug]
        # Telegram uses a custom end-to-end flow
        if slug == "telegram":
            print(f"  {BOLD(spec['label'])}  {DIM('· ' + spec['tagline'])}")
            if yes_no("Set up Telegram now?", default=True):
                telegram_flow(profile_name=PROFILES[profile]["name"])
            print()
        else:
            integration_step(slug, required=False)

def step_business(profile: str, step_num: int, total: int) -> None:
    p = PROFILES[profile]
    if not p["business"]:
        return
    if profile == "sunbiz":
        step_header(step_num, total, "Client systems",
                    "Let's connect the tools Solara needs to track deals, send texts, and keep the pipeline moving.")
    else:
        step_header(step_num, total, "Business operations",
                    "Revenue tracking, CRM, automations — all optional.")
    for slug in p["business"]:
        integration_step(slug, required=False)

def step_extra(profile: str, step_num: int, total: int) -> None:
    p = PROFILES[profile]
    if not p["extra"]:
        return
    step_header(step_num, total, f"{p['name']}-specific integrations",
                f"Tools that make sense for a {p['role'].lower()}.")
    for slug in p["extra"]:
        integration_step(slug, required=False)

def _playwright_chromium_present() -> bool:
    """Return True if a Playwright chromium build is already on disk.

    Checks the OS-specific cache dir Playwright uses. Skipping the download
    when already present matters — 500 MB / 1-3 min of tax on re-runs.
    """
    if os.name == "nt":
        cache = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    elif sys.platform == "darwin":
        cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    else:
        cache = Path.home() / ".cache" / "ms-playwright"
    if not cache.exists():
        return False
    # Playwright stores chromium under chromium-<revision>/chrome-<platform>/
    return any(p.name.startswith("chromium-") for p in cache.iterdir())


def step_playwright_browsers(step_num: int, total: int) -> None:
    """Opt-in Chromium install for browser automation.

    ~500 MB download. Skipped entirely when already installed. Never forced
    — many clients only need the chat/ops side of an agent. If they say
    yes, shells out to `python -m playwright install chromium`.
    """
    step_header(step_num, total, "Browser automation (optional)",
                "Chromium binaries for Playwright. ~500 MB — skip if unsure.")
    # If Playwright isn't even installed, there's nothing to do.
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import playwright; print('ok')"],
            capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            print(f"  {DIM('Playwright package not found — skipping. Re-run setup after fixing pip.')}")
            return
    except Exception:
        print(f"  {DIM('Could not probe Playwright — skipping.')}")
        return
    # Idempotent short-circuit.
    if _playwright_chromium_present():
        print(f"  {GREEN(OK)} Chromium already installed — skipping download.")
        return
    print(f"  {BOLD('Skool automation, client-portal scrapers, and every browser-use')}")
    print(f"  {BOLD('skill need this.')} {DIM('Chat/Stripe/Supabase only? Skip it.')}")
    print()
    if not yes_no("Download Chromium for Playwright now (~500 MB)?",
                  default=False):
        print(f"  {DIM('Skipped. Run `python -m playwright install chromium` later if needed.')}")
        return
    print(f"  {DIM(ARROW + ' This takes 1-3 minutes on a reasonable connection...')}")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            timeout=600)
        if r.returncode == 0:
            print(f"  {GREEN(OK)} Chromium installed.")
        else:
            print(f"  {YELLOW(WARN)} Install exited {r.returncode}. "
                  f"Try `python -m playwright install chromium` manually.")
    except Exception as exc:
        print(f"  {RED('Install error:')} {exc}")


def _harness_post_install_checklist() -> None:
    """Print the manual steps the user has to do AFTER install for harness
    to be useful. The install puts the binary on PATH but harness can only
    act on sites the user is ALREADY logged into in their dedicated Chrome
    profile. Without these steps the install is dead weight."""
    print()
    print(f"  {BOLD('What you do next (one-time, ~5 minutes):')}")
    print(f"    {CYAN('1.')} Run {CYAN('bravo browser setup')}")
    print(f"       {DIM('Opens a dedicated Chrome window with remote-debug enabled.')}")
    print(f"    {CYAN('2.')} In that Chrome window, log into the sites you want this agent to act on:")
    print(f"       {DIM('Skool, Stripe dashboard, Supabase, Vercel, anywhere it needs to act AS YOU.')}")
    print(f"    {CYAN('3.')} Leave that Chrome window running in the background.")
    print(f"       {DIM('The agent attaches to it; if it closes, the agent loses access until re-opened.')}")
    print(f"    {CYAN('4.')} Verify with {CYAN('bravo browser doctor')}.")
    print()
    print(f"  {DIM('You can do this later — `bravo browser setup` is safe to run anytime.')}")


def step_browser_harness(step_num: int, total: int) -> None:
    """Detect + optionally install Browser Harness.

    Complementary to Playwright — Browser Harness attaches to the user's
    LOGGED-IN Chrome/Edge for real-account actions (Skool posting, Stripe
    dashboard reads, etc.). Playwright launches its own throwaway browser;
    Browser Harness drives yours.

    Pre-existing installs are detected and skipped. Fresh installs are
    offered as opt-in since they need one-time Chrome remote-debug approval
    AND a manual login pass before they can do anything useful.
    """
    step_header(step_num, total, "Browser Harness (optional)",
                "Drives your real, logged-in Chrome/Edge — Skool, Stripe dashboard, etc.")
    harness_exe = shutil.which("browser-harness")
    local_exe = Path.home() / ".local" / "bin" / (
        "browser-harness.exe" if os.name == "nt" else "browser-harness")
    if harness_exe or local_exe.exists():
        found = harness_exe or str(local_exe)
        print(f"  {GREEN(OK)} Already installed at {CYAN(str(found))}")
        _harness_post_install_checklist()
        return

    # Plain-English explanation of the trade-off, since most clients
    # haven't seen this kind of tool before.
    print(f"  {DIM('Different from Playwright — drives your REAL browser session, not a throwaway one.')}")
    print(f"  {DIM('Use it when an action needs to happen UNDER YOUR LOGIN (Skool replies,')}")
    print(f"  {DIM('Stripe dashboard pulls, anything a public scraper would get blocked from).')}")
    print(f"  {DIM('Skip it if you only need APIs and clean public scraping — most workflows are fine without it.')}")
    print()
    if not yes_no("Install Browser Harness now?", default=False):
        print(f"  {DIM('Skipped. Later:')} {CYAN('bravo browser setup')}")
        return

    # Preferred install path: uv tool (fast, isolated). Fall back to pip.
    if shutil.which("uv"):
        cmd = ["uv", "tool", "install", "browser-use"]
        print(f"  {DIM(ARROW + ' uv tool install browser-use...')}")
    else:
        cmd = [sys.executable, "-m", "pip", "install", "browser-use"]
        print(f"  {DIM(ARROW + ' pip install browser-use...')}")
    try:
        r = subprocess.run(cmd, timeout=300)
        if r.returncode == 0:
            print(f"  {GREEN(OK)} Installed.")
            _harness_post_install_checklist()
        else:
            print(f"  {YELLOW(WARN)} Install exited {r.returncode}. "
                  f"See {link('https://github.com/browser-use/browser-use')}")
    except Exception as exc:
        print(f"  {RED('Install error:')} {exc}")


# Carries the post-install `bravo doctor` exit code from step_finalize
# back up to run_wizard, which propagates it to the CLI exit code so the
# one-liner returns non-zero when verification fails. A 1-element list
# (mutable holder) is used instead of a plain int because step_finalize
# is called from inside run_wizard's local scope and we want the value
# to survive whatever happens in the print/yes_no branches above it.
_post_doctor_rc: list[int] = [0]


# ── V6.0 deployment + sandbox steps ───────────────────────────────────────────

V6_SCOPED_ENV_FILES = {
    # service → list of env keys it needs. Anything not in the list is
    # withheld from that service's container — defense in depth against
    # one-service-RCE pulling every credential.
    "core": None,  # bravo-core gets everything; it's the autonomous loop
    "webhook": [
        "BRAVO_SUPABASE_URL", "BRAVO_SUPABASE_ANON_KEY",
        "STRIPE_WEBHOOK_SECRET", "WEBHOOK_HMAC_KEY",
        "N8N_WEBHOOK_TOKEN", "TELEGRAM_BOT_TOKEN",
        "EMPIRE_V6_MODE", "EMPIRE_HOOK_SECRET_GUARD", "EMPIRE_HOOK_EXEC_GUARD",
        "EMPIRE_HOOK_STATE_GUARD", "EMPIRE_DEPLOY_TARGET",
        "EMPIRE_DATA_BACKEND", "BRIDGE_PAIRING_TOKEN",
    ],
    "dashboard": [
        # Public Supabase only — no service-role, no Stripe secret, no Anthropic.
        "BRAVO_SUPABASE_URL", "BRAVO_SUPABASE_ANON_KEY",
        "NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY",
        "STATE_API_URL", "DASHBOARD_DOMAIN",
        "EMPIRE_DEPLOY_TARGET",
        # Data sovereignty: Turso reads when the tenant opts for local libSQL
        "EMPIRE_DATA_BACKEND", "TURSO_DB_PATH", "TURSO_DB_URL", "TURSO_AUTH_TOKEN",
    ],
}


def _detect_deploy_target() -> str:
    """Best-effort local-vs-cloud detection. Operator gets the final say."""
    if os.environ.get("EMPIRE_DEPLOY_TARGET"):
        return os.environ["EMPIRE_DEPLOY_TARGET"].lower()
    # Cloud signals: SSH session, no display, /sys/devices/virtual/dmi indicators
    if os.environ.get("SSH_CONNECTION"):
        return "cloud"
    if os.name == "posix" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        # No GUI on a Linux box → likely a VPS
        if Path("/.dockerenv").exists() or Path("/run/.containerenv").exists():
            return "cloud"
    return "local"


def _docker_available() -> tuple[bool, str]:
    """Return (available, message). Doesn't fail the wizard if Docker is missing."""
    if not shutil.which("docker"):
        return (False, "docker CLI not on PATH")
    try:
        r = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return (True, f"docker {r.stdout.strip()}")
        return (False, "docker daemon not responding (start Docker Desktop?)")
    except (subprocess.TimeoutExpired, OSError) as e:
        return (False, f"docker probe failed: {e}")


def _read_master_env() -> dict[str, str]:
    """Parse the master .env.agents into a dict (in-memory, never echoed)."""
    out: dict[str, str] = {}
    if not ENV_PATH.exists():
        return out
    for raw in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _write_scoped_env_file(path: Path, allowed_keys: list[str] | None,
                           master: dict[str, str]) -> int:
    """Write a per-service .env.agents.<service> file. Returns key count.

    `allowed_keys=None` means "every key the master has" (used by bravo-core).
    """
    if allowed_keys is None:
        keys = sorted(master.keys())
    else:
        keys = [k for k in allowed_keys if k in master]

    lines = [
        f"# {path.name} — scoped env, written by `bravo setup`.",
        "# Per-service subset of the master .env.agents.",
        "# Keys NOT listed here are deliberately withheld from this service",
        "# so a one-service compromise cannot exfiltrate the full credential set.",
        "",
    ]
    for k in keys:
        v = master[k]
        if v and ("\n" in v or " " in v or v != v.strip()):
            v = '"' + v.replace('"', '\\"') + '"'
        lines.append(f"{k}={v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _chmod_secret_file(path)
    return len(keys)


def _fan_out_scoped_env_files() -> dict[str, int]:
    """Generate .env.agents.{core,webhook,dashboard} from the master file."""
    master = _read_master_env()
    if not master:
        return {}
    counts: dict[str, int] = {}
    for service, allowed in V6_SCOPED_ENV_FILES.items():
        target = REPO_ROOT / f".env.agents.{service}"
        counts[service] = _write_scoped_env_file(target, allowed, master)
    return counts


def step_environment(step_num: int, total: int) -> None:
    """Detect local-vs-cloud deploy target so downstream steps can adapt."""
    step_header(step_num, total, "Deployment target",
                "Local laptop sandbox or always-on cloud VPS?")
    detected = _detect_deploy_target()
    print(f"  {DIM('Auto-detected:')} {CYAN(detected)}")
    print()
    print(f"  {BOLD('Where will this agent run day-to-day?')}")
    print(f"    {CYAN('1)')} Local — laptop / desktop, single operator")
    print(f"    {CYAN('2)')} Cloud — VPS / always-on, dashboard accessed remotely")
    print()
    default = "1" if detected == "local" else "2"
    try:
        choice = input(f"  Choose [1/2] (default {default}): ").strip() or default
    except (EOFError, KeyboardInterrupt):
        choice = default
    target = "local" if choice == "1" else "cloud"
    write_env("EMPIRE_DEPLOY_TARGET", target)
    print(f"  {GREEN(OK)} Target: {CYAN(target)}")
    print()


def step_data_sovereignty(profile: str, step_num: int, total: int) -> None:
    """
    Where does this tenant's BUSINESS DATA live? Two choices:

      1) Local Machine (Recommended)
         libSQL file at ~/.bravo/<profile>.db. Loan files, deal records,
         fan DMs, merch orders — never leave the operator's machine. OASIS
         operators read pulse/state via the bridge but cannot see client
         data. PII-heavy industries (funding, healthcare, legal) should
         pick this.

      2) Cloud (OASIS-hosted Supabase)
         Multi-tenant Supabase, RLS-isolated, OASIS-managed backups. Choose
         this if the operator wants zero-machine-management and is OK with
         their tenant data living in a managed cloud DB.

    Writes:
      EMPIRE_DATA_BACKEND = turso_local | supabase_cloud
      (turso_local) TURSO_DB_PATH, TURSO_AUTH_TOKEN

    The dashboard's lib/db.ts:getDbBackend() reads EMPIRE_DATA_BACKEND at
    request time, dispatches reads accordingly via lib/turso-queries.ts.
    """
    if profile == "sunbiz":
        step_header(step_num, total, "Solara's local brain",
                    "Where should Solara keep client records day to day?")
    else:
        step_header(step_num, total, "Data sovereignty",
                    "Where should this tenant's client data live?")

    # Default to Local for PII-heavy client agents; Cloud for empire profiles
    pii_heavy = profile in ("sunbiz", "suga_sean")
    default = "1" if pii_heavy else "2"

    if profile == "sunbiz":
        print(f"  {BOLD('Where should Solara keep the live records?')}")
        print(f"    {CYAN('1)')} Local Brain (Recommended) — private records on this machine.")
        print(f"    {CYAN('2)')} Cloud Records — managed workspace in the cloud.")
    else:
        print(f"  {BOLD('Where should client data live?')}")
        print(f"    {CYAN('1)')} Local Machine (Recommended) — libSQL file on this device. "
              f"PII never leaves the Mac/PC.")
        print(f"    {CYAN('2)')} Cloud — OASIS-hosted Supabase, multi-tenant, RLS-isolated.")
    if pii_heavy:
        print(f"  {DIM('PII-heavy profile — Local is the default. Press Enter to accept.')}")
    print()
    try:
        choice = input(f"  Choose [1/2] (default {default}): ").strip() or default
    except (EOFError, KeyboardInterrupt):
        choice = default

    if choice == "1":
        backend = "turso_local"
        # Resolve a local libSQL file path. Honor env override for ops; default
        # to ~/.bravo/<profile>.db so each profile gets its own physical file.
        db_path_env = os.environ.get("TURSO_DB_PATH") or read_env("TURSO_DB_PATH")
        if db_path_env:
            db_path = db_path_env
        else:
            bravo_dir = Path.home() / ".bravo"
            bravo_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(bravo_dir / f"{profile}.db")
        write_env("EMPIRE_DATA_BACKEND", backend)
        write_env("TURSO_DB_PATH", db_path)
        # No TURSO_AUTH_TOKEN for file: mode — libSQL doesn't authenticate
        # local file URLs. When/if we add hosted-Turso support, that step
        # collects the token at the same time as the URL.
        if profile == "sunbiz":
            print(f"  {GREEN(OK)} Solara's Local Brain is ready on this machine.")
        else:
            print(f"  {GREEN(OK)} Backend: {CYAN('Local libSQL')}")
            print(f"  {GREEN(OK)} DB path: {CYAN(db_path)}")
            print(f"  {DIM('Bootstrap the schema before first read:')} "
                  f"{CYAN('bravo db init --backend=turso')}")
    else:
        backend = "supabase_cloud"
        write_env("EMPIRE_DATA_BACKEND", backend)
        if profile == "sunbiz":
            print(f"  {GREEN(OK)} Solara will use cloud records for this workspace.")
        else:
            print(f"  {GREEN(OK)} Backend: {CYAN('OASIS Supabase Cloud')}")
            print(f"  {DIM('Reads route to BRAVO_SUPABASE_URL — your existing tenant.')}")
    print()


def step_v6_init(profile: str, step_num: int, total: int) -> None:
    """Bootstrap V6.0: write hook defaults, init state DB, build retrieval index, fan out env."""
    if profile == "sunbiz":
        step_header(step_num, total, "Setting up Solara's local brain",
                    "Preparing records, memory, and safety checks behind the scenes.")
    else:
        step_header(step_num, total, "V6.0 sandbox initialization",
                    "Boot the SQLite state DB, FTS5 index, and hook guards.")

    target = (read_env("EMPIRE_DEPLOY_TARGET") or "local").lower()

    # Hook mode defaults — safe-by-default for soak, enforce in cloud.
    if target == "cloud":
        v6_mode = "on"
        secret_mode = "enforce"
        exec_mode = "enforce"
        state_mode = "enforce"
    else:
        v6_mode = "shadow"
        secret_mode = "enforce"   # secrets always enforced — lowest false-positive risk
        exec_mode = "report"      # soak the regex 14 days before flipping
        state_mode = "off"        # off until cutover

    write_env("EMPIRE_V6_MODE", v6_mode)
    write_env("EMPIRE_HOOK_SECRET_GUARD", secret_mode)
    write_env("EMPIRE_HOOK_EXEC_GUARD", exec_mode)
    write_env("EMPIRE_HOOK_STATE_GUARD", state_mode)
    if profile == "sunbiz":
        print(f"  {GREEN(OK)} Solara's safety checks are active.")
    else:
        print(f"  {GREEN(OK)} V6.0 mode: {CYAN(v6_mode)}")
        print(f"  {GREEN(OK)} Hooks: secret={CYAN(secret_mode)} exec={CYAN(exec_mode)} state={CYAN(state_mode)}")

    # Bootstrap the DBs.
    sm_script = REPO_ROOT / "scripts" / "state_manager.py"
    if sm_script.exists():
        if profile != "sunbiz":
            print(f"  {DIM('Initializing')} {CYAN('state/empire_state.db')}{DIM('...')}")
        rc = subprocess.call([sys.executable, str(sm_script), "heartbeat",
                              "--agent", profile if profile in {"bravo","atlas","maven","hermes","aura","codex"} else "bravo",
                              "--status", "setup",
                              "--focus", "V6.0 wizard bootstrap"],
                             cwd=str(REPO_ROOT),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc == 0:
            if profile == "sunbiz":
                print(f"  {GREEN(OK)} Solara's operating memory is ready.")
            else:
                print(f"  {GREEN(OK)} State DB initialized.")
        else:
            print(f"  {YELLOW('state_manager.py heartbeat exited ' + str(rc) + ' — re-run after fixing.')}")

        # Idempotent — UNIQUE(session_id, note) handles dedup.
        subprocess.call([sys.executable, str(sm_script), "import-from-files"],
                        cwd=str(REPO_ROOT),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.call([sys.executable, str(sm_script), "export"],
                        cwd=str(REPO_ROOT),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    mr_script = REPO_ROOT / "scripts" / "memory_retriever.py"
    if mr_script.exists():
        if profile != "sunbiz":
            print(f"  {DIM('Building FTS5 retrieval index (')}{CYAN('state/memory_index.db')}{DIM(')...')}")
        rc = subprocess.call([sys.executable, str(mr_script), "build"],
                             cwd=str(REPO_ROOT),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc == 0:
            if profile == "sunbiz":
                print(f"  {GREEN(OK)} Solara's memory index is ready.")
            else:
                print(f"  {GREEN(OK)} Memory retriever ready.")
        else:
            print(f"  {YELLOW('memory_retriever.py build exited ' + str(rc) + '.')}")

    # Scoped env file fan-out — defense in depth.
    counts = _fan_out_scoped_env_files()
    if counts:
        if profile == "sunbiz":
            print(f"  {GREEN(OK)} Solara's background setup is finished.")
        else:
            per = ", ".join(f"{svc}={n}" for svc, n in counts.items())
            print(f"  {GREEN(OK)} Scoped env files written: {CYAN(per)} keys")

    # Optional Docker build prompt.
    docker_ok, docker_msg = _docker_available()
    if profile == "sunbiz":
        print()
        return

    if docker_ok:
        compose_file = "docker-compose.cloud.yml" if target == "cloud" else "docker-compose.local.yml"
        print()
        print(f"  {DIM('Detected:')} {GREEN(docker_msg)}")
        if yes_no(f"Build the V6.0 sandbox image now? (uses {compose_file})", default=False):
            print(f"  {DIM('Running')} {CYAN(f'docker compose -f infra/{compose_file} build')}{DIM(' (3-5 minutes on first run)...')}")
            rc = subprocess.call(
                ["docker", "compose", "-f", f"infra/{compose_file}", "build"],
                cwd=str(REPO_ROOT),
            )
            if rc == 0:
                print(f"  {GREEN(OK)} Sandbox image built. Start with: {CYAN(f'docker compose -f infra/{compose_file} up -d')}")
            else:
                print(f"  {YELLOW('docker compose build exited ' + str(rc) + ' — re-run manually.')}")
    else:
        print(f"  {DIM('Docker not available right now (')}{docker_msg}{DIM('). Install Docker Desktop later, then run:')}")
        print(f"    {CYAN('docker compose -f infra/docker-compose.local.yml up -d --build')}")
    print()


def _try_pair_code_flow(dashboard_url: str) -> bool:
    """Pair-code path: the operator generated a 9-char code from
    /settings → Devices → Generate code, and pastes it here. We POST to
    /api/auth/pair-code/redeem; the response shape matches the legacy
    /api/auth/pair endpoint so the rest of the bridge bootstrap works
    unchanged.

    Returns True if pairing succeeded (or the operator explicitly chose
    this path and got an error worth surfacing). Returns False if the
    operator declined — falls through to the legacy CLI_SIGNUP_SECRET
    path.
    """
    import platform as _platform
    import socket as _socket
    import json as _json
    import re as _re
    import urllib.request as _ureq
    import urllib.error as _uerr

    # Env-var path: when the install one-liner sets BRAVO_PAIR_CODE
    # (the dashboard's Install button does this — see DevicesEditor +
    # InstallBridgeModal in apps/command-center/), skip the manual paste
    # prompt entirely. The operator already clicked the button, so we
    # can go straight to redeem. Falls back to interactive prompt on
    # any failure (so existing CLI flow still works).
    env_code = (os.environ.get("BRAVO_PAIR_CODE") or "").strip().upper()
    if env_code and _re.fullmatch(r"[A-Z0-9]{3}-[A-Z0-9]{3}-[A-Z0-9]{3}", env_code):
        print(f"  {DIM('Using pair code from BRAVO_PAIR_CODE env: ' + env_code)}")
        code_raw = env_code
    else:
        if env_code:
            print(f"  {YELLOW('BRAVO_PAIR_CODE was set but invalid shape — ignoring.')}")
        # Premium UX: auto-open the operator's default browser to the Devices
        # page so they're one click from "Install Claude Code CLI bridge" →
        # 9-char code → paste back here. The dashboard's middleware bounces
        # unauthed visits to /login?next=/settings, so the sign-in step
        # happens inline in the browser.
        devices_url = f"{dashboard_url}/settings/devices"
        if os.environ.get("BRAVO_NO_BROWSER") != "1":
            try:
                import webbrowser as _wb
                _wb.open(devices_url, new=2)
                print(f"  {GREEN(OK)} Opened {CYAN(devices_url)} in your browser.")
            except Exception as exc:
                print(f"  {DIM('Could not auto-open browser:')} {exc}")
                print(f"  {DIM('Open manually:')} {CYAN(devices_url)}")
        else:
            print(f"  {DIM('Open manually:')} {CYAN(devices_url)}")
        print(f"  {BOLD('Pair code')}: 9-character code from your dashboard")
        print(f"  {DIM('Click \"Install Claude Code CLI bridge\" in Devices, then paste here.')}")
        print(f"  {DIM('Leave blank to skip and use the legacy bearer path.')}")
        code_raw = prompt("  Pair code", required=False).strip().upper()
        if not code_raw:
            return False  # operator skipped — fall through to legacy path

        if not _re.fullmatch(r"[A-Z0-9]{3}-[A-Z0-9]{3}-[A-Z0-9]{3}", code_raw):
            print(f"  {YELLOW('That code shape is invalid (expected XXX-XXX-XXX).')}")
            print(f"  {DIM('Falling back to legacy pairing.')}")
            return False

    body = {
        "code": code_raw,
        "machine": {
            "label": f"{_platform.system()} · {_socket.gethostname()}",
            "fingerprint": f"{_platform.system()}|{_platform.machine()}|{_socket.gethostname()}",
        },
    }
    req = _ureq.Request(
        f"{dashboard_url}/api/auth/pair-code/redeem",
        method="POST",
        data=_json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json"},
    )
    try:
        with _ureq.urlopen(req, timeout=15) as r:
            payload = _json.loads(r.read().decode("utf-8"))
    except _uerr.HTTPError as e:
        # 410 = consumed, 404 = expired/unknown — both "use a fresh code"
        msg = ""
        try:
            msg = e.read().decode("utf-8")[:200]
        except Exception:
            pass
        if e.code in (404, 410):
            print(f"  {YELLOW('Code rejected: ' + str(e.code) + ' — generate a fresh one.')}")
        else:
            print(f"  {YELLOW('Pair-code redeem returned ' + str(e.code))}")
            if msg:
                print(f"  {DIM(msg)}")
        return True  # operator tried this path; don't silently fall through
    except Exception as e:
        print(f"  {YELLOW('Could not reach dashboard — skipping.')}  {DIM(str(e))}")
        return True

    if not payload.get("ok"):
        print(f"  {YELLOW('Dashboard rejected pair: ' + str(payload.get('error', 'unknown')))}")
        return True

    bridge_token = (payload.get("bridge") or {}).get("token", "")
    if bridge_token:
        oasis_dir = Path.home() / ".oasis"
        oasis_dir.mkdir(parents=True, exist_ok=True)
        token_path = oasis_dir / "bridge_token"
        token_path.write_text(bridge_token, encoding="utf-8")
        if os.name != "nt":
            try:
                os.chmod(token_path, 0o600)
            except Exception:
                pass
        print(f"  {GREEN(OK)} Bridge token saved to {CYAN(str(token_path))}")
    redirect = (payload.get("bridge") or {}).get("dashboard_url", dashboard_url + "/")
    print(f"  {GREEN(OK)} Paired with code — dashboard handoff complete.")
    print()
    print(f"  {BOLD('Open your dashboard:')}  {link(redirect, redirect)}")
    print(f"  {BOLD('Then start the bridge:')} {CYAN('bravo bridge start')}")
    print()
    return True


def step_dashboard_pair(profile: str, step_num: int, total: int) -> None:
    """
    Hand off the wizard's answers to the OASIS dashboard:
      1. Read personalization fields from the env we just wrote
      2. POST to /api/auth/pair (Bearer secret) with profile data + machine info
      3. Persist the returned bridge token to ~/.oasis/bridge_token
      4. Print the dashboard URL — operator's data is already seeded when they click

    Skipped automatically when BRAVO_DASHBOARD_URL or CLI_SIGNUP_SECRET
    aren't set (offline / dev installs).
    """
    import platform as _platform
    import socket as _socket
    import json as _json
    import urllib.request as _ureq
    import urllib.error as _uerr

    if profile == "sunbiz":
        step_header(step_num, total, "Command Center handoff",
                    "Pair Solara with the client's Command Center.")
    else:
        step_header(step_num, total, "Dashboard pairing",
                    "Hand your setup off to the cloud Command Center.")

    dashboard_url = (
        os.environ.get("BRAVO_DASHBOARD_URL")
        or read_env("BRAVO_DASHBOARD_URL")
        or "https://agent-dashboard-cc90210.vercel.app"
    ).rstrip("/")
    secret = os.environ.get("CLI_SIGNUP_SECRET") or read_env("CLI_SIGNUP_SECRET")

    email = read_env("USER_EMAIL") or read_env("USER_PRIMARY_EMAIL") or ""
    # New path (preferred for client onboarding): the operator has a one-time
    # pair code from /settings → Devices → Generate code on their dashboard.
    # No CLI_SIGNUP_SECRET needed; the code itself authenticates the redeem.
    if _try_pair_code_flow(dashboard_url):
        return

    if not email:
        print(f"  {YELLOW('No email on file — skipping dashboard pairing.')}")
        print(f"  {DIM('Re-run the wizard or pair manually from /onboarding.')}")
        return
    if not secret:
        print(f"  {YELLOW('CLI_SIGNUP_SECRET not configured — pairing skipped.')}")
        print(f"  {DIM('Set it in .env.agents to enable cloud handoff,')}")
        print(f"  {DIM('or paste a pair code from /settings → Devices.')}")
        return

    # Compose the personalization payload from the wizard's saved env
    def _opt_int(k: str) -> int | None:
        v = read_env(k)
        try:
            return int(float(v)) if v else None
        except Exception:
            return None

    profile_payload: dict = {}
    pn = read_env("USER_FULL_NAME") or ""
    if pn:
        profile_payload["full_name"] = pn
    dn = read_env("USER_PREFERRED_NAME") or ""
    if dn:
        profile_payload["display_name"] = dn
    # Brand fallback chain — none of the legacy keys (BRAND / USER_BRAND) are
    # actually written by the wizard's steps. The values that DO exist after a
    # real run are USER_BUSINESS_NAME (every profile, via step_user_identity)
    # and BRAVO_PRIMARY_BRAND (bravo profile, via step_agent_questions). Read
    # all of them; first non-empty wins. Without this, /api/auth/pair never
    # receives a brand → applyClientProvisioningProfile can't route SunBiz /
    # Suga tenants to their dashboard profile slugs.
    brand = (
        read_env("BRAND")
        or read_env("USER_BRAND")
        or read_env("USER_BUSINESS_NAME")
        or read_env("BRAVO_PRIMARY_BRAND")
        or ""
    )
    if brand:
        profile_payload["brand"] = brand
    profile_payload["primary_agent"] = profile  # bravo / atlas / maven / aura / hermes
    mrr_target = _opt_int("MRR_TARGET_USD")
    if mrr_target is not None:
        profile_payload["mrr_target_usd"] = mrr_target
    mrr_current = _opt_int("MRR_CURRENT_USD")
    if mrr_current is not None:
        profile_payload["mrr_current_usd"] = mrr_current
    target_date = read_env("MRR_TARGET_DATE") or ""
    if target_date:
        profile_payload["mrr_target_date"] = target_date
    manifesto = read_env("USER_MANIFESTO") or ""
    if manifesto:
        profile_payload["manifesto"] = manifesto

    body = {
        "email": email,
        "profile": profile_payload,
        "machine": {
            "label": f"{_platform.system()} · {_socket.gethostname()}",
            "fingerprint": f"{_platform.system()}|{_platform.machine()}|{_socket.gethostname()}",
        },
    }
    req = _ureq.Request(
        f"{dashboard_url}/api/auth/pair",
        method="POST",
        data=_json.dumps(body).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {secret}",
        },
    )
    try:
        with _ureq.urlopen(req, timeout=15) as r:
            payload = _json.loads(r.read().decode("utf-8"))
    except _uerr.HTTPError as e:
        print(f"  {YELLOW('Dashboard pair returned ' + str(e.code) + ' — skipping.')}")
        try:
            print(f"  {DIM(e.read().decode('utf-8')[:200])}")
        except Exception:
            pass
        return
    except Exception as e:
        print(f"  {YELLOW('Could not reach dashboard — skipping.')}  {DIM(str(e))}")
        return

    if not payload.get("ok"):
        print(f"  {YELLOW('Dashboard rejected pair: ' + str(payload.get('error', 'unknown')))}")
        return

    # Persist the bridge token (chmod 600 on POSIX)
    bridge_token = (payload.get("bridge") or {}).get("token", "")
    if bridge_token:
        oasis_dir = Path.home() / ".oasis"
        oasis_dir.mkdir(parents=True, exist_ok=True)
        token_path = oasis_dir / "bridge_token"
        token_path.write_text(bridge_token, encoding="utf-8")
        if os.name != "nt":
            try:
                os.chmod(token_path, 0o600)
            except Exception:
                pass
        print(f"  {GREEN(OK)} Bridge token saved to {CYAN(str(token_path))}")
    redirect = (payload.get("bridge") or {}).get("dashboard_url", dashboard_url + "/")
    print(f"  {GREEN(OK)} Dashboard pairing recorded.")
    print()
    print(f"  {BOLD('Open your dashboard:')}  {link(redirect, redirect)}")
    print(f"  {BOLD('Then start the bridge:')} {CYAN('bravo bridge start')}")
    print()


def step_sunbiz_experience_handoff(step_num: int, total: int) -> None:
    step_header(step_num, total, "Launch Solara",
                "One last lead-intake and texting check before the client lands in the Command Center.")

    dashboard_url = _dashboard_url()
    webhook_url = f"{dashboard_url}/api/inbound/lead"

    print(f"  {BOLD('JotForm setup')}")
    print(f"    {DIM('1. Open the client JotForm and go to Settings -> Integrations -> Webhooks.')}")
    print(f"    {DIM('2. Paste this webhook URL:')} {CYAN(webhook_url)}")
    print(f"    {DIM('3. Save the form, then come back here so we can pulse-check it.')}")
    jotform_ready = yes_no("Mark JotForm as connected now?", default=True)
    if jotform_ready:
        write_env("JOTFORM_WEBHOOK_URL", webhook_url)

    text_torrent_ready = bool(read_env("TWILIO_ACCOUNT_SID") and read_env("TWILIO_AUTH_TOKEN"))

    services: dict[str, dict] = {
        "jotform": {
            "status": "healthy" if jotform_ready else "unconfigured",
            "metadata": {"via": "wizard", "agent": "solara", "webhook_url": webhook_url},
        },
        "text_torrent": {
            "status": "healthy" if text_torrent_ready else "unconfigured",
            "metadata": {"via": "wizard", "agent": "solara"},
        },
    }
    _post_bridge_services(dashboard_url, services)

    print()
    print(f"  {BOLD('Pulse Check')}")
    if jotform_ready:
        print(f"    {GREEN(OK)} Solara is connected to JotForm. She is ready to receive leads.")
    else:
        print(f"    {YELLOW(WARN)} JotForm is still waiting on its webhook.")
    if text_torrent_ready:
        print(f"    {GREEN(OK)} Solara is connected to Text Torrent. She is ready to send follow-ups.")
    else:
        print(f"    {YELLOW(WARN)} Text Torrent still needs its Account SID + Auth Token.")
    print()


def step_finalize(profile: str, step_num: int, total: int) -> None:
    step_header(step_num, total, "Finalize",
                "Summary of saved credentials and next steps.")
    write_env("BRAVO_ACTIVE_PROFILE", profile)
    config_path = _set_active_profile(profile)
    setup_profile_path = _write_setup_profile(profile)
    p = PROFILES[profile]

    # Big summary panel
    print()
    print(f"  {GREEN(OK)} Profile:  {p['color'](BOLD(p['name']))}  {DIM('· ' + p['role'])}")
    print(f"  {GREEN(OK)} Env file: {CYAN(str(ENV_PATH))}")
    print(f"  {GREEN(OK)} Setup profile: {CYAN(str(setup_profile_path))}")
    print(f"  {GREEN(OK)} Active config: {CYAN(str(config_path))}")
    print(f"  {GREEN(OK)} Home dir: {CYAN(str(BRAVO_HOME))}  {DIM('(profiles, sessions, logs)')}")
    print()

    # List every key saved in THIS wizard session so the user sees exactly
    # what was wired up — CC's "when they answer all the questions, it should
    # work" criterion.
    unique_saved = []
    for k in _SAVED_THIS_SESSION:
        if k not in unique_saved:
            unique_saved.append(k)
    if unique_saved:
        hr("─", 64)
        print(f"  {BOLD('Saved this session:')}  {DIM(f'{len(unique_saved)} key(s)')}")
        for k in unique_saved:
            print(f"    {GREEN(OK)} {k}")
        hr("─", 64)
        print()

    if profile == "sunbiz":
        dashboard_url = _dashboard_url()
        print(f"  {BOLD('What happens next:')}")
        print(f"    {GREEN(OK)} Solara's setup is complete.")
        print(f"    {GREEN(OK)} The Command Center is ready at {CYAN(dashboard_url + '/')}")
        print(f"    {GREEN(OK)} The Playbook tab walks the client through their first week with Solara.")
    else:
        print(f"  {BOLD('Next commands:')}")
        print(f"    {CYAN('bravo doctor')}          {DIM('— full health check')}")
        print(f"    {CYAN('bravo status')}          {DIM('— live operational summary')}")
        print(f"    {CYAN('bravo agent list')}      {DIM('— see sub-agents')}")
        print(f"    {CYAN('bravo sessions recent')} {DIM('— rewind past sessions')}")
        if read_env("TELEGRAM_BOT_TOKEN"):
            print(f"    {CYAN('bravo run telegram_agent')}  {DIM('— start the Telegram bridge')}")
    if profile == "hermes":
        hermes_root = Path(AGENT_REPOS["hermes"]["dir"]).expanduser()
        print()
        print(f"  {BOLD('Hermes local bootstrap:')}")
        if os.name == "nt":
            print(f"    {CYAN('cd ' + str(hermes_root))}")
            print(f"    {CYAN('powershell -ExecutionPolicy Bypass -File install.ps1')}")
        else:
            print(f"    {CYAN('cd ' + str(hermes_root))}")
            print(f"    {CYAN('bash install.sh')}")
    if profile == "custom":
        print()
        print(f"  {YELLOW('Custom profile selected.')}  Forge the new agent with:")
        print(f"    {CYAN('bravo agent create <name> --role \"<role>\"')}")
    print()
    hr("═", 64)
    print(f"  {BOLD(GREEN('Setup complete.'))}  "
          f"{DIM('Made by OASIS AI ·')} {link(OASIS_URL, 'oasisai.work')}")
    hr("═", 64)
    print()
    # Run scripts/personalize.py to materialize brain/USER.md +
    # memory/ACTIVE_TASKS.md + memory/SESSION_LOG.md from the wizard's
    # answers. This is what makes a fresh clone become *this operator's*
    # agent — without it, the wizard saves credentials but the agent has
    # no idea who it's working for.
    personalize_script = REPO_ROOT / "scripts" / "personalize.py"
    scaffold_script = REPO_ROOT / "scripts" / "scaffold.py"
    if personalize_script.exists() and profile == "bravo":
        print(f"  {BOLD('Personalizing identity files...')}")
        rc = subprocess.call([sys.executable, str(personalize_script), "apply", "--force"],
                             cwd=str(REPO_ROOT))
        if rc == 0:
            print(f"  {GREEN(OK)} brain/USER.md + memory/ACTIVE_TASKS.md + memory/SESSION_LOG.md rendered.")
        else:
            print(f"  {YELLOW('personalize.py apply returned ' + str(rc) + ' — re-run manually after fixing.')}")

        # Detect: is this a fresh fork (someone other than CC) or CC's
        # original repo? Only run scaffold (token-replace CC identifiers
        # across the whole codebase) on a fork.
        if scaffold_script.exists():
            new_operator = (read_env("USER_PREFERRED_NAME") or "").strip().upper() != "CC" \
                           and (read_env("USER_FULL_NAME") or "").strip().lower() != "conaugh mckenna"
            if new_operator:
                print()
                print(f"  {BOLD('Detected new operator')} — will replace CC's identifiers across "
                      f"the codebase with yours.")
                run_scaffold = yes_no("Run scaffold now? (recommended for fresh clones)", default=True)
                if run_scaffold:
                    rc = subprocess.call([sys.executable, str(scaffold_script),
                                          "--apply", "--backup"], cwd=str(REPO_ROOT))
                    if rc == 0:
                        print(f"  {GREEN(OK)} Codebase scaffolded for {read_env('USER_PREFERRED_NAME') or 'you'}.")
                    else:
                        print(f"  {YELLOW('scaffold.py exited ' + str(rc) + ' — re-run manually if needed.')}")
                else:
                    print(f"  {DIM('Skipped. Run later: python scripts/scaffold.py --apply --backup')}")
        print()

    # Bridge: auto-register at-login + spawn now. Removes the trailing
    # "two more commands left" tax — by the time the wizard exits, the
    # bridge is already running and the dashboard URL is hot. Idempotent:
    # cmd_install overwrites prior registration; the spawn no-ops if
    # something already holds :9100. Skipped for non-bravo profiles
    # (only Bravo's dashboard expects a localhost bridge today).
    if profile == "bravo" and os.environ.get("BRAVO_SKIP_BRIDGE_AUTOSTART") != "1":
        try:
            from . import local_bridge as _lb  # type: ignore
            print(f"  {BOLD('Bringing up the local bridge...')}")
            rc = _lb.cmd_install(None)
            if rc == 0:
                print(f"  {GREEN(OK)} Bridge auto-start registered for next login.")
            else:
                print(f"  {YELLOW('Bridge auto-start install returned ' + str(rc) + ' — re-run')} {CYAN('bravo bridge install')} {YELLOW('manually.')}")
            # Spawn the chat HTTP server in background so the dashboard URL
            # is usable RIGHT NOW. We don't reuse cmd_start (that one runs
            # the heartbeat _loop, a different process). Detached so the
            # wizard exits cleanly; logs go to ~/.oasis/bridge.log.
            log_path = Path.home() / ".oasis" / "bridge.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            py_runner = _lb._resolve_pythonw() if hasattr(_lb, "_resolve_pythonw") else sys.executable
            creation_flags = 0
            if os.name == "nt":
                creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            log_fh = log_path.open("a", encoding="utf-8")
            subprocess.Popen(
                [py_runner, "-m", "bravo_cli.bridge_chat_server"],
                stdout=log_fh, stderr=log_fh, stdin=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=(os.name != "nt"),
                creationflags=creation_flags,
                cwd=str(REPO_ROOT),
            )
            print(f"  {GREEN(OK)} Chat HTTP server spawned on {CYAN('http://localhost:9100')}.")
            dashboard_url = read_env("OASIS_DASHBOARD_URL") or "https://agent-dashboard-cc90210.vercel.app"
            print()
            print(f"  {BOLD('Open this now →')}  {link(dashboard_url + '/agents', dashboard_url + '/agents')}")
            print(f"  {DIM('Header turns cyan ('+'\"local bridge · full repo access\"'+') once the spawn finishes booting (~2s).')}")
            print()
        except Exception as exc:  # noqa: BLE001
            print(f"  {YELLOW('Bridge auto-start failed: ' + str(exc) + ' — run')} {CYAN('bravo bridge install && bravo bridge start')} {YELLOW('manually.')}")

    # Auto-run bravo doctor — no prompt. OpenClaw parity: onboarding that
    # asks "want me to verify this worked?" is weaker than onboarding that
    # just verifies it. Users who need to skip (CI, container builds) can
    # set BRAVO_SKIP_POST_DOCTOR=1 before running the wizard.
    # We capture the exit code (Codex P2, 2026-04-25): previously the
    # wizard printed "Setup complete." even when doctor failed, which let
    # broken installs pass silently. The exit code now propagates back
    # through run_wizard → cmd_setup → main, so the one-liner returns
    # non-zero if doctor isn't happy.
    if os.environ.get("BRAVO_SKIP_POST_DOCTOR") == "1":
        print(f"  {DIM('BRAVO_SKIP_POST_DOCTOR=1 — skipping post-install doctor.')}")
        _post_doctor_rc[0] = 0
    else:
        bravo_cmd = REPO_ROOT / "bravo_cli" / "main.py"
        if profile == "sunbiz":
            print(f"  {BOLD('Running a final health check for Solara...')}")
            rc = subprocess.call(
                [sys.executable, str(bravo_cmd), "doctor"],
                cwd=str(REPO_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            print(f"  {BOLD('Running')} {CYAN('bravo doctor')} {BOLD('to verify everything...')}")
            print()
            rc = subprocess.call([sys.executable, str(bravo_cmd), "doctor"],
                                 cwd=str(REPO_ROOT))
        _post_doctor_rc[0] = rc
        if rc != 0:
            print()
            if profile == "sunbiz":
                print(f"  {YELLOW('Solara finished onboarding, but one health check still needs attention.')}")
            else:
                print(f"  {YELLOW('Setup finished, but `bravo doctor` reported exit ' + str(rc) + '.')}")
                print(f"  {DIM('Run')} {CYAN('bravo doctor')} {DIM('again for full output, or set BRAVO_SKIP_POST_DOCTOR=1 to bypass on next run.')}")

# ── Self-update preflight ─────────────────────────────────────────────────────

def _self_update_preflight() -> bool:
    """Fast-forward REPO_ROOT to origin/<branch> before running the wizard.

    CC's intent: "the wizard should auto-update when we make
    improvements". The one-line installer pulls on re-run, but an
    operator who only runs `bravo setup` from an old shell wouldn't
    see new commits. This preflight fires on every wizard launch.

    Returns True if the wizard should restart (new commits applied),
    False to continue normally. Skipped when:
      - BRAVO_SKIP_AUTO_UPDATE=1 in env
      - REPO_ROOT is not a git working tree
      - No `git` on PATH
      - Network fetch fails (offline-tolerant)
      - Working tree is dirty AND user declines stash
    """
    if os.environ.get("BRAVO_SKIP_AUTO_UPDATE") == "1":
        return False
    if not (REPO_ROOT / ".git").exists():
        return False
    if not shutil.which("git"):
        return False

    def _git(*args: str, capture: bool = True) -> tuple[int, str]:
        try:
            r = subprocess.run(
                ["git", "-C", str(REPO_ROOT), *args],
                capture_output=capture, text=True, timeout=30,
                encoding="utf-8", errors="replace",
            )
            return r.returncode, (r.stdout or "") + (r.stderr or "")
        except Exception as exc:  # noqa: BLE001
            return 1, str(exc)

    # Skip if origin doesn't look like a CC90210 agent repo — keeps us
    # from auto-pulling on a fork or unrelated git working tree.
    rc, remote = _git("config", "--get", "remote.origin.url")
    if rc != 0 or "CC90210/" not in remote:
        return False

    rc, branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    branch = (branch.strip() or "main") if rc == 0 else "main"
    if branch == "HEAD":  # detached
        return False

    rc, _ = _git("fetch", "--depth", "50", "origin", branch)
    if rc != 0:
        return False  # offline — proceed silently

    rc, behind = _git("rev-list", "--count", f"HEAD..origin/{branch}")
    try:
        n_behind = int(behind.strip())
    except ValueError:
        return False
    if n_behind == 0:
        return False  # already up to date

    print()
    print(f"  {CYAN('Updates available:')} {n_behind} new commit(s) on origin/{branch}")
    rc, log = _git("log", "--oneline", f"HEAD..origin/{branch}")
    for line in (log or "").splitlines()[:5]:
        print(f"    {DIM(line)}")

    # Stash dirty changes so reset --hard doesn't lose work.
    rc, dirty = _git("status", "--porcelain")
    if dirty.strip():
        print(f"  {YELLOW('Local changes detected — stashing before update.')}")
        _git("stash", "push", "-u", "-m",
             f"auto-stash by wizard {int(time.time())}")

    rc, _ = _git("reset", "--hard", f"origin/{branch}")
    if rc != 0:
        print(f"  {YELLOW('Auto-update failed (reset --hard).')} Continuing with current code.")
        return False

    print(f"  {GREEN(OK)} Pulled {n_behind} commit(s). Restarting wizard with new code...")
    print()
    return True


# ── Entry point ───────────────────────────────────────────────────────────────

def run_wizard(profile_override: str | None = None) -> int:
    # Auto-pull updates before the wizard touches anything else.
    # Restart in a fresh subprocess so the new wizard.py runs, not the
    # old one already loaded into this Python process.
    if _self_update_preflight():
        env = os.environ.copy()
        env["BRAVO_SKIP_AUTO_UPDATE"] = "1"  # prevent infinite loop
        argv = [sys.executable, str(REPO_ROOT / "bravo_cli" / "main.py"), "setup"]
        if profile_override:
            argv += ["--profile", profile_override]
        return subprocess.call(argv, env=env, cwd=str(REPO_ROOT))

    try:
        step_welcome()
        if profile_override and profile_override in PROFILES:
            profile = profile_override
            p = PROFILES[profile]
            _confirm_profile(profile)
        else:
            profile = step_profile()
        p = PROFILES[profile]

        # Numbered steps start AFTER the profile pick (picker is unnumbered).
        # Compute the total from what actually applies to the chosen profile.
        total = 1  # finalize always runs
        total += 1                                         # V6.0 environment detection
        if AGENT_REPOS.get(profile):                       total += 1  # clone
        total += 1                                         # user identity
        if profile in BUSINESS_CONTEXT_PROFILES:           total += 1  # business ctx
        if PROFILE_QUESTIONS.get(profile):                 total += 1  # agent qs
        total += 1                                         # ai
        if p["chat"]:                                      total += 1
        if p["business"]:                                  total += 1
        if p["extra"]:                                     total += 1
        total += 2                                         # playwright + harness
        total += 1                                         # data sovereignty
        total += 1                                         # dashboard pairing
        if profile == "sunbiz":                            total += 1  # Solara launch checks
        total += 1                                         # V6.0 sandbox init

        step = 0

        # V6.0: detect deploy target FIRST so downstream steps can adapt.
        step += 1; step_environment(step, total)

        if AGENT_REPOS.get(profile):
            step += 1; step_clone_agent_repo(profile, step, total)
        step += 1; step_user_identity(profile, step, total)
        if profile in BUSINESS_CONTEXT_PROFILES:
            step += 1; step_business_context(profile, step, total)
        if PROFILE_QUESTIONS.get(profile):
            step += 1; step_agent_questions(profile, step, total)
        step += 1; step_ai(profile, step, total)
        if p["chat"]:
            step += 1; step_chat(profile, step, total)
        if p["business"]:
            step += 1; step_business(profile, step, total)
        if p["extra"]:
            step += 1; step_extra(profile, step, total)
        # Binary deps — both idempotent (skip if already installed).
        step += 1; step_playwright_browsers(step, total)
        step += 1; step_browser_harness(step, total)
        # Data sovereignty — operator picks Local libSQL or Cloud Supabase.
        # Runs BEFORE dashboard pairing so the dashboard handoff knows which
        # backend the bridge will write to.
        step += 1; step_data_sovereignty(profile, step, total)
        # Cloud handoff — wizard answers → dashboard, mint local-bridge token
        step += 1; step_dashboard_pair(profile, step, total)
        if profile == "sunbiz":
            step += 1; step_sunbiz_experience_handoff(step, total)
        # V6.0 sandbox: write hook defaults, boot state DB, build FTS5 index,
        # fan out scoped env files, optional docker build. Runs RIGHT BEFORE
        # finalize so the post-install `bravo doctor` sees a healthy V6.0 stack.
        step += 1; step_v6_init(profile, step, total)
        step += 1; step_finalize(profile, step, total)
        # Propagate the post-install bravo-doctor exit code so a broken
        # install can't show "Setup complete" + return 0 (Codex P2).
        return _post_doctor_rc[0]
    except KeyboardInterrupt:
        print()
        print(f"  {YELLOW('Wizard aborted.')} Re-run {CYAN('bravo setup')} anytime.")
        return 130


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="bravo-setup-wizard")
    parser.add_argument("--profile", choices=list(PROFILES.keys()),
                        help="Pre-select a profile (skips the picker)")
    args = parser.parse_args()
    return run_wizard(profile_override=args.profile)


if __name__ == "__main__":
    sys.exit(main())
