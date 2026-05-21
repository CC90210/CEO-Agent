#!/usr/bin/env bash
# ssh-setup-mac.sh
# One-shot SSH setup from Windows desktop -> CC's MacBook.
# Creates an SSH key if missing, copies it to the Mac, writes a ~/.ssh/config
# alias "cc-mac" so future commands are just `ssh cc-mac`.
#
# Usage:
#   bash scripts/ssh-setup-mac.sh <mac_host_or_ip> <mac_username>
#
# Examples:
#   bash scripts/ssh-setup-mac.sh 192.168.2.11 conaugh        # local LAN IP
#   bash scripts/ssh-setup-mac.sh cc-macbook.local conaugh    # Bonjour hostname
#   bash scripts/ssh-setup-mac.sh cc-macbook conaugh          # Tailscale hostname
#
# After this runs once:
#   ssh cc-mac "cd ~/APPS/Business-Empire-Agent && git status"
#   ssh cc-mac "uptime"

set -uo pipefail

if [[ $# -lt 2 ]]; then
    cat <<'EOF'
Usage: bash scripts/ssh-setup-mac.sh <mac_host_or_ip> <mac_username>

How to find Mac IP:
  - On Mac Terminal: ipconfig getifaddr en0
  - Or System Settings -> Wi-Fi -> Details -> TCP/IP

How to find Mac username:
  - On Mac Terminal: whoami

For Tailscale users:
  - On Mac: tailscale status   (find the Mac's Tailscale name)
  - Then pass that name as the first arg

EOF
    exit 1
fi

MAC_HOST="$1"
MAC_USER="$2"

if [[ -z "${NO_COLOR:-}" ]] && [[ -t 1 ]]; then
    G=$'\033[0;32m'; Y=$'\033[1;33m'; R=$'\033[0;31m'; B=$'\033[0;34m'; BOLD=$'\033[1m'; X=$'\033[0m'
else
    G=''; Y=''; R=''; B=''; BOLD=''; X=''
fi
ok()   { echo "${G}[ ok ]${X} $*"; }
info() { echo "${B}[info]${X} $*"; }
warn() { echo "${Y}[warn]${X} $*"; }
err()  { echo "${R}[err ]${X} $*" >&2; }

echo "${BOLD}=== SSH SETUP: Windows -> Mac ===${X}"
info "Target: ${MAC_USER}@${MAC_HOST}"

SSH_KEY="$HOME/.ssh/id_ed25519"
SSH_KEY_PUB="$SSH_KEY.pub"

if [[ ! -f "$SSH_KEY" ]]; then
    info "No SSH key found. Generating ed25519 key..."
    mkdir -p "$HOME/.ssh"
    chmod 700 "$HOME/.ssh" 2>/dev/null || true
    ssh-keygen -t ed25519 -f "$SSH_KEY" -N "" -C "cc-windows-$(date +%Y%m%d)" 2>&1 | tail -5
    ok "Generated key at $SSH_KEY"
else
    ok "Existing SSH key found at $SSH_KEY"
fi

info "Testing TCP reachability to ${MAC_HOST}:22..."
REACHABLE=0
if command -v nc &>/dev/null; then
    if nc -z -w 3 "$MAC_HOST" 22 2>/dev/null; then
        REACHABLE=1
    fi
fi
if [[ "$REACHABLE" == "0" ]]; then
    # Fallback: try a raw bash TCP check
    if (timeout 3 bash -c "cat < /dev/tcp/${MAC_HOST}/22" 2>/dev/null); then
        REACHABLE=1
    fi
fi

if [[ "$REACHABLE" == "1" ]]; then
    ok "Mac is reachable on port 22"
else
    warn "Mac not reachable on port 22 — attempting SSH anyway (NAT / Tailscale may still work)"
fi

info "Copying public key to Mac (you'll be prompted for Mac password ONCE)..."
PUB_KEY_CONTENT=$(cat "$SSH_KEY_PUB")

# Windows Git Bash has no ssh-copy-id, so do it manually
ssh -o StrictHostKeyChecking=accept-new "${MAC_USER}@${MAC_HOST}" bash <<REMOTE_EOF
mkdir -p ~/.ssh
chmod 700 ~/.ssh
if ! grep -qF "$PUB_KEY_CONTENT" ~/.ssh/authorized_keys 2>/dev/null; then
    echo "$PUB_KEY_CONTENT" >> ~/.ssh/authorized_keys
    chmod 600 ~/.ssh/authorized_keys
    echo "KEY_ADDED"
else
    echo "KEY_ALREADY_PRESENT"
fi
REMOTE_EOF

if [[ $? -ne 0 ]]; then
    err "Key copy failed. Common causes:"
    err "  - Wrong IP or hostname"
    err "  - Wrong username (try 'whoami' on Mac)"
    err "  - Mac Remote Login not enabled"
    err "  - Password typed incorrectly"
    exit 3
fi
ok "Public key installed on Mac"

SSH_CONFIG="$HOME/.ssh/config"
if [[ -f "$SSH_CONFIG" ]] && grep -q "^Host cc-mac\$" "$SSH_CONFIG"; then
    info "cc-mac alias already exists in $SSH_CONFIG (leaving as-is)"
else
    cat >> "$SSH_CONFIG" <<EOF

# cc-mac alias — added by ssh-setup-mac.sh
Host cc-mac
    HostName $MAC_HOST
    User $MAC_USER
    IdentityFile $SSH_KEY
    ServerAliveInterval 60
    ServerAliveCountMax 3
EOF
    chmod 600 "$SSH_CONFIG" 2>/dev/null || true
    ok "Added cc-mac alias to $SSH_CONFIG"
fi

info "Testing passwordless SSH..."
if ssh -o BatchMode=yes -o ConnectTimeout=5 cc-mac "uname -a && whoami" 2>&1; then
    ok "Passwordless SSH working"
else
    err "Passwordless SSH test failed. Check Mac sshd logs."
    exit 4
fi

echo
echo "${BOLD}=== DONE ===${X}"
echo "You can now run commands on Mac from Windows:"
echo "  ssh cc-mac \"uptime\""
echo "  ssh cc-mac \"cd ~/APPS/Business-Empire-Agent && git status\""
echo "  ssh cc-mac \"cd ~/APPS/Business-Empire-Agent && bash scripts/hooks/bravo-session-start.sh\""
echo
echo "Drop into an interactive Mac shell:  ssh cc-mac"
echo "Copy files to Mac:                    scp file.txt cc-mac:~/"
echo "Copy files from Mac:                  scp cc-mac:~/file.txt ."
