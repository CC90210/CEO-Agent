#!/usr/bin/env bash
# OASIS AI setup — one-line installer for macOS / Linux / WSL.
#
# Usage (from a fresh shell):
#   curl -sSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install/quickstart.sh | bash
#
# What this does:
#   1. Detects missing prerequisites (python3, git, node, npm).
#   2. AUTO-INSTALLS them via the platform's standard package manager
#      (Homebrew on macOS; apt / dnf / pacman on Linux), after one
#      consent prompt. Override with --no-auto-install (or
#      OASIS_NO_AUTO_INSTALL=1) to keep the old "tell me what's missing"
#      behavior. Override with --auto-install (or OASIS_AUTO_INSTALL=1)
#      to skip the consent prompt entirely (CI / scripted installs).
#   3. Clones CC90210/CEO-Agent into ~/bravo-repo (or updates if it exists).
#   4. Prepares the local Agent Factory launcher (idempotent).
#   5. Launches `bravo setup` (the interactive wizard).
#
# It NEVER touches your existing .env files. Sudo is only invoked when a
# package install genuinely needs it (Linux apt/dnf/pacman); macOS brew
# install runs as the current user.

set -euo pipefail

REPO_URL="https://github.com/CC90210/CEO-Agent.git"
REPO_DIR="${BRAVO_REPO_DIR:-$HOME/bravo-repo}"

# ---- Args / env -------------------------------------------------------------
AUTO_INSTALL_MODE="prompt"   # prompt | yes | no
for arg in "$@"; do
    case "$arg" in
        --auto-install)    AUTO_INSTALL_MODE="yes" ;;
        --no-auto-install) AUTO_INSTALL_MODE="no" ;;
    esac
done
case "${OASIS_AUTO_INSTALL:-}"    in 1|yes|true) AUTO_INSTALL_MODE="yes" ;; esac
case "${OASIS_NO_AUTO_INSTALL:-}" in 1|yes|true) AUTO_INSTALL_MODE="no"  ;; esac

# ---- Colors ----------------------------------------------------------------
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

# ---- Helpers ---------------------------------------------------------------
ok()    { printf '    %s[+] %s%s\n' "$C_GREEN"  "$1" "$C_RESET"; }
fail()  { printf '    %s[X] %s%s\n' "$C_RED"    "$1" "$C_RESET"; }
warn()  { printf '    %s[!] %s%s\n' "$C_YELLOW" "$1" "$C_RESET"; }
info()  { printf '    %s%s%s\n'      "$C_DIM"   "$1" "$C_RESET"; }

# Stdin may be the curl pipe (non-tty) when run as
# `curl ... | bash`. Read consent from /dev/tty so the user can answer.
ask_yes() {
    local question="$1" default="${2:-Y}"
    if [ "$AUTO_INSTALL_MODE" = "yes" ]; then return 0; fi
    if [ "$AUTO_INSTALL_MODE" = "no"  ]; then return 1; fi
    local hint="[Y/n]"; [ "$default" = "N" ] && hint="[y/N]"
    local reply=""
    if [ -r /dev/tty ]; then
        printf '%s %s ' "$question" "$hint" >/dev/tty
        IFS= read -r reply </dev/tty || reply=""
    else
        # No TTY (CI piping, no consent possible) — fall back to default.
        reply=""
    fi
    reply="${reply:-$default}"
    case "$reply" in [Yy]*) return 0 ;; *) return 1 ;; esac
}

# Detect OS family + Linux distro for the right package-manager call.
detect_os() {
    local uname_s="$(uname -s 2>/dev/null || echo unknown)"
    case "$uname_s" in
        Darwin) echo "mac" ;;
        Linux)
            if   command -v apt-get >/dev/null 2>&1; then echo "linux-apt"
            elif command -v dnf     >/dev/null 2>&1; then echo "linux-dnf"
            elif command -v pacman  >/dev/null 2>&1; then echo "linux-pacman"
            elif command -v zypper  >/dev/null 2>&1; then echo "linux-zypper"
            else echo "linux-unknown"; fi
            ;;
        *) echo "unknown" ;;
    esac
}

# Map our generic prereq names → platform-specific package names.
pkg_name() {
    local tool="$1" os="$2"
    case "$os:$tool" in
        mac:python3)  echo "python@3.12" ;;
        mac:node|mac:npm) echo "node" ;;
        mac:git)      echo "git" ;;
        linux-apt:python3) echo "python3 python3-pip python3-venv" ;;
        linux-apt:node|linux-apt:npm) echo "nodejs npm" ;;
        linux-apt:git)     echo "git" ;;
        linux-dnf:python3) echo "python3 python3-pip" ;;
        linux-dnf:node|linux-dnf:npm) echo "nodejs npm" ;;
        linux-dnf:git)     echo "git" ;;
        linux-pacman:python3) echo "python python-pip" ;;
        linux-pacman:node|linux-pacman:npm) echo "nodejs npm" ;;
        linux-pacman:git)     echo "git" ;;
        linux-zypper:python3) echo "python3 python3-pip" ;;
        linux-zypper:node|linux-zypper:npm) echo "nodejs npm" ;;
        linux-zypper:git)     echo "git" ;;
        *) echo "$tool" ;;
    esac
}

ensure_homebrew() {
    if command -v brew >/dev/null 2>&1; then return 0; fi
    warn "Homebrew not found — installing it now (the official one-liner)."
    info "https://brew.sh"
    NONINTERACTIVE=1 /bin/bash -c \
        "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
        || return 1
    # New brew installs may not be on PATH for this shell. Try the standard
    # locations so the upcoming `brew install` works without re-login.
    for shellenv in \
        /opt/homebrew/bin/brew \
        /usr/local/bin/brew \
        "$HOME/.linuxbrew/bin/brew" \
        /home/linuxbrew/.linuxbrew/bin/brew; do
        if [ -x "$shellenv" ]; then
            eval "$($shellenv shellenv)"
            break
        fi
    done
    command -v brew >/dev/null 2>&1
}

# Run a command, with sudo if needed and available. Returns 1 if neither
# direct nor sudo execution is possible.
run_pkg_install() {
    local cmd="$*"
    if [ "$(id -u)" = "0" ]; then
        eval "$cmd"
        return $?
    fi
    if command -v sudo >/dev/null 2>&1; then
        info "(this step needs sudo for the package manager)"
        sudo -v || return 1
        sudo bash -c "$cmd"
        return $?
    fi
    fail "no sudo available — cannot install system packages"
    info "as root: $cmd"
    return 1
}

install_missing() {
    local os="$1"; shift
    local tools=("$@")

    # Build the package list once (some tools map to multi-package
    # strings, e.g. 'python3 python3-pip python3-venv' on apt).
    local pkgs=()
    for t in "${tools[@]}"; do
        # shellcheck disable=SC2206
        pkgs+=( $(pkg_name "$t" "$os") )
    done
    # Deduplicate (node + npm both map to "nodejs npm" on linux).
    local uniq=() seen
    for p in "${pkgs[@]}"; do
        seen=0
        for u in "${uniq[@]}"; do [ "$u" = "$p" ] && seen=1 && break; done
        [ "$seen" = "0" ] && uniq+=("$p")
    done
    pkgs=("${uniq[@]}")

    case "$os" in
        mac)
            ensure_homebrew || return 1
            echo "==> Installing via Homebrew: ${pkgs[*]}"
            brew update --quiet || true
            brew install "${pkgs[@]}" || return 1
            ;;
        linux-apt)
            echo "==> Installing via apt-get: ${pkgs[*]}"
            run_pkg_install "apt-get update -y && apt-get install -y ${pkgs[*]}" || return 1
            ;;
        linux-dnf)
            echo "==> Installing via dnf: ${pkgs[*]}"
            run_pkg_install "dnf install -y ${pkgs[*]}" || return 1
            ;;
        linux-pacman)
            echo "==> Installing via pacman: ${pkgs[*]}"
            run_pkg_install "pacman -Sy --noconfirm ${pkgs[*]}" || return 1
            ;;
        linux-zypper)
            echo "==> Installing via zypper: ${pkgs[*]}"
            run_pkg_install "zypper install -y ${pkgs[*]}" || return 1
            ;;
        *)
            fail "no supported package manager detected on this system"
            return 1
            ;;
    esac
    return 0
}

# Print the manual-install commands for the user when auto-install is
# refused or unsupported.
print_manual_hint() {
    local os="$1"; shift
    local tools=("$@")
    echo
    case "$os" in
        mac)
            echo "  brew install $(for t in "${tools[@]}"; do pkg_name "$t" "$os"; done | sort -u | xargs)"
            ;;
        linux-apt)
            echo "  sudo apt-get update && sudo apt-get install -y \\"
            echo "    $(for t in "${tools[@]}"; do pkg_name "$t" "$os"; done | sort -u | xargs)"
            ;;
        linux-dnf)
            echo "  sudo dnf install -y $(for t in "${tools[@]}"; do pkg_name "$t" "$os"; done | sort -u | xargs)"
            ;;
        linux-pacman)
            echo "  sudo pacman -Sy --noconfirm $(for t in "${tools[@]}"; do pkg_name "$t" "$os"; done | sort -u | xargs)"
            ;;
        linux-zypper)
            echo "  sudo zypper install -y $(for t in "${tools[@]}"; do pkg_name "$t" "$os"; done | sort -u | xargs)"
            ;;
        *)
            echo "  (no auto-detected package manager — install python3, git, node, npm manually)"
            ;;
    esac
    echo
}

# ---- Prereqs ---------------------------------------------------------------
echo "==> Checking prerequisites"
missing=()
for tool in python3 git node npm; do
    if command -v "$tool" >/dev/null 2>&1; then
        ok "$tool"
    else
        fail "$tool"
        missing+=("$tool")
    fi
done

if [ ${#missing[@]} -gt 0 ]; then
    echo
    OS="$(detect_os)"
    printf '%sMissing: %s%s\n' "$C_YELLOW" "${missing[*]}" "$C_RESET"
    info "platform: $OS"
    echo

    if [ "$OS" = "unknown" ] || [ "$OS" = "linux-unknown" ]; then
        printf '%sNo auto-installer for this platform.%s Install manually:\n' \
            "$C_YELLOW" "$C_RESET"
        print_manual_hint "$OS" "${missing[@]}"
        exit 2
    fi

    # Consent: one prompt, plain English, exact list. Then go.
    pkg_preview="$(for t in "${missing[@]}"; do pkg_name "$t" "$OS"; done | tr '\n' ' ' | xargs)"
    printf '%sReady to install:%s %s\n' "$C_CYAN" "$C_RESET" "$pkg_preview"
    case "$OS" in
        mac)         info "via Homebrew (current user — no sudo)" ;;
        linux-apt|linux-dnf|linux-pacman|linux-zypper)
                     info "via your system package manager (will need sudo)" ;;
    esac
    if ask_yes "Continue?" "Y"; then
        if install_missing "$OS" "${missing[@]}"; then
            echo
            echo "==> Re-checking prerequisites after install"
            still_missing=()
            for tool in "${missing[@]}"; do
                if command -v "$tool" >/dev/null 2>&1; then
                    ok "$tool"
                else
                    fail "$tool"
                    still_missing+=("$tool")
                fi
            done
            if [ ${#still_missing[@]} -gt 0 ]; then
                echo
                printf '%sStill missing after install: %s%s\n' \
                    "$C_RED" "${still_missing[*]}" "$C_RESET"
                info "your shell may not have picked up new PATH entries —"
                info "open a new terminal and re-run this installer."
                exit 1
            fi
        else
            echo
            printf '%sAuto-install failed.%s Install manually and retry:\n' \
                "$C_RED" "$C_RESET"
            print_manual_hint "$OS" "${missing[@]}"
            exit 1
        fi
    else
        echo
        printf '%sSkipped auto-install.%s Install manually and re-run:\n' \
            "$C_YELLOW" "$C_RESET"
        print_manual_hint "$OS" "${missing[@]}"
        exit 2
    fi
fi
echo

# ---- Clone or update -------------------------------------------------------
if [ -d "$REPO_DIR/.git" ]; then
    echo "==> Updating existing repo at $REPO_DIR"
    git -C "$REPO_DIR" pull --ff-only
else
    echo "==> Cloning $REPO_URL into $REPO_DIR"
    git clone --depth 10 "$REPO_URL" "$REPO_DIR"
fi
echo

# ---- Lightweight local prep ------------------------------------------------
echo "==> Preparing local Agent Factory"
prep_log="${TMPDIR:-/tmp}/oasis-agent-factory-install.log"
if ! bash "$REPO_DIR/install/install.sh" --skip-path --skip-deps --skip-smoke >"$prep_log" 2>&1; then
    fail "prep failed"
    echo "    Log: $prep_log"
    tail -40 "$prep_log" || true
    exit 1
fi
ok "ready"
echo

# ---- Launch wizard ---------------------------------------------------------
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
