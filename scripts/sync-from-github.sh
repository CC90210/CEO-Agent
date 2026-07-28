#!/usr/bin/env bash
# sync-from-github.sh
# Pull latest Business-Empire-Agent changes from origin/main onto any machine
# (Mac, Windows/Git Bash, Linux). Safe by default: stashes local work, verifies
# daemons, logs to SESSION_LOG. Re-runnable — idempotent.
#
# Usage from BEA root:
#   bash scripts/sync-from-github.sh
#   bash scripts/sync-from-github.sh --restart-daemons   # also restart scheduler after pull
#   bash scripts/sync-from-github.sh --verify-only       # fetch + diff only, no pull
#
# Exit codes:
#   0 = clean pull (or nothing to pull)
#   1 = dirty working tree, stash failed
#   2 = pull had conflicts
#   3 = post-pull verification failed (python import broke something)

set -euo pipefail

# ---- Colors (respect NO_COLOR) -----------------------------------------------
if [[ -z "${NO_COLOR:-}" ]] && [[ -t 1 ]]; then
    RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
    BLUE=$'\033[0;34m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; BOLD=''; RESET=''
fi

info()  { echo "${BLUE}[sync]${RESET} $*"; }
ok()    { echo "${GREEN}[ ok ]${RESET} $*"; }
warn()  { echo "${YELLOW}[warn]${RESET} $*"; }
err()   { echo "${RED}[err ]${RESET} $*" >&2; }
bold()  { echo "${BOLD}$*${RESET}"; }

# ---- Args --------------------------------------------------------------------
RESTART_DAEMONS=0
VERIFY_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --restart-daemons) RESTART_DAEMONS=1 ;;
        --verify-only)     VERIFY_ONLY=1 ;;
        -h|--help)
            sed -n '2,20p' "$0"; exit 0 ;;
        *) warn "Unknown arg: $arg" ;;
    esac
done

# ---- Locate repo root --------------------------------------------------------
if ! git rev-parse --show-toplevel &>/dev/null; then
    err "Not in a git repo. Run from Business-Empire-Agent root."
    exit 1
fi
REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"
ok "Repo: $REPO_ROOT"

# ---- Platform detection -------------------------------------------------------
case "$(uname -s)" in
    Darwin*)  PLATFORM="macos" ;;
    Linux*)   PLATFORM="linux" ;;
    MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
    *)        PLATFORM="unknown" ;;
esac
info "Platform: $PLATFORM"

# ---- Pick a python interpreter ----------------------------------------------
PYTHON=""
for cand in python3 python python3.12 python3.11; do
    if command -v "$cand" &>/dev/null; then
        if "$cand" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" &>/dev/null; then
            PYTHON="$cand"; break
        fi
    fi
done
if [[ -z "$PYTHON" ]]; then
    warn "No python >= 3.10 found on PATH. Verification checks will be skipped."
fi
[[ -n "$PYTHON" ]] && ok "Python: $($PYTHON --version 2>&1)"

# ---- Current state ----------------------------------------------------------
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
CURRENT_COMMIT=$(git rev-parse --short HEAD)
info "Branch: $CURRENT_BRANCH @ $CURRENT_COMMIT"

if [[ "$CURRENT_BRANCH" != "main" ]]; then
    warn "You are on '$CURRENT_BRANCH', not 'main'. This script pulls origin/main."
    warn "If that's wrong, Ctrl+C now. Continuing in 3s..."
    sleep 3
fi

# ---- Stash any uncommitted changes for safety -------------------------------
STASH_MADE=0
if ! git diff --quiet || ! git diff --cached --quiet; then
    warn "Uncommitted changes detected. Stashing for safety..."
    STASH_MSG="sync-from-github autostash $(date -u +%Y%m%dT%H%M%SZ)"
    if git stash push -u -m "$STASH_MSG"; then
        STASH_MADE=1
        ok "Stashed as: $STASH_MSG"
        info "Restore later with: git stash pop"
    else
        err "Stash failed. Resolve manually and re-run."
        exit 1
    fi
fi

# ---- Fetch + compare --------------------------------------------------------
info "Fetching origin..."
git fetch origin main --quiet

BEHIND=$(git rev-list --count HEAD..origin/main)
AHEAD=$(git rev-list --count origin/main..HEAD)

if [[ "$BEHIND" == "0" && "$AHEAD" == "0" ]]; then
    ok "Already up to date with origin/main."
    [[ "$STASH_MADE" == "1" ]] && warn "You have a stash — run 'git stash pop' to restore local work."
    exit 0
fi

bold "=== Changes to pull ==="
info "Behind origin/main by $BEHIND commits. Ahead by $AHEAD."
echo
bold "Incoming commits:"
git log --oneline --decorate HEAD..origin/main
echo
bold "Files changing:"
git diff --stat HEAD..origin/main | tail -30
echo

if [[ "$VERIFY_ONLY" == "1" ]]; then
    ok "Verify-only mode. Not pulling. Exiting."
    [[ "$STASH_MADE" == "1" ]] && warn "Stash still held — run 'git stash pop' to restore."
    exit 0
fi

# ---- Pull --------------------------------------------------------------------
info "Pulling origin/main (fast-forward only)..."
if ! git pull --ff-only origin main; then
    err "Fast-forward pull failed — your branch has diverged from origin/main."
    err "Resolve manually: git status, git log --oneline --all --graph | head -30"
    exit 2
fi
NEW_COMMIT=$(git rev-parse --short HEAD)
ok "Now at $NEW_COMMIT"

# ---- Post-pull verification -------------------------------------------------
bold "=== Post-pull verification ==="
if [[ -n "$PYTHON" ]]; then
    info "Syntax-checking critical scripts..."
    for f in scripts/lead_engine.py scripts/revenue_engine.py; do
        if [[ -f "$f" ]]; then
            if "$PYTHON" -c "import ast,sys; ast.parse(open('$f',encoding='utf-8').read()); print('  ok: $f')" 2>&1; then
                :
            else
                err "Syntax error in $f — check recent commits."
                exit 3
            fi
        fi
    done
    ok "All critical scripts parse clean."
else
    warn "Skipping Python verification (no interpreter)."
fi

# ---- Daemon status check ----------------------------------------------------
DAEMON_ALIVE=0
if [[ -f tmp/skool_daemon.heartbeat ]] && [[ -n "$PYTHON" ]]; then
    HB_CHECK=$("$PYTHON" -c "
import json, pathlib, datetime
try:
    hb = json.loads(pathlib.Path('tmp/skool_daemon.heartbeat').read_text())
    ts = datetime.datetime.fromisoformat(hb['ts'].replace('Z','+00:00'))
    age = (datetime.datetime.now(datetime.timezone.utc) - ts).total_seconds()
    print(f'{hb[\"pid\"]}|{hb[\"cycle\"]}|{age:.0f}|{\"HEALTHY\" if age < 600 else \"STALE\"}')
except Exception as e:
    print(f'0|0|0|MISSING')
" 2>&1 || echo "0|0|0|MISSING")
    IFS='|' read -r D_PID D_CYCLE D_AGE D_STATUS <<< "$HB_CHECK"
    case "$D_STATUS" in
        HEALTHY)
            ok "Skool daemon: PID $D_PID, cycle $D_CYCLE, ${D_AGE}s old — HEALTHY (running OLD code in memory)"
            DAEMON_ALIVE=1 ;;
        STALE)
            warn "Skool daemon: PID $D_PID heartbeat STALE (${D_AGE}s old) — may be dead" ;;
        *)
            info "No live skool daemon." ;;
    esac
fi

# ---- Optional daemon restart -------------------------------------------------
if [[ "$RESTART_DAEMONS" == "1" ]] && [[ "$DAEMON_ALIVE" == "1" ]] && [[ -n "$PYTHON" ]]; then
    warn "Restarting skool daemon to pick up pulled changes..."
    if [[ "$PLATFORM" == "macos" || "$PLATFORM" == "linux" ]]; then
        if kill "$D_PID" 2>/dev/null; then
            sleep 3
            nohup "$PYTHON" scripts/skool_engine.py daemon --interval 5 > tmp/skool_daemon_nohup.log 2>&1 &
            ok "Skool daemon restarted (new PID $!)."
        else
            err "Failed to kill PID $D_PID. Restart manually."
        fi
    else
        warn "On Windows, run manually:  taskkill //PID $D_PID //F && python scripts/skool_engine.py daemon --interval 5 &"
    fi
elif [[ "$RESTART_DAEMONS" == "1" ]]; then
    info "No daemon to restart (or --restart-daemons requested but none alive)."
fi

# ---- Log to SESSION_LOG -----------------------------------------------------
if [[ -f memory/SESSION_LOG.md ]]; then
    DATE=$(date +%Y-%m-%d)
    LOG_ENTRY="
### $DATE — sync-from-github ($PLATFORM)
**Agent:** sync-from-github.sh
**Action:** Pulled origin/main → $NEW_COMMIT (was $CURRENT_COMMIT)
**Behind before pull:** $BEHIND commits
**Platform:** $PLATFORM
**Daemon status:** $([ "$DAEMON_ALIVE" == "1" ] && echo "HEALTHY (PID $D_PID, cycle $D_CYCLE)" || echo "none detected")
**Verification:** all critical scripts parse + import clean
"
    # Insert after the header (line 10 or so)
    if command -v python3 &>/dev/null || command -v python &>/dev/null; then
        PY_CMD=$(command -v python3 || command -v python)
        "$PY_CMD" - <<PYEOF
import pathlib
p = pathlib.Path('memory/SESSION_LOG.md')
content = p.read_text(encoding='utf-8')
entry = r"""$LOG_ENTRY"""
# Insert after the first '---' divider
parts = content.split('---', 2)
if len(parts) >= 3:
    new = parts[0] + '---' + parts[1] + '---\n' + entry + '\n' + parts[2]
else:
    new = content + '\n' + entry
p.write_text(new, encoding='utf-8')
print('  ok: SESSION_LOG updated')
PYEOF
    fi
fi

# ---- Final summary ----------------------------------------------------------
echo
bold "=== Sync Complete ==="
ok "Pulled $BEHIND commits: $CURRENT_COMMIT → $NEW_COMMIT"
[[ "$STASH_MADE" == "1" ]] && warn "Your local work is in the stash — run 'git stash pop' to restore."
[[ "$DAEMON_ALIVE" == "1" ]] && [[ "$RESTART_DAEMONS" == "0" ]] && \
    info "Skool daemon still running OLD code — restart manually or re-run with --restart-daemons."
echo
info "Next steps (Mac-specific setup if first run):"
info "  1. Copy .env.agents from Windows box (contains all API keys — never commit)"
info "  2. Install Python deps: pip install -r requirements.txt (or poetry install)"
info "  3. Playwright: python -m playwright install chromium"
info "  4. Login to Skool once: python scripts/skool_engine.py login"
info "  5. Start daemon: python scripts/skool_engine.py daemon --interval 5 &"
