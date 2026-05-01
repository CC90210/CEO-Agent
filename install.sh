#!/usr/bin/env bash
# Bravo — Autonomous AI Business Agent
# One-command installer for macOS / Linux / WSL
# Version: 6.0.0
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.sh | bash
#
#   # Pin to a specific release:
#   BRAVO_VERSION=v6.0.0 bash -c "$(curl -fsSL ...)"
#
#   # Override install directory (default: ~/.bravo):
#   BRAVO_HOME=/opt/bravo bash -c "$(curl -fsSL ...)"
#
#   # Upgrade existing install:
#   bash ~/.bravo/repo/install.sh --upgrade
#
#   # Uninstall:
#   bash ~/.bravo/repo/install.sh --uninstall
#
#   # Skip auto-install of missing prereqs (print URLs only):
#   bash install.sh --no-auto-install
#
#   # Non-interactive (CI): accept all defaults, skip wizard:
#   OASIS_AUTO_INSTALL=1 bash install.sh --skip-wizard
#
# License: MIT — Copyright (c) 2026 Conaugh McKenna / OASIS AI Solutions

set -euo pipefail

BRAVO_HOME="${BRAVO_HOME:-$HOME/.bravo}"
BRAVO_REPO="${BRAVO_HOME}/repo"
BRAVO_VERSION="${BRAVO_VERSION:-}"
REPO_URL="https://github.com/CC90210/CEO-Agent.git"
REPO_RAW="https://raw.githubusercontent.com/CC90210/CEO-Agent/main"
SCRIPT_VERSION="6.0.0"

# ── Flags ────────────────────────────────────────────────────────────────────
MODE="install"   # install | upgrade | uninstall
SKIP_WIZARD=0
AUTO_INSTALL_MODE="prompt"

for arg in "$@"; do
    case "$arg" in
        --upgrade)          MODE="upgrade" ;;
        --uninstall)        MODE="uninstall" ;;
        --skip-wizard)      SKIP_WIZARD=1 ;;
        --auto-install)     AUTO_INSTALL_MODE="yes" ;;
        --no-auto-install)  AUTO_INSTALL_MODE="no" ;;
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
    C_DIM=$'\033[2m'; C_YELLOW=$'\033[1;33m'; C_BOLD=$'\033[1m'; C_RESET=$'\033[0m'
else
    C_CYAN=''; C_GREEN=''; C_RED=''; C_DIM=''; C_YELLOW=''; C_BOLD=''; C_RESET=''
fi

ok()   { printf '  %s✓%s  %s\n'   "$C_GREEN"  "$C_RESET" "$1"; }
fail() { printf '  %s✗%s  %s\n'   "$C_RED"    "$C_RESET" "$1"; }
warn() { printf '  %s!%s  %s\n'   "$C_YELLOW" "$C_RESET" "$1"; }
info() { printf '  %s%s%s\n'      "$C_DIM"    "$1" "$C_RESET"; }
step() { printf '\n%s──  %s%s\n'  "$C_CYAN"   "$1" "$C_RESET"; }

# ── Banner ───────────────────────────────────────────────────────────────────
printf '%s\n' "$C_CYAN"
cat <<'BANNER'

  ██████╗ ██████╗  █████╗ ██╗   ██╗ ██████╗
  ██╔══██╗██╔══██╗██╔══██╗██║   ██║██╔═══██╗
  ██████╔╝██████╔╝███████║██║   ██║██║   ██║
  ██╔══██╗██╔══██╗██╔══██║╚██╗ ██╔╝██║   ██║
  ██████╔╝██║  ██║██║  ██║ ╚████╔╝ ╚██████╔╝
  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝   ╚═════╝

  Autonomous AI Business Agent  ·  oasisai.work
BANNER
printf '%s' "$C_RESET"
printf '  %sinstaller v%s%s\n\n' "$C_DIM" "$SCRIPT_VERSION" "$C_RESET"

# ── Uninstall ────────────────────────────────────────────────────────────────
if [ "$MODE" = "uninstall" ]; then
    step "Uninstall"
    if [ ! -d "$BRAVO_HOME" ]; then
        warn "Nothing to uninstall at $BRAVO_HOME"
        exit 0
    fi
    printf '%sThis will remove %s%s and the bravo PATH entry.\n' \
        "$C_YELLOW" "$BRAVO_HOME" "$C_RESET"
    printf 'Your .env.agents file will NOT be deleted. Confirm? [y/N] '
    read -r reply </dev/tty || reply=""
    case "${reply:-N}" in
        [Yy]*) ;;
        *) echo "Aborted."; exit 0 ;;
    esac
    rm -rf "$BRAVO_HOME"
    # Try removing PATH entry from shell rc files
    for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
        if [ -f "$rc" ]; then
            sed -i.bak '/\.bravo\/bin/d' "$rc" 2>/dev/null || true
        fi
    done
    ok "Removed $BRAVO_HOME"
    info "Shell rc files cleaned. Open a new terminal to finalize."
    exit 0
fi

# ── OS + arch detection ──────────────────────────────────────────────────────
detect_os() {
    local s; s="$(uname -s 2>/dev/null || echo unknown)"
    case "$s" in
        Darwin) echo "mac" ;;
        Linux)
            if   command -v apt-get >/dev/null 2>&1; then echo "linux-apt"
            elif command -v dnf     >/dev/null 2>&1; then echo "linux-dnf"
            elif command -v pacman  >/dev/null 2>&1; then echo "linux-pacman"
            elif command -v zypper  >/dev/null 2>&1; then echo "linux-zypper"
            else echo "linux-unknown"; fi ;;
        *)  echo "unknown" ;;
    esac
}
OS="$(detect_os)"

# ── Python ≥ 3.10 check ──────────────────────────────────────────────────────
check_python() {
    command -v python3 >/dev/null 2>&1 || return 1
    # Reject Apple stub
    if [ "$(uname -s 2>/dev/null)" = "Darwin" ] \
       && [ "$(command -v python3)" = "/usr/bin/python3" ]; then
        return 1
    fi
    local v
    v="$(python3 -c 'import sys; print(sys.version_info.major, sys.version_info.minor, sep=".")' 2>/dev/null)" || return 1
    case "$v" in 3.1[0-9]|3.[2-9][0-9]) return 0 ;; *) return 1 ;; esac
}

# ── Prerequisite check ───────────────────────────────────────────────────────
step "Checking prerequisites"
MISSING=()
for tool in python3 node npm git; do
    if [ "$tool" = "python3" ]; then
        if check_python; then ok "python3 (≥ 3.10)"; else fail "python3 (need 3.10+)"; MISSING+=("python3"); fi
        continue
    fi
    if command -v "$tool" >/dev/null 2>&1; then ok "$tool"; else fail "$tool"; MISSING+=("$tool"); fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    printf '\n%sMissing: %s%s\n' "$C_YELLOW" "${MISSING[*]}" "$C_RESET"

    # Provide install URLs + commands
    echo ""
    case "$OS" in
        mac)
            info "Install via Homebrew (https://brew.sh):"
            printf '    brew install python@3.12 node git\n'
            ;;
        linux-apt)
            info "Install via apt:"
            printf '    sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv nodejs npm git\n'
            ;;
        linux-dnf)
            info "Install via dnf:"
            printf '    sudo dnf install -y python3 python3-pip nodejs npm git\n'
            ;;
        linux-pacman)
            info "Install via pacman:"
            printf '    sudo pacman -Sy --noconfirm python python-pip nodejs npm git\n'
            ;;
        *)
            info "Install manually:"
            printf '    Python:  https://python.org/downloads\n'
            printf '    Node:    https://nodejs.org\n'
            printf '    Git:     https://git-scm.com\n'
            ;;
    esac

    if [ "$AUTO_INSTALL_MODE" = "no" ] || [ "$OS" = "unknown" ] || [ "$OS" = "linux-unknown" ]; then
        echo ""
        fail "Missing prerequisites. Install them and re-run."
        exit 2
    fi

    # Auto-install prompt
    if [ "$AUTO_INSTALL_MODE" = "prompt" ]; then
        printf '\n%sAuto-install the above? [Y/n] %s' "$C_CYAN" "$C_RESET"
        if [ -r /dev/tty ]; then
            read -r reply </dev/tty || reply="Y"
        else
            reply="Y"
        fi
        case "${reply:-Y}" in [Nn]*) fail "Aborted. Install manually and re-run."; exit 2 ;; esac
    fi

    # Run auto-install
    case "$OS" in
        mac)
            if ! command -v brew >/dev/null 2>&1; then
                info "Installing Homebrew..."
                NONINTERACTIVE=1 /bin/bash -c \
                    "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
                for d in /opt/homebrew/bin /usr/local/bin; do
                    [ -x "$d/brew" ] && eval "$("$d/brew" shellenv)" && break
                done
            fi
            brew install python@3.12 node git
            hash -r 2>/dev/null || true
            ;;
        linux-apt)
            sudo apt-get update -y
            sudo apt-get install -y python3 python3-pip python3-venv nodejs npm git
            ;;
        linux-dnf)
            sudo dnf install -y python3 python3-pip nodejs npm git
            ;;
        linux-pacman)
            sudo pacman -Sy --noconfirm python python-pip nodejs npm git
            ;;
        linux-zypper)
            sudo zypper install -y python3 python3-pip nodejs npm git
            ;;
    esac

    # Re-verify
    step "Re-checking after install"
    STILL_MISSING=()
    for tool in "${MISSING[@]}"; do
        if [ "$tool" = "python3" ]; then
            if check_python; then ok "python3"; else fail "python3"; STILL_MISSING+=("python3"); fi
            continue
        fi
        if command -v "$tool" >/dev/null 2>&1; then ok "$tool"; else fail "$tool"; STILL_MISSING+=("$tool"); fi
    done

    if [ ${#STILL_MISSING[@]} -gt 0 ]; then
        fail "Still missing: ${STILL_MISSING[*]}"
        info "Open a new terminal (PATH may not have refreshed) and re-run."
        exit 1
    fi
fi

# ── Clone / upgrade ──────────────────────────────────────────────────────────
step "${MODE^} Bravo"

if [ "$MODE" = "upgrade" ] && [ -d "$BRAVO_REPO/.git" ]; then
    info "Pulling latest from origin/main..."
    if [ -n "$(git -C "$BRAVO_REPO" status --porcelain 2>/dev/null)" ]; then
        warn "Local changes detected — stashing"
        git -C "$BRAVO_REPO" stash push -u -m "auto-stash $(date +%s)" >/dev/null 2>&1 || true
    fi
    git -C "$BRAVO_REPO" fetch --depth 50 origin main 2>/dev/null || warn "Fetch failed (offline?) — using local"
    git -C "$BRAVO_REPO" reset --hard origin/main >/dev/null 2>&1 || true
    ok "Repo updated"
elif [ -d "$BRAVO_REPO/.git" ]; then
    warn "Existing install found at $BRAVO_REPO"
    printf '%sOptions: [u]pgrade  [o]verwrite  [c]ancel  [default: cancel]: %s' "$C_CYAN" "$C_RESET"
    read -r reply </dev/tty 2>/dev/null || reply="c"
    case "${reply:-c}" in
        [Uu]*) MODE="upgrade"
               git -C "$BRAVO_REPO" fetch --depth 50 origin main 2>/dev/null || true
               git -C "$BRAVO_REPO" reset --hard origin/main >/dev/null 2>&1 || true
               ok "Upgraded" ;;
        [Oo]*) info "Removing old install..."
               rm -rf "$BRAVO_REPO"
               git clone --depth 10 ${BRAVO_VERSION:+--branch "$BRAVO_VERSION"} \
                   "$REPO_URL" "$BRAVO_REPO"
               ok "Cloned fresh" ;;
        *)     info "Cancelled. Re-run with --upgrade to update in place."; exit 0 ;;
    esac
else
    mkdir -p "$(dirname "$BRAVO_REPO")"
    info "Cloning $REPO_URL → $BRAVO_REPO"
    git clone --depth 10 ${BRAVO_VERSION:+--branch "$BRAVO_VERSION"} \
        "$REPO_URL" "$BRAVO_REPO"
    ok "Cloned"
fi

# ── Python venv + deps ───────────────────────────────────────────────────────
step "Installing Python dependencies"
cd "$BRAVO_REPO"

VENV_DIR="$BRAVO_HOME/venv"
if [ ! -x "$VENV_DIR/bin/python" ]; then
    info "Creating virtualenv at $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if [ -f "$BRAVO_REPO/requirements.txt" ]; then
    info "pip install -r requirements.txt"
    pip install --quiet --upgrade pip
    pip install --quiet -r "$BRAVO_REPO/requirements.txt" && ok "Python deps installed" \
        || { fail "pip install failed — see above for errors"; exit 1; }
else
    warn "requirements.txt not found — skipping pip install"
fi

# ── Node deps ────────────────────────────────────────────────────────────────
step "Installing Node.js dependencies"
if [ -f "$BRAVO_REPO/package.json" ]; then
    (cd "$BRAVO_REPO" && npm install --silent) && ok "Node deps installed" \
        || { fail "npm install failed"; exit 1; }
else
    warn "package.json not found — skipping npm install"
fi

# ── PATH shim ────────────────────────────────────────────────────────────────
step "Adding bravo to PATH"
BIN_DIR="$BRAVO_HOME/bin"
mkdir -p "$BIN_DIR"

# Write shim
SHIM="$BIN_DIR/bravo"
cat > "$SHIM" <<SHIM
#!/usr/bin/env bash
# Auto-generated by install.sh — do not edit
VENV_PYTHON="${VENV_DIR}/bin/python"
BRAVO_CLI="${BRAVO_REPO}/bravo_cli/main.py"
if [ ! -x "\$VENV_PYTHON" ]; then
    echo "bravo: venv not found at $VENV_DIR — re-run install.sh" >&2
    exit 1
fi
exec "\$VENV_PYTHON" "\$BRAVO_CLI" "\$@"
SHIM
chmod +x "$SHIM"
ok "Wrote $SHIM"

# Add to shell rc files
added_to_rc=0
for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    if [ -f "$rc" ] && ! grep -q '\.bravo/bin' "$rc" 2>/dev/null; then
        printf '\n# Bravo AI Agent\nexport PATH="%s:$PATH"\n' "$BIN_DIR" >> "$rc"
        info "Added to $rc"
        added_to_rc=1
    fi
done
if [ "$added_to_rc" = "0" ]; then
    info "PATH entry already present"
fi

# ── Setup wizard ─────────────────────────────────────────────────────────────
if [ "$SKIP_WIZARD" = "0" ]; then
    step "Setup wizard"
    PY3="$VENV_DIR/bin/python"
    WIZARD="$BRAVO_REPO/bravo_cli/main.py"
    if [ -f "$WIZARD" ]; then
        "$PY3" "$WIZARD" setup
    else
        warn "Wizard not found at $WIZARD — run manually: bravo setup"
    fi
fi

# ── Done ─────────────────────────────────────────────────────────────────────
printf '\n%s══════════════════════════════════════════════%s\n' "$C_GREEN" "$C_RESET"
printf '%s  Bravo is alive.%s\n' "$C_BOLD" "$C_RESET"
printf '%s══════════════════════════════════════════════%s\n\n' "$C_GREEN" "$C_RESET"
printf '  %sNext steps:%s\n' "$C_BOLD" "$C_RESET"
printf '    Open a new terminal (PATH update takes effect)\n\n'
printf '    %sbravo doctor%s    — full health check\n' "$C_CYAN" "$C_RESET"
printf '    %sbravo status%s    — live operational summary\n' "$C_CYAN" "$C_RESET"
printf '    %sbravo setup%s     — re-run credential wizard\n\n' "$C_CYAN" "$C_RESET"
printf '  %sSupport:%s https://oasisai.work\n\n' "$C_DIM" "$C_RESET"
