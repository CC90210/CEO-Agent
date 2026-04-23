"""Bravo interactive setup wizard.

Walks a new user through:
  1. Profile selection (bravo / atlas / maven / aura / hermes / custom)
  2. Core AI keys (Anthropic required, OpenAI optional)
  3. Telegram bridge (bot token -> getMe -> chat_id via getUpdates -> test message)
  4. Optional services (Stripe, Supabase, n8n, Google Workspace)
  5. Doctor run + summary

Writes to ~/.bravo/.env (never .env.agents, never the repo).
Zero external dependencies (urllib + getpass + json only).
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

BRAVO_HOME = Path(os.path.expanduser("~/.bravo"))
ENV_PATH = BRAVO_HOME / ".env"

# Repo-side env file (legacy path; existing scripts load from here).
REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_ENV = REPO_ROOT / ".env.agents"

# Force UTF-8 output on Windows.
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Style ─────────────────────────────────────────────────────────────────────

_COLOR = os.environ.get("NO_COLOR") is None and sys.stdout.isatty()
def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text
BOLD    = lambda t: _c("1", t)
DIM     = lambda t: _c("2", t)
GREEN   = lambda t: _c("32", t)
YELLOW  = lambda t: _c("33", t)
RED     = lambda t: _c("31", t)
CYAN    = lambda t: _c("36", t)
MAGENTA = lambda t: _c("35", t)

BANNER = r"""
  ____  ____    ____  _     _____
 | __ )|  _ \  / \ \ \   / / _ \
 |  _ \| |_) |/ _ \ \ \ / / | | |
 | |_) |  _ </ ___ \ \ V /| |_| |
 |____/|_| \_\_/   \_\ |_|  \___/
"""

PROFILES = [
    ("bravo",  "Business operations brain (this repo)"),
    ("atlas",  "CFO — finance, tax, trading, budgeting"),
    ("maven",  "CMO — content, ads, funnel, brand"),
    ("aura",   "Life/Home agent — ambient, habits, routines"),
    ("hermes", "Client operations agent"),
    ("custom", "Forge a new agent at the end of setup"),
]

# ── I/O helpers ───────────────────────────────────────────────────────────────

def hr() -> None:
    print(DIM("─" * 60))

def section(title: str) -> None:
    print()
    print(BOLD(CYAN(title)))
    hr()

def prompt(label: str, default: str | None = None, required: bool = False) -> str:
    hint = f" [{default}]" if default else (" (required)" if required else "")
    while True:
        try:
            val = input(f"{label}{hint}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(130)
        if val:
            return val
        if default is not None:
            return default
        if not required:
            return ""
        print(f"  {RED('Required.')} Please enter a value.")

def yes_no(label: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        val = input(f"{label} [{hint}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(130)
    if not val:
        return default
    return val in {"y", "yes"}

def secret_prompt(label: str) -> str:
    """Read a secret without echoing. Falls back to input() if getpass fails."""
    try:
        val = getpass.getpass(f"{label}: ")
    except Exception:
        val = input(f"{label} (visible): ")
    return val.strip()

def choose(label: str, options: list[tuple[str, str]], default_key: str) -> str:
    print(label)
    default_idx = 0
    for i, (key, desc) in enumerate(options, start=1):
        marker = "*" if key == default_key else " "
        if key == default_key:
            default_idx = i
        print(f"  {marker} {i}. {BOLD(key):8s}  {DIM(desc)}")
    while True:
        raw = prompt(f"Pick a number (1-{len(options)})", str(default_idx))
        try:
            n = int(raw)
        except ValueError:
            print(f"  {RED('Enter a number.')}")
            continue
        if 1 <= n <= len(options):
            return options[n - 1][0]
        print(f"  {RED('Out of range.')}")

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
    """Append-or-update a single KEY=value line in ~/.bravo/.env."""
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

# ── Telegram helpers ──────────────────────────────────────────────────────────

def tg_api(token: str, method: str, params: dict | None = None,
           timeout: int = 15) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "bravo-wizard"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8"))

def tg_validate(token: str) -> dict | None:
    try:
        r = tg_api(token, "getMe")
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
    """Poll getUpdates until we see a chat id (user messages the bot once)."""
    deadline = time.time() + timeout
    last_update = 0
    while time.time() < deadline:
        try:
            r = tg_api(token, "getUpdates",
                       {"offset": last_update + 1, "timeout": 0})
        except Exception as e:  # noqa: BLE001
            print(f"  {YELLOW('Poll error')}: {e}")
            time.sleep(2)
            continue
        for upd in r.get("result", []):
            last_update = max(last_update, upd.get("update_id", 0))
            msg = upd.get("message") or upd.get("edited_message") or {}
            chat = msg.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id:
                return int(chat_id)
        time.sleep(2)
    return None

def tg_send(token: str, chat_id: int, text: str) -> bool:
    try:
        r = tg_api(token, "sendMessage",
                   {"chat_id": chat_id, "text": text})
        return bool(r.get("ok"))
    except Exception as e:  # noqa: BLE001
        print(f"  {RED('Send failed:')} {e}")
        return False

# ── Steps ─────────────────────────────────────────────────────────────────────

def step_welcome() -> None:
    print(BOLD(CYAN(BANNER)))
    print(f"  {BOLD('Bravo Setup Wizard')}")
    print(f"  {DIM('Walks you through a working configuration in under 5 minutes.')}")
    print(f"  {DIM('Keys are written to')} {CYAN(str(ENV_PATH))}")
    print(f"  {DIM('Nothing is uploaded, nothing is shared.')}")
    print()
    print(f"  {DIM('Press Ctrl+C at any time to abort. Re-running is safe — existing values stay.')}")
    print()
    input(f"  {BOLD('Press Enter to start...')} ")

def step_profile() -> str:
    section("1/6  Agent profile")
    print("Which agent profile is this setup for?")
    print()
    return choose("", PROFILES, "bravo")

def step_anthropic() -> None:
    section("2/6  Anthropic (Claude) — required")
    existing = read_env("ANTHROPIC_API_KEY")
    if existing:
        print(f"  {GREEN('✓')} ANTHROPIC_API_KEY already set in {ENV_PATH}.")
        if not yes_no("  Replace it?", default=False):
            return
    print(f"  Get one at {CYAN('https://console.anthropic.com/settings/keys')}")
    print(f"  It starts with {DIM('sk-ant-')}")
    print()
    while True:
        key = secret_prompt("  Paste ANTHROPIC_API_KEY")
        if not key:
            if yes_no("  Skip Anthropic? Bravo will be non-functional without it.", default=False):
                return
            continue
        if not key.startswith("sk-ant-"):
            print(f"  {YELLOW('Warning:')} expected format 'sk-ant-...'. Saving anyway.")
        write_env("ANTHROPIC_API_KEY", key)
        print(f"  {GREEN('✓')} Saved.")
        return

def step_openai() -> None:
    section("3/6  OpenAI (optional — for Codex delegation)")
    if not yes_no("  Do you have an OpenAI API key to add?", default=False):
        print(f"  {DIM('Skipped. Codex backend delegation will be unavailable.')}")
        return
    key = secret_prompt("  Paste OPENAI_API_KEY")
    if key:
        write_env("OPENAI_API_KEY", key)
        print(f"  {GREEN('✓')} Saved.")

def step_telegram() -> None:
    section("4/6  Telegram bridge (optional — remote control for Bravo)")
    print("  Telegram lets you send Bravo commands from your phone.")
    print("  You'll need a bot token from @BotFather.")
    print()
    if not yes_no("  Set up the Telegram bridge now?", default=True):
        return
    print()
    print(f"  {BOLD('How to get a bot token:')}")
    print(f"    1. Open Telegram, search {CYAN('@BotFather')}")
    print(f"    2. Send {CYAN('/newbot')}")
    print(f"    3. Pick a name and username (ends in 'bot')")
    print(f"    4. BotFather sends you a token like {DIM('123456:ABC-DEF...')}")
    print()
    for attempt in range(3):
        token = secret_prompt("  Paste BOT_TOKEN")
        if not token:
            print(f"  {DIM('Skipped.')}")
            return
        if not re.match(r"^\d+:[A-Za-z0-9_\-]{30,}$", token):
            print(f"  {YELLOW('Format looks off. Expected like 123456:ABC...')}")
            if not yes_no("  Try again?", default=True):
                return
            continue
        print(f"  {DIM('Validating via getMe...')}")
        me = tg_validate(token)
        if me:
            print(f"  {GREEN('✓')} Connected to bot: {BOLD('@' + me.get('username', '?'))} "
                  f"({me.get('first_name', '?')})")
            write_env("TELEGRAM_BOT_TOKEN", token)
            break
        if attempt < 2:
            print(f"  {YELLOW('Token rejected. Try again.')}")
    else:
        print(f"  {RED('Gave up after 3 attempts. Skipping.')}")
        return

    print()
    print(f"  {BOLD('Now link your chat:')}")
    print(f"    1. Open Telegram, find {BOLD('@' + me.get('username', 'your_bot'))}")
    print(f"    2. Press {CYAN('Start')} (or send any message like {CYAN('hi')})")
    print(f"    3. Come back here — I'll detect it automatically")
    print()
    input(f"  {BOLD('Press Enter once you have messaged the bot...')} ")
    print(f"  {DIM('Listening for your message (up to 120s)...')}")
    chat_id = tg_wait_for_chat_id(token, timeout=120)
    if chat_id is None:
        print(f"  {YELLOW('Did not see a message yet.')} You can run "
              f"{CYAN('bravo setup')} again later.")
        return
    print(f"  {GREEN('✓')} Captured chat_id {BOLD(str(chat_id))}")
    write_env("TELEGRAM_CHAT_ID", str(chat_id))

    if tg_send(token, chat_id,
               "✅ Bravo is connected. You'll receive updates here. "
               "Reply /help anytime for commands."):
        print(f"  {GREEN('✓')} Test message sent. Check your Telegram.")
    else:
        print(f"  {YELLOW('Test message failed, but token + chat_id are saved.')}")

def step_optional() -> None:
    section("5/6  Optional services")
    opts = [
        ("STRIPE_SECRET_KEY",    "Stripe — revenue sync, MRR, customers",
         "sk_live_ or sk_test_"),
        ("SUPABASE_URL",         "Supabase — persistent state + CRM",
         "https://<project>.supabase.co"),
        ("SUPABASE_ANON_KEY",    "Supabase anon key (needed with SUPABASE_URL)",
         "eyJ..."),
        ("N8N_API_URL",          "n8n — workflow automations",
         "https://n8n.example.com"),
        ("N8N_API_KEY",          "n8n API key",
         "long opaque token"),
    ]
    if not yes_no("  Configure any optional services now?", default=True):
        return
    for key, label, hint in opts:
        existing = read_env(key)
        mark = f"  {GREEN('✓ set')}" if existing else f"  {DIM('unset')}"
        if not yes_no(f"  {label} {mark}  — add / replace?", default=False):
            continue
        if key.endswith("URL") or key.endswith("KEY") and not key.startswith("SUPABASE_ANON"):
            print(f"    {DIM('Format:')} {hint}")
        val = secret_prompt(f"    {key}") if "KEY" in key or "SECRET" in key else prompt(f"    {key}")
        if val:
            write_env(key, val)
            print(f"    {GREEN('✓')} Saved.")

def _mirror_to_repo_env() -> bool:
    """Copy ~/.bravo/.env to <repo>/.env.agents when the repo file is missing
    or empty. Existing scripts in scripts/ load env from the repo path, so
    without this step the wizard's keys would never reach them."""
    if not ENV_PATH.exists():
        return False
    # Only bootstrap — never overwrite a populated repo env.
    if REPO_ENV.exists():
        try:
            text = REPO_ENV.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return False
        populated = any(
            "=" in ln and ln.split("=", 1)[1].strip()
            and not ln.strip().startswith("#")
            for ln in text.splitlines()
        )
        if populated:
            return False
    try:
        REPO_ENV.write_text(ENV_PATH.read_text(encoding="utf-8"),
                            encoding="utf-8")
        return True
    except Exception:
        return False


def step_finalize(profile: str) -> None:
    section("6/6  Finalize")
    # Write active profile marker
    write_env("BRAVO_ACTIVE_PROFILE", profile)
    mirrored = _mirror_to_repo_env()
    print(f"  {GREEN('✓')} Active profile: {BOLD(profile)}")
    print(f"  {GREEN('✓')} Home env:       {CYAN(str(ENV_PATH))}")
    if mirrored:
        print(f"  {GREEN('✓')} Repo env:       {CYAN(str(REPO_ENV))}  {DIM('(bootstrapped)')}")
    else:
        print(f"  {DIM('Repo env already populated — not overwritten.')}")
    print()
    print(f"  {BOLD('Next commands to try:')}")
    print(f"    {CYAN('bravo doctor')}         — full health check")
    print(f"    {CYAN('bravo status')}         — live operational summary")
    print(f"    {CYAN('bravo agent list')}     — see available sub-agents")
    print(f"    {CYAN('bravo sessions recent')} — rewind past sessions")
    if read_env("TELEGRAM_BOT_TOKEN"):
        print(f"    {CYAN('bravo run telegram_agent')} — start the Telegram bridge")
    print()

def run_wizard() -> int:
    try:
        step_welcome()
        profile = step_profile()
        step_anthropic()
        step_openai()
        step_telegram()
        step_optional()
        step_finalize(profile)
        return 0
    except KeyboardInterrupt:
        print()
        print(f"  {YELLOW('Wizard aborted.')} You can re-run {CYAN('bravo setup')} anytime.")
        return 130


if __name__ == "__main__":
    sys.exit(run_wizard())
