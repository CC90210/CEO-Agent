---
tags: [turso, supabase, migration, handover, runbook]
last_updated: 2026-08-20
---

> **READ THIS BEFORE THE GATE IN §4 — re-verified 2026-08-20.** Supabase access is
> already gone: `SUPABASE_ACCESS_TOKEN` is absent from the agents env. Three of the
> four commands in the original cancellation gate therefore **cannot run**, and two
> of them fail *because the migration already succeeded*. §4 has been rewritten to a
> gate that actually executes. Do **not** "fix" it by restoring a Supabase token —
> the point of the project is that nothing needs one.

# Supabase to Turso Migration & Cancellation Handover

> **Purpose:** Master handover document for starting a fresh AI agent session to complete the final Supabase cancellation steps.
> **Authoritative Source:** CEO-Agent / Business-Empire-Agent (`C:\Users\User\Business-Empire-Agent`)
> **Status as of 2026-08-10:** Database schema & data parity **100% COMPLETE**. Transpiler lossy audit **PASS**. Real Estate Listing Studio **ONLINE**. Final cancellation gates ready for execution.

---

## 1. Executive Summary & Status Matrix

All 5 empire databases have been fully transpiled, migrated, and verified on Turso/libSQL. Data parity is 100% matched, auth bridges are tested, and the lossy transpiler audit (`scripts/turso_lossy_audit.py`) is merged and passing exit code 0 across all databases.

| Layer | Status | Verification & Evidence |
|---|---|---|
| **Data Parity** | ✅ Complete | `migration_completeness_audit.py` — bravo 161/161, breeze 46/46, oasis 17/17, propflow 43/43, nostalgic 8/8. All 5 DBs match 100%. |
| **Schema & Transpiler Audit** | ✅ Complete | `turso_lossy_audit.py` (PR #63 merged) — `merchant_summary` view ported into Turso; zero NULL secrets/expiries; all dropped CHECKs verified in app code. Exit code 0. |
| **Auth Bridge** | ✅ Complete | `verify_turso_auth.py` 20/20 against live Turso DB without Supabase service-role key. |
| **Real-Estate Marketing Suite** | ✅ Complete & Online | `real-estate-marketing-suite` Turso DB migrated, Vercel secrets synced, PM2 daemons (`rems-render`, `rems-publish`) online & polling Vercel. |
| **Storage (Cloudflare R2)** | ⛔ Code done, needs R2 keys | 4,118 objects archived + hash-verified; R2 adapter in all 4 apps. Needs R2 credentials in `.env.agents`. |
| **n8n Workflows** | ⛔ Needs CC decision | 5 nodes in 3 ACTIVE workflows write to Supabase. Endpoint ready: `POST /api/ingest/automation-log`. |
| **PM2 Harness Cutover** | ⛔ Ready for command | Cutover flag: `EMPIRE_TURSO_CUTOVER=1 pm2 restart ... --update-env`. |
| **PropFlow Production** | ⛔ Ready for command | PR #3 merged; production env sync command ready. |

---

## 2. What Was Completed & Verified in Current Phase

1. **Lossy Audit Gate (`scripts/turso_lossy_audit.py`):**
   - Transpiled-away objects like `merchant_summary` view were identified and manually ported into Turso (restoring 2,373 merchant records for the SunBiz sales pipeline).
   - Audited 36 dropped column defaults across 5 databases. Verified **zero NULL secrets or expiries** in live data.
   - Audited dropped `CHECK` constraints (e.g. `storage_path` tenant prefixes, `phone_last10` SMS opt-out format) and confirmed they are strictly enforced in application routes (`chat-attachments.ts:341`, `sms-inbound/route.ts:281`).
   - Pytest suite `scripts/tests/test_turso_lossy_audit.py` (7 tests) passing 100%.

2. **Listing Studio / Real Estate Marketing Suite:**
   - Dedicated Turso DB created: `real-estate-marketing-suite` (`libsql://real-estate-marketing-suite-cc90210...`).
   - 13 Listing Studio database migrations applied.
   - Vercel production variables (`TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `WORKER_SHARED_SECRET`) synced & build promoted to `READY`.
   - VPS background daemons `rems-render` and `rems-publish` online, authenticated, and polling Vercel in `fork` mode under PM2.

---

## 3. The 5 Remaining Action Items Before Hitting Cancel on Supabase

To shut down Supabase without breaking any live service, execute these 5 remaining steps:

### Item 1: Populate Cloudflare R2 Credentials (CC Action ~3 min)
Add the following keys to `.env.agents` on the local machine and VPS:
```env
CLOUDFLARE_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET=empire-media
R2_PUBLIC_BASE_URL=https://media.oasisai.work
```
Run storage sync:
```bash
python scripts/etl_storage_to_r2.py --project bravo --apply --verify
python scripts/etl_storage_to_r2.py --project propflow --apply --verify
python scripts/etl_storage_to_r2.py --project nostalgic --apply --verify
```

### Item 2: Repoint n8n Terminal Nodes (n8n Workflows)
Three ACTIVE n8n workflows insert into `automation_logs` via the *"Oasis SupaBase"* credential:
- **Shopify Automation**
- **Oasis Voice Agent**
- **GrapeVine Cottage Automations** (paying client workflow)

**Action:** Open n8n, edit the 5 terminal Supabase nodes to make HTTP POST requests to:
`POST https://oasisai.work/api/ingest/automation-log`

### Item 3: Execute PM2 Harness Cutover (`EMPIRE_TURSO_CUTOVER=1`)
Run the following command on the local execution machine:
```bash
EMPIRE_TURSO_CUTOVER=1 pm2 restart bravo-scheduler bravo-telegram bravo-coord claude-bridge claude-bridge-ping event-router --update-env
pm2 save
```
Verify patch:
```bash
python -c "import supabase; print(supabase.create_client.__module__)"
# Expected output: lib.turso_supabase_compat (patched)
```

### Item 4: Sync PropFlow Production Environment
Run Turso env sync for PropFlow production:
```bash
python scripts/integrations/vercel_turso_sync.py --project real-estate-app --db propflow --env production
```
Verify tenant isolation boundary:
```bash
python realestate-App/scripts/verify_tenant_isolation.py
```

### Item 5: APEX / Adon's Agent Alignment
Adon's agent (APEX) logs to `agent_activity`. Ensure APEX writes to Turso directly or via `POST /api/ingest/agent-activity`.

**Status 2026-08-20 — done on the Turso side, verified live.** `agent_activity` is
served from Turso and both agents are writing to it: Bravo posts via
`python scripts/integrations/agent_activity.py post --mirror`, and APEX's rows are
readable with `... peers` / `... claims`. APEX has also shipped its own `leadgen_*`
fleet (12 tables, 124,166 businesses) directly on Turso, so its data path no longer
touches Supabase at all.

Two live caveats worth carrying into the next session:
- **The Mac still thinks it needs Supabase.** It reported "Supabase unreachable — DNS
  resolution failure" while trying to read `agent_activity`. That is not a network
  fault; that host is gone. The Mac's `.env.agents` was never migrated to Turso. See
  the Mac repair message in the 2026-08-20 session notes.
- **The Telegram coordination bot is contended.** A duplicate poller (the Mac) fights
  this rig for `CC_AGENT_BOT_TOKEN`, producing a repeating 409 and dropped group
  messages. Until one machine owns the token, the `agent_activity` **table** is the
  reliable Bravo↔APEX channel, not the chat.

---

## 4. Final Cancellation Verification Gate Command

### Why the original gate is dead (verified 2026-08-20)

The gate written on 2026-08-10 compared Turso **against a live Supabase**. That
comparison is no longer possible, and its impossibility is not a regression — it is
the migration having finished. Measured, not assumed:

| Original command | Result today | Why |
|---|---|---|
| `turso_lossy_audit.py` | ✅ **exit 0, PASS** | Reads Turso only. Still the real gate. |
| `migration_completeness_audit.py` | ❌ `ERROR: SUPABASE_ACCESS_TOKEN absent` | Counts rows on BOTH sides; the Supabase side is unreachable. |
| `etl_storage_to_r2.py --all --verify` | ⛔ cannot run | Needs `CLOUDFLARE_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`. `capability_probe check cloudflare` → **NOT CONFIGURED**. |
| `etl_supabase_to_turso.py` | ❌ `SourceUnavailable` (`scripts/etl_supabase_to_turso.py:103`) | It *reads from Supabase*. There is nothing left to read. |

A gate that can never return green is worse than no gate: it either blocks the
operator indefinitely or teaches them to cancel without verifying. **Do not restore a
Supabase token to make these pass.** The question changed. It is no longer "does
Turso match Supabase" — that can never be re-asked — it is **"does Turso independently
satisfy every consumer?"**

### The gate that actually runs

```bash
# 1. Nothing the transpiler dropped is unaccounted for.  (verified PASS 2026-08-20)
python scripts/turso_lossy_audit.py

# 2. The whole agent harness is turnkey on Turso across every runtime.
#    11 slices: boundary, guards, live-health, lockstep, model-call, routing.
python scripts/harness_eval.py

# 3. Turso answers as the live backend, with the expected surface.
python scripts/integrations/turso_tool.py --json status

# 4. Auth works with NO Supabase service-role key present.
python scripts/verify_turso_auth.py

# 5. No code path still expects a live Supabase. Any hit here is a real blocker;
#    `supabase_tool.py` and `BRAVO_SUPABASE_*` are the Turso COMPAT SHIM and are
#    expected — a raw `*.supabase.co` URL or `SUPABASE_ACCESS_TOKEN` read is not.
grep -rn "supabase\.co\|SUPABASE_ACCESS_TOKEN" scripts/ --include=*.py | grep -v _archive
```

Green on 1–4, and 5 returning only the retired ETL/audit scripts, means every live
consumer is served by Turso. Supabase can be cancelled at that point; the ETL and
parity-audit scripts are *expected* to break, because their source is gone.

### Retire, do not repair

These exist only to serve a migration that is over. Cancelling Supabase is what makes
them permanently non-functional, which is correct:
`scripts/etl_supabase_to_turso.py`, `scripts/migration_completeness_audit.py`,
`scripts/etl_storage_to_r2.py` (once R2 is populated and verified once).
Move them to `scripts/_archive/` rather than leaving them to look like live tooling —
an agent that finds a runnable-looking script will run it and read the failure as a
system fault.

---

## 5. Prompt for the Next Fresh AI Chat Session

Copy and paste the prompt below when starting your next chat:

```markdown
I am resuming the Supabase to Turso migration & cancellation project.
Read `docs/SUPABASE_TO_TURSO_MIGRATION_HANDOVER.md` §4 FIRST — the original
verification gate is dead and §4 explains why. Do NOT restore a Supabase token
to make old commands pass; Supabase access is already gone and that is the
intended end state.

Establish ground truth before doing anything:
  python scripts/turso_lossy_audit.py        # expect PASS, exit 0
  python scripts/harness_eval.py             # expect ALL GREEN
  python scripts/integrations/turso_tool.py --json status

Then work only the items still genuinely open:
1. Cloudflare R2 — `capability_probe check cloudflare` reports NOT CONFIGURED.
   Needs CLOUDFLARE_ACCOUNT_ID + R2_ACCESS_KEY_ID + R2_SECRET_ACCESS_KEY +
   R2_BUCKET in .env.agents (CC action), then one verified storage sync.
2. n8n — 2 client webhooks remain (Oasis Voice Agent; GrapeVine Cottage, a
   churned client). Replacement endpoint POST /api/ingest/automation-log is
   proven. Confirm before assuming either still matters.
3. PropFlow production env sync.
4. Archive the migration-only scripts (§4 "Retire, do not repair") so no agent
   mistakes them for live tooling.

Report what you VERIFIED with command output, not what you assume. If a
document contradicts a live command, the command wins and the document is the
bug — say so instead of working around it.
```
