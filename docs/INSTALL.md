---
tags: [install, setup, onboarding]
last_updated: 2026-07-19
---

# Installing Bravo

Five ways to install, from fastest to most controlled.

---

## 1. Quick Install (one line)

Paste this into a terminal. Works on a fresh machine with only `curl` and `bash` installed.

**macOS / Linux / WSL:**
```bash
curl -fsSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.ps1 | iex
```

What it does in order:
1. Checks for Python 3.10+, Node 18+, Git — offers to install missing ones
2. Bootstraps the repo to `~/.oasis/wizard/repo`
3. Creates a Python virtualenv at `~/.oasis/wizard/venv`
4. Installs Python deps (`requirements.txt`) and Node deps (`package.json`)
5. Writes `oasis` and `bravo` shims to `~/.oasis/bin/` and adds that folder to your PATH
6. Launches the interactive setup wizard to collect your credentials and let you choose a profile like Bravo, Atlas, Maven, Aura, Hermes, or the client-product pair Solara + Helios (SunBiz ops + sales)
7. **Personalizes the agent for you:** wizard answers populate `brain/operator.profile.json`, `scripts/personalize.py` renders `brain/USER.md` + memory templates, `scripts/scaffold.py` token-replaces the original operator's identifiers (name, brand, website, north star) across the codebase with yours
8. Prints a success banner with your first commands

### What "personalize" and "scaffold" do

The repo ships as one operator's working copy. Two scripts turn it into yours:

- **`scripts/personalize.py apply`** — reads `brain/operator.profile.json` (built by the wizard) and renders `brain/USER.md`, `memory/ACTIVE_TASKS.md`, `memory/SESSION_LOG.md` from the matching `*.template.md` files. Idempotent. Skips files that already exist unless you pass `--force`. Run any time after changing your profile.
- **`scripts/scaffold.py --apply --backup`** — token-replaces the original operator's identifiers (full name, preferred name, personal brand, primary brand, website, email, booking link, north star, location) across all tracked files. **Refuses to run on the original operator's repo by design** — pass `--allow-cc-repo` to override. `--backup` snapshots every changed file to `.scaffold-backup/<timestamp>/` first.

Re-running `scripts/setup_wizard.py` later updates your profile and re-renders templates. Manual edits to `brain/USER.md` are preserved unless you pass `--force`.

After install, open a **new terminal** so the PATH update takes effect, then run:
```bash
bravo doctor    # full health check
bravo status    # live operational summary
```

---

## 2. Manual Install (step by step)

Use this if the one-liner fails, you are behind a proxy, or you prefer to see every step.

### Prerequisites

| Tool | Minimum version | Install |
|------|-----------------|---------|
| Python | 3.10+ | https://python.org/downloads |
| Node.js | 18+ | https://nodejs.org |
| Git | any | https://git-scm.com |

Verify:
```bash
python3 --version
node --version
git --version
```

### Step 1 — Clone

```bash
git clone https://github.com/CC90210/CEO-Agent.git ~/.oasis/wizard/repo
cd ~/.oasis/wizard/repo
```

### Step 2 — Python virtualenv

```bash
python3 -m venv ~/.oasis/wizard/venv
source ~/.oasis/wizard/venv/bin/activate        # macOS / Linux / WSL
# OR:  ~/.oasis/wizard/venv/Scripts/activate    # Windows PowerShell
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3 — Node deps

```bash
npm install
```

### Step 4 — Credentials

Run the interactive wizard:
```bash
python bravo_cli/main.py setup
```

The wizard walks you through every credential with links to where to get each one. Nothing is stored until you confirm.

What you need at minimum:
- **Anthropic API key** — https://console.anthropic.com/account/keys
- **Supabase URL + service role key** — https://supabase.com/dashboard
- **Telegram bot token** — create via @BotFather
- **Telegram chat ID** — get from @userinfobot

All other credentials (Stripe, GitHub, n8n, etc.) can be added later via `bravo setup`.

### Step 5 — Add bravo to PATH

**macOS / Linux / WSL:**
```bash
mkdir -p ~/.oasis/bin
cat > ~/.oasis/bin/oasis << 'EOF'
#!/usr/bin/env bash
exec ~/.oasis/wizard/venv/bin/python ~/.oasis/wizard/repo/bravo_cli/main.py "$@"
EOF
chmod +x ~/.oasis/bin/oasis
ln -sf ~/.oasis/bin/oasis ~/.oasis/bin/bravo
echo 'export PATH="$HOME/.oasis/bin:$PATH"' >> ~/.bashrc   # or ~/.zshrc
source ~/.bashrc
```

**Windows (PowerShell):**
```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.oasis\bin"
@"
@echo off
"$env:USERPROFILE\.oasis\wizard\venv\Scripts\python.exe" "$env:USERPROFILE\.oasis\wizard\repo\bravo_cli\main.py" %*
"@ | Set-Content "$env:USERPROFILE\.oasis\bin\oasis.cmd"
@"
@echo off
"$env:USERPROFILE\.oasis\wizard\venv\Scripts\python.exe" "$env:USERPROFILE\.oasis\wizard\repo\bravo_cli\main.py" %*
"@ | Set-Content "$env:USERPROFILE\.oasis\bin\bravo.cmd"
$current = [Environment]::GetEnvironmentVariable('Path','User')
[Environment]::SetEnvironmentVariable('Path', "$current;$env:USERPROFILE\.oasis\bin", 'User')
```

Open a new terminal, then:
```bash
bravo doctor
```

---

## 3. Cloud / VPS Install (Docker)

A `docker-compose.yml` is provided for cloud server deployments.

```bash
git clone https://github.com/CC90210/CEO-Agent.git bravo
cd bravo
cp .env.example .env.agents    # fill in credentials
docker-compose up -d
```

The compose file starts:
- `bravo-scheduler` — cron job orchestrator
- `bravo-telegram` — Telegram notification bridge
- `bravo-api` — FastAPI health/webhook endpoint (port 8000)

Check the container logs:
```bash
docker-compose logs -f bravo-scheduler
```

See `infra/docker-compose.yml` for full service definitions and environment variable docs.

---

## 4. Air-Gapped Install (no internet on target machine)

For machines with no outbound internet access.

**On a machine with internet access:**
```bash
git clone --depth 1 https://github.com/CC90210/CEO-Agent.git bravo
cd bravo
pip download -r requirements.txt -d ./pip-cache
npm pack --dry-run   # or bundle node_modules
tar -czf bravo-offline.tar.gz bravo/ --exclude=bravo/.git
```

**Transfer the tarball to the target machine**, then:
```bash
tar -xzf bravo-offline.tar.gz
cd bravo
python3 -m venv .venv && source .venv/bin/activate
pip install --no-index --find-links=./pip-cache -r requirements.txt
npm install --prefer-offline
python bravo_cli/main.py setup
```

---

## 5. Multi-Tenant Install (multiple clients on one host)

Each client gets an isolated home directory with its own `.env.agents`.

```bash
BRAVO_HOME=/opt/bravo/client-acme bash install.sh --skip-wizard
cd /opt/bravo/client-acme/repo
BRAVO_SETUP_CONFIG=/etc/bravo/acme-config.yaml python scripts/setup_wizard.py
```

`BRAVO_SETUP_CONFIG` points to a YAML file that pre-answers the wizard prompts. See `brain/CREDENTIALS_SCAFFOLD.md` for the full key list.

Example config YAML:
```yaml
profile: bravo
ANTHROPIC_API_KEY: sk-ant-api03-...
SUPABASE_URL: https://yourproject.supabase.co
SUPABASE_SERVICE_ROLE_KEY: eyJ...
TELEGRAM_BOT_TOKEN: 123:...
TELEGRAM_CHAT_ID: "987654321"
owner_name: "Acme Corp"
owner_email: admin@acme.com
skip_smoke: false
```

Run with `--non-interactive` to bypass all prompts:
```bash
python bravo_cli/main.py setup --noninteractive
```

---

## Auto-Update Behavior

GitHub does **not** push updates to existing clones automatically. There are three paths to receive new commits:

1. **Re-run the wizard** (recommended). The wizard calls `_self_update_preflight()` on every launch — it fetches origin, fast-forwards your branch if you have no local changes, and re-runs itself with the new code. Skip with `BRAVO_SKIP_AUTO_UPDATE=1` if you want to lock to the commit you have.

   ```bash
   python scripts/setup_wizard.py     # auto-pulls latest before running
   ```

2. **Re-run the install one-liner.** It detects the existing clone and offers `[u]pgrade` / `[o]verwrite` / `[c]ancel`. Pick `u` for a clean fast-forward.

   ```bash
   irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.ps1 | iex
   ```

3. **Manual git pull.**

   ```bash
   cd C:\Users\User\Business-Empire-Agent      # or wherever your clone lives
   git fetch origin && git reset --hard origin/main
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt   # if deps changed
   ```

Idle clones stay at whatever commit they had — they don't poll GitHub. Pin to a release with `BRAVO_VERSION=v6.5.0 install.ps1` if you ever want frozen behavior.

After any update, `bravo doctor` validates the full system: required files, self-audit health score, V6 stack (14 scripts loadable), MCP sync, available LLM providers, browser harness status, env-file completeness. One command, one screen, full picture.

```bash
bravo doctor
```

---

## Maintenance — `scripts/core/system_cleanup.py`

After multiple installs/upgrades, redundant clones (including legacy `~/.bravo`, plus `~/.oasis/wizard` and `~/.oasis/<slug>`) and pip/npm caches accumulate. Run a dry-run audit any time to see reclaimable space:

```bash
python scripts/core/system_cleanup.py
```

Output shows total reclaimable size + per-category breakdown. To delete (with per-category confirmation):

```bash
python scripts/core/system_cleanup.py --apply
```

Skip prompts entirely:

```bash
python scripts/core/system_cleanup.py --apply --yes
```

Be selective:

```bash
python scripts/core/system_cleanup.py --apply --skip pip,npm     # nuke clones only
python scripts/core/system_cleanup.py --apply --tmp-age 30       # keep tmp/ files <30d old
```

The active repo (where you're running the script from) is **always preserved** by a hardcoded safety guard. Categories: redundant clones, pip cache, npm cache, old `tmp/` files, `__pycache__` trees, scaffold backups.

---

## Upgrading

Pull the latest commits and reinstall deps:
```bash
bash ~/.oasis/wizard/repo/install.sh --upgrade
```

Or manually:
```bash
cd ~/.oasis/wizard/repo
git fetch origin && git reset --hard origin/main
source ~/.oasis/wizard/venv/bin/activate
pip install -r requirements.txt
npm install
bravo doctor
```

---

## Uninstalling

```bash
bash ~/.oasis/wizard/repo/install.sh --uninstall
```

This removes `~/.oasis/` and cleans the PATH entry from your shell rc files. Your `.env.agents` credentials file (if you put it somewhere else) will not be touched.

---

## Troubleshooting

### Python not found after install

The new Python binary may not be on the current session's PATH. Open a new terminal and try again. On macOS with Homebrew, run `hash -r` first.

### `pip install` fails on Windows (torch / triton)

`openai-whisper` is intentionally excluded from `requirements.txt` because it pulls in `torch`, which requires build tools on Windows. If you need audio transcription:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install openai-whisper
```

### `bravo doctor` reports Supabase connection failure

Your Supabase service role key may have changed or your project may be paused (free tier pauses after 1 week of inactivity). Log in at https://supabase.com/dashboard and resume the project, then re-run `bravo setup` to update the key.

### Telegram bot not receiving messages

1. Confirm the bot is started (message it `/start`)
2. Verify `TELEGRAM_CHAT_ID` matches your user ID from @userinfobot
3. Check that `TELEGRAM_BOT_TOKEN` is correct (no spaces, no quotes in the value)

### `npm install` fails with EACCES permission error (macOS/Linux)

You have a global `node_modules` permission issue. Fix it:
```bash
mkdir -p ~/.npm-global
npm config set prefix '~/.npm-global'
echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
npm install   # retry in the repo directory
```

### install.ps1 is blocked by PowerShell execution policy

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### `bravo doctor` passes but commands return errors

Your virtualenv may not be active. The `bravo` shim activates it automatically, but if you are calling `python scripts/...` directly:
```bash
source ~/.oasis/wizard/venv/bin/activate   # or .venv/Scripts/activate on Windows
```

---

## Related

- [[brain/CREDENTIALS_SCAFFOLD]] — full credential reference
- [[brain/CAPABILITIES]] — all 56+ CLI tools documented
- `install/install.sh` — the full annotated bash installer
- `install/install.ps1` — the PowerShell equivalent
- `install/quickstart.sh` — one-liner wrapper (auto-installs prereqs)
