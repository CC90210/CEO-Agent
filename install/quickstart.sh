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

# Run a privileged command as an argv array. No shell interpretation of
# package-name strings — eliminates the `sudo bash -c "$cmd"` injection
# pattern flagged in the 2026-04-25 security review. Each caller invokes
# this once per package-manager command (apt-get update is a separate
# call from apt-get install).
run_pkg_install_argv() {
    if [ "$(id -u)" = "0" ]; then
        "$@"
        return $?
    fi
    if command -v sudo >/dev/null 2>&1; then
        sudo -v || return 1
        sudo "$@"
        return $?
    fi
    fail "no sudo available — cannot install system packages"
    info "as root: $*"
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

    # Expand the multi-package strings ("python3 python3-pip python3-venv")
    # into the flat argv list that argv-mode sudo expects.
    local flat=()
    for p in "${pkgs[@]}"; do
        # shellcheck disable=SC2206
        flat+=( $p )
    done

    case "$os" in
        mac)
            ensure_homebrew || return 1
            echo "==> Installing via Homebrew: ${flat[*]}"
            brew update --quiet || true
            brew install "${flat[@]}" || return 1
            ;;
        linux-apt)
            echo "==> Installing via apt-get: ${flat[*]}"
            info "(this step needs sudo for apt-get)"
            run_pkg_install_argv apt-get update -y || return 1
            run_pkg_install_argv apt-get install -y "${flat[@]}" || return 1
            ;;
        linux-dnf)
            echo "==> Installing via dnf: ${flat[*]}"
            info "(this step needs sudo for dnf)"
            run_pkg_install_argv dnf install -y "${flat[@]}" || return 1
            ;;
        linux-pacman)
            echo "==> Installing via pacman: ${flat[*]}"
            info "(this step needs sudo for pacman)"
            # -Syu would auto-upgrade the entire system, which surprises users.
            # -Sy + targeted install is what most distro guides recommend.
            run_pkg_install_argv pacman -Sy --noconfirm "${flat[@]}" || return 1
            ;;
        linux-zypper)
            echo "==> Installing via zypper: ${flat[*]}"
            info "(this step needs sudo for zypper)"
            run_pkg_install_argv zypper install -y "${flat[@]}" || return 1
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
# Special handling for python3: on a fresh macOS the only python3 on PATH is
# the Apple stub at /usr/bin/python3, which prompts to install Xcode CLT
# the first time you invoke it (a system-modal popup that blocks scripts).
# We treat that as missing so brew installs python@3.12 cleanly. We also
# require Python 3.10+ so older brew/system pythons don't squeak past.
check_python3() {
    command -v python3 >/dev/null 2>&1 || return 1
    if [ "$(uname -s 2>/dev/null)" = "Darwin" ] \
       && [ "$(command -v python3)" = "/usr/bin/python3" ]; then
        return 1   # Apple stub — force a real install via brew
    fi
    # Resolved path is safe to invoke; check version.
    local v
    v="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)" \
        || return 1
    case "$v" in
        3.10|3.11|3.12|3.13|3.14|3.15) return 0 ;;
        *) return 1 ;;
    esac
}

echo "==> Checking prerequisites"
missing=()
for tool in python3 git node npm; do
    if [ "$tool" = "python3" ]; then
        if check_python3; then ok "python3 (>= 3.10)"; else fail "python3"; missing+=("python3"); fi
        continue
    fi
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
            # Mac brew installs python@3.12 to /opt/homebrew/bin (Apple
            # Silicon) or /usr/local/bin (Intel). Refresh the shell hash
            # so command -v sees the new binaries on the PATH that
            # ensure_homebrew just sourced.
            hash -r 2>/dev/null || true
            still_missing=()
            for tool in "${missing[@]}"; do
                if [ "$tool" = "python3" ]; then
                    if check_python3; then ok "python3 (>= 3.10)"; else fail "python3"; still_missing+=("python3"); fi
                    continue
                fi
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

# ---- Clone or update (atomic) ----------------------------------------------
# Codex P2: a previous failed clone leaves a non-empty $REPO_DIR without
# a .git/. Re-runs then crash with "destination path already exists".
# Solution: clone into a sibling temp dir, swap it into place atomically.
if [ -d "$REPO_DIR/.git" ]; then
    echo "==> Updating existing repo at $REPO_DIR"
    git -C "$REPO_DIR" pull --ff-only
elif [ -d "$REPO_DIR" ] && [ -z "$(ls -A "$REPO_DIR" 2>/dev/null || true)" ]; then
    echo "==> Cloning $REPO_URL into $REPO_DIR"
    rmdir "$REPO_DIR" 2>/dev/null || true
    git clone --depth 10 "$REPO_URL" "$REPO_DIR"
else
    if [ -e "$REPO_DIR" ]; then
        warn "$REPO_DIR exists but is not a clean git clone — repairing via atomic swap."
        tmp_clone="$(mktemp -d "${REPO_DIR}.partial.XXXXXX" 2>/dev/null \
                     || echo "${REPO_DIR}.partial.$$")"
        rm -rf "$tmp_clone"
        git clone --depth 10 "$REPO_URL" "$tmp_clone"
        backup="${REPO_DIR}.broken.$(date +%s)"
        mv "$REPO_DIR" "$backup"
        mv "$tmp_clone" "$REPO_DIR"
        info "old contents preserved at $backup (delete when ready)"
    else
        echo "==> Cloning $REPO_URL into $REPO_DIR"
        git clone --depth 10 "$REPO_URL" "$REPO_DIR"
    fi
fi
echo

# ---- Lightweight local prep ------------------------------------------------
echo "==> Preparing local Agent Factory"
# Use mktemp for an unpredictable per-run path. Avoids the symlink TOCTOU
# in /tmp (security review 2026-04-25, MEDIUM-3).
prep_log="$(mktemp "${TMPDIR:-/tmp}/oasis-prep.XXXXXXXX.log" 2>/dev/null \
            || echo "${TMPDIR:-/tmp}/oasis-prep.$$.$(date +%s).log")"
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

# Resolve python3 to its absolute path BEFORE prepending ~/.bravo/bin to
# PATH, so a malicious shim placed there at any point cannot intercept us
# (security review 2026-04-25, MEDIUM-5). Re-resolves a fresh path on
# Mac when brew just installed Python 3.12 to /opt/homebrew.
PY3="$(command -v python3 || true)"
if [ -z "$PY3" ]; then
    fail "python3 not found after install — open a new terminal and re-run"
    exit 1
fi
export PATH="$HOME/.bravo/bin:$PATH"
"$PY3" "$REPO_DIR/bravo_cli/main.py" setup

echo
printf '%s[+] Done.%s Next shells: add %s$HOME/.bravo/bin%s to PATH.\n' \
    "$C_GREEN" "$C_RESET" "$C_CYAN" "$C_RESET"
printf '   Try: %sbravo doctor%s   |   %sbravo status%s\n' \
    "$C_CYAN" "$C_RESET" "$C_CYAN" "$C_RESET"
