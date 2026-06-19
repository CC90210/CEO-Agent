#!/usr/bin/env bash
#
# env_backup.sh — encrypted off-box copy of the un-versioned runtime secrets.
#
# .env.agents is the ONLY copy of every credential the daemons need (Supabase
# service-role, Gmail app password, bridge bearer, HMAC secrets, the backup
# passphrase, ...). It lives nowhere durable. This gpg-encrypts it (AES256,
# symmetric, same BACKUP_GPG_PASSPHRASE) into /srv/sunbiz/backups/secrets/ and
# hands off to backups_push.sh for off-box replication.
#
# Decryption requires BACKUP_GPG_PASSPHRASE, which is itself stored OFF the box
# in CC's password manager — so a box loss is recoverable (see the runbook).
#
# The passphrase is read from .env.agents and passed to gpg over a file
# descriptor — never echoed, never in argv/ps.

set -euo pipefail

REPO_ROOT="/srv/sunbiz/ceo-agent"
ENV_FILE="$REPO_ROOT/.env.agents"
SECRETS_DIR="/srv/sunbiz/backups/secrets"
RETAIN=14   # keep the last N encrypted env snapshots
LOG="${OPS_LOG:-/srv/sunbiz/backups/ops.log}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

log() { printf '%s [env_backup] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"; }

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

PASS="$(grep -E '^BACKUP_GPG_PASSPHRASE=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
if [ -z "${PASS:-}" ]; then
  log "ERROR BACKUP_GPG_PASSPHRASE not set — cannot encrypt; aborting."
  exit 1
fi

# Un-versioned runtime config to back up. .env.agents (the ceo-agent file the
# sunbiz-agent symlink points at) is the critical one. Add more here if other
# un-versioned secrets appear on the box.
FILES=("$ENV_FILE")

STAGE="$(mktemp -d /tmp/sunbiz_env.XXXXXX)"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

for f in "${FILES[@]}"; do
  [ -f "$f" ] && cp -a "$f" "$STAGE/$(basename "$f")"
done
tar -C "$STAGE" -czf "$STAGE.tar.gz" .

OUT="$SECRETS_DIR/env-agents-${TS}.tar.gz.gpg"
gpg --batch --yes --pinentry-mode loopback --passphrase-fd 3 \
    --symmetric --cipher-algo AES256 -o "$OUT" "$STAGE.tar.gz" 3<<<"$PASS"
rm -f "$STAGE.tar.gz"
chmod 600 "$OUT"
SIZE="$(du -h "$OUT" | cut -f1)"
log "encrypted secrets snapshot: $OUT ($SIZE)"

# Self-check: confirm it decrypts (no count drill needed for a config blob).
if gpg --batch --yes --pinentry-mode loopback --passphrase-fd 3 -d "$OUT" 3<<<"$PASS" \
     | tar -tz >/dev/null 2>&1; then
  log "decrypt self-check OK"
else
  log "ERROR decrypt self-check FAILED — keeping artifact for inspection"
  exit 1
fi

# Retention: keep the newest RETAIN snapshots.
mapfile -t OLD < <(ls -1t "$SECRETS_DIR"/env-agents-*.tar.gz.gpg 2>/dev/null | tail -n +$((RETAIN+1)))
for o in "${OLD[@]:-}"; do [ -n "$o" ] && rm -f "$o" && log "retention: pruned $(basename "$o")"; done

# Off-box replication (guarded).
if [ -x "$REPO_ROOT/scripts/ops/backups_push.sh" ]; then
  "$REPO_ROOT/scripts/ops/backups_push.sh" || log "WARN off-box push reported a problem"
fi

log "done ($SIZE)"
