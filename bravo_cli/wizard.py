"""Bravo interactive setup wizard — Agent Factory onboarding.

Walks a new user through:
  1. Profile picker (Bravo / Atlas / Maven / Aura / Hermes / Custom)
  2. AI provider keys (Anthropic required; OpenAI + Google AI optional)
  3. Chat bridges (Telegram, Discord, Slack, WhatsApp/Twilio)
  4. Domain integrations (per profile: finance / marketing / home / client)
  5. Doctor run + summary

Writes secrets to ~/.bravo/.env (0600 on POSIX). If the repo's .env.agents
is missing or empty, it's bootstrapped with the same contents so existing
scripts in scripts/ (which load from the repo) start working immediately.

Zero external dependencies — stdlib only (urllib, getpass, json, re).
"""

from __future__ import annotations

import getpass
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

# ── Paths ─────────────────────────────────────────────────────────────────────

BRAVO_HOME = Path(os.path.expanduser("~/.bravo"))
ENV_PATH = BRAVO_HOME / ".env"
REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_ENV = REPO_ROOT / ".env.agents"

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
BLUE    = lambda t: _c("34", t)
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

_BANNER_UNICODE = r"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║    ██████╗ ██████╗  █████╗ ██╗   ██╗ ██████╗                 ║
║    ██╔══██╗██╔══██╗██╔══██╗██║   ██║██╔═══██╗                ║
║    ██████╔╝██████╔╝███████║██║   ██║██║   ██║                ║
║    ██╔══██╗██╔══██╗██╔══██║╚██╗ ██╔╝██║   ██║                ║
║    ██████╔╝██║  ██║██║  ██║ ╚████╔╝ ╚██████╔╝                ║
║    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝   ╚═════╝                 ║
║                                                              ║
║    Agent Factory · Business-in-a-Box                         ║
║    Made by OASIS AI · oasisai.work                           ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

_BANNER_ASCII = r"""
+==============================================================+
|                                                              |
|   ######  ######   #####   ##   ##   ######                  |
|   ##   ## ##   ## ##   ##  ##   ##  ##    ##                 |
|   ######  ######  #######  ##   ##  ##    ##                 |
|   ##   ## ##   ## ##   ##  ##   ##  ##    ##                 |
|   ######  ##   ## ##   ##   #####    ######                  |
|                                                              |
|   Agent Factory * Business-in-a-Box                          |
|   Made by OASIS AI * oasisai.work                            |
|                                                              |
+==============================================================+
"""

def banner() -> str:
    return _BANNER_UNICODE if _UNICODE else _BANNER_ASCII

OASIS_URL = "https://oasisai.work"

def print_banner() -> None:
    print(CYAN(banner()))
    print(f"  {DIM('version:')} {BOLD('V1.2')}  "
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
        "extra": ["tax_region"],
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
        "color": BLUE,
        "role": "Client operations agent",
        "tagline": "Commerce · orders · inventory · client portals",
        "required": ["anthropic"],
        "ai": ["anthropic", "openai"],
        "chat": ["telegram", "discord", "slack", "whatsapp"],
        "business": ["stripe", "supabase"],
        "extra": ["client_name"],
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

# ── Integrations ──────────────────────────────────────────────────────────────

# Each integration: {env_key, label, url, format, instructions, validator}
# validator(value) -> (ok: bool, detail: str)

INTEGRATIONS: dict[str, dict] = {
    # AI providers
    "anthropic": {
        "env_key": "ANTHROPIC_API_KEY",
        "label": "Anthropic (Claude)",
        "tagline": "Primary reasoning engine — required",
        "url": "https://console.anthropic.com/settings/keys",
        "format": "sk-ant-api03-...",
        "secret": True,
        "instructions": [
            "Sign in to console.anthropic.com",
            "Settings -> API Keys -> Create Key",
            "Copy the full key (starts with sk-ant-)",
        ],
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
        "env_key": "SUPABASE_URL",
        "label": "Supabase",
        "tagline": "Persistent state + CRM + memory store",
        "url": "https://supabase.com/dashboard/projects",
        "format": "https://<project>.supabase.co",
        "secret": False,
        "instructions": [
            "Go to supabase.com/dashboard/projects",
            "Pick your project -> Settings -> API",
            "Copy the Project URL here; you'll paste the anon key next",
        ],
        "followup_key": "SUPABASE_ANON_KEY",
        "followup_label": "Supabase anon key",
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
        "env_key": "LINKEDIN_ACCESS_TOKEN",
        "label": "LinkedIn",
        "tagline": "Post scheduling, messaging, company page",
        "url": "https://www.linkedin.com/developers/apps",
        "format": "OAuth token",
        "secret": True,
        "instructions": [
            "LinkedIn Developers -> Create App",
            "Auth -> Request an access token with w_member_social",
        ],
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

def ensure_env_file() -> None:
    BRAVO_HOME.mkdir(parents=True, exist_ok=True)
    if not ENV_PATH.exists():
        ENV_PATH.write_text(
            "# Bravo environment — managed by `bravo setup`.\n"
            "# One KEY=value per line. Never commit this file.\n\n",
            encoding="utf-8",
        )
        if os.name != "nt":
            try:
                os.chmod(ENV_PATH, 0o600)
            except Exception:
                pass

def write_env(key: str, value: str) -> None:
    ensure_env_file()
    text = ENV_PATH.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(text):
        new_text = pattern.sub(line, text)
    else:
        new_text = text.rstrip() + f"\n{line}\n"
    ENV_PATH.write_text(new_text, encoding="utf-8")

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

def mirror_to_repo_env() -> bool:
    """Bootstrap <repo>/.env.agents when missing or empty. Never overwrites."""
    if not ENV_PATH.exists():
        return False
    if REPO_ENV.exists():
        try:
            text = REPO_ENV.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return False
        populated = any(
            "=" in ln and ln.split("=", 1)[1].strip() and not ln.strip().startswith("#")
            for ln in text.splitlines()
        )
        if populated:
            return False
    try:
        REPO_ENV.write_text(ENV_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        return True
    except Exception:
        return False

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
    hint = f" [{default}]" if default else (f" {DIM('(required)')}" if required else "")
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
        print(f"  {RED('Required.')}")

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
    status, _ = _http_get("https://api.openai.com/v1/models",
                          {"Authorization": f"Bearer {key}"})
    if status == 200:
        return True, "accepted"
    if status == 401:
        return False, "unauthorized"
    return status == 0, f"HTTP {status}"

def validate_google_ai(key: str) -> tuple[bool, str]:
    status, _ = _http_get(
        f"https://generativelanguage.googleapis.com/v1beta/models?key={key}")
    if status == 200:
        return True, "accepted"
    if status in (401, 403):
        return False, "unauthorized"
    return status == 0, f"HTTP {status}"

def validate_stripe(key: str) -> tuple[bool, str]:
    status, _ = _http_get("https://api.stripe.com/v1/balance",
                          {"Authorization": f"Bearer {key}"})
    if status == 200:
        return True, "accepted"
    if status == 401:
        return False, "unauthorized"
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
    input(f"  {DIM('Press Enter once you have messaged your bot...')} ")
    print(f"  {DIM(ARROW + ' Listening for your message (up to 120s)...')}")
    chat_id = tg_wait_for_chat_id(token, timeout=120)
    if chat_id is None:
        print(f"  {YELLOW('No message detected.')} Re-run {CYAN('bravo setup')} later.")
        return False
    print(f"  {GREEN(OK)} Captured chat_id {BOLD(str(chat_id))}")
    write_env("TELEGRAM_CHAT_ID", str(chat_id))
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

    # Follow-up key (e.g., SUPABASE_ANON_KEY, N8N_API_KEY)
    if spec.get("followup_key"):
        fkey = spec["followup_key"]
        flabel = spec.get("followup_label", fkey)
        fsecret = spec.get("followup_secret", True)
        fval = (secret_prompt(f"Paste {flabel}")
                if fsecret else prompt(flabel))
        if fval:
            write_env(fkey, fval)
            print(f"    {GREEN(OK)} {fkey} saved")
    print()
    return True

# ── Steps ─────────────────────────────────────────────────────────────────────

def step_welcome() -> None:
    print_banner()
    print(f"  {BOLD('Welcome.')} This wizard sets up a working Bravo agent in under 5 minutes.")
    print(f"  {DIM('Keys go to')} {CYAN(str(ENV_PATH))}  {DIM('(0600 on POSIX)')}.")
    print(f"  {DIM('Nothing is uploaded; you stay in full control.')}")
    print()
    try:
        input(f"  {BOLD('Press Enter to begin...')} ")
    except (EOFError, KeyboardInterrupt):
        sys.exit(130)

def step_profile(total_steps: int) -> str:
    step_header(1, total_steps, "Choose an agent profile",
                "Pick the role this install is for — integrations adapt to it.")
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
        raw = prompt(f"Pick an agent (1-{len(slugs)})", default="1")
        try:
            n = int(raw)
            if 1 <= n <= len(slugs):
                chosen = slugs[n - 1]
                print(f"  {PROFILES[chosen]['color'](OK)} "
                      f"Selected: {BOLD(PROFILES[chosen]['name'])}")
                return chosen
        except ValueError:
            pass
        print(f"  {RED('Enter a number 1-' + str(len(slugs)))}")

def step_ai(profile: str, step_num: int, total: int) -> None:
    p = PROFILES[profile]
    step_header(step_num, total, "AI providers",
                "Anthropic is required. Others are optional fallbacks / delegates.")
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
        if slug == "tax_region":
            region = prompt("Tax region (CA/US/UK/EU/OTHER)", default="CA")
            write_env("ATLAS_TAX_REGION", region.upper())
            print(f"  {GREEN(OK)} ATLAS_TAX_REGION={region.upper()}")
            print()
            continue
        if slug == "client_name":
            name = prompt("Client name (for Hermes scaffolding later)", default="")
            if name:
                write_env("HERMES_CLIENT_NAME", name)
                print(f"  {GREEN(OK)} HERMES_CLIENT_NAME={name}")
            print()
            continue
        integration_step(slug, required=False)

def step_finalize(profile: str, step_num: int, total: int) -> None:
    step_header(step_num, total, "Finalize",
                "Writing config, mirroring to repo, verifying.")
    write_env("BRAVO_ACTIVE_PROFILE", profile)
    mirrored = mirror_to_repo_env()
    p = PROFILES[profile]
    print(f"  {GREEN(OK)} Profile:     {p['color'](BOLD(p['name']))}  {DIM('(' + p['role'] + ')')}")
    print(f"  {GREEN(OK)} Home env:    {CYAN(str(ENV_PATH))}")
    if mirrored:
        print(f"  {GREEN(OK)} Repo env:    {CYAN(str(REPO_ENV))}  {DIM('(bootstrapped)')}")
    else:
        print(f"  {DIM('Repo env already populated — not overwritten.')}")
    print()
    print(f"  {BOLD('Next commands:')}")
    print(f"    {CYAN('bravo doctor')}          {DIM('— full health check')}")
    print(f"    {CYAN('bravo status')}          {DIM('— live operational summary')}")
    print(f"    {CYAN('bravo agent list')}      {DIM('— see sub-agents')}")
    print(f"    {CYAN('bravo sessions recent')} {DIM('— rewind past sessions')}")
    if read_env("TELEGRAM_BOT_TOKEN"):
        print(f"    {CYAN('bravo run telegram_agent')}  {DIM('— start the Telegram bridge')}")
    if profile == "custom":
        print()
        print(f"  {YELLOW('Custom profile selected.')}  Forge the new agent with:")
        print(f"    {CYAN('bravo agent create <name> --role \"<role>\"')}")
    print()
    hr("═", 64)
    print(f"  {BOLD(GREEN('Setup complete.'))}  "
          f"{DIM('Made by OASIS AI ·')} {link(OASIS_URL, 'oasisai.work')}")
    hr("═", 64)

# ── Entry point ───────────────────────────────────────────────────────────────

def run_wizard(profile_override: str | None = None) -> int:
    try:
        step_welcome()
        if profile_override and profile_override in PROFILES:
            profile = profile_override
            p = PROFILES[profile]
            print(f"  {p['color'](OK)} Profile pre-selected via --profile: "
                  f"{BOLD(p['name'])}")
        else:
            profile = step_profile(total_steps=5)
        p = PROFILES[profile]
        steps_total = 2  # ai + finalize always
        if p["chat"]:      steps_total += 1
        if p["business"]:  steps_total += 1
        if p["extra"]:     steps_total += 1

        step = 1  # profile already done as step 1 in the header
        step += 1; step_ai(profile, step, steps_total + 1)
        if p["chat"]:
            step += 1; step_chat(profile, step, steps_total + 1)
        if p["business"]:
            step += 1; step_business(profile, step, steps_total + 1)
        if p["extra"]:
            step += 1; step_extra(profile, step, steps_total + 1)
        step += 1; step_finalize(profile, step, steps_total + 1)
        return 0
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
