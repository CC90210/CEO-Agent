# RUNBOOK — Personal Bridge Tunnel (CC's home machine → oasisai.work)

> **Why this exists:** the OASIS Command Center on `oasisai.work` is served
> by Vercel. CC's personal agents (Bravo, Atlas, Maven, Aura, Hermes,
> Life-Preservation) run on his Windows home machine via `claude-bridge`
> at `localhost:9100`. Vercel server-side fetches cannot reach
> `localhost` on CC's machine — so the dashboard's `/api/bridge/*` proxy
> currently forwards every request to the SunBiz VPS instead. That's why
> picking **Bravo + Gemini CLI** from his OASIS portal works (CEO-Agent
> happens to be cohabited at `/srv/sunbiz/ceo-agent`) but **Atlas /
> Maven / Aura / Hermes / Life-Preservation** all return
> `agent_not_paired_locally` — those repos only exist on his home
> machine, not on the SunBiz VPS.
>
> The fix: a Cloudflare Tunnel from CC's home machine to a public URL
> (e.g. `bridge-cc.oasisai.work`). The same pattern SunBiz uses
> (`bridge.oasisai.work` → SunBiz VPS). Once the tunnel is up, the
> per-tenant resolver shipped in commit `<TBD>` reads
> `tenants.custom_fields.bridge_url` for CC's OASIS tenant and routes
> his bridge traffic to his home machine instead of the SunBiz VPS.

## Prerequisites

- `cloudflared` CLI installed on the Windows home machine
- Cloudflare account with the `oasisai.work` zone (already in CC's
  Cloudflare per the SunBiz tunnel setup)
- Bridge daemon (`claude-bridge`) already running and healthy on
  `localhost:9100`. Verify with `pm2 status claude-bridge`.
- `CLOUDFLARE_TOKEN` is in `.env.agents` (per
  `reference_cloudflare_api_in_env_agents.md`), so DNS upserts can be
  scripted via `scripts/integrations/cloudflare_admin.py`.

## Phase 1 — create the tunnel (one-time, on the home machine)

Run in PowerShell on CC's Windows home machine (NOT the VPS):

```powershell
# 1. Authenticate cloudflared with your Cloudflare account (browser flow)
cloudflared tunnel login

# 2. Create the tunnel
cloudflared tunnel create bridge-cc

# Note the tunnel UUID it prints. Save it.
# Example: Created tunnel bridge-cc with id 12345678-aaaa-bbbb-cccc-DDDDDDDDDDDD

# 3. Configure the tunnel — create %USERPROFILE%\.cloudflared\config.yml:
```

Contents of `C:\Users\User\.cloudflared\config.yml`:

```yaml
tunnel: <UUID from step 2>
credentials-file: C:\Users\User\.cloudflared\<UUID>.json

ingress:
  - hostname: bridge-cc.oasisai.work
    service: http://localhost:9100
  # Catch-all (required) — any non-matching request returns 404
  - service: http_status:404
```

Then back in PowerShell:

```powershell
# 4. Point the public DNS at the tunnel
cloudflared tunnel route dns bridge-cc bridge-cc.oasisai.work

# 5. Verify
cloudflared tunnel info bridge-cc
```

## Phase 2 — run the tunnel as a Windows service

```powershell
# As an Administrator PowerShell:
cloudflared service install
sc.exe start cloudflared
sc.exe query cloudflared    # should show RUNNING
```

The service auto-starts on boot. The tunnel stays up as long as the
machine is awake and online.

## Phase 3 — generate the per-tenant bearer token

Generate a strong random bearer token for the OASIS tenant. This is
DIFFERENT from the SunBiz `BRIDGE_BEARER_TOKEN` — keep them separate so
a compromise of one doesn't bleed across.

```powershell
# Python on the home machine — same .venv used by the bridge:
& C:\Users\User\Business-Empire-Agent\.venv\Scripts\python.exe -c `
  "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the token. You'll set it in two places (Phase 4 + Phase 5).

## Phase 4 — install the bearer on the home-machine bridge

Edit `C:\Users\User\Business-Empire-Agent\.env.agents` and add:

```
BRIDGE_BEARER_TOKEN=<the token from Phase 3>
```

(The bridge already reads this env var; SunBiz reuses the same variable
name but on a different machine. CC's home machine has its own
`.env.agents`.)

Restart the bridge so it picks up the new env:

```powershell
pm2 restart claude-bridge
pm2 logs claude-bridge --lines 20
```

The log should show the bridge accepting POSTs only when the
`Authorization: Bearer <token>` header matches. Test from the home
machine:

```powershell
# Without bearer — should 401
curl -X POST http://localhost:9100/chat -H "content-type: application/json" `
  -d '{"agent":"bravo","messages":[{"role":"user","content":"ping"}]}'

# With bearer — should accept and start streaming
curl -X POST http://localhost:9100/chat `
  -H "content-type: application/json" `
  -H "Authorization: Bearer <token>" `
  -d '{"agent":"bravo","messages":[{"role":"user","content":"ping"}]}'
```

## Phase 5 — install the bearer in Vercel (for the proxy to forward)

In Vercel project settings for `agent-dashboard` → Environment Variables
→ Production:

```
BRIDGE_BEARER_TOKEN_OASIS=<the same token from Phase 3>
```

The variable name uses the tenant slug — `OASIS` because CC's personal
tenant has slug `oasis` (UPPER for the env var name). If your tenant
slug is different, use `BRIDGE_BEARER_TOKEN_<YOUR_SLUG_UPPER>`. Per the
new per-tenant resolver, the env var name can also be customized via
`tenants.custom_fields.bridge_bearer_token_env`.

Trigger a Vercel rebuild (or `vercel deploy --prod`) so the new env var
is available to the running functions.

## Phase 6 — wire the tunnel URL into the OASIS tenant

Find your OASIS tenant ID, then update `tenants.custom_fields`:

```bash
# From Bravo's repo
python scripts/integrations/supabase_tool.py select tenants \
  --filter "slug=eq.oasis" --columns "id,slug,custom_fields"

# Then upsert custom_fields with the bridge_url
python scripts/integrations/supabase_tool.py update tenants \
  '{"custom_fields": {"bridge_url": "https://bridge-cc.oasisai.work"}}' \
  --filter "id=eq.<tenant_id>"
```

If your tenant already has other `custom_fields` set, MERGE rather than
overwrite — the supabase_tool.py update is a full-field replace, so you
need to:

1. SELECT the current `custom_fields`
2. Merge `{ bridge_url: "https://bridge-cc.oasisai.work" }` into it
3. UPDATE with the merged blob

## Phase 7 — verify end-to-end

1. Hard-refresh `oasisai.work/agents` (Cmd/Ctrl+Shift+R)
2. Pick **Atlas** → Gemini CLI → ask "who are you?"
   - Expected: Atlas identity (CFO voice, finance/leverage/analysis)
   - If you see `agent_not_paired_locally`: the tunnel isn't reaching
     your home bridge OR `BRIDGE_VPS_URL`'s per-tenant override didn't
     resolve. Check `vercel logs` for the function output.
3. Pick **Maven** → expect Maven (CMO voice)
4. Pick **Aura** → expect Aura
5. Pick **Hermes** → expect Hermes

The SunBiz portal (`submissions` tenant) is UNAFFECTED — it has no
`custom_fields.bridge_url` so it still routes through the global
`BRIDGE_VPS_URL` to the SunBiz VPS. Solara + Helios on `oasisai.work`
when logged in as a SunBiz employee continue to work exactly as before.

## Failure modes + diagnostics

| Symptom | Likely cause | Fix |
|---|---|---|
| `bridge_not_configured` 503 | `tenants.custom_fields.bridge_url` set but `BRIDGE_BEARER_TOKEN_OASIS` env var missing in Vercel | Add the env var, redeploy. The new resolver fails closed on this rather than falling back to SunBiz VPS — intentional |
| `bridge_unreachable` 502 | Tunnel down or `cloudflared` service stopped | `sc.exe query cloudflared`; restart if needed |
| `vps_unauthorized` (from /health) | Bearer mismatch between Vercel `BRIDGE_BEARER_TOKEN_OASIS` and home-machine `.env.agents` `BRIDGE_BEARER_TOKEN` | Re-paste the token; ensure no trailing whitespace |
| `agent_not_paired_locally` (from bridge) | Home machine bridge can't resolve the requested agent slug to a repo path | Verify the agent's repo exists at the expected path per `bravo_cli/agent_roots.py` DEFAULTS |

## Cross-cutting note

This runbook documents the path for CC's PERSONAL OASIS tenant. The
same pattern extends to any future tenant that needs its own bridge:
generate a per-tenant tunnel URL + per-tenant bearer token, store the
URL in `tenants.custom_fields.bridge_url`, store the token in
`BRIDGE_BEARER_TOKEN_<SLUG>` env var on Vercel. The resolver picks the
right pair based on which user authed.

Authoritative resolution code: `lib/bridge-proxy.ts::resolveBridgeTarget`
in the oasis-command-center repo.
