#!/usr/bin/env bash
#
# liveness_pager.sh — alert when a SunBiz daemon / tunnel / bridge dies.
#
# Each run checks:
#   (a) every expected pm2 daemon is 'online' in `pm2 jlist`
#   (b) systemctl is-active cloudflared == active
#   (c) bridge GET http://127.0.0.1:9100/health returns 401 (bearer enforced)
#   (d) heartbeat fresh: /srv/sunbiz/deploy.log (the 15-min auto-sync) updated
#       within HEARTBEAT_MAX_AGE — a stalled timer/box goes stale here.
#
# On ANY failure it sends ONE email via the existing send_gateway path to the
# ops inbox, deduped by a 30-min cooldown file so a sustained outage pages once,
# not every 5 minutes. (Email is the SunBiz ops channel — no Telegram.)
#
# Run with --force to inject a synthetic failure and send a test alert,
# bypassing the cooldown (used to verify delivery).
#
# No -e: we run ALL checks and aggregate, rather than aborting on the first.

set -uo pipefail

REPO_ROOT="/srv/sunbiz/ceo-agent"
PY="$REPO_ROOT/.venv/bin/python"
SUNBIZ_TID="aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110"
ALERT_TO="echelonx.aisolutions@gmail.com"
BRIDGE_HEALTH="http://127.0.0.1:9100/health"
DEPLOY_LOG="/srv/sunbiz/deploy.log"
HEARTBEAT_MAX_AGE="${HEARTBEAT_MAX_AGE:-2700}"   # 45 min (3 auto-sync ticks)
COOLDOWN_FILE="/srv/sunbiz/backups/.pager_cooldown"
COOLDOWN_SECONDS=1800                            # 30 min
LOG="${OPS_LOG:-/srv/sunbiz/backups/ops.log}"

# Expected pm2 daemons on the SunBiz VPS (the funnel + its infra).
EXPECTED_DAEMONS=(
  event-router
  sunbiz-sequence-runner
  sunbiz-lender-response-classifier
  claude-bridge-ping
  claude-bridge
  sunbiz-cold-outreach-runner
  sunbiz-sentinel
)

FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

log() { printf '%s [liveness_pager] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"; }

FAILURES=()

# (a) daemons online — one python pass over jlist.
#
# jlist goes through a TEMP FILE, not an env var. It was an env var until
# 2026-08-30, and with 18 daemons `pm2 jlist` is ~140KB — past Linux's 128KB
# MAX_ARG_STRLEN ceiling on a single env entry. execve then failed with
# "Argument list too long", the command substitution returned the empty string,
# and empty read as "nothing failing". This check had been fail-OPEN on every
# run since the daemon list grew: a dead daemon would never have paged anyone.
JLIST_FILE="$(mktemp)"
trap 'rm -f "$JLIST_FILE"' EXIT
pm2 jlist >"$JLIST_FILE" 2>/dev/null || echo '[]' >"$JLIST_FILE"
DAEMON_FAILS="$(EXPECTED="${EXPECTED_DAEMONS[*]}" JLIST_FILE="$JLIST_FILE" python3 - <<'PY'
import os, json, sys
expected = os.environ.get("EXPECTED", "").split()
try:
    with open(os.environ["JLIST_FILE"]) as fh:
        arr = json.load(fh)
except Exception as exc:
    # Fail CLOSED. Not knowing the daemon states is itself pageable; the old
    # code turned exactly this condition into a clean bill of health.
    print("jlist_unreadable=%s" % type(exc).__name__)
    sys.exit(0)
state = {p.get("name"): ((p.get("pm2_env") or {}).get("status")) for p in arr}
bad = [d + "=" + (state.get(d) or "MISSING") for d in expected if state.get(d) != "online"]
print(",".join(bad))
PY
)" || DAEMON_FAILS="daemon_check_crashed"
[ -n "$DAEMON_FAILS" ] && FAILURES+=("daemons[$DAEMON_FAILS]")

# (b) cloudflared tunnel.
CF="$(systemctl is-active cloudflared 2>/dev/null || true)"
[ "$CF" = "active" ] || FAILURES+=("cloudflared=$CF")

# (c) bridge health == 401 (bearer enforced, process up).
CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$BRIDGE_HEALTH" 2>/dev/null || echo 000)"
[ "$CODE" = "401" ] || FAILURES+=("bridge_health=$CODE")

# (d) heartbeat freshness (auto-sync writes deploy.log every ~15 min).
if [ -f "$DEPLOY_LOG" ]; then
  AGE=$(( $(date +%s) - $(stat -c %Y "$DEPLOY_LOG") ))
  [ "$AGE" -le "$HEARTBEAT_MAX_AGE" ] || FAILURES+=("autosync_heartbeat_stale=${AGE}s")
else
  FAILURES+=("autosync_heartbeat=missing")
fi

# Forced test: inject a synthetic failure so delivery can be verified.
if [ "$FORCE" = "1" ]; then
  FAILURES+=("FORCED_TEST_ALERT (synthetic — ignore)")
fi

if [ "${#FAILURES[@]}" -eq 0 ]; then
  log "all healthy (daemons OK, cloudflared active, bridge 401, heartbeat fresh)"
  exit 0
fi

SUMMARY="$(IFS='; '; echo "${FAILURES[*]}")"
log "FAILURES detected: $SUMMARY"

# Cooldown dedupe (skipped on --force).
NOW="$(date +%s)"
if [ "$FORCE" != "1" ] && [ -f "$COOLDOWN_FILE" ]; then
  LAST="$(cat "$COOLDOWN_FILE" 2>/dev/null || echo 0)"
  if [ $(( NOW - LAST )) -lt "$COOLDOWN_SECONDS" ]; then
    log "alert SUPPRESSED (cooldown $(( COOLDOWN_SECONDS - (NOW - LAST) ))s left)"
    exit 0
  fi
fi

HOST="$(hostname)"
SUBJECT="[SunBiz VPS] LIVENESS ALERT: ${SUMMARY}"
BODY="SunBiz VPS liveness check FAILED at $(date -u +%Y-%m-%dT%H:%M:%SZ) on host ${HOST}.

Failing checks:
$(printf '  - %s\n' "${FAILURES[@]}")

Checked:
  (a) pm2 daemons online
  (b) cloudflared active
  (c) bridge /health == 401
  (d) auto-sync heartbeat (deploy.log) fresh

This pager runs every 5 min; further alerts are suppressed for 30 min.
Investigate: pm2 list; systemctl status cloudflared vps_autosync.timer; tail /srv/sunbiz/backups/ops.log"

# Send ONE email via send_gateway. tenant-id scopes lead resolution to SunBiz.
SEND_RC=0
"$PY" "$REPO_ROOT/scripts/integrations/send_gateway.py" send --json \
  --channel email \
  --agent-source liveness_pager \
  --to "$ALERT_TO" \
  --subject "$SUBJECT" \
  --body "$BODY" \
  --brand sunbiz \
  --intent transactional \
  --tenant-id "$SUNBIZ_TID" >>"$LOG" 2>&1 || SEND_RC=$?

if [ "$SEND_RC" -eq 0 ]; then
  echo "$NOW" > "$COOLDOWN_FILE"
  log "ALERT SENT to ${ALERT_TO} (cooldown armed 30m)"
else
  log "ERROR send_gateway failed (rc=$SEND_RC) — alert NOT delivered; will retry next run"
fi
exit 0
