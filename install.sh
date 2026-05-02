#!/usr/bin/env bash
# OASIS AI — Multi-Agent Installer (macOS / Linux / WSL)
# Version: 6.2.0
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.sh | bash
#
#   # Skip the picker:
#   OASIS_PROFILE=atlas bash -c "$(curl -fsSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.sh)"
#
#   # Override install directory (default: ~/.oasis):
#   OASIS_HOME=/opt/oasis bash -c "$(curl -fsSL ...)"
#
# License: MIT — Copyright (c) 2026 OASIS AI Solutions

set -euo pipefail

OASIS_HOME="${OASIS_HOME:-$HOME/.oasis}"
SCRIPT_VERSION="6.2.0"

# ── Agent registry ───────────────────────────────────────────────────────────
# slug | name | role | repo | branch | tagline
read -r -d '' AGENT_REGISTRY <<'EOF' || true
bravo|Bravo|CEO|https://github.com/CC90210/CEO-Agent.git|main|Autonomous CEO — strategy, clients, revenue, outreach
atlas|Atlas|CFO|https://github.com/CC90210/CFO-Agent.git|master|Autonomous CFO — tax, treasury, FIRE, trading
maven|Maven|CMO|https://github.com/CC90210/CMO-Agent.git|main|Autonomous CMO — content, ads, brand, video pipeline
aura|Aura|Lifestyle|https://github.com/CC90210/Aura-Home-Agent.git|main|Lifestyle agent — home, habits, smart-home, voice
hermes|Hermes|Commerce|https://github.com/CC90210/hermes.git|main|Commerce agent — POS, EDI, chargebacks, fulfillment
EOF

# ── Flags ────────────────────────────────────────────────────────────────────
MODE="install"
SKIP_WIZARD=0
AUTO_INSTALL_MODE="prompt"
PROFILE_FROM_FLAG=""

for arg in "$@"; do
    case "$arg" in
        --upgrade)          MODE="upgrade" ;;
        --uninstall)        MODE="uninstall" ;;
        --skip-wizard)      SKIP_WIZARD=1 ;;
        --auto-install)     AUTO_INSTALL_MODE="yes" ;;
        --no-auto-install)  AUTO_INSTALL_MODE="no" ;;
        --profile=*)        PROFILE_FROM_FLAG="${arg#--profile=}" ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
    esac
done

case "${OASIS_AUTO_INSTALL:-}"    in 1|yes|true) AUTO_INSTALL_MODE="yes" ;; esac
case "${OASIS_NO_AUTO_INSTALL:-}" in 1|yes|true) AUTO_INSTALL_MODE="no"  ;; esac

# ── Colors ───────────────────────────────────────────────────────────────────
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_CYAN=$'\033[1;36m'; C_GREEN=$'\033[1;32m'; C_RED=$'\033[1;31m'
    C_DIM=$'\033[2m'; C_YELLOW=$'\033[1;33m'; C_BOLD=$'\033[1m'; C_WHITE=$'\033[1;37m'; C_RESET=$'\033[0m'
else
    C_CYAN=''; C_GREEN=''; C_RED=''; C_DIM=''; C_YELLOW=''; C_BOLD=''; C_WHITE=''; C_RESET=''
fi

ok()   { printf '  %s[+]%s  %s\n'   "$C_GREEN"  "$C_RESET" "$1"; }
fail() { printf '  %s[x]%s  %s\n'   "$C_RED"    "$C_RESET" "$1"; }
warn() { printf '  %s[!]%s  %s\n'   "$C_YELLOW" "$C_RESET" "$1"; }
info() { printf '  %s%s%s\n'        "$C_DIM"    "$1" "$C_RESET"; }
step() { printf '\n%s──  %s%s\n'    "$C_CYAN"   "$1" "$C_RESET"; }

# ── OASIS banner ─────────────────────────────────────────────────────────────
printf '%s\n' "$C_CYAN"
cat <<'BANNER'
   ██████╗  █████╗ ███████╗██╗███████╗      █████╗ ██╗
  ██╔═══██╗██╔══██╗██╔════╝██║██╔════╝     ██╔══██╗██║
  ██║   ██║███████║███████╗██║███████╗     ███████║██║
  ██║   ██║██╔══██║╚════██║██║╚════██║     ██╔══██║██║
  ╚██████╔╝██║  ██║███████║██║███████║     ██║  ██║██║
   ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝╚══════╝     ╚═╝  ╚═╝╚═╝
BANNER
printf '%s' "$C_RESET"
printf '\n  %sAutonomous AI C-Suite  ·  oasisai.work%s\n' "$C_WHITE" "$C_RESET"
printf '  %sinstaller v%s%s\n\n' "$C_DIM" "$SCRIPT_VERSION" "$C_RESET"

# ── Agent picker ─────────────────────────────────────────────────────────────
SELECTED=""
if [ -n "$PROFILE_FROM_FLAG" ]; then SELECTED="$(echo "$PROFILE_FROM_FLAG" | tr '[:upper:]' '[:lower:]')"; fi
if [ -z "$SELECTED" ] && [ -n "${OASIS_PROFILE:-}" ]; then SELECTED="$(echo "$OASIS_PROFILE" | tr '[:upper:]' '[:lower:]')"; fi

# Validate selection if provided
if [ -n "$SELECTED" ]; then
    if ! echo "$AGENT_REGISTRY" | awk -F'|' -v s="$SELECTED" '$1==s{found=1} END{exit !found}'; then
        warn "Unknown profile '$SELECTED' — choose from picker."
        SELECTED=""
    fi
fi

if [ -z "$SELECTED" ]; then
    printf '  %sChoose an agent:%s\n\n' "$C_WHITE" "$C_RESET"
    i=1
    SLUGS=()
    while IFS='|' read -r slug name role repo branch tagline; do
        [ -z "$slug" ] && continue
        printf '    %s%d.%s  %s%s%s  (%s)  %s%s%s\n' \
            "$C_DIM" "$i" "$C_RESET" \
            "$C_CYAN" "$name" "$C_RESET" \
            "$role" \
            "$C_DIM" "$tagline" "$C_RESET"
        SLUGS+=("$slug")
        i=$((i+1))
    done <<< "$AGENT_REGISTRY"
    printf '\n'
    while [ -z "$SELECTED" ]; do
        printf '  Pick an agent (1-%d): ' "${#SLUGS[@]}"
        read -r reply </dev/tty || reply=""
        if [[ "$reply" =~ ^[0-9]+$ ]] && [ "$reply" -ge 1 ] && [ "$reply" -le "${#SLUGS[@]}" ]; then
            SELECTED="${SLUGS[$((reply-1))]}"
        else
            printf '  %sEnter a number 1-%d%s\n' "$C_RED" "${#SLUGS[@]}" "$C_RESET"
        fi
    done
fi

# Resolve agent metadata
AGENT_LINE="$(echo "$AGENT_REGISTRY" | awk -F'|' -v s="$SELECTED" '$1==s')"
AGENT_NAME="$(echo "$AGENT_LINE" | cut -d'|' -f2)"
AGENT_ROLE="$(echo "$AGENT_LINE" | cut -d'|' -f3)"
REPO_URL="$(echo "$AGENT_LINE" | cut -d'|' -f4)"
BRANCH="$(echo "$AGENT_LINE" | cut -d'|' -f5)"

AGENT_HOME="${OASIS_HOME}/${SELECTED}"
AGENT_REPO="${AGENT_HOME}/repo"
AGENT_VENV="${AGENT_HOME}/venv"

printf '\n  %sInstalling: %s%s%s (%s)%s\n' "$C_WHITE" "$C_CYAN" "$AGENT_NAME" "$C_RESET" "$AGENT_ROLE" "$C_RESET"

# ── Uninstall ────────────────────────────────────────────────────────────────
if [ "$MODE" = "uninstall" ]; then
    step "Uninstall $AGENT_NAME"
    if [ ! -d "$AGENT_HOME" ]; then warn "Nothing to uninstall at $AGENT_HOME"; exit 0; fi
    warn "This will remove $AGENT_HOME"
    printf "  Continue? [y/N] "
    read -r reply </dev/tty || reply=""
    case "$reply" in [Yy]*) rm -rf "$AGENT_HOME"; ok "Uninstalled $AGENT_NAME";; *) info "Aborted";; esac
    exit 0
fi

# ── Prerequisites ────────────────────────────────────────────────────────────
step "Checking prerequisites"
MISSING=()
PYTHON_CMD=""
for cmd in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        ver=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "")
        if [[ "$ver" =~ ^3\.(1[0-9]|[2-9][0-9])$ ]]; then PYTHON_CMD="$cmd"; ok "python ($ver)"; break; fi
    fi
done
[ -z "$PYTHON_CMD" ] && { fail "python (need 3.10+)"; MISSING+=("python"); }
for tool in node npm git; do
    if command -v "$tool" >/dev/null 2>&1; then ok "$tool"; else fail "$tool"; MISSING+=("$tool"); fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    warn "Missing: ${MISSING[*]}"
    info "Install manually then re-run:"
    info "  Python: https://python.org/downloads"
    info "  Node:   https://nodejs.org"
    info "  Git:    https://git-scm.com"
    exit 2
fi

# ── Clone / upgrade ──────────────────────────────────────────────────────────
step "$(echo "$MODE" | sed 's/^./\U&/') $AGENT_NAME"
mkdir -p "$AGENT_HOME"

if [ "$MODE" = "upgrade" ] && [ -d "$AGENT_REPO/.git" ]; then
    git -C "$AGENT_REPO" fetch --depth 50 origin "$BRANCH" >/dev/null 2>&1 || warn "Fetch failed"
    git -C "$AGENT_REPO" reset --hard "origin/$BRANCH" >/dev/null 2>&1
    ok "$AGENT_NAME updated"
elif [ -d "$AGENT_REPO/.git" ]; then
    warn "Existing $AGENT_NAME install at $AGENT_REPO"
    printf "  [u]pgrade  [o]verwrite  [c]ancel  (default: cancel): "
    read -r reply </dev/tty || reply=""
    case "$reply" in
        [Uu]*) git -C "$AGENT_REPO" fetch --depth 50 origin "$BRANCH" >/dev/null 2>&1
               git -C "$AGENT_REPO" reset --hard "origin/$BRANCH" >/dev/null 2>&1
               ok "Upgraded" ;;
        [Oo]*) rm -rf "$AGENT_REPO"
               git clone --depth 10 --branch "$BRANCH" "$REPO_URL" "$AGENT_REPO" >/dev/null 2>&1 || { fail "clone failed"; exit 1; }
               ok "Cloned fresh" ;;
        *)     info "Cancelled. Re-run with --upgrade to update in place."; exit 0 ;;
    esac
else
    info "Cloning $REPO_URL ($BRANCH) -> $AGENT_REPO"
    git clone --depth 10 --branch "$BRANCH" "$REPO_URL" "$AGENT_REPO" >/dev/null 2>&1 || { fail "git clone failed"; exit 1; }
    ok "Cloned"
fi

# ── Python venv + deps ───────────────────────────────────────────────────────
step "Installing Python dependencies"
cd "$AGENT_REPO"
if [ ! -x "$AGENT_VENV/bin/python" ]; then
    info "Creating virtualenv at $AGENT_VENV"
    "$PYTHON_CMD" -m venv "$AGENT_VENV"
fi
VENV_PY="$AGENT_VENV/bin/python"
if [ -f "requirements.txt" ]; then
    "$VENV_PY" -m pip install --quiet --upgrade pip 2>/dev/null
    "$VENV_PY" -m pip install --quiet -r requirements.txt 2>/dev/null && ok "Python deps installed" || { fail "pip install failed"; exit 1; }
else warn "requirements.txt not found - skipping"; fi

# ── Node deps ────────────────────────────────────────────────────────────────
step "Installing Node.js dependencies"
if [ -f "package.json" ]; then
    npm install --silent 2>/dev/null && ok "Node deps installed" || { fail "npm install failed"; exit 1; }
else warn "package.json not found - skipping"; fi

# ── PATH shim ────────────────────────────────────────────────────────────────
step "Adding $SELECTED to PATH"
BIN_DIR="$AGENT_HOME/bin"
mkdir -p "$BIN_DIR"

CLI_PATH=""
for cand in "$AGENT_REPO/${SELECTED}_cli/main.py" "$AGENT_REPO/bravo_cli/main.py" "$AGENT_REPO/scripts/setup_wizard.py"; do
    if [ -f "$cand" ]; then CLI_PATH="$cand"; break; fi
done
[ -z "$CLI_PATH" ] && CLI_PATH="$AGENT_REPO/scripts/setup_wizard.py"

cat > "$BIN_DIR/$SELECTED" <<EOF
#!/usr/bin/env bash
exec "$VENV_PY" "$CLI_PATH" "\$@"
EOF
chmod +x "$BIN_DIR/$SELECTED"
ok "Wrote $BIN_DIR/$SELECTED"

# Add to user shell rc
RC_FILE=""
[ -n "${BASH_VERSION:-}" ] && RC_FILE="$HOME/.bashrc"
[ -n "${ZSH_VERSION:-}" ] || [ -f "$HOME/.zshrc" ] && RC_FILE="$HOME/.zshrc"
if [ -n "$RC_FILE" ] && ! grep -q "$BIN_DIR" "$RC_FILE" 2>/dev/null; then
    echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$RC_FILE"
    info "Added $BIN_DIR to PATH in $RC_FILE (open a new terminal)"
fi

# ── Setup wizard ─────────────────────────────────────────────────────────────
if [ "$SKIP_WIZARD" -eq 0 ]; then
    step "$AGENT_NAME setup wizard"
    if [ -f "$CLI_PATH" ]; then
        # bravo_cli/main.py needs 'setup' subcommand; setup_wizard.py runs directly
        if [[ "$CLI_PATH" == *_cli/main.py ]]; then
            "$VENV_PY" "$CLI_PATH" setup
        else
            "$VENV_PY" "$CLI_PATH"
        fi
    else
        warn "Wizard not found - cd $AGENT_REPO && python scripts/setup_wizard.py"
    fi
fi

# ── Done ─────────────────────────────────────────────────────────────────────
printf '\n%s============================================%s\n' "$C_GREEN" "$C_RESET"
printf '  %s%s is alive.%s\n' "$C_WHITE" "$AGENT_NAME" "$C_RESET"
printf '%s============================================%s\n\n' "$C_GREEN" "$C_RESET"
printf '  Open a new terminal, then:\n'
printf '    %s%s doctor%s    -- health check\n' "$C_CYAN" "$SELECTED" "$C_RESET"
printf '    %s%s status%s    -- live summary\n' "$C_CYAN" "$SELECTED" "$C_RESET"
printf '    %s%s setup%s     -- re-run wizard\n\n' "$C_CYAN" "$SELECTED" "$C_RESET"
printf '  Install another agent:\n'
printf '    %scurl -fsSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.sh | bash%s\n\n' "$C_DIM" "$C_RESET"
printf '  Support: https://oasisai.work\n\n'
