#!/usr/bin/env bash
#
# backups_push.sh — replicate the ENCRYPTED backups off-box.
#
# /srv/sunbiz/backups is intended to be a git repo whose remote is the PRIVATE
# GitHub repo CC90210/sunbiz-backups. Only gpg-encrypted artifacts are tracked
# (see /srv/sunbiz/backups/.gitignore) so GitHub never sees plaintext PII.
#
# This script is GUARDED: if the backups dir is not yet a git repo with an
# 'origin' remote, it logs the gap and exits 0 (so the backup itself still
# succeeds). Once CC provisions the remote, replication starts automatically.
#
# NOTE (2026-06-18): initial provisioning of the off-box GitHub remote was held
# pending operator authorization — the auto-mode guard flagged pushing PII (even
# encrypted) to a new external repo. See VPS_REBUILD_RUNBOOK.md "Off-box".

set -euo pipefail

BACKUP_ROOT="/srv/sunbiz/backups"
LOG="${OPS_LOG:-/srv/sunbiz/backups/ops.log}"
log() { printf '%s [backups_push] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"; }

if [ ! -d "$BACKUP_ROOT/.git" ]; then
  log "skip: $BACKUP_ROOT is not a git repo yet (off-box remote not provisioned)"
  exit 0
fi
if ! git -C "$BACKUP_ROOT" remote get-url origin >/dev/null 2>&1; then
  log "skip: no 'origin' remote on the backups repo (off-box remote not provisioned)"
  exit 0
fi

# Only ever track encrypted blobs (defense in depth alongside .gitignore).
# GitHub hard-rejects a single file over 100MB. Artifacts from before
# 2026-08-11 are ~1.8GB each because they still contained merchant documents;
# staging one makes EVERY push fail from then on. Stage only what can actually
# travel, and report what could not.
MAX_PUSH_BYTES=94371840   # 90MB, under GitHub's 100MB wall
SKIPPED=0
find "$BACKUP_ROOT" -name '*.gpg' -type f -print | while IFS= read -r f; do
  sz="$(stat -c %s "$f" 2>/dev/null || echo 0)"
  rel="${f#"$BACKUP_ROOT"/}"
  if [ "$sz" -gt "$MAX_PUSH_BYTES" ]; then
    log "SKIP too-large-for-github ($((sz/1048576))MB): $rel — stays on this host ONLY"
    continue
  fi
  git -C "$BACKUP_ROOT" add -f -- "$rel" 2>/dev/null || true
done

# Repo growth watch: ~4.6MB/night is ~1.7GB/year and git keeps history forever.
# GitHub starts warning past 1GB, so surface it long before it becomes a wall.
REPO_MB="$(du -sm "$BACKUP_ROOT/.git" 2>/dev/null | cut -f1)"
if [ "${REPO_MB:-0}" -gt 800 ]; then
  log "WARN off-box repo is ${REPO_MB}MB — squash history before it hits GitHub's limit"
fi
if git -C "$BACKUP_ROOT" diff --cached --quiet; then
  log "nothing new to replicate"
  exit 0
fi
git -C "$BACKUP_ROOT" -c user.name='sunbiz-ops' -c user.email='ops@sunbizfunding.com' \
    commit -q -m "backups $(date -u +%Y-%m-%dT%H:%M:%SZ)"
if git -C "$BACKUP_ROOT" push -q origin HEAD 2>>"$LOG"; then
  log "off-box replication pushed to origin"
else
  log "WARN off-box push failed (see log) — local copy retained"
fi
