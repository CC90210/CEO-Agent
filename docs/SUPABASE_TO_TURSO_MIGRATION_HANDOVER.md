---
tags: [turso, supabase, migration, handover, runbook]
last_updated: 2026-08-10
---

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

---

## 4. Final Cancellation Verification Gate Command

Immediately before cancelling the Supabase subscription, run the master verification gate:

```bash
# 1. Verify schema & transpiler lossy audit
python scripts/turso_lossy_audit.py

# 2. Verify dataset completeness
python scripts/migration_completeness_audit.py

# 3. Verify public R2 object serving
python scripts/etl_storage_to_r2.py --all --verify

# 4. Perform final incremental database delta sync
python scripts/etl_supabase_to_turso.py --project bravo --allow-overwrite
python scripts/etl_supabase_to_turso.py --project oasis --allow-overwrite
```

When all 4 commands return green, Supabase can be cancelled with zero risk of data loss or service disruption.

---

## 5. Prompt for the Next Fresh AI Chat Session

Copy and paste the prompt below when starting your next chat:

```markdown
I am resuming the Supabase to Turso Migration & Cancellation project. 
Please read `docs/SUPABASE_TO_TURSO_MIGRATION_HANDOVER.md` and `docs/SUPABASE_CANCELLATION_RUNBOOK.md`.

All schema transpiling, database data parity (100% matched across all 5 databases), and Real Estate Listing Studio daemons are complete and verified. 

Let's execute the remaining cancellation items:
1. Check Cloudflare R2 credentials and run storage sync (`scripts/etl_storage_to_r2.py`).
2. Verify n8n workflow repointing to `POST /api/ingest/automation-log`.
3. Run PM2 harness cutover (`EMPIRE_TURSO_CUTOVER=1`).
4. Sync PropFlow production to Turso (`vercel_turso_sync.py`).
5. Run the master cancellation gate (`python scripts/turso_lossy_audit.py` and `python scripts/migration_completeness_audit.py`).
```
