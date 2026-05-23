---
adr: 0006
title: Multi-employee tenant access to a shared admin bridge
status: accepted
date: 2026-05-23
deciders: [bravo, cc]
supersedes: null
superseded_by: null
---

# ADR-0006 — Multi-employee tenant access to a shared admin bridge

> **STATUS — ACCEPTED 2026-05-23.** CC's open questions answered:
> 1. Employees use admin's CLI subscription by default. Hard requirement.
> 2. Employees can paste their own API key in their personal portal;
>    that key is **private to them** — no other tenant member can read,
>    use, or even see it exists.
> 3. Build now: ship the policy + privacy + UX polish today.
>    Defer cloud-relay infrastructure (Option B) until a real client
>    actually needs it.
>
> Implementation lives in the action items at the bottom of this ADR.

## Context

CC's mental model for client deployments:

> "We're going to set the admin / owner of the company we're working with up with either a local install or a cloud install, with a working machine that stays running 24/7. From that connection, all of their employees can use that bridge, even though they have different accounts. They are connected to that business portal, and that business portal has a machine on file."

The expectation: every employee on the tenant should be able to use chat + CRM updates + backend automations powered by the admin's always-on machine, regardless of which laptop the employee is browsing from.

### What's already built — the parts that already work for multi-employee tenants

1. **Tenant-scoped data on Supabase, accessed by every employee.** Every page is server-rendered against `getAuthedSupabase()` with `auth.uid()` → `user_profiles.tenant_id` → tenant-scoped rows via RLS. Employee B and Admin A see the same dashboard data because they're on the same tenant.

2. **Backend daemon callback channel — `/api/bridge/records/[entity]`.** Tenant's bridge_token authenticates writes to `tenant_records` from anywhere. The closed-loop endpoint VPS-hosted Python daemons POST/PATCH to. So a daemon running on the admin's machine OR on a per-client VPS can update the dashboard's CRM without carrying the dashboard's service-role key. This is the architecture CC implicitly wants — the admin's machine pushes updates that all employees see in the dashboard. **It works today.**

3. **Cloud chat path — `/api/chat`.** Employees who DON'T have a local bridge route through Vercel `/api/chat` which uses the tenant's saved provider API key (Anthropic / OpenAI / Google / OpenRouter). Native tool_use loop on Anthropic; cloud-only tool surface. **Works today for every employee on a tenant with a saved key.**

4. **Per-employee personal API keys + workspace defaults.** `agent_model_config` table supports `(tenant_id, agent_key)` rows with `user_id IS NULL` (workspace default — every employee uses this) plus `(tenant_id, agent_key, user_id = <employee>)` rows (per-user override). Resolution priority in `lib/chat-auth.ts:resolveChatContext` picks per-user first, falls back to workspace. **Works today.**

5. **Multi-machine pairings per tenant.** `bridge_pairings` table allows multiple `(tenant_id, machine_fingerprint)` rows. Pairing dedupes per machine. **Schema supports it; no UX gap.**

6. **Heartbeat freshness via Postgres.** Dashboard's `getBridgeOnline(tenantId)` queries the freshest `last_seen_at` across the tenant's pairings. If ANY machine in the tenant is heartbeating, the dashboard sees the bridge as online. **Tenant-scoped, not user-scoped — correct.**

### What's NOT built — the gap

The chat surface's CLI-via-bridge path is **localhost-only**:

- `lib/agent-roots.ts` line 18 hardcodes `BRIDGE_CHAT_BASE = "http://127.0.0.1:9100"`.
- `ChatWidget.tsx` (line 820) probes `${BRIDGE_CHAT_BASE}/health` from the browser. Only succeeds if the browser is running on the same machine as the bridge.
- Browser POST to `${BRIDGE_CHAT_BASE}/chat` for CLI chat is direct localhost; no proxy.

**Implication:** Employee B browsing from Machine B will see "BRIDGE OFFLINE" even if Admin A's bridge is heartbeating on Machine A. Employee B's chat would auto-route to the cloud path (`/api/chat`), which uses the tenant's API key and tenant-cloud-tools — but **NOT** the admin's local Claude Code / Codex / Gemini subscription, and **NOT** local file access.

So:
- ✓ Employee can chat (via cloud, with tenant API key)
- ✓ Employee sees dashboard / metrics / CRM data updated by admin's bridge
- ✓ Backend daemons keep running on admin's machine, posting updates that every employee sees
- ✗ Employee CANNOT chat using admin's Claude/Codex/Gemini CLI subscription
- ✗ Employee CANNOT trigger local-file tools (read/write/script) on admin's machine via chat

The gap is **CLI-chat-from-employee-browser**. Everything else CC described works.

## The decision to make

Whether to close the gap, and how. Three options:

### Option A — Accept the current model. Employees use cloud chat; admin uses CLI bridge.

- **What ships:** Nothing new. The current architecture is the answer.
- **UX update needed:** ChatWidget should detect "this tenant has a bridge online but it's not on this machine" and show a friendlier message than "BRIDGE OFFLINE" — something like "Bridge running on admin's machine; this session uses cloud chat." Set expectations correctly.
- **Cost:** ~30 minutes of ChatWidget + lib/queries.ts edits.
- **Trade-off:** Loses the CC-stated promise of "employees use admin's bridge for CLI chat." Cloud chat works (tenant API key) but employees can't burn admin's Claude Pro subscription.

### Option B — Cloud-relay (the proper architecture)

Bridge maintains a long-lived outbound websocket/SSE connection to the dashboard. Dashboard proxies employee chat requests to the bridge over that connection. Employee browser → `/api/chat/cli-relay` → tenant's bridge (via the held-open connection) → back through dashboard → employee browser.

- **What ships:**
  - New `bravo_cli/bridge_relay_client.py` — bridge connects to `wss://agent-dashboard-cc90210.vercel.app/api/bridge/relay` on boot, holds it open, re-connects on drop.
  - New `app/api/bridge/relay/route.ts` — Vercel websocket / SSE endpoint that pipes chat requests to the bridge over the held connection. (Vercel websockets are limited; might need a Cloudflare Worker or self-hosted relay between bridge and dashboard.)
  - `BRIDGE_CHAT_BASE` semantics change: browser hits a dashboard URL, not localhost.
  - `bridge_pairings` gets a `relay_session_id` column tracking the active connection.
  - Auth: every chat request through the relay carries `tenant_id + employee auth_user_id` headers; bridge can audit / refuse per-employee.
- **Cost:** ~2-3 days of work. Real infra (websocket lifecycle, reconnect logic, Vercel's limitations on long-held connections).
- **Trade-off:** Bridge needs outbound internet (already true). One bridge = one bottleneck for the tenant. Crash recovery + load balancing become real concerns. But it matches CC's stated model.

### Option C — Tailscale / Cloudflare Tunnel (off-the-shelf relay)

Admin's bridge exposes itself via Tailscale Funnel or Cloudflare Tunnel. Public hostname like `tenant-<tenant-id>-bridge.example.com` resolves to admin's bridge.

- **What ships:**
  - Setup wizard step: "Install Cloudflare Tunnel / Tailscale; we'll wire the public hostname."
  - `bridge_pairings.public_url` column stores the tunnel URL.
  - `BRIDGE_CHAT_BASE` becomes dynamic per-tenant — server-rendered into the page based on the tenant's pairing.
  - Bridge needs to validate JWT'd requests (employee → dashboard → public bridge URL). Adds an auth-middleware layer to the bridge.
- **Cost:** ~1-2 days of work + per-tenant Cloudflare / Tailscale setup. Less custom code than Option B.
- **Trade-off:** Adds an external dependency (Cloudflare / Tailscale) per client. Some clients (corporate IT) may not let employees install Tailscale. But the infra is battle-tested.

## Accepted policy (2026-05-23)

**Default = admin's CLI subscription + admin's bridge tools for every employee.**

Mechanics:
- Admin's machine runs the bridge 24/7. Bridge heartbeats to Postgres; `getBridgeOnline(tenantId)` sees it as online for everyone on the tenant.
- Employee browser opens dashboard, picks chat mode "Auto" or "CLI": chat request routes to admin's bridge (via the cloud-relay path when shipped — until then, employees on a machine that can't reach admin's `localhost:9100` get cloud chat with the tenant's saved API key; ChatWidget surfaces this clearly).

**Personal-key override = private to that employee.**

Mechanics:
- Per-user override row in `agent_model_config` (`user_id = auth.uid()`).
- RLS policy `amc_select_own_and_default` (migration 063, shipping with this ADR): tenant default rows visible to all tenant members; per-user override rows visible ONLY to the owner or to a tenant admin.
- Resolver in `lib/chat-auth.ts:resolveChatContext` already prioritizes per-user → tenant default → platform fallback. No code change needed.
- Encrypted ciphertext was already isolated by encryption (AES-256-GCM via `BRAVO_FIELD_ENCRYPTION_KEY`). Migration 063 closes the metadata leak too — provider name, model choice, last_used_at timestamp, presence-of-override.

**Economics:**
- Admin's Claude Pro / Codex / Gemini subscription gets burned by the whole tenant. Rate limits + flat-rate quota costs land on admin's account. Accepted trade-off — empire's use is unlikely to saturate one operator's quota.
- If quota IS exceeded: ChatWidget surfaces the bridge's `cli_auth_required` / `cli_empty_output` error codes with actionable next steps. Employees paste their own key in Settings → My Agents and chat continues against the (private) personal key.

**Deferred:** Cloud-relay (Option B) and Tunnel (Option C). Re-open when:
- A client onboards and reports CLI-chat-from-remote-employee-browser as a real blocker, OR
- The dashboard's cloud chat fails to satisfy 90%+ of employee chat needs (e.g. operators need actual local-file tools, not just records updates).

## Action items — shipping today

1. **Migration 063** — tighten SELECT RLS on `agent_model_config` so per-user override rows are owner-only. Filed at `database/063_agent_config_read_privacy.sql`. Apply via the Supabase SQL editor or migration tool of choice. **THIS IS THE LOAD-BEARING PRIVACY FIX.**
2. **ChatWidget UX polish** — when `localhost:9100/health` from this browser is unreachable but the tenant has a bridge online elsewhere, render "Bridge runs on `<owner_label>`'s machine; this session uses cloud chat with the tenant API key" instead of "BRIDGE OFFLINE." Helper: query the freshest `bridge_pairings.label` server-side and pass it through to ChatWidget.
3. **Settings → Devices** — surface "your tenant's primary bridge is on `<machine_label>` (owned by `<owner_name>`)" so employees understand the model at a glance.
4. **Setup wizard / client-deploy prompts** — make the admin-bridge model explicit on the first-deploy screen and in the client-onboarding prompts: "One machine in your company stays on 24/7 to power the bridge. Employees connect from anywhere; their personal API keys are private to them."

## Action items — future / on-demand

- **Option B (cloud-relay)** — `bridge_relay_client.py` connects out to `wss://agent-dashboard-cc90210.vercel.app/api/bridge/relay`; held-open. Dashboard proxies CLI chat requests via the connection. Auth: per-employee identity forwarded in request headers; bridge validates against `bridge_pairings.tenant_id`.
- **Option C (Cloudflare Tunnel / Tailscale)** — admin's bridge gets a per-tenant public hostname; `bridge_pairings.public_url` carries it; `BRIDGE_CHAT_BASE` becomes tenant-dynamic.
- Re-open this ADR when the cost of NOT shipping these exceeds the cost of building them.

