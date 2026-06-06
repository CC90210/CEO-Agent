#!/usr/bin/env bash
# vps_bearer_provision.sh — push BRIDGE_BEARER_TOKEN from Vercel into VPS .env.agents
#
# Why this exists: 2026-06-06 diagnostic showed the VPS bridge accepts
# unauthenticated requests on bridge.oasisai.work because BRIDGE_BEARER_TOKEN
# is not set in /srv/sunbiz/ceo-agent/.env.agents. The Vercel server-side env
# DOES have the correct value (BRIDGE_BEARER_TOKEN, set 2d ago). This script
# pulls the canonical value from Vercel and writes/updates it in .env.agents
# on the VPS, then restarts the bridge so it enforces the bearer.
#
# Run ON THE VPS as root. Requires the Vercel CLI to be installed and
# logged into CC's cc90210 team (or a VERCEL_TOKEN env var with project scope).
#
# Usage:
#   sudo bash vps_bearer_provision.sh
#
# Or pass the value directly (no Vercel CLI needed):
#   sudo BRIDGE_BEARER_TOKEN_VALUE='<paste-the-value>' bash vps_bearer_provision.sh

set -euo pipefail

ENV_FILE="/srv/sunbiz/ceo-agent/.env.agents"
BACKUP_FILE="/srv/sunbiz/ceo-agent/.env.agents.bak.$(date -u +%Y%m%dT%H%M%SZ)"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE missing — clone CEO-Agent first." >&2
  exit 1
fi

# Option A — value passed via env var (no Vercel CLI needed).
if [[ -n "${BRIDGE_BEARER_TOKEN_VALUE:-}" ]]; then
  TOKEN="$BRIDGE_BEARER_TOKEN_VALUE"
  echo "[info] using BRIDGE_BEARER_TOKEN_VALUE from env"
else
  # Option B — pull from Vercel CLI.
  if ! command -v vercel >/dev/null 2>&1; then
    echo "ERROR: vercel CLI not installed and BRIDGE_BEARER_TOKEN_VALUE not set." >&2
    echo "Either: (1) install vercel + log in (npm i -g vercel && vercel login)" >&2
    echo "    or: (2) re-run with BRIDGE_BEARER_TOKEN_VALUE='<the-value>'" >&2
    exit 1
  fi
  TMP="$(mktemp /tmp/vercel-env.XXXXXX)"
  trap 'rm -f "$TMP"' EXIT
  echo "[info] pulling production env from Vercel agent-dashboard project..."
  # Pull to a temp file so we never touch the local repo dir.
  vercel env pull "$TMP" --environment=production --yes >/dev/null 2>&1 \
    || { echo "ERROR: vercel env pull failed. Run 'vercel link' first." >&2; exit 1; }
  TOKEN="$(grep '^BRIDGE_BEARER_TOKEN=' "$TMP" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
  rm -f "$TMP"
  trap - EXIT
fi

if [[ -z "$TOKEN" ]]; then
  echo "ERROR: extracted BRIDGE_BEARER_TOKEN is empty." >&2
  exit 1
fi
if [[ "${#TOKEN}" -lt 24 ]]; then
  echo "WARNING: token is only ${#TOKEN} chars; double-check this is the right value." >&2
fi

cp -p "$ENV_FILE" "$BACKUP_FILE"
echo "[info] backed up to $BACKUP_FILE"

# Idempotent write: replace the existing key, or append if missing.
if grep -q '^BRIDGE_BEARER_TOKEN=' "$ENV_FILE"; then
  # Escape any &/\/ for sed safety; embed via | delim.
  ESC_TOKEN="$(printf '%s' "$TOKEN" | sed -e 's/[\/&|]/\\&/g')"
  sed -i "s|^BRIDGE_BEARER_TOKEN=.*|BRIDGE_BEARER_TOKEN=$ESC_TOKEN|" "$ENV_FILE"
  echo "[info] replaced BRIDGE_BEARER_TOKEN in $ENV_FILE"
else
  printf '\nBRIDGE_BEARER_TOKEN=%s\n' "$TOKEN" >> "$ENV_FILE"
  echo "[info] appended BRIDGE_BEARER_TOKEN to $ENV_FILE"
fi

chmod 600 "$ENV_FILE"

# Restart the bridge so the new env is picked up.
if command -v pm2 >/dev/null 2>&1; then
  echo "[info] restarting claude-bridge to load new env..."
  pm2 restart claude-bridge --update-env >/dev/null
  pm2 save >/dev/null
fi

# Verify: /chat without bearer should now 401.
if command -v curl >/dev/null 2>&1; then
  CODE="$(curl -sS -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:9100/chat || true)"
  if [[ "$CODE" == "401" || "$CODE" == "403" ]]; then
    echo "[ok] bridge now enforces bearer (got HTTP $CODE on /chat without auth)"
  elif [[ "$CODE" == "200" ]]; then
    echo "[warn] bridge still returns 200 without auth — check bridge code reads BRIDGE_BEARER_TOKEN from env" >&2
  else
    echo "[info] bridge returned HTTP $CODE on /chat — manually verify"
  fi
fi

echo "[done] BRIDGE_BEARER_TOKEN provisioned. Restart any other daemons that read .env.agents to pick up the value."
