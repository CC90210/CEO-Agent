---
tags: [docs, deploy]
last_updated: 2026-07-09
---

> ⚠️ **SUPERSEDED 2026-07-09** — do NOT paste `ANTHROPIC_API_KEY` into any env.
> Auth = `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` (see memory `reference_claude_code_headless_vps_auth`).
> MRR reporting is Atlas-owned.

# VPS Production-Readiness Prompt — Twilio + Anthropic + Submissions Email Smoke Test

> Paste everything between the triple-dashes into your VPS Claude Code chat.
> Two `<FILL_IN>` placeholders inside — CC pastes the actual values into the
> chat alongside the prompt, the agent writes them to `.env.agents` and
> validates end-to-end.

---

You are a Claude Code agent on CC's SunBiz Funding VPS (Ubuntu 22.04,
srv1723601, non-root user `sunbiz`). Two prior passes have landed:

- **Diagnostic + bearer enforcement** (`docs/deploy/VPS_DIAGNOSTIC_PROMPT.md`)
- **Finalization patches** (`docs/deploy/VPS_FINALIZATION_PROMPT.md` —
  `fix/vps-readiness-patches` merged locally)

CC has now provisioned the last two credentials he was holding —
**Twilio** + **Anthropic** — and wants the full system validated to
production-grade. He specifically wants to confirm the SunBiz portal
can send an email from `submissions@sunbizfunding.com` end-to-end (lead
submits form → dashboard records lead → sequence-runner picks it up →
send_gateway sends via Gmail SMTP).

## Scope — strictly SunBiz infrastructure

Touch ONLY:
- `/srv/sunbiz/ceo-agent` + `/srv/sunbiz/sunbiz-agent`
- `/srv/sunbiz/ceo-agent/.env.agents` (the shared secrets file)
- PM2 daemons in the `sunbiz` user's pm2 (NOT root's)
- Supabase rows scoped to `tenant_id=aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110`

Do NOT touch:
- `~/CMO-Agent`, `~/APPS/CFO-Agent`, or any non-SunBiz repo
- `oasis-command-center` (lives on Vercel, not the VPS)
- The retired prior-client cold-outreach runner

## Step 1 — Pull the latest

Both SunBiz repos. Fast-forward only; if dirty, STOP and report.

```bash
cd /srv/sunbiz/ceo-agent && git fetch origin && git status --short
cd /srv/sunbiz/ceo-agent && git log --oneline HEAD..origin/main | head -10
cd /srv/sunbiz/ceo-agent && git pull --ff-only origin main

cd /srv/sunbiz/sunbiz-agent && git fetch origin && git status --short
cd /srv/sunbiz/sunbiz-agent && git log --oneline HEAD..origin/main | head -10
cd /srv/sunbiz/sunbiz-agent && git pull --ff-only origin main
```

If anything is on a non-`main` branch (`fix/vps-readiness-patches`,
`fix/sms-namespace`, etc.) and was MERGED upstream, check out main and
delete the local branch (`git branch -d <name>`). Don't force-delete
unmerged branches — surface them in the report.

## Step 2 — Provision the two new credentials

CC will paste the actual values into the chat next to this prompt.
Replace each `<FILL_IN>` placeholder below with the literal value CC
provided. Do NOT echo the values back to chat — just confirm "written"
after writing.

Append (or replace if present) in `/srv/sunbiz/ceo-agent/.env.agents`:

```
# Twilio — SunBiz tenant namespace (per CC's blocker-5 decision)
SUNBIZ_TWILIO_ACCOUNT_SID=<FILL_IN_TWILIO_SID>
SUNBIZ_TWILIO_AUTH_TOKEN=<FILL_IN_TWILIO_AUTH>
SUNBIZ_TWILIO_FROM_NUMBER=<FILL_IN_TWILIO_FROM>

# Anthropic — for backend automation paths that call Claude server-side
ANTHROPIC_API_KEY=<FILL_IN_ANTHROPIC_KEY>
BRAVO_ANTHROPIC_API_KEY=<FILL_IN_ANTHROPIC_KEY>
```

(Both `ANTHROPIC_API_KEY` and `BRAVO_ANTHROPIC_API_KEY` get the same
value — the codebase reads `BRAVO_ANTHROPIC_API_KEY` first and falls
back to `ANTHROPIC_API_KEY`. Setting both removes ambiguity.)

After writing:

```bash
chmod 600 /srv/sunbiz/ceo-agent/.env.agents
ls -la /srv/sunbiz/ceo-agent/.env.agents   # confirm -rw-------
pm2 restart all --update-env
pm2 list
```

These commands run as the current user (root on CC's VPS layout; future
tenants with the non-root migration would prefix `sudo -u sunbiz`).

## Step 3 — Doctor sweep

```bash
cd /srv/sunbiz/sunbiz-agent
/srv/sunbiz/ceo-agent/.venv/bin/python scripts/doctor.py --json | head -200
```

Every check must report `"status": "ok"`. Specifically confirm:

- `gmail` → ok (so `submissions@sunbizfunding.com` is reachable)
- `twilio` → ok (Twilio creds valid; from-number verified)
- `anthropic` → ok (Anthropic key valid; one cheap test call lands)
- `supabase` → ok (tenant row + RLS scope correct)
- `bridge` → ok (bearer-enforced, `/chat` returns 200 with auth)
- `cloudflare_tunnel` → ok (bridge.oasisai.work resolves)

If any fail, fix root cause before continuing. Do NOT mask with
`--force` flags or by deleting failing checks.

## Step 4 — PM2 health

```bash
pm2 list
pm2 logs --lines 20 --nostream
```

Required online (status=`online`, restarts <5, uptime >1m):

- `claude-bridge` — CEO-Agent bridge daemon
- `claude-bridge-ping` — keepalive
- `event-router` — V6 event bus
- `sunbiz-sequence-runner` — drip engine
- `sunbiz-lender-response-classifier` — Gmail classifier
- `sunbiz-cold-outreach-runner` — scheduled blast scheduler
- `bridge-lock-heartbeat` (if installed)

If any are in `errored` / restart-loop, pull the last 100 log lines for
THAT daemon, identify root cause, fix, restart `--update-env`. Surface
the diagnosis in the report — don't silently kill or mask.

## Step 5 — Bridge bearer enforcement (regression check)

```bash
# No auth → must return 401
curl -sS http://127.0.0.1:9100/chat -X POST -H "Content-Type: application/json" -d '{}' -o /dev/null -w "no-auth /chat: %{http_code}\n"
curl -sS https://bridge.oasisai.work/chat -X POST -d '{}' -H 'Content-Type: application/json' -o /dev/null -w "external no-auth /chat: %{http_code}\n"

# WITH auth (read token from .env.agents — do NOT echo it) → must return 200
TOKEN=$(grep '^BRIDGE_BEARER_TOKEN=' /srv/sunbiz/ceo-agent/.env.agents | cut -d= -f2-)
curl -sS http://127.0.0.1:9100/chat -X POST -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"messages":[{"role":"user","content":"reply with the word verified"}],"agent":"solara"}' -w "\nauth /chat: %{http_code}\n" | tail -2
unset TOKEN
```

Both no-auth probes MUST be 401. Auth probe MUST be 200 with a real
agent response containing "verified". If anything else, halt and
report.

## Step 6 — End-to-end submissions email smoke test (THE THING CC WANTS)

The point of this whole pass. Validates: dashboard form submit →
Supabase lead row → sequence-runner picks up → send_gateway sends via
Gmail SMTP from `submissions@sunbizfunding.com` → email arrives at the
test inbox.

### 6a — Confirm the gateway is in LIVE mode (not dry-run)

```bash
grep '^BRAVO_FORCE_DRY_RUN=' /srv/sunbiz/ceo-agent/.env.agents
```

Must be `BRAVO_FORCE_DRY_RUN=0`. If `=1`, this is correct for safety
until CC explicitly flips it — STOP here and confirm with CC before
sending real email.

### 6b — Submit a test lead via the public SunBiz form

Use the dashboard's public form URL (NOT direct DB insert — we want
the full path tested):

```bash
# Replace <TEST_INBOX> with an inbox CC owns and can check (his own
# personal email, or a + alias if you have one set up)
TEST_EMAIL="<TEST_INBOX>"

# Trigger the form-submission API directly. The same path the public
# /f/<tenant>/<form>/<lead_token> page POSTs to.
curl -sS -X POST https://oasisai.work/api/forms/submit \
  -H "Content-Type: application/json" \
  -d "{
    \"tenant_slug\": \"sunbiz-funding\",
    \"form_slug\": \"initial-lead-capture\",
    \"lead_token\": \"prod-readiness-smoke-$(date +%s)\",
    \"submission\": {
      \"name\": \"Production Readiness Smoke Test\",
      \"company\": \"SunBiz QA\",
      \"email\": \"$TEST_EMAIL\",
      \"phone\": \"+15551234567\",
      \"monthly_revenue\": 50000,
      \"funding_needed\": 100000,
      \"time_in_business\": 36
    }
  }" -w "\nstatus: %{http_code}\n"
```

Expect HTTP 200 + `{"ok": true, "lead_id": "..."}`. Record the
`lead_id` for the next step.

### 6c — Watch the sequence-runner pick it up

```bash
pm2 logs sunbiz-sequence-runner --lines 50 --nostream
```

Within 60 seconds you should see a log line referencing the new lead
ID and an "email queued" or "email sent" event. If you only see
"enqueued, dry-run", `BRAVO_FORCE_DRY_RUN` is still `=1` — fix 6a.

### 6d — Confirm Gmail SMTP delivered

```bash
/srv/sunbiz/ceo-agent/.venv/bin/python -c "
import sys, os
sys.path.insert(0, '/srv/sunbiz/ceo-agent/scripts')
from lib.secret_loader import load_env
env = load_env()
print('GMAIL_USER:', env.get('GMAIL_USER'))
print('FROM matches submissions@sunbizfunding.com:', env.get('GMAIL_USER') == 'submissions@sunbizfunding.com')
"
```

Then check the Supabase `lead_interactions` table for the row
created by the send:

```bash
/srv/sunbiz/ceo-agent/.venv/bin/python /srv/sunbiz/ceo-agent/scripts/supabase_tool.py query \
  --table lead_interactions \
  --where "tenant_id=eq.aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110&order=created_at.desc&limit=3" \
  --select "id,lead_id,type,direction,channel,subject,agent_source,created_at"
```

The top row should be `type=email_sent`, `direction=outbound`,
`channel=email`, `agent_source=sunbiz-sequence-runner`, subject line
matching the SunBiz first-touch template, created in the last few
minutes.

### 6e — Operator confirms the email actually landed

Tell CC in the final report:
> "Smoke test email sent from submissions@sunbizfunding.com to
> <TEST_INBOX>. Sequence-runner logged delivery at <ISO timestamp>.
> Supabase `lead_interactions` row id `<id>`. CC, confirm the email
> arrived in <TEST_INBOX> and the subject + body look correct."

The agent CANNOT verify inbox arrival from the VPS — only CC can.

## Step 7 — Cron-job sanity check

```bash
/srv/sunbiz/ceo-agent/.venv/bin/python /srv/sunbiz/ceo-agent/scripts/supabase_tool.py query \
  --table tenant_cron_jobs \
  --where "tenant_id=eq.aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110&order=next_run_at.asc&limit=10" \
  --select "id,name,enabled,next_run_at,last_run_at,last_status"
```

For each row:
- `enabled=true` → expect `next_run_at` in the future (not >24h ago)
- `last_status` → expect `success` or `null` (no `error` rows)

If any are stale or erroring, surface in the report. Do NOT
auto-disable or auto-fix — these are CC's policy calls.

## Step 8 — Final report

Write to `/srv/sunbiz/production-readiness.log`:

```
=== SunBiz VPS Production Readiness — {ISO timestamp} ===

[1] Repos current                : YES / NO — {sha pulled for each repo}
[2] SUNBIZ_TWILIO_* set          : YES / NO
[3] ANTHROPIC_API_KEY set        : YES / NO (both ANTHROPIC_API_KEY + BRAVO_ANTHROPIC_API_KEY)
[4] Doctor check                  : ALL OK / FAILING — {list failing}
[5] PM2 daemons online           : N/N — {any errored?}
[6] Bridge bearer enforced       : YES / NO (internal + external 401)
[7] Bridge auth call works       : YES / NO (200 + "verified" response)
[8] BRAVO_FORCE_DRY_RUN          : 0 / 1
[9] Submissions email smoke test : SENT / FAILED — {lead_id, interaction_id, ISO timestamp}
[10] Cron jobs healthy            : ALL GREEN / list errors
[11] Local branches clean        : YES / NO — {any unmerged?}

Readiness estimate: {%}
```

Plus a one-paragraph plain-English summary to CC:
- What's now operational
- The one thing he needs to confirm manually (email landed in inbox)
- Any non-blocking warnings (cron drift, stale branches, log noise)
- Whether the system is green-light for production-grade operation

## Constraints — non-negotiable

1. **Never echo secret values to chat.** Treat both `<FILL_IN>` values
   as write-once-and-forget. Confirm "written" or "key starts with
   prefix `sk-ant-…`" / `AC…` etc. but never the full value.
2. **Never push to git from this VPS.** If a commit needs to be
   merged, do it locally and report — CC pushes from his PC.
3. **Never trigger an outbound send the operator didn't ask for.**
   The 6b smoke test IS authorized (CC's request); anything beyond it
   needs explicit confirmation.
4. **Never flip `BRAVO_FORCE_DRY_RUN=0` if it's currently `=1`** —
   that's a policy decision, not a fix. Surface in the report.
5. **If any step fails, halt and report.** Do not proceed to later
   steps that depend on a failed earlier step — a half-working
   production setup is worse than a clearly-broken one.

Begin Step 1 now.

## Obsidian Links
- [[docs/INDEX]]
- [[brain/STATE]]
