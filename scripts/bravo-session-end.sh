#!/usr/bin/env bash
# bravo-session-end.sh
# Run at the END of every Claude Code session on either machine.
# Writes SESSION_LOG entry + HANDOFF.md, commits + pushes, releases ACTIVE_SESSION.
#
# Usage: bash scripts/bravo-session-end.sh "one-line summary of what I did"

set -uo pipefail

SUMMARY="${1:-session complete}"

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

# ---- Repo root + platform ----------------------------------------------------
if ! git rev-parse --show-toplevel &>/dev/null; then
    err "Not in a git repo."
    exit 1
fi
REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

case "$(uname -s)" in
    Darwin*)              MACHINE="mac" ;;
    Linux*)               MACHINE="linux" ;;
    MINGW*|MSYS*|CYGWIN*) MACHINE="windows" ;;
    *)                    MACHINE="unknown" ;;
esac

PYTHON=""
for cand in python3 python python3.12; do
    if command -v "$cand" &>/dev/null; then
        PYTHON="$cand"; break
    fi
done

DATE=$(date +%Y-%m-%d)
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

echo "${BOLD}=== BRAVO SESSION END ===${X}"
info "Machine: $MACHINE"
info "Summary: $SUMMARY"

# ---- 1. Append to SESSION_LOG ------------------------------------------------
if [[ -f "memory/SESSION_LOG.md" ]] && [[ -n "$PYTHON" ]]; then
    "$PYTHON" - <<PYEOF
import pathlib
p = pathlib.Path("memory/SESSION_LOG.md")
content = p.read_text(encoding="utf-8")
entry = """
### $DATE — session end ($MACHINE)
**Agent:** bravo-session-end
**Note:** $SUMMARY

"""
# Insert after the first '---' divider
parts = content.split("---", 2)
if len(parts) >= 3:
    new = parts[0] + "---" + parts[1] + "---\n" + entry + parts[2]
else:
    new = content + "\n" + entry
p.write_text(new, encoding="utf-8")
PYEOF
    ok "Appended to SESSION_LOG.md"
fi

# ---- 2. Update HANDOFF.md ----------------------------------------------------
if [[ -n "$PYTHON" ]]; then
    "$PYTHON" - <<PYEOF
import pathlib, subprocess

try:
    out = subprocess.run(["git","diff","--name-only","HEAD"], capture_output=True, text=True, timeout=10)
    files = [line for line in out.stdout.splitlines() if line.strip()]
except Exception:
    files = []

content = f"""# HANDOFF — Last Session

**From:** $MACHINE
**At:**   $TS
**Summary:** $SUMMARY

## Files touched this session
"""
if files:
    for f in files[:40]:
        content += f"- {f}\n"
else:
    content += "- (none staged at handoff time)\n"

content += """
## Next machine: pick up from here
1. bash scripts/bravo-session-start.sh
2. Read brain/STATE.md and memory/ACTIVE_TASKS.md
3. Continue the work described above

## Notes for the next session
(add context if needed — edit this file before commit)
"""
pathlib.Path("memory/HANDOFF.md").write_text(content, encoding="utf-8")
PYEOF
    ok "Wrote memory/HANDOFF.md"
fi

# ---- 3. Release ACTIVE_SESSION claim -----------------------------------------
if [[ -f "memory/ACTIVE_SESSION.json" ]] && [[ -n "$PYTHON" ]]; then
    "$PYTHON" - <<PYEOF
import json, datetime, pathlib
p = pathlib.Path("memory/ACTIVE_SESSION.json")
try:
    data = json.loads(p.read_text(encoding="utf-8"))
    data["released_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    data["last_heartbeat"] = data["released_at"]
    data["current_task"] = "released"
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
except Exception:
    pass
PYEOF
    ok "Released ACTIVE_SESSION claim"
fi

# ---- 4. Commit + push --------------------------------------------------------
if ! git diff --quiet || ! git diff --cached --quiet; then
    info "Staging changes..."
    git add memory/SESSION_LOG.md memory/HANDOFF.md memory/ACTIVE_SESSION.json 2>/dev/null || true
    # Also stage any tracked file that has changes
    git add -u 2>/dev/null || true

    if git diff --cached --quiet; then
        warn "Nothing staged — skipping commit."
    else
        COMMIT_MSG="bravo($MACHINE): $SUMMARY"
        if git commit -m "$COMMIT_MSG" --quiet 2>&1; then
            ok "Committed: $COMMIT_MSG"
            if git push origin main --quiet 2>&1; then
                ok "Pushed to origin/main"
            else
                err "Push failed — resolve and push manually."
                exit 2
            fi
        else
            warn "Commit skipped (pre-commit hook or empty diff)."
        fi
    fi
else
    info "No uncommitted changes."
fi

echo
ok "Session ended cleanly. Other machine can now pull and resume."
echo
