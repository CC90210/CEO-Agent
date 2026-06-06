# VPS Diagnostic Prompt — SunBiz Portal Health Check

> Paste everything between the triple-dashes into your VPS Claude Code
> chat. The agent will diagnose every layer of the SunBiz portal, fix
> what it can safely, and report what needs your attention. No
> SSH-from-Windows needed.

---

You are a Claude Code agent running on the **SunBiz Funding VPS**
(Ubuntu 22.04, srv1723601, eth0=2.25.159.226). Your job is to verify
that the SunBiz Agent Command Center is fully operational, fix anything
that's safe to fix, and report what's not.

## Scope — what's IN

You own everything that makes the **SunBiz portal** work:
- The bridge runtime at `/srv/sunbiz/ceo-agent` (Bravo's repo, but on
  this VPS it serves only the SunBiz tenant)
- The SunBiz daemons at `/srv/sunbiz/sunbiz-agent` (Solara/Helios)
- The Cloudflare Tunnel (`cloudflared` service)
- PM2 daemons for SunBiz
- The shared `.env.agents` at `/srv/sunbiz/ceo-agent/.env.agents`
- The Supabase rows scoped to `tenant_id = aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110`

## Scope — what's OUT (do NOT touch)

- Maven (CMO-Agent), Atlas (CFO-Agent), Aura, or any other agent's repo
  if it happens to be cloned here. SunBiz is the only tenant this VPS
  serves today.
- The dashboard code at `oasis-command-center` — that lives on Vercel,
  not here. If you find a clone, leave it alone.
- The `oasis-ai-platform` project — that's CC's deprecated marketing
  site, unrelated to SunBiz.
- Cold outreach to the prior community. Even if `cold_outreach_runner`
  is healthy, do NOT manually trigger a campaign. CC's standing rule:
  outreach is operator-initiated only.

## What "operational" means

A SunBiz employee (Ezra, Jordan, Alex, or Emily) logs in at
`https://oasisai.work`, clicks chat, types something, and gets a real
agent reply. Drip sequences fire automatically. Lender Gmail threads
are classified within 5 minutes of a reply landing.

## Diagnostic — run in order

For each section, run the listed commands, record pass/fail, and
ATTEMPT a safe repair if you have a high-confidence fix. Log everything
to `/srv/sunbiz/diagnostic.log` so a re-run shows the delta.

### 1. Repos current

```bash
cd /srv/sunbiz/ceo-agent      && git fetch origin && git status --short && git log --oneline -1
cd /srv/sunbiz/sunbiz-agent   && git fetch origin && git status --short && git log --oneline -1
```

Each should be on `main`, clean, and at the latest origin commit. If a
repo is behind by a clean fast-forward, `git pull --ff-only`. If it has
unpushed local commits or dirty working tree, STOP and surface — do not
discard work.

### 2. Python runtime

```bash
ls /srv/sunbiz/ceo-agent/.venv/bin/python   # must exist
/srv/sunbiz/ceo-agent/.venv/bin/python -c "import supabase, anthropic; print('ok')"
```

If missing or broken, recreate:
```bash
cd /srv/sunbiz/ceo-agent
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd /srv/sunbiz/sunbiz-agent
/srv/sunbiz/ceo-agent/.venv/bin/pip install -r requirements.txt
```

### 3. Credentials

```bash
ls -la /srv/sunbiz/ceo-agent/.env.agents     # must exist, 0600 perms
```

Confirm these keys exist (use `grep -c '^KEY=' .env.agents`, NEVER cat
the file — `secret_guard` will block you and that's the point):

REQUIRED for SunBiz:
- `BRAVO_SUPABASE_URL`
- `BRAVO_SUPABASE_SERVICE_ROLE_KEY`
- `BRAVO_SUPABASE_ANON_KEY`
- `BRIDGE_BEARER_TOKEN`
- `GMAIL_USER` (must be `submissions@sunbizfunding.com` for SunBiz sends)
- `GMAIL_APP_PASSWORD`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`
- `KIXIE_API_KEY` (if Phase 3 Kixie outbound is enabled)
- `TEXTTORRENT_API_KEY` (if Phase 3 TT outbound is enabled)
- `ANTHROPIC_API_KEY`
- `CLOUDFLARE_API_TOKEN` (Zone:DNS + Tunnel:Edit scopes)

If any required key is missing, list them in the report and STOP — do
not generate placeholder values.

### 4. SunBiz doctor

```bash
cd /srv/sunbiz/sunbiz-agent
/srv/sunbiz/ceo-agent/.venv/bin/python scripts/doctor.py --json
```

Every check must report `"status": "ok"`. Common failures + fixes:
- Gmail check fails → confirm `GMAIL_USER` is `submissions@sunbizfunding.com` and `GMAIL_APP_PASSWORD` is current
- Supabase check fails → tenant row missing or service-role key wrong
- Twilio fails → check `TWILIO_FROM_NUMBER` is the verified SunBiz line

### 5. PM2 daemons

```bash
pm2 list
```

Required online (status=online, restarts < 5, uptime > 1m):
- `claude-bridge` — the bridge daemon (CEO-Agent ecosystem)
- `claude-bridge-ping` — keepalive
- `event-router` — V6 event bus
- `sunbiz-sequence-runner` — drip engine
- `sunbiz-lender-response-classifier` — Gmail classifier
- `sunbiz-cold-outreach-runner` — scheduled blast scheduler

If a daemon is missing entirely (not in the list), start it:
```bash
# Bridge + event-router from CEO-Agent
cd /srv/sunbiz/ceo-agent
pm2 start ecosystem.config.js --only claude-bridge,claude-bridge-ping,event-router

# SunBiz daemons from SunBiz-Agent
cd /srv/sunbiz/sunbiz-agent
pm2 start ecosystem.config.js
pm2 save
```

If a daemon is `errored` or restart-looping, fetch the last 50 log
lines and diagnose root cause. DO NOT mask with `--force` restarts.

### 6. Bridge bearer enforcement (security gap CC flagged)

```bash
curl -sS http://127.0.0.1:9100/health -o /dev/null -w "no-auth: %{http_code}\n"
curl -sS http://127.0.0.1:9100/chat -X POST -H "Content-Type: application/json" -d '{}' -o /dev/null -w "no-auth /chat: %{http_code}\n"
```

If `/chat` returns 200 without auth, the bridge is NOT enforcing the
bearer. Verify `BRIDGE_BEARER_TOKEN` is set in `.env.agents` AND the
bridge service has it loaded. The bridge restarts pick up env on next
start, so:

```bash
pm2 restart claude-bridge --update-env
```

Re-test. `/chat` without bearer should now return 401. `/chat` WITH
the bearer (read from .env.agents) should reach the agent.

### 7. Cloudflare Tunnel

```bash
systemctl status cloudflared --no-pager | head -10
```

Must be `active (running)`. If stopped: `systemctl start cloudflared`.
If failed: check `journalctl -u cloudflared -n 50 --no-pager`.

Verify external reachability:
```bash
curl -sS https://bridge.oasisai.work/health -w "\nstatus: %{http_code}\n"
```

Must return 200 + JSON. If 530 / 1033, tunnel registration is broken
— restart cloudflared.

### 8. Supabase row health (per-tenant scope)

The SunBiz tenant id: `aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110`.
Confirm:
- 4 active user_profiles on this tenant (Ezra owner, Jordan admin, Alex
  member, Emily member) — query `user_profiles` filtered by
  `tenant_id`.
- At least 1 row in `drip_sequences` for this tenant (sequence-runner
  has work to do).
- `email_suppressions` table exists (migration 094, shipped today).

Use the read-only Supabase MCP or `psql` via the service-role JWT.
Do NOT mutate.

### 9. Smoke test the end-to-end flow

Open the dashboard from a browser ON the VPS (use `curl` since there's
no GUI):

```bash
curl -sSL https://oasisai.work -o /tmp/dash.html -w "dashboard: %{http_code}\n"
curl -sSL https://oasisai.work/unsubscribe?email=test@example.com -w "unsubscribe: %{http_code}\n"
```

Both should be 200.

POST a test unsubscribe (cleanup is automatic — the SunBiz tenant won't
care about a `test@example.com` row):

```bash
curl -sS -X POST https://oasisai.work/api/unsubscribe \
  -H "Content-Type: application/json" \
  -d '{"email":"vps-diagnostic@example.com","brand":"SunBiz"}'
```

Expect `{"ok":true}`.

### 10. Report

Write the diagnostic result to `/srv/sunbiz/diagnostic.log` in this
exact format:

```
=== SunBiz VPS Diagnostic — {ISO timestamp} ===

[1] Repos current        : PASS / FAIL — {detail}
[2] Python runtime       : PASS / FAIL — {detail}
[3] Credentials          : PASS / FAIL — {missing keys list, never values}
[4] SunBiz doctor        : PASS / FAIL — {failing checks}
[5] PM2 daemons          : PASS / FAIL — {which are down}
[6] Bridge bearer        : ENFORCED / OPEN — {detail}
[7] Cloudflare Tunnel    : RUNNING / DOWN — {detail}
[8] Supabase rows        : OK / DRIFT — {detail}
[9] End-to-end smoke     : PASS / FAIL — {response codes}

Repairs attempted:
- {what you fixed}

Decisions for CC:
- {what needs his input — be specific, link evidence}
```

Then write a one-paragraph summary to stdout addressed to CC, plain
English, no jargon. Lead with whether SunBiz is **operational** or
**degraded**, then list the top 3 things to do next.

## Rules — non-negotiable

1. **Never modify `.env.agents` without explicit CC approval.** Adding
   a missing key is a CC decision (what value, from where).
2. **Never push code changes from this VPS.** Pulls only. If you find a
   bug, propose the fix in the report — don't commit.
3. **Never trigger an outbound send** (email, SMS, RCS) in your
   diagnostics. Smoke-test the routes, not the gateways.
4. **Never run `cold_outreach_runner` against the prior client's lead
   list.** That product is retired per CC's standing rule.
5. **Fail closed on ambiguity.** If you can't tell whether something is
   broken or just degraded, log "uncertain" and ask CC.

When done, exit. Don't loop — CC re-invokes this prompt when he wants a
re-check.
