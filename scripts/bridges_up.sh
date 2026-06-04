#!/usr/bin/env bash
# bridges_up.sh — turnkey starter for CC's Telegram agent bridges.
#
# Brings up every agent Telegram bridge that exists on THIS machine
# (Bravo / Maven / Atlas), persists the PM2 process list, and prints a
# health report. Idempotent: safe to run by hand or from the login
# LaunchAgent (~/Library/LaunchAgents/com.bravo.bridges.plist).
#
# Why this exists: on 2026-06-01 the MacBook rebooted, PM2 was never
# resurrected (no boot hook), and all three agents went dark for days.
# This script + the LaunchAgent are the "won't happen again" fix.
#
# Usage:
#   scripts/bridges_up.sh          # start/refresh the fleet + save + status
#   scripts/bridges_up.sh --boot   # same; the label the LaunchAgent passes
set -uo pipefail

# --- Resolve node/pm2 even under launchd's minimal env -----------------------
# launchd does NOT source the login shell, so PATH is bare. Glob the highest
# installed nvm node version so a node upgrade doesn't break boot resurrection.
NVM_NODE_BIN="$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -1)"
export PATH="${NVM_NODE_BIN:-}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

PM2_BIN="$(command -v pm2 || true)"
if [[ -z "$PM2_BIN" ]]; then
  echo "[bridges_up] FATAL: pm2 not found on PATH (node bin: ${NVM_NODE_BIN:-none})." >&2
  echo "[bridges_up] Fix: ensure nvm + pm2 are installed, then re-run." >&2
  exit 1
fi

CEO="$HOME/CEO-Agent"
CMO="$HOME/CMO-Agent"
# Atlas lives at ~/CFO-Agent on some machines, ~/APPS/CFO-Agent on others —
# mirror scripts/fleet_health.py's multi-path resolution instead of hardcoding.
CFO=""
for _cand in "$HOME/CFO-Agent" "$HOME/APPS/CFO-Agent"; do
  [[ -f "$_cand/ecosystem.config.js" ]] && { CFO="$_cand"; break; }
done

echo "[bridges_up] $(date '+%Y-%m-%d %H:%M:%S') — starting fleet via $PM2_BIN"

# start_bridge <pm2-name> <ecosystem.config.js path>
start_bridge () {
  local name="$1" eco="$2"
  if [[ ! -f "$eco" ]]; then
    echo "[bridges_up] SKIP $name — no ecosystem at $eco"
    return
  fi
  if "$PM2_BIN" describe "$name" >/dev/null 2>&1; then
    "$PM2_BIN" restart "$name" --update-env >/dev/null 2>&1 \
      && echo "[bridges_up] restarted $name (already registered)"
  else
    "$PM2_BIN" start "$eco" --only "$name" >/dev/null 2>&1 \
      && echo "[bridges_up] started $name"
  fi
}

start_bridge "bravo-telegram" "$CEO/ecosystem.config.js"
start_bridge "maven-telegram" "$CMO/ecosystem.config.js"

# Atlas (CFO resolved above across ~/CFO-Agent and ~/APPS/CFO-Agent). Its bridge
# is a Python script (telegram_bridge.py), not telegram_agent.js.
if [[ -n "$CFO" ]]; then
  start_bridge "atlas-telegram" "$CFO/ecosystem.config.js"
else
  echo "[bridges_up] NOTE: Atlas not deployed here (no CFO-Agent ecosystem) — skipping."
fi

# Persist so `pm2 resurrect` / a manual restart restores the same set.
"$PM2_BIN" save >/dev/null 2>&1 && echo "[bridges_up] pm2 save OK"

echo "[bridges_up] ---- status ----"
"$PM2_BIN" list
