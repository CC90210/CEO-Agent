#!/usr/bin/env bash
# OASIS AI — One-Line Installer (macOS / Linux / WSL)
# Version: 6.3.0
#
# This is a thin bootstrap. It clones the OASIS wizard, installs deps,
# then HANDS OFF to the real wizard (bravo_cli) which has the full UX:
# big figlet agent picker, identity questions, and per-agent repo cloning.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.sh | bash
#
# License: MIT — Copyright (c) 2026 OASIS AI Solutions

set -euo pipefail

OASIS_HOME="${OASIS_HOME:-$HOME/.oasis}"
WIZARD_HOME="${OASIS_HOME}/wizard"
WIZARD_REPO="${WIZARD_HOME}/repo"
WIZARD_VENV="${WIZARD_HOME}/venv"
BOOTSTRAP_REPO="https://github.com/CC90210/CEO-Agent.git"
BOOTSTRAP_BRANCH="main"
SCRIPT_VERSION="6.3.0"

MODE="install"
SKIP_WIZARD=0
AUTO_INSTALL_MODE="prompt"

for arg in "$@"; do
    case "$arg" in
        --upgrade)         MODE="upgrade" ;;
        --uninstall)       MODE="uninstall" ;;
        --skip-wizard)     SKIP_WIZARD=1 ;;
        --auto-install|-y) AUTO_INSTALL_MODE="yes" ;;
        --no-auto-install) AUTO_INSTALL_MODE="no" ;;
        -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    esac
done

case "${OASIS_AUTO_INSTALL:-}"    in 1|yes|true) AUTO_INSTALL_MODE="yes" ;; esac
case "${OASIS_NO_AUTO_INSTALL:-}" in 1|yes|true) AUTO_INSTALL_MODE="no"  ;; esac

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_CYAN=$'\033[1;36m'; C_GREEN=$'\033[1;32m'; C_RED=$'\033[1;31m'
    C_DIM=$'\033[2m'; C_YELLOW=$'\033[1;33m'; C_WHITE=$'\033[1;37m'; C_RESET=$'\033[0m'
else
    C_CYAN=''; C_GREEN=''; C_RED=''; C_DIM=''; C_YELLOW=''; C_WHITE=''; C_RESET=''
fi

ok()   { printf '  %s[+]%s  %s\n'   "$C_GREEN"  "$C_RESET" "$1"; }
fail() { printf '  %s[x]%s  %s\n'   "$C_RED"    "$C_RESET" "$1"; }
warn() { printf '  %s[!]%s  %s\n'   "$C_YELLOW" "$C_RESET" "$1"; }
info() { printf '  %s%s%s\n'        "$C_DIM"    "$1" "$C_RESET"; }
step() { printf '\n%s──  %s%s\n'    "$C_CYAN"   "$1" "$C_RESET"; }

ask_yn() {
    local q="$1"; local def="${2:-y}"
    if [ "$AUTO_INSTALL_MODE" = "yes" ]; then return 0; fi
    if [ "$AUTO_INSTALL_MODE" = "no" ];  then return 1; fi
    local hint='[Y/n]'; [ "$def" = "n" ] && hint='[y/N]'
    printf '  %s %s ' "$q" "$hint"
    local reply=""; read -r reply </dev/tty 2>/dev/null || reply=""
    if [ -z "$reply" ]; then [ "$def" = "y" ] && return 0 || return 1; fi
    [[ "$reply" =~ ^[Yy] ]] && return 0 || return 1
}

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
printf '  %sbootstrap v%s%s\n\n' "$C_DIM" "$SCRIPT_VERSION" "$C_RESET"
printf '  %sAfter dependencies install, the wizard will let you pick:%s\n' "$C_WHITE" "$C_RESET"
printf '    %sBravo (CEO)  ·  Atlas (CFO)  ·  Maven (CMO)  ·  Aura  ·  Hermes%s\n\n' "$C_DIM" "$C_RESET"

ask_yn "Continue with installation?" y || { warn "Aborted."; exit 0; }

# ── Uninstall ────────────────────────────────────────────────────────────────
if [ "$MODE" = "uninstall" ]; then
    step "Uninstall OASIS"
    [ ! -d "$OASIS_HOME" ] && { warn "Nothing at $OASIS_HOME"; exit 0; }
    warn "This will remove $OASIS_HOME (every installed agent)."
    ask_yn "Continue?" n || { info "Aborted"; exit 0; }
    rm -rf "$OASIS_HOME"
    ok "Uninstalled."
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
    command -v "$tool" >/dev/null 2>&1 && ok "$tool" || { fail "$tool"; MISSING+=("$tool"); }
done

if [ ${#MISSING[@]} -gt 0 ]; then
    warn "Missing: ${MISSING[*]}"
    info "Install manually then re-run:"
    info "  Python: https://python.org/downloads"
    info "  Node:   https://nodejs.org"
    info "  Git:    https://git-scm.com"
    exit 2
fi

# ── Clone wizard repo ────────────────────────────────────────────────────────
step "Fetching OASIS wizard"
mkdir -p "$WIZARD_HOME"

if [ -d "$WIZARD_REPO/.git" ] && [ "$MODE" != "upgrade" ]; then
    warn "Wizard already at $WIZARD_REPO"
    printf "  [u]pgrade  [r]un wizard now  [c]ancel  (default: run): "
    reply=""; read -r reply </dev/tty 2>/dev/null || reply=""
    case "$reply" in
        [Uu]*) git -C "$WIZARD_REPO" fetch --depth 50 origin "$BOOTSTRAP_BRANCH" >/dev/null 2>&1
               git -C "$WIZARD_REPO" reset --hard "origin/$BOOTSTRAP_BRANCH" >/dev/null 2>&1
               ok "Updated" ;;
        [Cc]*) info "Cancelled"; exit 0 ;;
        *)     info "Skipping clone — using existing wizard." ;;
    esac
elif [ "$MODE" = "upgrade" ] && [ -d "$WIZARD_REPO/.git" ]; then
    git -C "$WIZARD_REPO" fetch --depth 50 origin "$BOOTSTRAP_BRANCH" >/dev/null 2>&1
    git -C "$WIZARD_REPO" reset --hard "origin/$BOOTSTRAP_BRANCH" >/dev/null 2>&1
    ok "Wizard updated"
else
    [ -d "$WIZARD_REPO" ] && rm -rf "$WIZARD_REPO"
    info "Cloning $BOOTSTRAP_REPO -> $WIZARD_REPO (about 5 seconds)"
    git clone --depth 10 --branch "$BOOTSTRAP_BRANCH" "$BOOTSTRAP_REPO" "$WIZARD_REPO" >/dev/null 2>&1 || { fail "clone failed"; exit 1; }
    ok "Cloned"
fi

# ── Python venv + deps ───────────────────────────────────────────────────────
VENV_PY="$WIZARD_VENV/bin/python"
if [ -x "$VENV_PY" ]; then
    step "Python virtualenv (already present, reusing)"
    ok "venv at $WIZARD_VENV"
else
    step "Python virtualenv"
    info "Creating virtualenv at $WIZARD_VENV (about 15-30 seconds)..."
    ask_yn "Continue?" y || { warn "Aborted."; exit 0; }
    cd "$WIZARD_REPO"
    "$PYTHON_CMD" -m venv "$WIZARD_VENV"
    [ ! -x "$VENV_PY" ] && { fail "venv creation failed"; exit 1; }
    ok "venv created"
fi

if [ -f "$WIZARD_REPO/requirements.txt" ]; then
    step "Python dependencies"
    info "pip install -r requirements.txt — this can take 2-4 minutes."
    info "(SHOWING progress so you know it's not frozen.)"
    ask_yn "Continue?" y || { warn "Aborted."; exit 0; }
    printf '\n'
    "$VENV_PY" -m pip install --upgrade pip 2>&1 | sed 's/^/       /'
    "$VENV_PY" -m pip install -r "$WIZARD_REPO/requirements.txt" 2>&1 | sed 's/^/       /'
    [ "${PIPESTATUS[0]:-0}" -eq 0 ] && ok "Python deps installed" || { fail "pip install failed"; exit 1; }
fi

# ── Node deps ────────────────────────────────────────────────────────────────
if [ -f "$WIZARD_REPO/package.json" ]; then
    step "Node.js dependencies"
    info "npm install — this can take 1-3 minutes."
    if ask_yn "Continue?" y; then
        printf '\n'
        npm install --prefix "$WIZARD_REPO" 2>&1 | sed 's/^/       /' || warn "npm install had issues — wizard may still work"
        ok "Node deps installed"
    else
        warn "Skipped npm install"
    fi
fi

# ── PATH shim ────────────────────────────────────────────────────────────────
step "Adding 'oasis' command to PATH"
BIN_DIR="$OASIS_HOME/bin"
mkdir -p "$BIN_DIR"
WIZARD_ENTRY="$WIZARD_REPO/bravo_cli/main.py"

cat > "$BIN_DIR/oasis" <<EOF
#!/usr/bin/env bash
exec "$VENV_PY" "$WIZARD_ENTRY" "\$@"
EOF
chmod +x "$BIN_DIR/oasis"

# Backwards-compat 'bravo' alias
ln -sf "$BIN_DIR/oasis" "$BIN_DIR/bravo" 2>/dev/null || cp "$BIN_DIR/oasis" "$BIN_DIR/bravo"
chmod +x "$BIN_DIR/bravo"

ok "Wrote $BIN_DIR/oasis (and 'bravo' alias)"

RC_FILE=""
[ -f "$HOME/.zshrc" ] && RC_FILE="$HOME/.zshrc"
[ -z "$RC_FILE" ] && [ -f "$HOME/.bashrc" ] && RC_FILE="$HOME/.bashrc"
if [ -n "$RC_FILE" ] && ! grep -q "$BIN_DIR" "$RC_FILE" 2>/dev/null; then
    echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$RC_FILE"
    info "Added $BIN_DIR to PATH in $RC_FILE (open a new terminal)"
fi

# ── Hand off to the wizard ───────────────────────────────────────────────────
if [ "$SKIP_WIZARD" -eq 0 ]; then
    printf '\n%s============================================%s\n' "$C_GREEN" "$C_RESET"
    printf '  %sBootstrap complete. Launching wizard...%s\n' "$C_WHITE" "$C_RESET"
    printf '%s============================================%s\n\n' "$C_GREEN" "$C_RESET"
    cd "$WIZARD_REPO"
    "$VENV_PY" "$WIZARD_ENTRY" setup
fi
