---
tags: [docs, playbooks, client, breeze, maintainer, mac-mini]
purpose: CC's operator runbook for maintaining the BreezeAdvance deployment on their Mac Mini — where everything lives, how to connect, and the exact cd + spawn-Claude commands to fix or change each part. This is the first CLIENT maintainer playbook; the pattern generalizes (see CLIENT_PLAYBOOK_TEMPLATE.md).
owner: CC (Conaugh McKenna)
last_updated: 2026-07-08
---

# Client Maintainer Playbook — BreezeAdvance

> **When to open this:** you (CC) need to fix or change something on Breeze's autonomous
> agent system, remotely (SSH) or in person at the Mac Mini. This tells you where to `cd`
> and how to spawn the Claude maintainer agent to make the change. **Bravo/the CEO harness
> is the maintainer; the Breeze agents are the "employees" it maintains.**

## 0. Model in one paragraph

Breeze's stack is **theirs** (own GitHub org, own Cloudflare account, `breezeadvance.com`,
own Supabase). It runs on a **dedicated Mac Mini**. The **software** is `breeze-portal`
(Vercel + Supabase-cloud). The **AI employees** are autonomous cron jobs on the Mac Mini that
write results + a run-record. **You maintain it by spawning Claude (the Bravo harness) on the
box, `cd`-ing to the right repo, making the change, and shipping.** Everything is behind a
Cloudflare tunnel, so location (apartment → Florida) doesn't matter.

## 1. Connect

```sh
# Remote (from your laptop):
ssh <you>@breeze-mac        # e.g. add to ~/.ssh/config: Host breeze-mac / HostName <tailscale-or-LAN-ip>
# In person: just open Terminal on the Mac Mini.
```

## 2. Where everything lives (the map)

```
~/APPS/breeze-portal            ← the software (portal + bridge + agents + tools)
   ├─ bridge/                   ← the chat bridge (PM2 "breeze-bridge", :3100)
   ├─ agents/                   ← aria (merchant chat), mistral (funder chat), + the employee
   │    └─ <employee>/brain/    ← the autonomous employee's persona + SOPs
   ├─ agent/tools/*.py          ← read-only data tools the agents use
   ├─ supabase/migrations/      ← DB schema (0065 agent_runs, 0066 interactions, 0067 sequences)
   └─ .env.agents               ← Breeze creds (bridge secret, Supabase, Claude token) — never commit
~/breeze-scheduler (or in-repo) ← the daemon that runs the AI employees on intervals
```

PM2 fleet on this box: `pm2 list` → `breeze-bridge` (chat) + `breeze-scheduler` (employees).

## 3. Spawn the maintainer to make a change

The pattern is always: **`cd` to the repo → run `claude` → describe the change → let it ship.**

```sh
# Change the SOFTWARE (portal UI, a route, the Command Centre):
cd ~/APPS/breeze-portal && claude
#   e.g. "wire the Comms-log tab to the interactions table and deploy"

# Change an AGENT's persona/SOPs (aria/mistral/<employee> brain):
cd ~/APPS/breeze-portal && claude
#   e.g. "tighten mistral's underwriting memo to always show with-us leverage"
#   then verify: node agents/tools/doctor.mjs

# Change an autonomous EMPLOYEE / its schedule:
cd ~/APPS/breeze-portal && claude
#   e.g. "add a nightly portfolio-risk employee that writes agent_runs"
#   then restart the daemon:  pm2 restart breeze-scheduler && pm2 save
```

> The Claude you spawn is the **Bravo/CEO maintainer harness** (its guards + skills), not a
> Breeze employee. It reads `CLAUDE.md`, follows the same safety rules, and ships via git
> (Vercel auto-deploys the portal). Confirm-before-money/outbound still applies.

## 4. Common tasks cookbook

| You want to… | Do this |
|---|---|
| **Deploy a portal change** | `cd ~/APPS/breeze-portal` → make the change (or via Claude) → `git push` (Vercel auto-deploys) → verify `https://app.breezeadvance.com/api/health` |
| **Merchant/funder chat is down** | `curl -s localhost:3100/health` → if bad: `pm2 restart breeze-bridge`; then `curl https://bridge.breezeadvance.com/health` |
| **An AI employee failed** | `pm2 logs breeze-scheduler --lines 80 --nostream`; check `agent_runs` (status='failed') via `python agent/tools/... ` or the Agent tab |
| **See what the employees did** | Command Centre → `/lender/ops/agent` (reads `agent_runs`), or query `agent_runs` directly |
| **Restart everything** | `pm2 restart all && pm2 save` |
| **Health check the box** | `cd ~/APPS/breeze-portal` → `node agents/tools/doctor.mjs`; on the maintainer harness: `python3 scripts/machine_parity.py --check` |
| **Add/edit a drip sequence** | edit `sequences` rows (via Claude or the Automations tab); the `breeze-scheduler` picks up due steps |
| **Apply a new migration** | in the Breeze Supabase SQL editor, run the new `supabase/migrations/00NN_*.sql` (DB is Breeze-owned) |

## 5. Safety (unchanged from the harness)

- The guards still apply on the maintainer: `secret_guard` (no reading `.env` files), `exec_guard`
  (no destructive SQL / force-push), `state_guard`.
- **Autonomous employee sends stay DRAFT-gated** until you explicitly open each — money + CASL
  + legal exposure. Approvals/funding/term-changes are human-only.
- Claude runs on **CC's subscription** (`CLAUDE_CODE_OAUTH_TOKEN`), never an API key. If the
  employees silently stop producing, re-check that token for the service user first
  (see `reference_claude_code_headless_vps_auth`).

## 6. Moving the box (apartment → Florida)

Tunnels are outbound-only: `pm2 save` → power off → ship → power on at the new network →
`cloudflared` reconnects, `bridge.breezeadvance.com` unchanged. Then re-run the health check (§4).

## Related
- Bring-up: `Business-Empire-Agent/docs/deploy/MAC_MINI_ONBOARDING.md`, `breeze-portal/docs/MAC_MINI_HANDOFF.md`
- Reusable pattern: `docs/playbooks/CLIENT_PLAYBOOK_TEMPLATE.md`
- [[docs/playbooks/INDEX]] · [[docs/playbooks/04-pause-and-rollback]]
