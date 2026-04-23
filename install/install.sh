#!/usr/bin/env bash
# Bravo one-command installer for macOS / Linux / WSL.
# Idempotent. Safe to re-run. Never mutates .env.agents.
#
# Usage:
#   bash install/install.sh
#   bash install/install.sh --skip-path
#   bash install/install.sh --dry-run

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BRAVO_HOME="${BRAVO_HOME:-$HOME/.bravo}"
BIN_DIR="$BRAVO_HOME/bin"

DRY_RUN=0
SKIP_PATH=0
for arg in "$@"; do
    case "$arg" in
        --dry-run)   DRY_RUN=1 ;;
        --skip-path) SKIP_PATH=1 ;;
        *)           echo "unknown arg: $arg"; exit 1 ;;
    esac
done

# Colors
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_CYAN=$'\033[1;36m'; C_GREEN=$'\033[1;32m'; C_RED=$'\033[1;31m'
    C_DIM=$'\033[2m';     C_YELLOW=$'\033[1;33m'; C_RESET=$'\033[0m'
else
    C_CYAN=''; C_GREEN=''; C_RED=''; C_DIM=''; C_YELLOW=''; C_RESET=''
fi

printf '%s\n' "$C_CYAN"
cat <<'BANNER'

  ____  ____    ____  _     _____
 | __ )|  _ \  / \ \ \   / / _ \
 |  _ \| |_) |/ _ \ \ \ / / | | |
 | |_) |  _ </ ___ \ \ V /| |_| |
 |____/|_| \_\_/   \_\ |_|  \___/

BANNER
printf '%s' "$C_RESET"
echo "  Bravo installer — Business-Empire-Agent"
printf '  %srepo:%s %s\n\n' "$C_DIM" "$C_RESET" "$REPO_ROOT"

# Detect platform
UNAME_S="$(uname -s 2>/dev/null || echo unknown)"
case "$UNAME_S" in
    Darwin)                    PLATFORM=macos ;;
    Linux)                     PLATFORM=linux ;;
    MINGW*|MSYS*|CYGWIN*)      PLATFORM=windows-bash ;;
    *)                         PLATFORM=unknown ;;
esac
echo "==> Platform: $PLATFORM"
echo

if [ "$PLATFORM" = "windows-bash" ]; then
    echo "${C_YELLOW}Detected Git Bash / MSYS on Windows.${C_RESET}"
    echo "For best results run install.ps1 from PowerShell instead."
    echo "  powershell -ExecutionPolicy Bypass -File install/install.ps1"
    echo
fi

# Prereq scan
echo "==> Checking prerequisites"
need_ok=true
has() { command -v "$1" >/dev/null 2>&1; }

check_required() {
    local name="$1"
    if has "$name"; then
        printf '    %s[+] %s%s\n' "$C_GREEN" "$name" "$C_RESET"
    else
        printf '    %s[X] %s%s\n' "$C_RED" "$name" "$C_RESET"
        need_ok=false
    fi
}
check_optional() {
    local name="$1"
    if has "$name"; then
        printf '    %s[+] %s%s\n' "$C_GREEN" "$name" "$C_RESET"
    else
        printf '    %s[o] %s (optional)%s\n' "$C_YELLOW" "$name" "$C_RESET"
    fi
}

for t in python3 node npm git; do check_required "$t"; done
for t in uv rg ffmpeg browser-harness; do check_optional "$t"; done

if ! $need_ok; then
    echo
    echo "${C_RED}Missing required tools.${C_RESET}"
    case "$PLATFORM" in
        macos)
            echo "  brew install python node git uv ripgrep ffmpeg"
            ;;
        linux)
            echo "  sudo apt install python3 python3-pip nodejs npm git ripgrep ffmpeg"
            echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
            ;;
    esac
    exit 2
fi
echo

# Bootstrap
echo "==> Creating $BRAVO_HOME tree + profiles + env template"
if [ "$DRY_RUN" -eq 1 ]; then
    echo "    ${C_DIM}(dry run — skipping)${C_RESET}"
else
    python3 "$REPO_ROOT/install/bootstrap.py" --home "$BRAVO_HOME" --repo "$REPO_ROOT"
fi
echo

# Verify shim
echo "==> Verifying bravo shim at $BIN_DIR/bravo"
if [ "$DRY_RUN" -eq 1 ]; then
    echo "    ${C_DIM}(dry run)${C_RESET}"
elif [ -x "$BIN_DIR/bravo" ]; then
    echo "    ${C_GREEN}present + executable${C_RESET}"
else
    echo "    ${C_RED}missing or not executable${C_RESET}"
    exit 3
fi
echo

# PATH hint
if [ "$SKIP_PATH" -eq 0 ]; then
    shell_rc=""
    case "${SHELL:-}" in
        */zsh)  shell_rc="$HOME/.zshrc" ;;
        */bash) shell_rc="$HOME/.bashrc" ;;
    esac
    export_line="export PATH=\"$BIN_DIR:\$PATH\""
    echo "==> Add to PATH"
    if [ -n "$shell_rc" ] && [ -f "$shell_rc" ] && grep -Fq "$BIN_DIR" "$shell_rc"; then
        echo "    ${C_GREEN}already in $shell_rc${C_RESET}"
    else
        echo "    Add this line to your shell profile:"
        echo
        printf '      %s%s%s\n' "$C_CYAN" "$export_line" "$C_RESET"
        echo
        if [ -n "$shell_rc" ] && [ "$DRY_RUN" -eq 0 ]; then
            if [ -f "$shell_rc" ]; then
                echo "    Detected $shell_rc. Append automatically? [y/N] "
                read -r answer || answer=""
                if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
                    printf '\n# Bravo launcher\n%s\n' "$export_line" >> "$shell_rc"
                    echo "    ${C_GREEN}appended to $shell_rc${C_RESET}"
                fi
            fi
        fi
    fi
    echo
fi

# Smoke tests
echo "==> Running self_audit"
if [ "$DRY_RUN" -eq 0 ]; then
    python3 "$REPO_ROOT/scripts/self_audit.py" 2>&1 | tail -5 || true
fi
echo

# Done
printf '%s=================================================%s\n' "$C_CYAN" "$C_RESET"
printf '%s Bravo installed.%s\n' "$C_CYAN" "$C_RESET"
printf '%s=================================================%s\n' "$C_CYAN" "$C_RESET"
echo
echo "  Next:"
echo "    1. source your shell profile (or open a new terminal)"
printf '    2. %sbravo doctor%s\n' "$C_GREEN" "$C_RESET"
printf '    3. %sbravo setup%s\n' "$C_GREEN" "$C_RESET"
printf '    4. %sbravo agent list%s\n' "$C_GREEN" "$C_RESET"
echo
