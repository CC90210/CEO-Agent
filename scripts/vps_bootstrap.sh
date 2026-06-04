#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────
# SunBiz VPS Bootstrap — minimal, no Docker. Run as root on fresh Ubuntu 22.04.
#
# PROVISIONS ONLY. It does NOT start daemons and does NOT author a PM2 config —
# the real, committed ecosystems live in the two repos and are the source of
# truth. Daemons start only AFTER credentials + migrations are in (see the
# printed NEXT STEPS, and docs/VPS_SETUP_HANDOFF.md / SunBiz-Agent VPS_BRINGUP.md).
#
# Rewritten 2026-06-03 after an audit found the prior version would brick the box:
#   - authored a phantom ecosystem.config.cjs pointing at 3 non-existent scripts
#     (webhook_listener.py / core/scheduler.py / state_bridge.py)
#   - created `venv/` while both real ecosystems hardcode `.venv/` on Linux
#   - never set up SunBiz-Agent's venv/deps (its daemons run under CEO's .venv)
#   - disabled SSH password auth before verifying the deploy key → lockout risk
#   - proxied nginx / → :3000 and /webhook/ → :8000 (nothing binds either)
#   - used non-canonical env key names (SUPABASE_URL vs BRAVO_SUPABASE_URL)
#   - ran `pm2 startup` with no `pm2 save` → nothing resurrects on reboot
# ──────────────────────────────────────────────────────────────────────────

C_CYAN='\033[1;36m'; C_GREEN='\033[1;32m'; C_RED='\033[1;31m'; C_YEL='\033[1;33m'; C_RESET='\033[0m'
log()  { printf "${C_GREEN}==>${C_RESET} %s\n" "$1"; }
warn() { printf "${C_YEL}!!>${C_RESET} %s\n" "$1"; }
die()  { printf "${C_RED}xx>${C_RESET} %s\n" "$1" >&2; exit 1; }

# Repo layout MUST match the Linux branch hardcoded in both ecosystem.config.js
# files: CEO PROJECT_ROOT=/srv/sunbiz/ceo-agent, SunBiz PROJECT_ROOT=/srv/sunbiz/
# sunbiz-agent, both interpreters = /srv/sunbiz/ceo-agent/.venv/bin/python.
SUNBIZ_REPO="${SUNBIZ_REPO:-git@github.com:CC90210/SunBiz-Agent.git}"
CEO_REPO="${CEO_REPO:-git@github.com:CC90210/Business-Empire-Agent.git}"
DEPLOY_DIR="${DEPLOY_DIR:-/srv/sunbiz}"
CEO_DIR="$DEPLOY_DIR/ceo-agent"
SUNBIZ_DIR="$DEPLOY_DIR/sunbiz-agent"
DEPLOY_USER="${DEPLOY_USER:-bravo}"

[ "$(id -u)" -eq 0 ] || die "Run as root."

# ── 1. System packages ─────────────────────────────────────────────────────
log "Updating system packages"
apt update && apt upgrade -y
log "Installing core packages"
apt install -y \
    curl wget git build-essential \
    nginx certbot python3-certbot-nginx \
    ufw fail2ban unattended-upgrades \
    python3-pip python3-venv software-properties-common

# ── 2. Firewall ─────────────────────────────────────────────────────────────
log "Configuring firewall"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
systemctl enable --now fail2ban
systemctl enable --now unattended-upgrades

# ── 3. Python 3.12 (Ubuntu 22.04 ships 3.10) ───────────────────────────────
if ! python3.12 --version &>/dev/null; then
    log "Installing Python 3.12 from deadsnakes"
    add-apt-repository -y ppa:deadsnakes/ppa
    apt update
    apt install -y python3.12 python3.12-venv python3.12-dev
fi
PYTHON="python3.12"
log "Python: $($PYTHON --version)"

# ── 4. Node.js 20 + PM2 ────────────────────────────────────────────────────
if ! node --version &>/dev/null; then
    log "Installing Node.js 20"
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt install -y nodejs
fi
log "Node: $(node --version) / npm: $(npm --version)"
log "Installing PM2 globally"
npm install -g pm2

# ── 5. Deploy user ──────────────────────────────────────────────────────────
if ! id -u "$DEPLOY_USER" &>/dev/null; then
    log "Creating $DEPLOY_USER user"
    adduser --disabled-password --gecos "" "$DEPLOY_USER"
    usermod -aG sudo "$DEPLOY_USER"
fi
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
if [ -s /root/.ssh/authorized_keys ]; then
    cp /root/.ssh/authorized_keys "/home/$DEPLOY_USER/.ssh/authorized_keys"
    chown "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh/authorized_keys"
    chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
fi

# ── 6. SSH hardening — GUARDED so we can never lock ourselves out ───────────
# Only disable password auth if $DEPLOY_USER actually has a usable key, AND
# leave a clear escape hatch. The prior version disabled it unconditionally.
if [ -s "/home/$DEPLOY_USER/.ssh/authorized_keys" ]; then
    log "Hardening SSH (key-only; $DEPLOY_USER has an authorized key)"
    sed -i 's/#\?PermitRootLogin .*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
    sed -i 's/#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
    systemctl restart ssh
    warn "Before closing this session, OPEN A SECOND TERMINAL and confirm:"
    warn "    ssh $DEPLOY_USER@<this-host>   works with your key."
else
    warn "SKIPPING SSH hardening: /home/$DEPLOY_USER/.ssh/authorized_keys is empty."
    warn "Add a key for $DEPLOY_USER first, then re-run, or harden manually."
fi

# ── 7. SSH config for GitHub (deploy key) ──────────────────────────────────
sudo -u "$DEPLOY_USER" bash -c "cat > /home/$DEPLOY_USER/.ssh/config <<'EOF'
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
EOF"
chmod 600 "/home/$DEPLOY_USER/.ssh/config"
cat <<SSHHINT
  ┌──────────────────────────────────────────────────────────┐
  │ If GitHub clone fails on auth, generate a deploy key:     │
  │   sudo -u $DEPLOY_USER ssh-keygen -t ed25519 -f \\         │
  │        /home/$DEPLOY_USER/.ssh/id_ed25519 -N ''           │
  │   sudo -u $DEPLOY_USER cat /home/$DEPLOY_USER/.ssh/id_ed25519.pub │
  │   → add to BOTH repos' Deploy keys on GitHub, then re-run │
  └──────────────────────────────────────────────────────────┘
SSHHINT

# ── 8. Clone both repos ────────────────────────────────────────────────────
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$DEPLOY_DIR"
[ -d "$CEO_DIR" ]    || { log "Cloning CEO-Agent → $CEO_DIR";       sudo -u "$DEPLOY_USER" git clone "$CEO_REPO" "$CEO_DIR"; }
[ -d "$SUNBIZ_DIR" ] || { log "Cloning SunBiz-Agent → $SUNBIZ_DIR"; sudo -u "$DEPLOY_USER" git clone "$SUNBIZ_REPO" "$SUNBIZ_DIR"; }

# ── 9. Virtualenvs (.venv — matches both ecosystems' Linux branch) ─────────
# CEO's .venv is the interpreter for ALL daemons: the CEO PM2 apps, the SunBiz
# PM2 apps (interpreter=BRAVO_ROOT/.venv/bin/python), AND the cron poller which
# execs SunBiz scripts via CEO's sys.executable. So CEO's .venv must carry BOTH
# repos' dependencies. SunBiz's own .venv is for manual doctor/cron_registry runs.
log "Creating CEO-Agent .venv + installing BOTH repos' requirements into it"
sudo -u "$DEPLOY_USER" bash -c "
    set -e
    cd '$CEO_DIR'
    $PYTHON -m venv .venv
    . .venv/bin/activate
    pip install --upgrade pip wheel
    [ -f requirements.txt ] && pip install -r requirements.txt
    [ -f '$SUNBIZ_DIR/requirements.txt' ] && pip install -r '$SUNBIZ_DIR/requirements.txt'
"
log "Creating SunBiz-Agent .venv + installing its requirements"
sudo -u "$DEPLOY_USER" bash -c "
    set -e
    cd '$SUNBIZ_DIR'
    $PYTHON -m venv .venv
    . .venv/bin/activate
    pip install --upgrade pip wheel
    [ -f requirements.txt ] && pip install -r requirements.txt
"
log "Installing CEO-Agent Node deps (PM2 entry points / tooling)"
sudo -u "$DEPLOY_USER" bash -c "cd '$CEO_DIR' && npm install --no-audit --no-fund" || warn "npm install had warnings (non-fatal)"

# ── 10. .env.agents placeholder — CANONICAL key names ──────────────────────
# Keys mirror SunBiz-Agent/docs/VPS_BRINGUP.md §3. The daemons read CEO's file;
# SunBiz's doctor + cron_registry read SunBiz's file — so we create BOTH and
# symlink SunBiz's to CEO's to keep them identical. NO Telegram keys on the VPS
# (single-bot-token invariant — Telegram stays on Bravo's Windows host).
write_env () {
  local f="$1"
  [ -f "$f" ] && { warn ".env.agents already exists at $f — leaving it untouched"; return; }
  log "Writing $f placeholder"
  cat > "$f" <<'ENVTPL'
# ── SAFETY (keep this until CC explicitly approves live outbound) ──────────
BRAVO_FORCE_DRY_RUN=1
EMAIL_REQUIRE_FROM_DOMAIN=sunbizfunding.com
# Treat Supabase suppressions as authoritative + fail CLOSED if no suppression
# source is reachable (prod must never fail-open on a missing CSV). See
# scripts/casl_compliance.py.
CASL_FAIL_CLOSED=1

# ── SUPABASE (daemons connect as service-role to see all tenants) ─────────
BRAVO_SUPABASE_URL=
BRAVO_SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ACCESS_TOKEN=
BRAVO_FIELD_ENCRYPTION_KEY=

# ── AI ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# ── EMAIL (shared submissions@sunbizfunding.com inbox) ────────────────────
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=
EMAIL_FROM_NAME=SunBiz Funding
EMAIL_UNSUBSCRIBE_BASE_URL=

# ── SUNBIZ SMS / FORMS ────────────────────────────────────────────────────
SUNBIZ_TWILIO_ACCOUNT_SID=
SUNBIZ_TWILIO_AUTH_TOKEN=
SUNBIZ_TWILIO_FROM_NUMBER=
JOTFORM_API_KEY=
JOTFORM_FORM_ID=
SUNBIZ_AGENT_HMAC_SECRET=

# ── KIXIE + TEXTTORRENT (outbound; wired but live-untested) ───────────────
KIXIE_API_KEY=
KIXIE_BUSINESS_ID=
KIXIE_WEBHOOK_SECRET=
TEXTTORRENT_API_KEY=
TEXTTORRENT_API_URL=

# ── BRIDGE (MANDATORY if nginx ever exposes the bridge publicly — see §11) ─
# Unset = the bridge auth gate is a NO-OP. Never expose port 9100 without this.
BRIDGE_BEARER_TOKEN=

# ── CASL IDENTITY ──────────────────────────────────────────────────────────
CASL_SENDER_NAME=SunBiz Funding
CASL_BUSINESS_NAME=SunBiz Funding
CASL_BUSINESS_ADDRESS=
ENVTPL
  chown "$DEPLOY_USER:$DEPLOY_USER" "$f"
  chmod 600 "$f"
}
write_env "$CEO_DIR/.env.agents"
if [ ! -e "$SUNBIZ_DIR/.env.agents" ]; then
    sudo -u "$DEPLOY_USER" ln -s "$CEO_DIR/.env.agents" "$SUNBIZ_DIR/.env.agents"
    log "Symlinked $SUNBIZ_DIR/.env.agents → $CEO_DIR/.env.agents (single source of truth)"
fi

# ── 11. nginx — healthz + a SAFE, DISABLED-by-default bridge proxy template ─
# The dashboard is on Vercel (stateless VPS), so there is NO / → :3000 and NO
# /webhook/ → :8000 (nothing binds them). The only thing worth exposing is the
# bridge (127.0.0.1:9100) for the dashboard's /api/bridge/* proxy — but that is
# an RCE-capable surface, so it stays COMMENTED until BRIDGE_BEARER_TOKEN is set
# and the public path matches the dashboard's configured bridge URL.
log "Writing nginx site (healthz live; bridge proxy commented until secured)"
cat > /etc/nginx/sites-available/sunbiz <<'NGINXTPL'
server {
    listen 80;
    server_name _;

    location /healthz {
        return 200 "ok";
        add_header Content-Type text/plain;
    }

    # ── ENABLE ONLY AFTER: BRIDGE_BEARER_TOKEN is set in .env.agents, TLS is
    # provisioned (certbot), and this path matches the dashboard's bridge URL.
    # location /bridge/ {
    #     proxy_pass http://127.0.0.1:9100/;
    #     proxy_set_header Host $host;
    #     proxy_set_header X-Real-IP $remote_addr;
    #     proxy_read_timeout 600s;
    # }
}
NGINXTPL
[ -L /etc/nginx/sites-enabled/sunbiz ] || ln -s /etc/nginx/sites-available/sunbiz /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ── 12. PM2 boot resurrection (unit only — nothing is started/saved yet) ───
# Daemons start AFTER creds + migrations (NEXT STEPS). pm2 save MUST run as
# $DEPLOY_USER after `pm2 start`, or nothing resurrects. We only install the
# systemd unit here so that later `pm2 save` (as $DEPLOY_USER) takes effect.
log "Installing PM2 systemd boot unit for $DEPLOY_USER"
env PATH="$PATH:/usr/bin:/usr/local/bin" pm2 startup systemd -u "$DEPLOY_USER" --hp "/home/$DEPLOY_USER" || \
    warn "pm2 startup returned non-zero — run the command it printed manually."

# ── Done ───────────────────────────────────────────────────────────────────
PUBLIC_IP=$(curl -4 -s ifconfig.me 2>/dev/null || echo "<vps-ip>")
cat <<DONE

$(printf "${C_CYAN}═══════════════════════════════════════════════════════════${C_RESET}")
$(printf "${C_CYAN} SunBiz VPS bootstrap complete — PROVISIONED, NOT YET RUNNING${C_RESET}")
$(printf "${C_CYAN}═══════════════════════════════════════════════════════════${C_RESET}")

  Host: $PUBLIC_IP   Deploy: $DEPLOY_DIR   User: $DEPLOY_USER

  NEXT STEPS (do in order; nothing outbound fires while BRAVO_FORCE_DRY_RUN=1):

  1. Fill credentials (interactively on the box, never via chat):
       sudo -u $DEPLOY_USER nano $CEO_DIR/.env.agents      # chmod 600 already
     (SunBiz's .env.agents is a symlink to this one.)

  2. Verify env detection — do NOT trust "file exists":
       cd $SUNBIZ_DIR && .venv/bin/python scripts/doctor.py --json

  3. Apply migrations (idempotent, numeric order) per VPS_BRINGUP.md §5.

  4. Start the REAL daemons (the committed ecosystems — there is NO
     bootstrap-authored PM2 config):
       cd $CEO_DIR    && pm2 start ecosystem.config.js --only event-router,claude-bridge-ping
       cd $SUNBIZ_DIR && pm2 start ecosystem.config.js     # sunbiz-* apps, all Linux-safe
       pm2 save                                            # <-- REQUIRED for reboot resurrection
     NOTE: VPS_BRINGUP.md §6 lists "--only ...,sequence-runner,lender-response-classifier"
     from the CEO repo — that is STALE. Those daemons are sunbiz-sequence-runner /
     sunbiz-lender-response-classifier in SunBiz's ecosystem and start from $SUNBIZ_DIR.

  5. Pair the bridge (drop the token, restart the ping loop):
       mkdir -p /home/$DEPLOY_USER/.oasis
       echo "<pairing-token>" > /home/$DEPLOY_USER/.oasis/bridge_token
       chmod 600 /home/$DEPLOY_USER/.oasis/bridge_token
       pm2 restart claude-bridge-ping

  6. TLS (only after DNS A-record → $PUBLIC_IP):
       certbot --nginx -d portal.sunbizfunding.com

  Canonical runbooks:  $CEO_DIR/docs/VPS_SETUP_HANDOFF.md  (10-phase)
                       $SUNBIZ_DIR/docs/VPS_BRINGUP.md      (8-step)
DONE
