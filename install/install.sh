#!/usr/bin/env bash
# Bravo one-command installer for macOS / Linux / WSL.
# Idempotent. Safe to re-run. Never mutates .env.agents.
#
# Usage:
#   bash install/install.sh
#   bash install/install.sh --skip-path
#   bash install/install.sh --dry-run
#   bash install/install.sh --skip-deps --skip-smoke

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BRAVO_HOME="${BRAVO_HOME:-$HOME/.bravo}"
BIN_DIR="$BRAVO_HOME/bin"

DRY_RUN=0
SKIP_PATH=0
SKIP_DEPS=0
SKIP_SMOKE=0
for arg in "$@"; do
    case "$arg" in
        --dry-run)    DRY_RUN=1 ;;
        --skip-path)  SKIP_PATH=1 ;;
        --skip-deps)  SKIP_DEPS=1 ;;
        --skip-smoke) SKIP_SMOKE=1 ;;
        *)            echo "unknown arg: $arg"; exit 1 ;;
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

# python3 needs the same Apple-stub guard + version check as quickstart.sh.
# Without this, `command -v python3` on a fresh Mac returns the
# /usr/bin/python3 Xcode-CLT trampoline, install.sh marks it green, then
# bootstrap.py hits the modal Xcode-install dialog and hangs.
has_python3_310_plus() {
    has python3 || return 1
    if [ "$(uname -s 2>/dev/null)" = "Darwin" ] \
       && [ "$(command -v python3)" = "/usr/bin/python3" ]; then
        return 1
    fi
    # Same probe form as quickstart.sh + the PowerShell Resolve-Python310Plus.
    # No embedded double-quotes, no % formatting — survives any shell's
    # argv handling identically.
    local v
    v="$(python3 -c 'import sys; print(sys.version_info.major, sys.version_info.minor, sep=".")' 2>/dev/null)" \
        || return 1
    case "$v" in
        3.10|3.11|3.12|3.13|3.14|3.15) return 0 ;;
        *) return 1 ;;
    esac
}

check_required() {
    local name="$1"
    local label="$name"
    local ok_check
    if [ "$name" = "python3" ]; then
        ok_check="has_python3_310_plus"
        label="python3 (>= 3.10)"
    else
        ok_check="has $name"
    fi
    if eval "$ok_check"; then
        printf '    %s[+] %s%s\n' "$C_GREEN" "$label" "$C_RESET"
    else
        printf '    %s[X] %s%s\n' "$C_RED" "$label" "$C_RESET"
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

# Python + Node dependencies via the shared bootstrap helper.
# Same code path as install.ps1 — single source of truth in bootstrap.py.
if [ "$SKIP_DEPS" -eq 0 ]; then
    echo "==> Installing Python + Node packages (pip + npm, both idempotent; first run can take 2-5 min)"
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "    ${C_DIM}(dry run — skipping)${C_RESET}"
    else
        python3 "$REPO_ROOT/install/bootstrap.py" --repo "$REPO_ROOT" --install-deps \
            || echo "    ${C_YELLOW}WARN: some packages failed to install${C_RESET}"
    fi
    echo
fi

# OASIS Command Center signup
if [ "${SKIP_SIGNUP:-0}" -eq 0 ] && [ -t 0 ]; then
    echo "==> OASIS AI Agent Command Center signup"
    echo "    Create your operator account at https://agent-dashboard-cc90210.vercel.app"
    echo "    (skip with SKIP_SIGNUP=1 to do this later via the dashboard)"
    echo
    read -r -p "    Email address: " CC_EMAIL
    read -r -p "    Full name: " CC_NAME
    read -r -p "    Brand / company name [OASIS AI]: " CC_BRAND
    CC_BRAND="${CC_BRAND:-OASIS AI}"
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "    ${C_DIM}(dry run — skipping)${C_RESET}"
    elif [ -n "$CC_EMAIL" ] && [ -n "$CC_NAME" ]; then
        echo "    Sign in option:"
        echo "      [1] Email + password (we'll send an invite email)"
        echo "      [2] Continue with Google (no email; sign in via Google on first visit)"
        read -r -p "    Choose [1/2]: " CC_AUTH_CHOICE
        OAUTH_FLAG=""
        if [ "$CC_AUTH_CHOICE" = "2" ]; then
            OAUTH_FLAG="--prefer-oauth"
        fi
        python3 "$REPO_ROOT/install/bootstrap.py" \
            --create-command-center-account \
            --email "$CC_EMAIL" \
            --full-name "$CC_NAME" \
            --brand "$CC_BRAND" \
            $OAUTH_FLAG \
            || echo "    ${C_YELLOW}WARN: signup failed — finish at https://agent-dashboard-cc90210.vercel.app/signup${C_RESET}"
    else
        echo "    ${C_DIM}skipped (email or name empty)${C_RESET}"
    fi
    echo
fi

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
if [ "$SKIP_SMOKE" -eq 0 ]; then
    echo "==> Running self_audit"
    if [ "$DRY_RUN" -eq 0 ]; then
        # Surface the audit's exit code instead of silently swallowing it.
        # We don't FAIL the install on a non-zero (drift can be cosmetic
        # and shouldn't block a fresh client setup), but the user must
        # not get a false "all green" signal — they get a clear warning
        # pointing at `bravo doctor` for the detail.
        # set +e in this scope so we don't trip set -e (install.sh is
        # not strict-set today, but staying defensive).
        set +e
        python3 "$REPO_ROOT/scripts/core/self_audit.py" 2>&1 | tail -5
        audit_rc="${PIPESTATUS[0]}"
        set -e
        if [ "$audit_rc" != "0" ]; then
            printf '    %s[!] self_audit exit %s — install still complete; run %sbravo doctor%s for details.%s\n' \
                "$C_YELLOW" "$audit_rc" "$C_CYAN" "$C_YELLOW" "$C_RESET"
        fi
    fi
    echo
fi

# Done
printf '%s=================================================%s\n' "$C_CYAN" "$C_RESET"
printf '%s OASIS AI Agent Factory is ready.%s\n' "$C_CYAN" "$C_RESET"
printf '%s=================================================%s\n' "$C_CYAN" "$C_RESET"
echo
echo "  Next:"
echo "    1. source your shell profile (or open a new terminal)"
printf '    2. %sbravo doctor%s\n' "$C_GREEN" "$C_RESET"
printf '    3. %sbravo setup%s\n' "$C_GREEN" "$C_RESET"
printf '    4. %sbravo agent list%s\n' "$C_GREEN" "$C_RESET"
echo
