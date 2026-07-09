---
tags: [mac-mini, onboarding, bootstrap, daemons, tunnels, florida, always-on]
purpose: Exact, copy-paste bring-up for the dedicated Mac Mini as the empire's always-on local rig. Stitches machine_parity + the PM2 fleet + breeze bridge + Cloudflare tunnels into one sequence, with the daemon-ownership handoff and the apartment→Florida move.
owner: CC (Conaugh McKenna)
last_updated: 2026-07-08
---

# Mac Mini Onboarding — the empire's always-on local rig

> **What this box becomes:** the permanent, always-on host for the Bravo agent fleet,
> the Breeze chat bridge + automations, and the dashboard chat bridge — everything the
> Hostinger VPS was NOT (the VPS is now SunBiz-only). Fronted entirely by Cloudflare
> tunnels, so its public URLs don't depend on its IP → **the apartment→Florida move is
> just "power it off, ship it, power it on."**
>
> **Two phases, on purpose:**
> - **Phase T (train, ~1–2 weeks, apartment):** Mac Mini runs only the *per-machine*
>   services (breeze bridge, dashboard chat bridge). Windows stays the daemon primary.
> - **Phase C (cutover, Florida):** the Mac Mini becomes always-on and TAKES OVER the
>   state-mutating daemons; Windows stops them. Do NOT run both at once (see §7).

Canonical paths on this Mac (load-bearing — the fleet config hardcodes them):
- Bravo harness → **`~/CEO-Agent`** (this repo; `ecosystem.config.js` expects it here)
- Breeze portal + bridge → **`~/APPS/breeze-portal`**

---

## 0. macOS base — make it a server (~20 min)

```sh
# System Settings you MUST set for an unattended server:
#   • Energy: "Prevent automatic sleeping when display is off" = ON; "Start up
#     automatically after a power failure" = ON; disable screen-lock sleep.
#   • Users: enable automatic login (so a reboot comes back without a password).
#   • (optional) Sharing → Remote Login (SSH) ON, for headless access.

# Homebrew + toolchain
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install git gh node python@3.12 ffmpeg cloudflared
npm install -g pm2
# Claude Code CLI (subscription auth — NEVER an API key)
brew install --cask claude   # or the official installer; confirm `claude --version`
```

## 1. Clone the repos to their canonical Mac paths

```sh
gh auth login                                   # authorize CC90210
# Bravo harness → ~/CEO-Agent (ecosystem.config.js hardcodes this path on macOS)
git clone https://github.com/CC90210/Business-Empire-Agent.git ~/CEO-Agent
# Breeze portal + bridge → ~/APPS/breeze-portal
mkdir -p ~/APPS && git clone https://github.com/CC90210/breeze-portal.git ~/APPS/breeze-portal
```
> Do **not** clone/run SunBiz-Agent here — its daemons live on the VPS (always-on,
> single-owner). Cloning it is fine for code reference; starting its PM2 fleet is not.

## 2. Install deps + the agentic bootstrap (the one command)

```sh
# --- Bravo harness (~/CEO-Agent) ---
cd ~/CEO-Agent
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
npm install

# --- Breeze bridge (~/APPS/breeze-portal) ---
cd ~/APPS/breeze-portal/bridge && npm ci
cd ~/APPS/breeze-portal/agent && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```

Then make Claude Code itself agentic on this machine (hooks, guards, memory loop):
```sh
cd ~/CEO-Agent
python3 scripts/machine_parity.py --fix     # renders OS-correct hooks, self-tests, heals deps
#  → do its printed manual-steps list
#  → RESTART Claude Code so the hooks load
python3 scripts/machine_parity.py --check   # repeat until GREEN
```
See `docs/deploy/MACHINE_PARITY_BOOTSTRAP.md` for the full detail. Then:
```sh
node ~/.claude/codex-plugin/scripts/codex-companion.mjs status   # auth Codex if prompted (Rule 8)
# plugins + global config: run the lines in docs/deploy/CAPABILITY_MANIFEST.md
[ -f ~/.claude/CLAUDE.md ] || cp docs/deploy/global-CLAUDE.md ~/.claude/CLAUDE.md
```

## 3. Connect the accounts + fill `.env.agents` (manual, never committed)

Create `~/CEO-Agent/.env.agents` and `~/APPS/breeze-portal/.env.agents`. **Don't guess the
key list** — the parity doctor tells you exactly what's missing, by name:
```sh
cd ~/CEO-Agent && python3 scripts/machine_parity.py --check   # lists missing .env.agents KEYS
```
Fill them from their sources (templates: `~/APPS/breeze-portal/agent/ENV_TEMPLATE.md`,
`docs/ENV_KEYS_TEMPLATE.md`). Account/login checklist:
- [ ] GitHub (`gh auth`) · [ ] Claude subscription (`claude setup-token`) · [ ] Codex/OpenAI
- [ ] Cloudflare (`cloudflared tunnel login`) · [ ] Supabase (Bravo + Breeze projects)
- [ ] Vercel · [ ] Resend (`RESEND_API_KEY`) · [ ] Google / Gmail app password
- [ ] Telegram bot tokens (DM + `CC_AGENT_BOT_TOKEN` for coord) · [ ] Plaid (breeze, optional)

> `BRIDGE_SECRET` in the breeze `.env.agents` MUST equal Vercel `VPS_BRIDGE_SECRET`.

## 4. Cloudflare tunnels — public reachability that survives the move

Tunnels are **outbound-only**, so no port-forwarding / static IP, and the move to Florida
needs zero network config. One tunnel serves both bridges by hostname:
```sh
cloudflared tunnel login                          # grants DNS in oasisai.work
cloudflared tunnel create mac-mini
# ~/.cloudflared/config.yml:
#   tunnel: mac-mini
#   credentials-file: /Users/<you>/.cloudflared/<id>.json
#   ingress:
#     - hostname: breeze-bridge.oasisai.work   # Breeze funder/merchant chat
#       service: http://localhost:3100
#     - service: http_status:404
cloudflared tunnel route dns mac-mini breeze-bridge.oasisai.work
brew services start cloudflared   # or `cloudflared tunnel run mac-mini` under pm2/launchd
```
> Also delete the stale `breeze-bridge.oasisai.work` Public Hostname from the old
> **oasisai** tunnel so the name resolves only to this Mac. (The dashboard chat bridge on
> :9100 discovers itself via the `bridge_pairings` token — it does not need a public
> hostname unless you want to reach it off-LAN.)

## 5. Start the PER-MACHINE services (safe in BOTH phases)

These are per-machine (no single-owner conflict) — start them now, on the Mac Mini:
```sh
# Breeze chat bridge (host-portable config — no edits needed)
cd ~/APPS/breeze-portal/bridge && pm2 start ecosystem.config.js

# Bravo dashboard chat bridge + heartbeat/cron-poller (per-machine, giggly-reef)
cd ~/CEO-Agent && pm2 start ecosystem.config.js --only claude-bridge,claude-bridge-ping,event-router

pm2 save
caffeinate -dimsu &          # keep the box awake even if a display sleeps
```

## 6. Verify FUNCTION (not just "online")

```sh
cd ~/CEO-Agent && python3 scripts/machine_parity.py --check    # GREEN
curl -s http://127.0.0.1:3100/health                            # breeze bridge ok
curl -s https://breeze-bridge.oasisai.work/health               # {"ok":true,"service":"breeze-bridge"}
curl -s https://breeze-portal-mu.vercel.app/api/health          # vps_bridge_health_ok: true
curl -s http://127.0.0.1:9100/health                            # dashboard chat bridge ok
```
Then the human gates: David → `/lender/assistant` → real reply; dashboard shows the bridge
online. Exercise each daemon's real handler once — "online" has masked a per-request crash
before (CROSS_MACHINE_SYNC verify rule).

## 7. Daemon ownership — the one thing you must NOT get wrong

`brain/CROSS_MACHINE_SYNC.md` is law: exactly ONE machine runs the state-mutating daemons.

- **Phase T (training, Windows still on):** Windows keeps `bravo-scheduler`, `bravo-telegram`,
  `bravo-coord`. The Mac Mini runs only §5's per-machine bridges. Running a second scheduler
  against the shared Supabase `cron_jobs` table fires every job **twice**.
- **Phase C (cutover to always-on Mac Mini / Florida):**
  ```sh
  # On Windows, BEFORE handoff:
  pm2 stop bravo-scheduler bravo-telegram bravo-coord && pm2 save
  # On the Mac Mini:
  pm2 start ecosystem.config.js --only bravo-telegram,bravo-coord && pm2 save
  ```
  > **DECISION / one code change:** `bravo-scheduler` is gated `if (IS_WIN)` in
  > `ecosystem.config.js` (line ~122) so it will NOT start on macOS. To make the Mac Mini
  > the full always-on scheduler host, that gate must be relaxed to allow this box (and
  > Windows must never run it again). This is a deliberate one-liner — flag me when you're
  > ready to cut over and I'll make it + update CROSS_MACHINE_SYNC so the ownership is
  > unambiguous. Until then, keep the scheduler on Windows.

## 8. Reboot persistence

```sh
pm2 save
pm2 startup            # run the exact command it prints → installs the launchd auto-start
```
With "start up automatically after a power failure" (step 0) + `pm2 startup` + `pm2 save`,
the whole fleet comes back after any reboot or outage, unattended.

## 9. Apartment → Florida move

Because every public surface is a Cloudflare tunnel (outbound connections, DNS unchanged):
1. `pm2 save` on the Mac Mini (so it resurrects the same fleet).
2. Shut down, ship, plug in at the Florida network, power on.
3. `cloudflared` reconnects from the new IP automatically; `breeze-bridge.oasisai.work` and
   the dashboard bridge keep resolving — **no DNS, port-forward, or config changes.**
4. Complete the Phase C daemon handoff (§7) if not already done — this is when Windows
   permanently stops the `bravo-*` daemons and the Mac Mini owns them.

## Reference
- Agentic bootstrap detail: `docs/deploy/MACHINE_PARITY_BOOTSTRAP.md`
- Plugins / Codex / bins: `docs/deploy/CAPABILITY_MANIFEST.md`
- Daemon ownership law: `brain/CROSS_MACHINE_SYNC.md`
- Breeze bridge specifics: `~/APPS/breeze-portal/docs/MAC_MINI_HANDOFF.md`, `docs/CHAT_PRODUCTION_RUNBOOK.md`
