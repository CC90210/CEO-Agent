> ⚠️ **SUPERSEDED 2026-07-09** — do NOT paste `ANTHROPIC_API_KEY` into any env.
> Auth = `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` (see memory `reference_claude_code_headless_vps_auth`).
> MRR reporting is Atlas-owned.

# VPS Full Verify Prompt — end-to-end check that everything is wired

> Paste between the dashes into your VPS Claude Code chat. No inputs
> needed from CC — pure verification, no writes (except a single
> dry-run sync of provision_secrets which is idempotent).
>
> Output: one report at `/srv/sunbiz/verify.log` that tells you
> exactly what's green and what's red, with file:line refs and
> remediation steps for anything that isn't.

---

You are the Claude Code agent on CC's SunBiz Funding VPS (Ubuntu 22.04,
srv1723601). CC has finished entering all credentials via the dashboard
(`oasisai.work/settings`). Your job: prove end-to-end that every part of
the SunBiz outbound infrastructure is wired correctly. No code changes —
this is a verification pass.

Run every step. On any FAIL, capture exact stderr + file:line, surface
in the report, and continue. Don't halt unless explicitly told.

## Scope

Touch ONLY:
- `/srv/sunbiz/ceo-agent` + `/srv/sunbiz/sunbiz-agent` (read-only except
  for the dry-run provision_secrets call)
- Supabase rows scoped to `tenant_id=aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110`
- pm2 status queries

Do NOT touch: `~/CMO-Agent`, `~/APPS/CFO-Agent`, the dashboard repo, any
non-SunBiz tenant rows.

## Step 1 — Repos current

```bash
cd /srv/sunbiz/ceo-agent && git fetch origin && git log --oneline HEAD..origin/main | head -5
cd /srv/sunbiz/sunbiz-agent && git fetch origin && git log --oneline HEAD..origin/main | head -5
```

Expect: zero unpulled commits. If any commits behind, run `git pull
--ff-only origin main` for that repo and note in the report.

## Step 2 — Phase 1 + Phase 2 new files all present

```bash
ls -la \
  /srv/sunbiz/ceo-agent/scripts/pause_controller.py \
  /srv/sunbiz/sunbiz-agent/scripts/sentinel.py \
  /srv/sunbiz/sunbiz-agent/scripts/import_mca_leads.py \
  /srv/sunbiz/sunbiz-agent/database/078_adon_inquiry_welcomer_template.sql
```

All 4 must exist.

## Step 3 — Sync credentials FROM the dashboard

CC has entered Anthropic key + other secrets in the dashboard. They live
encrypted in Supabase. Run the existing sync script to pull them down to
`.env.agents`. This is idempotent.

```bash
cd /srv/sunbiz/ceo-agent
python3 scripts/provision_secrets.py --tenant sun --apply
```

Expect a "✅ Wrote N updated key(s)" line. If N > 0, CC has entered new
credentials since the last sync. If N == 0, everything was already
synced (also a pass).

## Step 4 — Anthropic key sanity

```bash
python3 -c "
from lib.secret_loader import load_env
env = load_env()
k = (env.get('BRAVO_ANTHROPIC_API_KEY') or env.get('ANTHROPIC_API_KEY') or '').strip()
print(f'present: {bool(k)}, length: {len(k)}, prefix: {k[:14]}')
"
```

Expect: present=True, length ≥ 100, prefix starts `sk-ant-api03-`. If
length < 50, the dashboard sync didn't pick up the new key — CC may need
to re-enter via Settings → AI setup.

## Step 5 — Restart pm2 with synced env + Sentinel

```bash
pm2 restart all --update-env
pm2 list
```

If `sunbiz-sentinel` is NOT in the list, register it:

```bash
cd /srv/sunbiz/sunbiz-agent
pm2 start /srv/sunbiz/ceo-agent/.venv/bin/python \
  --name sunbiz-sentinel \
  --interpreter none \
  -- scripts/sentinel.py loop --interval 60
pm2 save
```

Expect all daemons online, restarts < 5, uptime > 30s.

## Step 6 — Sentinel LLM smoke test

```bash
python3 /srv/sunbiz/sunbiz-agent/scripts/sentinel.py score \
  --text "stop emailing me you idiots" --json | head -10
```

Expect: `"source": "llm"` and score around -100. If `"source": "fallback"`,
the Anthropic key isn't valid — Step 4 was a false positive.

## Step 7 — Bridge + bearer enforcement

```bash
# No auth → must be 401
curl -sS http://127.0.0.1:9100/chat -X POST -H "Content-Type: application/json" -d '{}' -o /dev/null -w "no-auth /chat: %{http_code}\n"
curl -sS https://bridge.oasisai.work/chat -X POST -d '{}' -H 'Content-Type: application/json' -o /dev/null -w "external /chat: %{http_code}\n"

# With auth → 200
TOKEN=$(grep '^BRIDGE_BEARER_TOKEN=' /srv/sunbiz/ceo-agent/.env.agents | cut -d= -f2-)
curl -sS http://127.0.0.1:9100/chat -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"messages":[{"role":"user","content":"reply with the word verified"}],"agent":"solara"}' \
  -w "\nauth /chat: %{http_code}\n" | tail -3
unset TOKEN
```

Both no-auth probes MUST be 401. With-auth probe MUST be 200 + an agent
response containing "verified".

## Step 8 — send_gateway extended gates importable

```bash
python3 -c "
import sys
sys.path.insert(0, '/srv/sunbiz/ceo-agent/scripts')
sys.path.insert(0, '/srv/sunbiz/ceo-agent/scripts/integrations')
from integrations.send_gateway import (
    _check_manual_pause, _check_sentinel_pause, _check_send_window,
    _check_reply_since_last_outbound, _check_inter_touch_gap,
    _check_suppression,
)
from pause_controller import check_kill_switches, check_operating_mode
print('all 8 new gate helpers importable')
"
```

## Step 9 — Operator kill switches round-trip

```bash
# Pause an arbitrary test agent
python3 /srv/sunbiz/ceo-agent/scripts/pause_controller.py --json pause agent verify_test --reason "verify pass"

# Confirm it shows in status
python3 /srv/sunbiz/ceo-agent/scripts/pause_controller.py --json status | grep -A 1 verify_test

# Clean up
python3 /srv/sunbiz/ceo-agent/scripts/pause_controller.py --json resume agent verify_test
```

Each command should return `"ok": true`.

## Step 10 — Inquiry Welcomer template present, still disabled

```bash
python3 -c "
from lib.secret_loader import load_env
import os
for k,v in load_env().items(): os.environ.setdefault(k,v)
from supabase import create_client
sb = create_client(os.environ['BRAVO_SUPABASE_URL'], os.environ['BRAVO_SUPABASE_SERVICE_ROLE_KEY'])
r = sb.table('drip_sequences').select('id, name, enabled, trigger_filter').eq('id', 'a4d1a5c2-1111-5811-1111-c87a83d40078').execute()
for row in r.data or []:
    print(f'name=\"{row[\"name\"]}\" enabled={row[\"enabled\"]} trigger={row[\"trigger_filter\"]}')
"
```

Expect one row: name contains "Inquiry Welcomer", enabled=False, trigger
points at stage=hot_lead. If enabled=True, CC has already activated it —
note in the report.

## Step 11 — SunBiz dashboard form pickability

```bash
python3 -c "
from lib.secret_loader import load_env
import os
for k,v in load_env().items(): os.environ.setdefault(k,v)
from supabase import create_client
sb = create_client(os.environ['BRAVO_SUPABASE_URL'], os.environ['BRAVO_SUPABASE_SERVICE_ROLE_KEY'])
r = sb.table('forms').select('id, slug, enabled, tenant:tenants!inner(slug)').eq('tenant_id', 'aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110').eq('enabled', True).execute()
print(f'enabled SunBiz forms: {len(r.data or [])}')
for f in r.data or []:
    tslug = f['tenant'][0]['slug'] if isinstance(f['tenant'], list) else f['tenant']['slug']
    print(f'  slug={f[\"slug\"]} tenant_slug={tslug}')
"
```

Expect ≥ 1 enabled form so application_url stamping has a target. If 0,
CC needs to publish at least one form via /sequences in the dashboard.

## Step 12 — BRAND_IDENTITY placeholder status

```bash
grep -A 6 '"sunbiz":' /srv/sunbiz/ceo-agent/scripts/integrations/send_gateway.py
```

Look for `sender_name` and `business_address` lines. If either still
contains `# TODO: confirm with Ezra`, SunBiz commercial sends will block
at the placeholder gate (send_gateway line 2349). CC needs to either:
- Edit those two strings directly in this file (one-time), OR
- Send me his SunBiz mailing address and I'll generate a patch.

## Step 13 — Bridge + chat-proxy from the dashboard side

The dashboard's chat at `oasisai.work/agents` uses `/api/bridge/chat`
(proxy mode). This means CC doesn't need to enter an Anthropic API key
to use Claude Code / Codex / Gemini CLI from the chat — the proxy
attaches the bearer token server-side. Verify the proxy reaches us:

```bash
curl -sS "https://oasisai.work/api/bridge/health" -o /dev/null -w "proxy /health: %{http_code}\n"
```

Expect 200 (or 401 if your bearer isn't set, which means CC needs to
verify BRIDGE_BEARER_TOKEN on Vercel matches the one in .env.agents).

## Step 14 — Final report

Write to `/srv/sunbiz/verify.log`:

```
=== SunBiz Full Verify — {ISO timestamp} ===

[1]  Repos current                  : YES / NO (ceo-agent={sha}, sunbiz-agent={sha})
[2]  Phase 1+2 files present        : 4/4 / partial
[3]  Credentials sync               : N keys updated / N=0 (already synced)
[4]  Anthropic key valid            : YES / NO (length, prefix)
[5]  pm2 daemons online             : N/N / errored=[list]
[5]  sunbiz-sentinel registered     : online / not registered
[6]  Sentinel LLM smoke             : PASS / FAIL (source, score)
[7]  Bridge bearer enforcement      : PASS / FAIL (no-auth 401, auth 200)
[8]  send_gateway gates importable  : 8/8 / partial
[9]  pause_controller round-trip    : PASS / FAIL
[10] Inquiry Welcomer template      : present + disabled / present + ENABLED / missing
[11] SunBiz enabled forms           : N forms
[12] BRAND_IDENTITY                 : non-placeholder / TODO remains
[13] Vercel proxy /health           : 200 / 401 / other

Production-readiness: {%}
```

Plus a one-paragraph summary for CC: what's green, what's red, the
single most important thing he needs to do next (probably either resolve
the BRAND_IDENTITY TODO or activate the Inquiry Welcomer template via
the dashboard).

## Constraints

- Never echo secret values to chat (Anthropic key, bearer, etc.).
- Never push to git from this VPS.
- Never flip the Inquiry Welcomer enabled=true — that's CC's browser
  action via /sequences.
- If Step 7 fails (bridge bearer rejected), check whether
  BRIDGE_BEARER_TOKEN was rotated on Vercel without updating .env.agents
  here (or vice versa). The two values MUST match.

Begin Step 1 now.
