# VPS Handoff — VERIFY 3 durable-cron switch + finalization

> Paste this entire file into a fresh Claude Code session on the SunBiz VPS.
> The previous session lost connection mid-handoff. You are picking up
> exactly where it died. Working dir: `/srv/sunbiz/ceo-agent`.

---

## Identity (read first)

You are **Solara** — SunBiz Funding's operations agent, running on the
SunBiz VPS (Linode, Ubuntu). You are NOT Bravo (that's the agent on CC's
Windows machine) and you are NOT the Claude model — you are Solara.

Your entry file is `/srv/sunbiz/ceo-agent/SOLARA.md` — read it before
acting if you need full context.

---

## Where we stand (confirmed by the previous session, before it died)

**Commits (don't touch — already pushed + pulled here):**

- CEO-Agent at `44735ac` — Bravo's `--brand`/`--intent` forwarding +
  `--to-phone` routing fixes for `send_gateway.py` + `bridge_tools.py`.
- SunBiz-Agent at `a65277e` — `IS_SANDBOX=1` persisted in
  `ecosystem.config.js` so Claude Code root execution survives reboots.

**Daemons (verify with `pm2 status`):**

- `claude-bridge` online — fingerprint matches CC's dashboard
  (`6e1f718ea16bdd85`).
- 7/7 daemons online.

**Verification gates (closed by previous session):**

- ✅ **VERIFY 1** — `send_email` bridge tool no longer ships under
  OASIS brand. `--brand sunbiz` forwards correctly; off-hours
  send-window correctly stops the dry test.
- ✅ **VERIFY 2** — `send_sms` bridge tool no longer fails with
  `requires to_phone` error. `--to-phone` routes correctly;
  downstream timezone-gate is the new (correct) stopping point.
- ⏳ **VERIFY 3** — full-gate dry-run scheduled for **13:12 UTC today
  (9:12 AM EDT)**. The previous session registered this via Claude
  Code's `CronCreate` (job `253fedae`), but that scheduler is
  **session-only** — and the previous session **died**, so the job is
  **dead with it**.

---

## Your one task: switch VERIFY 3 to durable `tenant_cron_jobs`

The previous session was about to do this when it lost connection. Pick
it up. CC's exact instruction was: **"yes, switch it to the durable
dashboard-cron"**.

**Why durable:** `tenant_cron_jobs` rows are stored in Supabase. The
bridge poller (`bravo_cli/cron_runner.py`) polls every 60s and fires
matching rows regardless of any Claude Code session state. Survives
reboots, network blips, dead sessions.

### Tenant + constants

```
TENANT_ID = aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110
BRAND     = sunbiz
SCHEDULE  = 12 13 9 6 *   # 13:12 UTC, June 9, any DOW = 9:12 AM EDT today
```

### Step 1 — Register the durable cron row

The action is a `script_run` of `send_gateway.py` with `--dry-run`. The
bridge's cron_runner captures stdout into `last_run_output` and sets
`last_run_status='success'` on exit-0 (every gate passed) or
`'error'` on exit-1 (some gate failed).

```bash
cd /srv/sunbiz/ceo-agent
python scripts/integrations/supabase_tool.py insert tenant_cron_jobs '{
  "tenant_id": "aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110",
  "agent_key": "solara",
  "name": "VERIFY 3 — full gate dry-run (one-shot)",
  "description": "Walks every send_gateway gate (kill-switch, cooldown, daily cap, send-window, brand, intent, CASL suppression, dedup) without sending. Exit-0 = all gates green; output JSON has status=dry_run.",
  "schedule": "12 13 9 6 *",
  "action_type": "script_run",
  "action_payload": {
    "script": "integrations/send_gateway.py",
    "args": [
      "send",
      "--dry-run",
      "--channel", "email",
      "--to", "verify3@sunbizfunding.com",
      "--subject", "VERIFY 3 — full gate dry-run",
      "--body-html", "<p>VERIFY 3 probe — every gate should pass.</p>",
      "--brand", "sunbiz",
      "--intent", "transactional",
      "--agent-source", "solara",
      "--json"
    ]
  },
  "enabled": true
}'
```

Capture the returned `id` UUID — that's the cron job's primary key.

### Step 2 — Smoke-test the exact command locally NOW (don't wait for 9am)

Run the same args directly so you know the command works before the cron
fires it:

```bash
cd /srv/sunbiz/ceo-agent
python scripts/integrations/send_gateway.py send \
  --dry-run \
  --channel email \
  --to verify3@sunbizfunding.com \
  --subject "VERIFY 3 — full gate dry-run" \
  --body-html "<p>VERIFY 3 probe.</p>" \
  --brand sunbiz \
  --intent transactional \
  --agent-source solara \
  --json
```

Expected output (one-line JSON): `{"status": "dry_run", "reason": "dry_run=True, nothing sent", ...}` + **exit code 0**.

If you get a different `status` (e.g. `"blocked"`), the gate that
blocked tells you exactly what to fix BEFORE the 9am fire. Common
non-fatal blocks at 2:30 AM ET: send-window (business hours 9-18 ET)
— but `--dry-run` should bypass that. If it doesn't bypass, the
previous session would have already caught it; treat any block here as
new and investigate.

### Step 3 — Confirm the bridge poller sees the row

Wait ~60s after the insert, then:

```bash
pm2 logs claude-bridge --lines 80 --nostream | grep -iE "cron_runner|tenant_cron|VERIFY 3" | tail -20
```

You should see a poll cycle that includes the new row (probably with a
"not due yet" message — that's correct; it fires at 13:12 UTC).

### Step 4 — Sanity-check the row in Supabase

```bash
python scripts/integrations/supabase_tool.py select tenant_cron_jobs \
  --filter "name=eq.VERIFY 3 — full gate dry-run (one-shot)" \
  --columns "id,schedule,enabled,last_run_at,last_run_status"
```

Expected: 1 row, `enabled=true`, `last_run_at=null` (hasn't fired yet),
`last_run_status=null`.

---

## Report back to CC

When all four steps complete cleanly, respond with **exactly this
shape** (fill in the bracketed values):

```
VERIFY 3 — durable cron registered

- tenant_cron_jobs.id: [uuid from step 1]
- schedule: 12 13 9 6 * (13:12 UTC = 9:12 AM EDT today)
- smoke-test (step 2): exit=0, status=dry_run ✅
- bridge poller (step 3): row picked up at [HH:MM:SS UTC]
- Supabase row (step 4): enabled=true, awaiting fire

What happens at 9:12 AM EDT:
1. cron_runner fires the script_run action
2. send_gateway runs the dry-run walk
3. Result written to tenant_cron_jobs.last_run_output
4. CC reads it from dashboard /automations panel

If any gate fails: last_run_status='error', last_run_error names the failing gate.
If all green: last_run_status='success', last_run_output has the dry_run JSON.

Solara out — session can safely end after this confirmation.
```

---

## Before you end the session

Run state sync:

```bash
cd /srv/sunbiz/ceo-agent
python scripts/state/state_sync.py --note "solara: VERIFY 3 migrated to durable tenant_cron_jobs; handoff from dead session complete"
```

Then say **"Handoff complete."** to CC.

---

## Anomalies to surface (don't fix silently)

- `pm2 status` shows anything in `errored` or `stopped` state
- `claude-bridge` log shows `409 Conflict` from Telegram or any
  `BRIDGE_OFFLINE` events in the last 5 minutes
- Smoke-test (step 2) returns `status != "dry_run"` — read the
  `reason` field and surface it verbatim
- supabase_tool.py insert returns an RLS error or schema mismatch —
  surface the exact error, don't retry blindly
- Git working tree is dirty in `/srv/sunbiz/ceo-agent` or
  `/srv/sunbiz/sunbiz-agent` — surface what's modified, don't commit

CC will fix any of these from his side. Your job is to report, not patch
mid-handoff.
