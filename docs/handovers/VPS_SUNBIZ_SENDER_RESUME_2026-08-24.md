---
description: "VPS handoff: resume the 2 parked SunBiz outbound senders, fix the stale Daily Plan Generator, retire the leftover VERIFY-3 probe job"
tags: [sunbiz, vps, handoff, cron, shop-out]
last_updated: 2026-08-24
freshness_threshold_days: 30
status: active
---

# VPS Handoff — Resume SunBiz outbound automation (2026-08-24)

> **For CC:** paste the fenced block into the agent session running ON the SunBiz VPS
> (`srv1723601`, `/srv/sunbiz`). Do not SSH from Windows.

## Verified facts behind this handoff (checked live 2026-08-24, Turso `tenant_cron_jobs`)

- The VPS (`srv1723601 (Linux)`) is paired to the **correct** SunBiz tenant
  `aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110` and its executor is **alive** —
  `SunBiz Health Check` ran green at 13:01 UTC today.
- **Parked since 2026-08-06** (`enabled=0`), pending CC's decision — now approved:
  - `SunBiz Shop-Out Sender` (`* * * * *` → `scripts/shop_out_sender.py once`)
  - `SunBiz Cold Outreach Runner` (`*/15 * * * *` → `scripts/cold_outreach_runner.py once`)
- Also parked in the same sweep: `SunBiz Underwriting Orchestrator` (`*/15` →
  `scripts/underwriting_orchestrator.py once`) — report on it, don't enable without CC's yes.
- **Stale despite enabled:** `SunBiz Daily Plan Generator` (`30 6 * * *` →
  `scripts/daily_plan_generator.py once`) — `enabled=1` but `last_run_at` is **2026-08-05**
  (19 days silent). Diagnose and fix.
- **Leftover test job:** `VERIFY 3 — full gate dry-run (one-shot)` is still `enabled=1` and
  fires **daily** 13:12 UTC (a dry-run probe to verify3@sunbizfunding.com). It was a one-shot
  gate verification — retire it.
- Tenant split confirmed clean: **0** SunBiz rows in CC's local empire `cron_jobs` table.

## The paste block

```
You are the agent running on the SunBiz VPS (srv1723601, repos under /srv/sunbiz).
Scope: the SunBiz tenant ONLY (tenant_id aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110).
Do NOT touch any OASIS/CC-tenant rows or repos. VERIFY-FIRST: re-run every
diagnostic live and quote actual output before changing anything; do not trust
this brief's claims blindly — they were true at 2026-08-24 13:05 UTC.

CONTEXT — the tenant split (verified):
- CC's own automations (empire `cron_jobs` table) run on HIS Windows PC. Not your problem.
- SunBiz client automations (`tenant_cron_jobs` table) execute HERE on the VPS via the
  poll executor. That executor is alive — "SunBiz Health Check" ran green today.

WHAT'S BROKEN / PARKED (all in tenant_cron_jobs for the SunBiz tenant):
1. "SunBiz Shop-Out Sender"  — enabled=0 since 2026-08-06 (parked pending the operator's
   decision; CC has now approved resuming). Script: scripts/shop_out_sender.py, args: once.
2. "SunBiz Cold Outreach Runner" — enabled=0 since 2026-08-06 (same park; approved).
   Script: scripts/cold_outreach_runner.py, args: once.
3. "SunBiz Daily Plan Generator" — enabled=1 but last_run_at=2026-08-05 (19 days stale).
   Script: scripts/daily_plan_generator.py, args: once. Something is silently failing or
   the executor skips it — diagnose to root cause.
4. "SunBiz Underwriting Orchestrator" — enabled=0 since 2026-08-06 (parked in the same
   sweep). REPORT its state + what re-enabling would do; do NOT enable it without CC's
   explicit yes.
5. "VERIFY 3 — full gate dry-run (one-shot)" — a leftover one-shot verification probe still
   firing DAILY (13:12 UTC). Retire it: set enabled=0.

PHASE 0 — PULL LATEST:
  cd /srv/sunbiz/sunbiz-agent && git status && git pull --ff-only
  (and /srv/sunbiz/ceo-agent if present). If a pull is NOT fast-forward, STOP and report
  what diverged — do not discard VPS-local changes blindly.

PHASE 1 — DIAGNOSE (read-only, report before editing):
  a. Query tenant_cron_jobs for the SunBiz tenant and quote the 5 rows above as they are NOW.
  b. Daily Plan Generator: run `python scripts/daily_plan_generator.py once` MANUALLY from
     the sunbiz-agent repo, capture the full output/traceback, and identify why it hasn't
     run since Aug 5 (missing dep? env var? exception swallowed by the executor?). Check the
     executor's logs for skipped/error rows for this job name.
  c. Confirm scripts/shop_out_sender.py and scripts/cold_outreach_runner.py exist and
     `python -m py_compile` both cleanly.

PHASE 2 — FIX:
  d. Re-enable the two senders:
       UPDATE tenant_cron_jobs SET enabled=1, updated_at=<utcnow>
       WHERE tenant_id='aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110'
         AND name IN ('SunBiz Shop-Out Sender','SunBiz Cold Outreach Runner');
     (Use the repo's own DB tooling/supabase_tool; never hardcode credentials.)
  e. Fix the Daily Plan Generator root cause found in (b). Keep the fix surgical.
  f. Retire the probe: UPDATE tenant_cron_jobs SET enabled=0 WHERE name LIKE 'VERIFY 3%'
     AND tenant_id='aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110'.

PHASE 3 — VERIFY (proof, not "should work"):
  g. Run each sender manually once: `python scripts/shop_out_sender.py once` and
     `python scripts/cold_outreach_runner.py once`. Expected: clean exit; if there are no
     pending lender rows / due outreach steps, a "nothing to do" log line is SUCCESS.
     Do NOT manufacture a real send to a real lender/prospect as a test.
  h. Confirm the next scheduled tick updates last_run_at with last_run_status='success'
     (quote the row). The Daily Plan fix is proven when its manual run exits clean AND the
     row shows a fresh last_run_at after the next 06:30 tick (or a manual run + row update).
  i. Re-query the table: exactly 2 rows flipped to enabled=1, VERIFY-3 at enabled=0,
     nothing else changed.

PHASE 4 — REPORT back in plain English:
  - Changed: rows/files touched (exact SQL + diffs).
  - Proof: quoted command output for (g), (h), (i).
  - Daily Plan root cause, in one sentence.
  - The Underwriting Orchestrator recommendation (resume or leave parked, and why).

HARD CONSTRAINTS:
- Compliance gates are untouchable: send_gateway's CASL suppression, kill-switch, caps,
  and the draft critic stay exactly as they are. You are resuming schedulers, not
  loosening send rules.
- Never echo secrets/env values into chat or logs.
- No DROP/TRUNCATE/DELETE on any table. UPDATE only the rows named above.
- SunBiz tenant only. If anything you find contradicts this brief, STOP and report
  instead of improvising.
```

## After the VPS run

- Expect `daily_plan_items` to populate again the morning after the Daily Plan fix.
- First real shop-out/cold-outreach sends resume on the next due rows — CASL/suppression
  gates still apply per message, so parked-era backlog won't blast out ungated.
