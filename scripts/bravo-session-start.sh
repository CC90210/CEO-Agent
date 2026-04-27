#!/usr/bin/env bash
# bravo-session-start.sh
# Run at the START of every Claude Code session on either machine.
# Pulls latest code, claims an ACTIVE_SESSION slot, reads HANDOFF, reports state.
#
# Usage:  bash scripts/bravo-session-start.sh
#
# Exits 0 on clean start. Exits non-zero only on git failure.

set -uo pipefail  # do NOT use -e: we want to continue past soft warnings

# ---- Colors ------------------------------------------------------------------
if [[ -z "${NO_COLOR:-}" ]] && [[ -t 1 ]]; then
    G=$'\033[0;32m'; Y=$'\033[1;33m'; R=$'\033[0;31m'; B=$'\033[0;34m'; BOLD=$'\033[1m'; X=$'\033[0m'
else
    G=''; Y=''; R=''; B=''; BOLD=''; X=''
fi
ok()   { echo "${G}[ ok ]${X} $*"; }
info() { echo "${B}[info]${X} $*"; }
warn() { echo "${Y}[warn]${X} $*"; }
err()  { echo "${R}[err ]${X} $*" >&2; }
bold() { echo "${BOLD}$*${X}"; }

# ---- Locate repo root --------------------------------------------------------
if ! git rev-parse --show-toplevel &>/dev/null; then
    err "Not in a git repo. Run from Business-Empire-Agent root."
    exit 1
fi
REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

# ---- Platform detection ------------------------------------------------------
case "$(uname -s)" in
    Darwin*)              MACHINE="mac";     HOST=$(hostname) ;;
    Linux*)               MACHINE="linux";   HOST=$(hostname) ;;
    MINGW*|MSYS*|CYGWIN*) MACHINE="windows"; HOST=${COMPUTERNAME:-$(hostname)} ;;
    *)                    MACHINE="unknown"; HOST=$(hostname) ;;
esac

# Pick python
PYTHON=""
for cand in python3 python python3.12 python3.11; do
    if command -v "$cand" &>/dev/null; then
        PYTHON="$cand"; break
    fi
done

bold "=== BRAVO SESSION START ==="
info "Machine: $MACHINE ($HOST)"
info "Repo:    $REPO_ROOT"

# ---- Daemon exclusivity enforcement (Mac must never run production daemons) --
if [[ "$MACHINE" == "mac" || "$MACHINE" == "linux" ]]; then
    ROGUE_PROCS=""
    if command -v pgrep &>/dev/null; then
        ROGUE_PROCS=$(pgrep -fl "scripts/scheduler.py\|scripts/skool_engine.py daemon\|telegram_agent.js" 2>/dev/null || true)
    else
        ROGUE_PROCS=$(ps aux 2>/dev/null | grep -E "scripts/scheduler.py|scripts/skool_engine.py daemon|telegram_agent.js" | grep -v grep || true)
    fi
    if [[ -n "$ROGUE_PROCS" ]]; then
        err "ROGUE DAEMONS DETECTED on $MACHINE — these must only run on Windows:"
        echo "$ROGUE_PROCS" | sed 's/^/  /'
        err "Kill them immediately with: kill <PID> (or pm2 delete <name> if PM2-managed)"
        err "See brain/CROSS_MACHINE_SYNC.md Rule 2 for why this matters."
    fi
    if command -v pm2 &>/dev/null; then
        PM2_ROGUE=$(pm2 jlist 2>/dev/null | grep -oE '"name":"bravo-[a-z]+"' | sort -u || true)
        if [[ -n "$PM2_ROGUE" ]]; then
            err "ROGUE PM2 ENTRIES DETECTED on $MACHINE:"
            echo "$PM2_ROGUE" | sed 's/^/  /'
            err "Delete with: pm2 delete bravo-scheduler bravo-telegram bravo-skool && pm2 save"
        fi
    fi
fi

# ---- Git pull ----------------------------------------------------------------
info "Pulling origin/main..."
if ! git fetch origin main --quiet 2>/dev/null; then
    warn "git fetch failed (offline?). Continuing with local state."
else
    BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo 0)
    if [[ "$BEHIND" -gt 0 ]]; then
        info "Behind origin/main by $BEHIND commits. Pulling..."
        if ! git pull --ff-only origin main; then
            err "Pull failed — branch has diverged from origin/main."
            err "Resolve manually. Session NOT started."
            exit 2
        fi
    else
        ok "Already up to date with origin/main."
    fi
fi

CURRENT_COMMIT=$(git rev-parse --short HEAD)

# ---- Check for another active session ---------------------------------------
ACTIVE_FILE="memory/ACTIVE_SESSION.json"
STALE_MINUTES=30

if [[ -f "$ACTIVE_FILE" ]] && [[ -n "$PYTHON" ]]; then
    OTHER_INFO=$("$PYTHON" - <<PYEOF 2>/dev/null
import json, datetime, pathlib
try:
    data = json.loads(pathlib.Path("$ACTIVE_FILE").read_text(encoding="utf-8"))
    ts = datetime.datetime.fromisoformat(data["last_heartbeat"].replace("Z","+00:00"))
    now = datetime.datetime.now(datetime.timezone.utc)
    age_min = (now - ts).total_seconds() / 60
    if age_min > $STALE_MINUTES:
        print(f"STALE|{data.get('machine','?')}|{data.get('hostname','?')}|{age_min:.0f}|{data.get('current_task','?')}")
    else:
        print(f"LIVE|{data.get('machine','?')}|{data.get('hostname','?')}|{age_min:.0f}|{data.get('current_task','?')}")
except Exception as e:
    print(f"ERROR|{e}")
PYEOF
)

    IFS='|' read -r STATUS OTHER_MACHINE OTHER_HOST OTHER_AGE OTHER_TASK <<< "$OTHER_INFO"
    case "$STATUS" in
        LIVE)
            if [[ "$OTHER_MACHINE" != "$MACHINE" ]] || [[ "$OTHER_HOST" != "$HOST" ]]; then
                warn "Another session is LIVE: $OTHER_MACHINE ($OTHER_HOST) — ${OTHER_AGE}m ago"
                warn "  Task: $OTHER_TASK"
                warn "  Proceed carefully. File conflicts are YOUR problem to resolve."
            else
                info "Reclaiming own session slot (same machine, ${OTHER_AGE}m ago)."
            fi ;;
        STALE)
            info "Previous session went stale (${OTHER_AGE}m ago, $OTHER_MACHINE). Reclaiming."
            ;;
        *)
            warn "Could not parse ACTIVE_SESSION.json — proceeding." ;;
    esac
fi

# ---- Claim session slot ------------------------------------------------------
if [[ -n "$PYTHON" ]]; then
    "$PYTHON" - <<PYEOF 2>/dev/null
import json, datetime, pathlib
data = {
    "machine": "$MACHINE",
    "hostname": "$HOST",
    "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "last_heartbeat": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "current_task": "session start",
    "commit_at_start": "$CURRENT_COMMIT",
}
pathlib.Path("memory").mkdir(exist_ok=True)
pathlib.Path("memory/ACTIVE_SESSION.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
PYEOF
    ok "Claimed ACTIVE_SESSION slot."
fi

# ---- Read and display HANDOFF.md --------------------------------------------
if [[ -f "memory/HANDOFF.md" ]]; then
    echo
    bold "=== LAST HANDOFF ==="
    head -40 memory/HANDOFF.md
    echo
fi

# ---- Summary -----------------------------------------------------------------
bold "=== STATE SUMMARY ==="
info "Commit: $CURRENT_COMMIT"
if [[ -f "memory/ACTIVE_TASKS.md" ]] && [[ -n "$PYTHON" ]]; then
    P0=$(grep -c '^\- \[ \]' memory/ACTIVE_TASKS.md 2>/dev/null || echo 0)
    info "Open tasks: $P0"
fi

echo
ok "Session started. Run 'bash scripts/bravo-session-end.sh \"<summary>\"' when done."
echo
