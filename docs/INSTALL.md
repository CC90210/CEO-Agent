---
tags: [install, setup, onboarding]
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
2. Clones the repo to `~/.bravo/repo`
3. Creates a Python virtualenv at `~/.bravo/venv`
4. Installs Python deps (`requirements.txt`) and Node deps (`package.json`)
5. Writes a `bravo` shim to `~/.bravo/bin/` and adds it to your PATH
6. Launches the interactive setup wizard to collect your credentials
7. Prints a success banner with your first commands

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
git clone https://github.com/CC90210/CEO-Agent.git ~/.bravo/repo
cd ~/.bravo/repo
```

### Step 2 — Python virtualenv

```bash
python3 -m venv ~/.bravo/venv
source ~/.bravo/venv/bin/activate        # macOS / Linux / WSL
# OR:  ~/.bravo/venv/Scripts/activate    # Windows PowerShell
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
mkdir -p ~/.bravo/bin
cat > ~/.bravo/bin/bravo << 'EOF'
#!/usr/bin/env bash
exec ~/.bravo/venv/bin/python ~/.bravo/repo/bravo_cli/main.py "$@"
EOF
chmod +x ~/.bravo/bin/bravo
echo 'export PATH="$HOME/.bravo/bin:$PATH"' >> ~/.bashrc   # or ~/.zshrc
source ~/.bashrc
```

**Windows (PowerShell):**
```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.bravo\bin"
@"
@echo off
"$env:USERPROFILE\.bravo\venv\Scripts\python.exe" "$env:USERPROFILE\.bravo\repo\bravo_cli\main.py" %*
"@ | Set-Content "$env:USERPROFILE\.bravo\bin\bravo.cmd"
$current = [Environment]::GetEnvironmentVariable('Path','User')
[Environment]::SetEnvironmentVariable('Path', "$current;$env:USERPROFILE\.bravo\bin", 'User')
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

## Upgrading

Pull the latest commits and reinstall deps:
```bash
bash ~/.bravo/repo/install.sh --upgrade
```

Or manually:
```bash
cd ~/.bravo/repo
git fetch origin && git reset --hard origin/main
source ~/.bravo/venv/bin/activate
pip install -r requirements.txt
npm install
bravo doctor
```

---

## Uninstalling

```bash
bash ~/.bravo/repo/install.sh --uninstall
```

This removes `~/.bravo/` and cleans the PATH entry from your shell rc files. Your `.env.agents` credentials file (if you put it somewhere else) will not be touched.

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
source ~/.bravo/venv/bin/activate   # or .venv/Scripts/activate on Windows
```

---

## Related

- [[brain/CREDENTIALS_SCAFFOLD]] — full credential reference
- [[brain/CAPABILITIES]] — all 56+ CLI tools documented
- `install/install.sh` — the full annotated bash installer
- `install/install.ps1` — the PowerShell equivalent
- `install/quickstart.sh` — one-liner wrapper (auto-installs prereqs)
