# VPS Phase 1 Deploy Prompt — Adon MCA brief infrastructure

> Paste everything between the triple-dashes into your VPS Claude Code chat.
> Two `<FILL_IN>` placeholders inside if Twilio/Anthropic creds still need
> provisioning — but Phase 1 itself only requires Anthropic for the Sentinel.
> Twilio is not part of Phase 1.

---

You are a Claude Code agent on CC's SunBiz Funding VPS (Ubuntu 22.04,
srv1723601, `sunbiz` user). CC + Bravo just shipped Phase 1 of Adon's
MCA follow-up architecture brief (commits: CEO-Agent `1cc17da`,
SunBiz-Agent `a8d4f4b` after rebase, oasis-command-center `12a0c63` —
dashboard deploys automatically via Vercel). Your job is to deploy the
agent-side changes to this VPS and verify them end-to-end.

## What landed in this push

**CEO-Agent (Business-Empire-Agent → ceo-agent/) — `1cc17da`:**
- `scripts/integrations/send_gateway.py` — added 5 new pre-send gates
  (manual_pause, sentinel_pause, send_window, reply_since_outbound,
  inter_touch_gap) + surfaced CASL suppression in `can_act()`. Gate
  count went from 5 to 10. Each gate fails closed on DB error.

**SunBiz-Agent (sunbiz-agent/) — `a8d4f4b`:**
- `scripts/sentinel.py` (NEW) — merchant-reply sentiment scorer. Polls
  inbound `lead_interactions` every 60s, scores -100..+100 via Claude
  Haiku + deterministic signal modifiers, maintains rolling avg of last
  5 inbounds per lead. On rolling avg ≤ -30: sets
  `lead.data.sentinel_pause_until = now+7d`, emits BRAVO_SENTIMENT_PAUSE
  event, fires Telegram alert. On new score ≥ +20: clears active pause.
- `scripts/import_mca_leads.py` (NEW) — bulk-importer for Adon's MCA
  web-form spreadsheet. Maps multi-position funding history, multi-phone,
  PII-safe SSN handling (last-4 + hash only) into tenant_records.data.

**oasis-command-center (Vercel) — `12a0c63`:**
- `lib/sunbiz-stage-meta.ts` — `LEAD_PIPELINE_STAGES` expanded from 9 to
  14 (added: funded, renewal_eligible, ghost, renewed_elsewhere, opted_out).
- `components/leads/MCAProfilePanel.tsx` (NEW) — surfaces MCA-specific
  lead fields in the pipeline detail drawer.

## Scope — strictly SunBiz infrastructure

Touch ONLY:
- `/srv/sunbiz/ceo-agent` + `/srv/sunbiz/sunbiz-agent`
- `/srv/sunbiz/ceo-agent/.env.agents` (the shared secrets file)
- The `sunbiz` user's PM2 instance — add ONE new daemon (`sunbiz-sentinel`)
- Supabase rows scoped to `tenant_id=aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110`

Do NOT touch:
- `~/CMO-Agent`, `~/APPS/CFO-Agent`, or any non-SunBiz repo
- The dashboard repo `oasis-command-center` (Vercel handles it)
- Database schema migrations (Phase 1 uses jsonb fields only; no DDL)

## Step 1 — Pull the latest

Fast-forward only; if either repo is dirty, STOP and report.

```bash
cd /srv/sunbiz/ceo-agent && git fetch origin && git status --short
cd /srv/sunbiz/ceo-agent && git log --oneline HEAD..origin/main | head -5
cd /srv/sunbiz/ceo-agent && git pull --ff-only origin main

cd /srv/sunbiz/sunbiz-agent && git fetch origin && git status --short
cd /srv/sunbiz/sunbiz-agent && git log --oneline HEAD..origin/main | head -5
cd /srv/sunbiz/sunbiz-agent && git pull --ff-only origin main
```

After pull, verify the new files landed:

```bash
ls -la /srv/sunbiz/sunbiz-agent/scripts/sentinel.py
ls -la /srv/sunbiz/sunbiz-agent/scripts/import_mca_leads.py
grep -c "_check_sentinel_pause\|_check_manual_pause\|_check_inter_touch_gap\|_check_send_window\|_check_reply_since_last_outbound" /srv/sunbiz/ceo-agent/scripts/integrations/send_gateway.py
# Expect: the grep returns at least 5
```

Install the new spreadsheet dependency. `import_mca_leads.py` needs
`openpyxl` (just added to SunBiz-Agent requirements.txt):

```bash
sudo -u sunbiz /srv/sunbiz/ceo-agent/.venv/bin/pip install openpyxl
sudo -u sunbiz /srv/sunbiz/ceo-agent/.venv/bin/python -c "import openpyxl; print(f'openpyxl {openpyxl.__version__}')"
# Expect: a version string like "openpyxl 3.1.x"
```

Make sure the import landing directory exists for Step 7:

```bash
sudo -u sunbiz mkdir -p /srv/sunbiz/imports
sudo -u sunbiz chmod 750 /srv/sunbiz/imports
```

## Step 2 — Sanity check existing creds

Sentinel needs ANTHROPIC_API_KEY. Phase 1 does NOT need Twilio.

```bash
cd /srv/sunbiz/ceo-agent && /srv/sunbiz/ceo-agent/.venv/bin/python -c "
from lib.secret_loader import load_env
env = load_env()
k = (env.get('BRAVO_ANTHROPIC_API_KEY') or env.get('ANTHROPIC_API_KEY') or '').strip()
print(f'anthropic_key_present: {bool(k)}')
print(f'anthropic_key_len: {len(k)} (expect 100+ for real key)')
print(f'anthropic_key_prefix: {k[:14] if k else \"(missing)\"}')
"
```

If `anthropic_key_len < 50`, the key is a placeholder. Ask CC to paste the
real key in the chat and write it to `.env.agents` as BOTH
`ANTHROPIC_API_KEY` and `BRAVO_ANTHROPIC_API_KEY` (the codebase reads
either). After write: `chmod 600` and `sudo -u sunbiz pm2 restart all
--update-env`.

## Step 3 — Smoke test the Sentinel (no DB writes)

Standalone scoring test — exercises the LLM call and deterministic modifiers
without touching production data.

```bash
cd /srv/sunbiz/sunbiz-agent
/srv/sunbiz/ceo-agent/.venv/bin/python scripts/sentinel.py score \
  --text "stop emailing me you idiots, this is harassment" --json
# Expect: score ~-100, source=llm, frustration_signals includes
#         "profanity:idiot" + "hard_stop_keyword:stop"

/srv/sunbiz/ceo-agent/.venv/bin/python scripts/sentinel.py score \
  --text "Hey, thanks for following up — I'd love to chat tomorrow if you're free?" --json
# Expect: score ~+50 to +80, source=llm, positive_signals non-empty
```

If both pass: Sentinel scoring is wired correctly. If `source=fallback` on
both: ANTHROPIC_API_KEY is wrong — see Step 2.

## Step 4 — One-pass Sentinel run against production inbounds

Real run — touches the DB. Scores any unscored inbound merchant replies
from the last 48h. If avg drops below -30 for any lead, it WILL pause that
lead and send a Telegram alert. That's the intended behavior.

```bash
cd /srv/sunbiz/sunbiz-agent
/srv/sunbiz/ceo-agent/.venv/bin/python scripts/sentinel.py once
```

Expected output:
```
[ISO timestamp] run_once: scored=N paused=M recovered=K errors=E
```

If `scored=0` and there are no errors: no fresh inbounds in the last 48h
(normal). If `errors>0`: read `/srv/sunbiz/sunbiz-agent/state/sentinel.log`
for the failure mode.

## Step 5 — Start the Sentinel daemon under PM2

```bash
cd /srv/sunbiz/sunbiz-agent
sudo -u sunbiz pm2 start /srv/sunbiz/ceo-agent/.venv/bin/python \
  --name sunbiz-sentinel \
  --interpreter none \
  -- scripts/sentinel.py loop --interval 60
sudo -u sunbiz pm2 save
sudo -u sunbiz pm2 list | grep sentinel
# Expect: status=online, restarts=0
sudo -u sunbiz pm2 logs sunbiz-sentinel --lines 10 --nostream
# Expect: "sentinel: starting loop interval=60s window=5"
```

If the daemon crash-loops within 60s: check the log for the failure mode,
fix root cause, do NOT auto-restart with `--force`.

## Step 6 — send_gateway gate verification

Verify the new gates fire correctly. The CLI has a `can-act` subcommand —
we'll create a synthetic test lead with each pause flag, then probe.

```bash
cd /srv/sunbiz/ceo-agent
/srv/sunbiz/ceo-agent/.venv/bin/python -c "
import json
from scripts.lib.secret_loader import load_env
import os
env = load_env()
for k, v in env.items():
    os.environ.setdefault(k, v)

# Confirm the gate functions exist
import sys
sys.path.insert(0, '/srv/sunbiz/ceo-agent/scripts')
from integrations.send_gateway import (
    _check_manual_pause, _check_sentinel_pause, _check_send_window,
    _check_reply_since_last_outbound, _check_inter_touch_gap,
    _check_suppression,
)
print('all 6 new gate functions imported OK')
print('test manual_pause flag:',
      _check_manual_pause({'manual_paused': True},
                          __import__('datetime').datetime.now(
                              __import__('datetime').timezone.utc)))
"
# Expect: "all 6 new gate functions imported OK"
# Expect: "test manual_pause flag: lead manually paused by operator..."
```

If imports fail with `ModuleNotFoundError`: the daemon's venv is out of date.
`pip install -r /srv/sunbiz/ceo-agent/requirements.txt` and retry.

## Step 7 — End-to-end lead import (dry-run first, then real)

CC will SCP Adon's xlsx to the VPS. Run dry-run on 10 rows first to verify
parsing, then full import.

```bash
# Expect CC to drop the file here:
ls -la /srv/sunbiz/imports/MCA_Webforms_June1-5.xlsx

# Dry-run on first 10 rows — no DB writes, prints report
/srv/sunbiz/ceo-agent/.venv/bin/python \
  /srv/sunbiz/sunbiz-agent/scripts/import_mca_leads.py \
  --source-path /srv/sunbiz/imports/MCA_Webforms_June1-5.xlsx \
  --source-tag adon_handoff_2026-06-08 \
  --date-range 2026-06-01..2026-06-05 \
  --dry-run --limit 10
```

Review the dry-run report:
- `parsed`: should equal 10
- `insertable`: ≥ 8 (some rows may be skipped malformed if name+company+contact all blank — that's expected)
- `skipped_duplicate`: 0 if this is the first run; >0 if CC has imported any of these before
- `by_state` + `by_positions`: spot-check the totals make sense

If the report looks healthy, do the full import:

```bash
/srv/sunbiz/ceo-agent/.venv/bin/python \
  /srv/sunbiz/sunbiz-agent/scripts/import_mca_leads.py \
  --source-path /srv/sunbiz/imports/MCA_Webforms_June1-5.xlsx \
  --source-tag adon_handoff_2026-06-08 \
  --date-range 2026-06-01..2026-06-05
```

Final report goes to `/srv/sunbiz/sunbiz-agent/state/import_mca_leads.<timestamp>.json`.
Surface the totals to CC.

## Step 8 — Cross-check the dashboard

The new stages + MCA profile panel deploy automatically via Vercel from the
oasis-command-center push. Confirm they're live by curling the dashboard:

```bash
curl -sS https://oasisai.work/api/health 2>&1 | head -3
# Expect: 200 + {"ok": true, ...}
```

CC will eyeball the dashboard manually:
- /pipeline (SunBiz tenant): kanban shows 14 stage columns including the
  new ones (funded / renewal_eligible / ghost / renewed_elsewhere / opted_out)
- /pipeline/<lead_id> on any imported MCA lead: "MCA Profile" collapsible
  card visible between LeadLifecycleActions and LeadTimelinePanel, showing
  positions / current_funders / EIN / SSN-last-4 / etc.

## Step 9 — Final report

Write to `/srv/sunbiz/phase1-deploy.log`:

```
=== SunBiz Phase 1 Deploy — {ISO timestamp} ===

[1] Repos current                    : YES / NO — {SHA pulled for each}
[2] Anthropic key valid              : YES / NO — {len + prefix}
[3] Sentinel score CLI smoke test    : PASS / FAIL — {hostile + friendly scores}
[4] Sentinel run_once (production)   : scored=N paused=M errors=E
[5] sunbiz-sentinel pm2 daemon       : online / errored / restart-looping
[6] send_gateway new gates imported  : 6/6 / partial / failed
[7] MCA lead import dry-run          : parsed=N insertable=M skipped_dupe=K
[8] MCA lead import (full)           : inserted=N / DEFERRED / SKIPPED
[9] Dashboard /api/health            : 200 / non-200
[10] /pipeline kanban stages         : 14 / fewer (record actual count)

Phase 1 readiness: {%}
```

Plus a one-paragraph plain-English summary to CC: what's operational,
what's deferred, any decisions needed.

## Constraints — non-negotiable

1. **Never echo secret values to chat.** Sentinel + import use the same
   `.env.agents`; you should never need to see a key value.
2. **Never push to git from this VPS.** Anything that needs to land in
   the repo gets committed locally and reported — CC pushes from his PC.
3. **Never flip BRAVO_FORCE_DRY_RUN.** Phase 1 doesn't require it. If
   it's currently `=1`, the Sentinel still scores and pauses (those are
   metadata writes, not sends). The cold-outreach question Adon's brief
   raises (Agent 11 — Lost Deal Reanimator) is explicitly OUT OF SCOPE
   for this deploy.
4. **Sentinel scoring is a DB write.** It updates `lead_interactions.metadata`
   and `tenant_records.data.sentiment_history`. These writes are additive
   and reversible (`UPDATE tenant_records SET data = data - 'sentiment_history'
   WHERE tenant_id = '<sunbiz>'`). But still — verify Step 3 (CLI smoke
   test) is green before letting Step 4 (production run) touch the DB.
5. **If any step fails, halt and report.** Half-deployed gates are worse
   than clearly-broken-and-rolled-back.

Begin Step 1 now.
