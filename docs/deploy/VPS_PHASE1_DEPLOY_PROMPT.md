---
tags: [docs, deploy]
last_updated: 2026-07-09
---

> ⚠️ **SUPERSEDED 2026-07-09** — do NOT paste `ANTHROPIC_API_KEY` into any env.
> Auth = `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` (see memory `reference_claude_code_headless_vps_auth`).
> MRR reporting is Atlas-owned.

# VPS Full Deploy Prompt — Adon MCA infrastructure (Phase 1 + Phase 2)

> Paste everything between the triple-dashes into your VPS Claude Code chat.
> One end-to-end deploy: pulls latest code from both SunBiz repos, installs
> deps, registers new daemon under pm2, applies migration 078 (Inquiry
> Welcomer template), runs smoke tests, end-to-end verification.
>
> Supersedes earlier `VPS_PHASE1_DEPLOY_PROMPT` (single-stage Phase 1 prompt).

---

You are a Claude Code agent on CC's SunBiz Funding VPS (Ubuntu 22.04,
srv1723601, `sunbiz` user). CC has shipped Phase 1 + Phase 2 of Adon's
MCA follow-up architecture across three repos. Your job: deploy
everything VPS-side and verify it end-to-end.

## What this deploy lands

**Business-Empire-Agent (ceo-agent/) — tip `ed2bdce`:**
- `scripts/integrations/send_gateway.py` — extended from 5 to 12 pre-send
  gates (kill switches, operating modes, sentinel pause, send window,
  reply-since-outbound, 90-min inter-touch + yellow-flag 180-min, etc.)
- `scripts/pause_controller.py` (NEW) — operator kill switches +
  operating modes, backed by `tenant_records` rows
- `telegram_agent.js` — `/sb` operator panic command suite (Telegram-side)

**SunBiz-Agent (sunbiz-agent/) — tip `2ad664d`:**
- `scripts/sentinel.py` (NEW) — Claude-scored merchant-reply sentiment +
  auto-pause + Telegram alert daemon
- `scripts/import_mca_leads.py` (NEW) — bulk MCA lead importer (xlsx /
  CSV / PDF)
- `scripts/sequence_runner.py` — brand resolved from tenant + reads
  `body_html` from step templates
- `database/078_adon_inquiry_welcomer_template.sql` (NEW) — first of 12
  Adon drip templates. Ships DISABLED — operator activates from
  `/sequences` after smoke-testing.

**oasis-command-center (Vercel, auto-deploys) — tip `e343770`:**
- Per-lead `application_url` auto-stamping on lead create/update
- Lead drawer UI polish (softer borders, refined chip + composer)
- 14 pipeline stages including post-funded lifecycle

## Scope — strictly SunBiz infrastructure

Touch ONLY:
- `/srv/sunbiz/ceo-agent` + `/srv/sunbiz/sunbiz-agent`
- The shared secrets file at `/srv/sunbiz/ceo-agent/.env.agents`
- The `sunbiz` user's pm2 (add ONE new daemon: `sunbiz-sentinel`)
- Supabase rows scoped to `tenant_id=aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110`

Do NOT touch: `~/CMO-Agent`, `~/APPS/CFO-Agent`, the `oasis-command-center`
repo (Vercel handles it), any non-SunBiz tenant rows.

## Step 1 — Pull both repos

```bash
cd /srv/sunbiz/ceo-agent && git fetch origin && git status --short
cd /srv/sunbiz/ceo-agent && git log --oneline HEAD..origin/main | head -10
cd /srv/sunbiz/ceo-agent && git pull --ff-only origin main

cd /srv/sunbiz/sunbiz-agent && git fetch origin && git status --short
cd /srv/sunbiz/sunbiz-agent && git log --oneline HEAD..origin/main | head -10
cd /srv/sunbiz/sunbiz-agent && git pull --ff-only origin main
```

If either repo is dirty, STOP and report what's uncommitted. Do not
discard work.

Verify the new files landed:

```bash
ls -la /srv/sunbiz/ceo-agent/scripts/pause_controller.py
ls -la /srv/sunbiz/sunbiz-agent/scripts/sentinel.py
ls -la /srv/sunbiz/sunbiz-agent/scripts/import_mca_leads.py
ls -la /srv/sunbiz/sunbiz-agent/database/078_adon_inquiry_welcomer_template.sql
```

## Step 2 — Install Python dependencies

```bash
/srv/sunbiz/ceo-agent/.venv/bin/pip install openpyxl pdfplumber
/srv/sunbiz/ceo-agent/.venv/bin/python -c "import openpyxl, pdfplumber; print(f'openpyxl {openpyxl.__version__} / pdfplumber {pdfplumber.__version__}')"
```

Both versions must print. If `pdfplumber` install fails on a slim
Debian, install build deps first: `sudo apt-get install -y libpango-1.0-0
libpangoft2-1.0-0`.

## Step 3 — Anthropic key sanity + optional SSN pepper

Sentinel needs `ANTHROPIC_API_KEY` (or `BRAVO_ANTHROPIC_API_KEY`). Check
what's currently configured:

```bash
/srv/sunbiz/ceo-agent/.venv/bin/python -c "
from lib.secret_loader import load_env
env = load_env()
k = (env.get('BRAVO_ANTHROPIC_API_KEY') or env.get('ANTHROPIC_API_KEY') or '').strip()
print(f'present: {bool(k)}, length: {len(k)}, prefix: {k[:14]}')
"
```

If `length < 50`, the value is a placeholder. Ask CC to paste the real
key in this chat (don't echo back), then append both forms to the
secrets file:

```bash
# When CC pastes the real key, replace REAL_KEY below
bash -c 'cat >> /srv/sunbiz/ceo-agent/.env.agents <<EOF
BRAVO_ANTHROPIC_API_KEY=REAL_KEY
ANTHROPIC_API_KEY=REAL_KEY
EOF'
sudo chmod 600 /srv/sunbiz/ceo-agent/.env.agents
```

Optional — if CC wants SSN dedup hashing across imports (not required;
last-4 alone is sufficient for display):

```bash
PEPPER=$(openssl rand -hex 32)
bash -c "echo SSN_HMAC_PEPPER=$PEPPER >> /srv/sunbiz/ceo-agent/.env.agents"
unset PEPPER
sudo chmod 600 /srv/sunbiz/ceo-agent/.env.agents
```

## Step 4 — SunBiz BRAND_IDENTITY confirmation (one-time)

`scripts/integrations/send_gateway.py` BRAND_IDENTITY["sunbiz"] has two
TODO placeholders that BLOCK external SunBiz emails until resolved.
Inspect:

```bash
grep -A 6 '"sunbiz":' /srv/sunbiz/ceo-agent/scripts/integrations/send_gateway.py
```

If you see `sender_name: "Sun Biz Funding Team"` or `business_address:
"Sun Biz Funding"`, those are placeholders. Real values needed:
- `sender_name`: the human name SunBiz emails sign off as (probably
  "Ezra" given that's the operator). Confirm with CC.
- `business_address`: the legal mailing address for the CASL footer.
  REQUIRED by Canada anti-spam law — without it commercial sends will
  block at the placeholder check.

If CC supplies values, patch the file:

```bash
# Replace these literal strings — CC provides EZRA_NAME and FULL_ADDR
sed -i \
  -e 's|"sender_name": "Sun Biz Funding Team",|"sender_name": "EZRA_NAME",|' \
  -e 's|"business_address": "Sun Biz Funding",|"business_address": "FULL_ADDR",|' \
  /srv/sunbiz/ceo-agent/scripts/integrations/send_gateway.py

# Also remove the placeholder from PLACEHOLDER_BUSINESS_ADDRESSES
grep "PLACEHOLDER_BUSINESS_ADDRESSES" /srv/sunbiz/ceo-agent/scripts/integrations/send_gateway.py
# If you see the frozenset still listing "Sun Biz Funding", remove that
# entry manually with sed or by editing the file.
```

If CC doesn't have the address ready, leave the placeholders in place,
note in the final report that SunBiz commercial email sends will block
until resolved.

## Step 5 — Apply migration 078 (Inquiry Welcomer template)

```bash
cd /srv/sunbiz/sunbiz-agent
/srv/sunbiz/ceo-agent/.venv/bin/python \
  scripts/apply_migration.py database/078_adon_inquiry_welcomer_template.sql
```

Expected output: `Adon Agent 1 (Inquiry Welcomer) template inserted
DISABLED.` If you see `Skipping insert — an Inquiry Welcomer already
exists`, an operator-created duplicate is in the way — surface to CC,
don't overwrite.

Verify the template:

```bash
/srv/sunbiz/ceo-agent/.venv/bin/python -c "
from lib.secret_loader import load_env
import os
for k,v in load_env().items(): os.environ.setdefault(k,v)
from supabase import create_client
sb = create_client(os.environ['BRAVO_SUPABASE_URL'], os.environ['BRAVO_SUPABASE_SERVICE_ROLE_KEY'])
r = sb.table('drip_sequences').select('id, name, enabled').eq('id', 'a4d1a5c2-1111-5811-1111-c87a83d40078').execute()
print(r.data)
"
# Expect: one row, enabled=False
```

## Step 6 — Restart pm2 with new env

```bash
pm2 restart all --update-env
pm2 list
```

Existing daemons should all return to `online` with restarts <= prior +1.
If any errored, pull the log for that specific daemon and surface to CC
— don't auto-restart.

## Step 7 — Register the Sentinel daemon

```bash
cd /srv/sunbiz/sunbiz-agent
pm2 start /srv/sunbiz/ceo-agent/.venv/bin/python \
  --name sunbiz-sentinel \
  --interpreter none \
  -- scripts/sentinel.py loop --interval 60
pm2 save
pm2 list | grep sentinel
# Expect: sunbiz-sentinel, online, restarts=0

sleep 5
pm2 logs sunbiz-sentinel --lines 5 --nostream
# Expect: "sentinel: starting loop interval=60s window=5 tenant=aa04fa1f.."
```

## Step 8 — Smoke tests

### 8a. Sentinel scoring (no DB writes)

```bash
/srv/sunbiz/ceo-agent/.venv/bin/python \
  /srv/sunbiz/sunbiz-agent/scripts/sentinel.py score \
  --text "stop emailing me you idiots, this is harassment" --json | head -10
# Expect: score ~-100, source=llm, frustration_signals includes profanity + hard_stop

/srv/sunbiz/ceo-agent/.venv/bin/python \
  /srv/sunbiz/sunbiz-agent/scripts/sentinel.py score \
  --text "Hey, thanks for following up — I'd love to chat tomorrow if you're free?" --json | head -10
# Expect: score ~+50 to +80
```

If both `source=fallback`, the Anthropic key from Step 3 isn't valid —
fix that first.

### 8b. Operator kill switches (pause_controller)

```bash
/srv/sunbiz/ceo-agent/.venv/bin/python \
  /srv/sunbiz/ceo-agent/scripts/pause_controller.py --json status
# Expect: ok=true, operating_mode.mode='standard', empty pause arrays
```

### 8c. Send-gateway extended gates load correctly

```bash
/srv/sunbiz/ceo-agent/.venv/bin/python -c "
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
# Expect: "all 8 new gate helpers importable"
```

## Step 9 — End-to-end smoke (no real lead created)

Create a synthetic SunBiz lead via the dashboard's API to exercise the
full path: lead insert → `application_url` stamping → event publish →
sequence_runner enrollment check. Template is disabled so NO actual
emails go out.

```bash
# 9a. Confirm SunBiz has at least one enabled intake form (required for
# URL stamping). Schema reference: database/042_tenant_forms.sql — the
# table is actually `forms` (NOT `tenant_forms` despite the migration
# filename) and the active flag is `enabled` (NOT `published`). Earlier
# revs of this prompt had the wrong names — fixed 2026-06-08.
/srv/sunbiz/ceo-agent/.venv/bin/python -c "
from lib.secret_loader import load_env
import os
for k,v in load_env().items(): os.environ.setdefault(k,v)
from supabase import create_client
sb = create_client(os.environ['BRAVO_SUPABASE_URL'], os.environ['BRAVO_SUPABASE_SERVICE_ROLE_KEY'])
r = sb.table('forms').select('id, slug, enabled').eq('tenant_id', 'aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110').eq('enabled', True).execute()
print(f'enabled SunBiz forms: {len(r.data or [])}')
for f in r.data or []: print(f'  {f[\"slug\"]} ({f[\"id\"][:8]}..)')
"
```

If zero enabled forms: report to CC. He needs to publish at least one
form via `/sequences` (or `/forms` if that page is wired) before
`application_url` can be generated. Skip the rest of Step 9.

If at least one form exists:

```bash
# 9b. Verify FORM_LINK_HMAC_KEY is set in env (required for token signing)
grep -c "^FORM_LINK_HMAC_KEY=" /srv/sunbiz/ceo-agent/.env.agents
# Expect: 1
```

If 0, CC needs to set this either in `.env.agents` here OR in Vercel env
(the URL signing happens dashboard-side; this Vercel env is what
matters). Surface to CC.

## Step 10 — Final report

Write to `/srv/sunbiz/full-deploy.log`:

```
=== SunBiz Full Deploy — {ISO timestamp} ===

[1] Repos current                  : YES / NO — ceo-agent={sha}, sunbiz-agent={sha}
[2] openpyxl + pdfplumber installed: YES / NO — versions
[3] Anthropic key valid            : YES / NO — length
[4] SunBiz BRAND_IDENTITY resolved : YES / NO — sender_name + business_address now non-placeholder
[5] Migration 078 applied          : INSERTED / SKIPPED-DUPLICATE / FAILED
[6] pm2 daemons after restart      : N/N online, errored=[list]
[7] sunbiz-sentinel registered     : online / errored / restart-looping
[8a] Sentinel score smoke          : PASS / FAIL — hostile + friendly scores
[8b] pause_controller status       : PASS / FAIL
[8c] send_gateway gate imports     : 8/8 / partial / failed
[9a] SunBiz published forms        : N forms found
[9b] FORM_LINK_HMAC_KEY in env     : YES / NO
[10] Lead import dry-run available : YES (script: import_mca_leads.py) / NO

Production-readiness: {%}
```

Plus a one-paragraph summary for CC: what's operational, what's still
blocked on him (Anthropic key, BRAND_IDENTITY values, published form,
HMAC key in Vercel env), and the single most important next step.

## Constraints — non-negotiable

1. Never echo secret values to chat (Anthropic key, HMAC pepper, etc.).
2. Never push to git from this VPS — CC pushes from his PC.
3. Never flip `BRAVO_FORCE_DRY_RUN=0` if currently `=1` — that's a
   policy decision. Inquiry Welcomer ships disabled anyway, so no
   automated sends would happen yet.
4. Never enable the Inquiry Welcomer template via SQL — operator
   activates from `/sequences` after smoke-testing.
5. If any step fails, halt and report. Don't proceed with steps that
   depend on a failed earlier step.

Begin Step 1 now.

## Obsidian Links
- [[docs/INDEX]]
- [[brain/STATE]]
