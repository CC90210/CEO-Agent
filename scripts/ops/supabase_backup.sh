#!/usr/bin/env bash
#
# supabase_backup.sh — SunBiz-scoped logical backup of the shared Supabase.
#
# REST tenant-scoped export (tenant_id = SunBiz ONLY) of every relevant table
# to NDJSON + this tenant's lead-documents Storage objects → tar → gzip → gpg
# (AES256, symmetric, passphrase from .env.agents). Then a restore drill loads
# the NDJSON back into a scratch SQLite table and matches row counts.
#
# Deliberately NOT pg_dump: (1) no DB connection string is in .env.agents,
# (2) pg client tools are not installed, (3) a full dump would copy EVERY
# tenant's PII onto this box — violating SunBiz scope. The schema lives in
# version-controlled migrations; this captures the SunBiz data + documents.
#
# Retains 14 days locally. Off-box replication is delegated to backups_push.sh
# (guarded: no-ops with a clear log line until a remote is configured).
#
# Secrets: the gpg passphrase is read from .env.agents and passed to gpg over a
# file descriptor — never echoed, never in argv/ps. Service-role JWT is read by
# the python helper via the repo secret_loader and never printed.

set -euo pipefail

REPO_ROOT="/srv/sunbiz/ceo-agent"
PY="$REPO_ROOT/.venv/bin/python"
HELPER="$REPO_ROOT/scripts/ops/_supabase_backup.py"
ENV_FILE="$REPO_ROOT/.env.agents"
BACKUP_DIR="/srv/sunbiz/backups/supabase"
RETAIN_DAYS=14
LOG="${OPS_LOG:-/srv/sunbiz/backups/ops.log}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

log() { printf '%s [supabase_backup] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"; }

mkdir -p "$BACKUP_DIR"

# Read the symmetric passphrase WITHOUT printing it.
PASS="$(grep -E '^BACKUP_GPG_PASSPHRASE=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
if [ -z "${PASS:-}" ]; then
  log "ERROR BACKUP_GPG_PASSPHRASE not set in .env.agents — cannot encrypt; aborting."
  exit 1
fi

STAGE="$(mktemp -d /tmp/sunbiz_bkp.XXXXXX)"
OUT="$BACKUP_DIR/sunbiz-${TS}.tar.gz.gpg"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

log "start → $OUT"

# 1. Export tables + storage (SunBiz-scoped) into the staging dir.
if ! "$PY" "$HELPER" export "$STAGE"; then
  log "ERROR export failed — aborting (no partial artifact written)"
  exit 1
fi

# 2. tar + gzip + gpg-encrypt (AES256). Passphrase via fd 3 (not argv).
tar -C "$STAGE" -czf "$STAGE.tar.gz" .
gpg --batch --yes --pinentry-mode loopback --passphrase-fd 3 \
    --symmetric --cipher-algo AES256 -o "$OUT" "$STAGE.tar.gz" 3<<<"$PASS"
rm -f "$STAGE.tar.gz"
SIZE="$(du -h "$OUT" | cut -f1)"
log "encrypted artifact written: $OUT ($SIZE)"

# 3. Restore drill: decrypt → extract → verify row counts in a scratch table.
DRILL="$(mktemp -d /tmp/sunbiz_drill.XXXXXX)"
gpg --batch --yes --pinentry-mode loopback --passphrase-fd 3 \
    -d -o "$DRILL/restore.tar.gz" "$OUT" 3<<<"$PASS"
tar -C "$DRILL" -xzf "$DRILL/restore.tar.gz"
VERIFY_RC=0
"$PY" "$HELPER" verify "$DRILL" || VERIFY_RC=$?
rm -rf "$DRILL"
if [ "$VERIFY_RC" -ne 0 ]; then
  log "ERROR restore drill FAILED (rc=$VERIFY_RC) — keeping artifact for inspection"
  exit "$VERIFY_RC"
fi
log "restore drill PASSED — backup is decryptable + complete"

# 4. Retention: drop encrypted artifacts older than RETAIN_DAYS.
DELETED="$(find "$BACKUP_DIR" -maxdepth 1 -name 'sunbiz-*.tar.gz.gpg' -mtime +"$RETAIN_DAYS" -print -delete | wc -l)"
[ "$DELETED" -gt 0 ] && log "retention: pruned $DELETED artifact(s) older than ${RETAIN_DAYS}d"

# 5. Off-box replication (guarded — no-op until a remote is configured).
if [ -x "$REPO_ROOT/scripts/ops/backups_push.sh" ]; then
  "$REPO_ROOT/scripts/ops/backups_push.sh" || log "WARN off-box push reported a problem"
fi

# 6. Storage completeness gate.
#
# The restore drill above verifies TABLE row counts. It says nothing about the
# documents, so on 2026-08-12 this script logged "storage: 0 objects, failed=3481",
# then VERIFY PASS, then done — a 4.6M artifact where the baseline was 1.8G, with
# every bank statement missing, and exited 0. systemd recorded a clean run.
#
# A backup missing 100% of its documents is not a successful backup. The artifact
# is KEPT (the table data is real and worth having) but the job exits non-zero so
# the failure is visible instead of silent.
# Parse the manifest with the venv python, not sed. The first version matched
# `"failed"` anywhere in the file and picked a table's field instead of the
# storage block, read 0, and stayed quiet on a run that lost 3481 documents —
# the gate reproducing the exact bug it was written to catch.
STORAGE_STATS="$("$PY" - "$STAGE/manifest.json" <<'PYGATE'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        s = (json.load(fh).get("storage") or {})
    print(int(s.get("objects") or 0), int(s.get("failed") or 0))
except Exception:
    print(-1, -1)          # unreadable manifest is itself a failure
PYGATE
)"
STORAGE_CAPTURED="$(printf %s "$STORAGE_STATS" | cut -d' ' -f1)"
STORAGE_FAILED="$(printf %s "$STORAGE_STATS" | cut -d' ' -f2)"
if [ "$STORAGE_CAPTURED" -lt 0 ]; then
  log "ERROR could not read storage stats from manifest.json — treating as failure"
  exit 4
fi
if [ "$STORAGE_CAPTURED" -eq 0 ] && [ "$STORAGE_FAILED" -gt 0 ]; then
  log "ERROR storage capture TOTAL FAILURE: 0 of $STORAGE_FAILED objects. Artifact kept ($SIZE) and its TABLE data is verified, but every document is missing. Cause on this host: no Cloudflare R2 credentials (scripts/etl_storage_to_r2.py absent). Exiting non-zero so this is not recorded as a clean run."
  exit 3
fi
if [ "$STORAGE_FAILED" -gt 0 ]; then
  log "WARN storage partially incomplete: captured $STORAGE_CAPTURED, failed $STORAGE_FAILED"
fi

log "done ($SIZE)"
