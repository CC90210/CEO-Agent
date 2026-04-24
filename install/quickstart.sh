#!/usr/bin/env bash
# OASIS AI setup — one-line installer for macOS / Linux / WSL.
#
# Usage (from a fresh shell):
#   curl -sSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install/quickstart.sh | bash
#
# What this does:
#   1. Checks prerequisites (python3, git, node)
#   2. Clones CC90210/CEO-Agent into ~/bravo-repo  (or updates if it exists)
#   3. Prepares the local Agent Factory launcher (idempotent, no heavy deps)
#   4. Launches `bravo setup`  (the interactive wizard)
#
# It NEVER touches your existing .env files, and NEVER asks for sudo.

set -euo pipefail

REPO_URL="https://github.com/CC90210/CEO-Agent.git"
REPO_DIR="${BRAVO_REPO_DIR:-$HOME/bravo-repo}"

# Colors (gracefully degrade on dumb terminals)
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_CYAN=$'\033[1;36m'; C_GREEN=$'\033[1;32m'; C_RED=$'\033[1;31m'
    C_DIM=$'\033[2m';     C_YELLOW=$'\033[1;33m'; C_RESET=$'\033[0m'
else
    C_CYAN=''; C_GREEN=''; C_RED=''; C_DIM=''; C_YELLOW=''; C_RESET=''
fi

printf '%s\n' "$C_CYAN"
cat <<'BANNER'

╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║    ██████╗  █████╗ ███████╗██╗███████╗    █████╗ ██╗               ║
║   ██╔═══██╗██╔══██╗██╔════╝██║██╔════╝   ██╔══██╗██║               ║
║   ██║   ██║███████║███████╗██║███████╗   ███████║██║               ║
║   ██║   ██║██╔══██║╚════██║██║╚════██║   ██╔══██║██║               ║
║   ╚██████╔╝██║  ██║███████║██║███████║   ██║  ██║██║               ║
║    ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝╚══════╝   ╚═╝  ╚═╝╚═╝               ║
║                                                                    ║
║    Agent Factory · Business-in-a-Box                               ║
║    oasisai.work                                                    ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝
BANNER
printf '%s' "$C_RESET"
echo "  OASIS AI setup - choose your agent, then configure it"
printf '  %sRepo:%s %s\n' "$C_DIM" "$C_RESET" "$REPO_URL"
printf '  %sDest:%s %s\n\n' "$C_DIM" "$C_RESET" "$REPO_DIR"

# --- Prereqs (kept in sync with install.sh + bootstrap.py) ---
echo "==> Checking prerequisites"
missing=()
for tool in python3 git node npm; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        missing+=("$tool")
        printf '    %s[X] %s%s\n' "$C_RED" "$tool" "$C_RESET"
    else
        printf '    %s[+] %s%s\n' "$C_GREEN" "$tool" "$C_RESET"
    fi
done

if [ ${#missing[@]} -gt 0 ]; then
    echo
    printf '%sMissing: %s%s\n' "$C_RED" "${missing[*]}" "$C_RESET"
    uname_s="$(uname -s 2>/dev/null || echo unknown)"
    case "$uname_s" in
        Darwin) echo "  brew install python node git" ;;
        Linux)  echo "  sudo apt install python3 python3-pip nodejs npm git  # Debian/Ubuntu"
                echo "  sudo pacman -S  python nodejs npm git                # Arch"
                ;;
    esac
    exit 2
fi
echo

# --- Clone or update ---
if [ -d "$REPO_DIR/.git" ]; then
    echo "==> Updating existing repo at $REPO_DIR"
    git -C "$REPO_DIR" pull --ff-only
else
    echo "==> Cloning $REPO_URL into $REPO_DIR"
    git clone --depth 10 "$REPO_URL" "$REPO_DIR"
fi
echo

# --- Lightweight local prep ---
echo "==> Preparing local Agent Factory"
prep_log="${TMPDIR:-/tmp}/oasis-agent-factory-install.log"
if ! bash "$REPO_DIR/install/install.sh" --skip-path --skip-deps --skip-smoke >"$prep_log" 2>&1; then
    printf '    %s[X] prep failed%s\n' "$C_RED" "$C_RESET"
    echo "    Log: $prep_log"
    tail -40 "$prep_log" || true
    exit 1
fi
printf '    %s[+] ready%s\n' "$C_GREEN" "$C_RESET"
echo

# --- Launch wizard ---
printf '%s=================================================%s\n' "$C_CYAN" "$C_RESET"
printf '%s Launching OASIS AI setup...%s\n' "$C_CYAN" "$C_RESET"
printf '%s=================================================%s\n\n' "$C_CYAN" "$C_RESET"

export PATH="$HOME/.bravo/bin:$PATH"
python3 "$REPO_DIR/bravo_cli/main.py" setup

echo
printf '%s[+] Done.%s Next shells: add %s$HOME/.bravo/bin%s to PATH.\n' \
    "$C_GREEN" "$C_RESET" "$C_CYAN" "$C_RESET"
printf '   Try: %sbravo doctor%s   |   %sbravo status%s\n' \
    "$C_CYAN" "$C_RESET" "$C_CYAN" "$C_RESET"
