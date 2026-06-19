#!/usr/bin/env bash
#
# vps_autosync.sh — guarded auto-deploy for the SunBiz VPS daemon repos.
#
# WHY: the dashboard (oasis-command-center) auto-deploys via Vercel, but the VPS
# daemon repos had no equivalent — so /srv/sunbiz/ceo-agent drifted BEHIND origin
# and /srv/sunbiz/sunbiz-agent drifted AHEAD (un-pushed local commits). This is
# the "Vercel for the VPS": a systemd timer / cron runs it every ~15 min and it
# keeps each repo in sync WITHOUT ever clobbering local work.
#
# Per-repo policy (the safety latches):
#   - dirty (uncommitted edits)   -> skip + WARN (never discard local changes)
#   - ahead only (unpushed)       -> skip + WARN (surface for push; never lost)
#   - diverged (ahead AND behind) -> skip + ERROR (manual reconcile)
#   - behind only + clean         -> ff-only pull -> PRE-DEPLOY GATE -> pm2 reload
#                                    (this repo's daemons only) -> post-deploy
#                                    health probe (informational).
#
# Safety latches:
#   - --ff-only: can only fast-forward, never merge/overwrite a diverged repo.
#   - PRE-DEPLOY GATE: byte-compiles the .py files CHANGED by the pull before any
#     reload; if a changed file doesn't compile, the pull is ROLLED BACK
#     (git reset --hard to the pre-pull SHA) and the daemons keep running the
#     last-good code. Gating only the CHANGED files means a pre-existing
#     un-compilable file elsewhere can't block deploys (no false positives), and
#     it never imports/runs code (no env/runtime false positives).
#   - post-deploy health probe is INFORMATIONAL ONLY: the doctors mark
#     not-yet-provisioned channels (e.g. SMS) as failures, so the verdict is
#     noisy by design — it is logged, never used to auto-revert (rollback is
#     driven solely by the deterministic compile gate above).
#
# Idempotent, single-instance (flock), logs to $LOG. Exits non-zero only on a
# HARD failure so `systemctl status vps_autosync` / the daily diagnostic surface
# it. Pass --dry-run to report what it WOULD do without pulling/reloading.

set -euo pipefail

REPOS=("/srv/sunbiz/ceo-agent" "/srv/sunbiz/sunbiz-agent")
BRANCH="main"
LOG="${VPS_AUTOSYNC_LOG:-/srv/sunbiz/deploy.log}"
LOCK="/tmp/vps_autosync.lock"

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"; }

# Single-instance guard so a slow pull can't overlap the next timer tick.
exec 9>"$LOCK"
if ! flock -n 9; then
  log "[skip] another vps_autosync run holds the lock"
  exit 0
fi

had_error=0

# Pre-deploy gate: byte-compile the .py files this pull CHANGED. Returns non-zero
# if any changed file fails to compile (syntax error) — the caller then rolls the
# pull back before reloading daemons. Scoped to changed files so unrelated
# pre-existing breakage can't block deploys; compile-only so there are no
# env/runtime false positives.
predeploy_gate() {
  local dir="$1" name="$2" prior="$3"
  command -v python3 >/dev/null 2>&1 || { log "[$name] gate: python3 unavailable — skipped"; return 0; }
  local changed
  changed="$(git -C "$dir" diff --name-only "$prior"..HEAD -- '*.py' 2>/dev/null || true)"
  if [ -z "$changed" ]; then
    log "[$name] gate: no changed .py files — OK"; return 0
  fi
  local f rc=0 n=0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ -f "$dir/$f" ] || continue   # skip deleted/renamed-away files
    n=$((n + 1))
    if ! python3 -m py_compile "$dir/$f" >/dev/null 2>&1; then
      log "[$name] gate FAIL: $f does not compile"; rc=1
    fi
  done <<< "$changed"
  [ "$rc" = 0 ] && log "[$name] pre-deploy gate OK (compiled $n changed .py)"
  return "$rc"
}

# Post-deploy health probe — INFORMATIONAL ONLY (never triggers rollback). Calls
# the repo's health script with NO flags (the universal-safe invocation; every
# probe sets its exit code by health), so it can't break on a flag mismatch.
post_deploy_health() {
  local dir="$1" name="$2"
  command -v python3 >/dev/null 2>&1 || return 0
  local probe=""
  if [ -f "$dir/scripts/doctor.py" ]; then probe="$dir/scripts/doctor.py"
  elif [ -f "$dir/scripts/state/health_aggregator.py" ]; then probe="$dir/scripts/state/health_aggregator.py"
  elif [ -f "$dir/scripts/system_health.py" ]; then probe="$dir/scripts/system_health.py"
  fi
  if [ -z "$probe" ]; then
    log "[$name] post-deploy health: no probe in repo (skipped)"; return 0
  fi
  if python3 "$probe" >/dev/null 2>&1; then
    log "[$name] post-deploy health: OK ($(basename "$probe"))"
  else
    log "[$name] post-deploy health: WARN ($(basename "$probe") exit non-zero — informational; review if unexpected)"
  fi
}

reload_repo_daemons() {
  # Reload only the PM2 apps whose working dir lives under this repo, derived
  # live from `pm2 jlist` so daemon names are never hardcoded.
  local dir="$1" name="$2"
  command -v pm2 >/dev/null 2>&1 || { log "[$name] pm2 not on PATH — skipping reload"; return; }
  local apps
  apps="$(pm2 jlist 2>/dev/null | python3 - "$dir" <<'PY' 2>/dev/null || true
import sys, json, os
root = os.path.realpath(sys.argv[1])
try:
    arr = json.load(sys.stdin)
except Exception:
    arr = []
for a in arr:
    env = a.get("pm2_env") or {}
    cwd = env.get("pm_cwd") or a.get("pm_cwd") or ""
    try:
        if cwd and os.path.realpath(cwd).startswith(root):
            print(a.get("name", ""))
    except Exception:
        pass
PY
)"
  apps="$(printf '%s\n' "$apps" | awk 'NF' | sort -u)"
  if [ -z "$apps" ]; then
    log "[$name] no PM2 apps mapped to $dir (nothing to reload)"
    return
  fi
  while IFS= read -r app; do
    [ -n "$app" ] || continue
    if [ "$DRY" = "1" ]; then
      log "[$name] DRY would pm2 reload $app"
    else
      log "[$name] pm2 reload $app"
      pm2 reload "$app" --update-env >/dev/null 2>&1 || log "[$name] WARN reload $app failed"
    fi
  done <<< "$apps"
}

sync_repo() {
  local dir="$1"
  local name; name="$(basename "$dir")"

  if [ ! -d "$dir/.git" ]; then
    log "[$name] ERROR not a git repo at $dir"; had_error=1; return
  fi
  if ! git -C "$dir" fetch --quiet origin "$BRANCH"; then
    log "[$name] ERROR fetch failed"; had_error=1; return
  fi

  # Refuse to touch a repo with uncommitted local edits.
  if ! git -C "$dir" diff --quiet || ! git -C "$dir" diff --cached --quiet; then
    log "[$name] WARN dirty working tree — skipping (commit/stash on the VPS first)"; return
  fi

  local local_head remote_head ahead behind
  local_head="$(git -C "$dir" rev-parse HEAD)"
  remote_head="$(git -C "$dir" rev-parse "origin/$BRANCH")"
  if [ "$local_head" = "$remote_head" ]; then
    log "[$name] up-to-date @ ${local_head:0:8}"; return
  fi
  ahead="$(git -C "$dir" rev-list --count "origin/$BRANCH"..HEAD)"
  behind="$(git -C "$dir" rev-list --count "HEAD..origin/$BRANCH")"

  if [ "$ahead" -gt 0 ] && [ "$behind" -gt 0 ]; then
    log "[$name] ERROR diverged (ahead $ahead / behind $behind) — manual reconcile needed"; had_error=1; return
  fi
  if [ "$ahead" -gt 0 ]; then
    log "[$name] WARN ahead $ahead unpushed commit(s) — NOT pulling; push these to origin so they're backed up"; return
  fi

  # behind only + clean → fast-forward. PRIOR_SHA is the pre-pull HEAD so the
  # gate can deterministically roll back to last-good.
  local prior_sha="$local_head"
  log "[$name] behind $behind — ff-only ${local_head:0:8}..${remote_head:0:8}"
  if [ "$DRY" = "1" ]; then
    log "[$name] DRY would git pull --ff-only + gate + reload"; return
  fi
  if ! git -C "$dir" pull --ff-only --quiet origin "$BRANCH"; then
    log "[$name] ERROR ff-only pull failed"; had_error=1; return
  fi

  # PRE-DEPLOY GATE — compile the changed .py before touching live daemons.
  if ! predeploy_gate "$dir" "$name" "$prior_sha"; then
    log "[$name] ERROR pre-deploy gate FAILED — rolling back to ${prior_sha:0:8} (daemons untouched)"
    if git -C "$dir" reset --hard "$prior_sha" >/dev/null 2>&1; then
      log "[$name] rolled back to ${prior_sha:0:8}"
    else
      log "[$name] ERROR rollback FAILED — MANUAL INTERVENTION NEEDED (repo at ${remote_head:0:8})"
    fi
    had_error=1; return
  fi

  reload_repo_daemons "$dir" "$name"
  post_deploy_health "$dir" "$name"
  log "[$name] deployed @ ${remote_head:0:8}"
}

log "=== vps_autosync start${DRY:+ }$([ "$DRY" = 1 ] && echo '(dry-run)') ==="
for r in "${REPOS[@]}"; do sync_repo "$r"; done
log "=== vps_autosync done (had_error=$had_error) ==="
exit "$had_error"
