---
tags:
  - automation
  - cron
  - implementation-plan
---

Related: [[scripts/core/cron_engine.py]], [[docs/audits/2026-09-16-command-center-automation-inventory.md]], [[database/turso_migrations/bravo__108_cron_owner_agent_key.sql]]

# Command Center Automation Inventory Repair Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore the Command Center's complete scheduled-automation inventory, make ownership and toggle state durable and auditable, install the one missing registered Maven job, and align Maven's displayed contract with GEN-10.

**Architecture:** Keep the two legitimate scheduler lanes separate: `tenant_cron_jobs.enabled` remains the bridge-polled tenant lane, while `cron_jobs.is_active` remains the Empire scheduler lane. The API merges them only for a verified platform operator, normalizes both into one UI shape, and uses a durable `cron_jobs.owner_agent_key` with name inference only for legacy compatibility. Background workers remain a separate health/control surface.

**Tech stack:** Python 3.12, pytest, Turso/libSQL migrations, TypeScript, Next.js 15 App Router, React 19, Cloudflare Workers.

## Task 1: Lock the failure and ownership contract with red tests

**Files:**

- Modify: `scripts/tests/test_cron_seed_jobs.py`
- Modify: `oasis-command-center/tests/cron-empire-row.test.ts`
- Create: `oasis-command-center/tests/automation-inventory-contract.test.ts`
- Modify: `oasis-command-center/tests/_suite.mjs`

1. Require every seed to resolve to a durable owner and pin all six verified Maven jobs to `maven`.
2. Assert the missing `Carousel Media Retention` job is a Maven seed and Maven's carousel description says GEN-10.
3. Assert a stored owner wins over inference, legacy rows still infer, and `next_run_at` survives normalization.
4. Assert operator email configuration augments rather than replaces the canonical CC address.
5. Assert GET fails closed on an Empire query error and selects durable ownership.
6. Assert Empire PATCH is tenant-scoped, verifies the readback, returns the normalized shape, and audits the mutation.
7. Assert the UI sends the row source and only reports success after authoritative state is returned.
8. Run the targeted tests and capture the expected failures before implementation.

## Task 2: Add durable ownership and reconcile the source registry

**Files:**

- Create: `database/turso_migrations/bravo__108_cron_owner_agent_key.sql`
- Modify: `scripts/core/cron_engine.py`
- Modify: `scripts/tests/test_cron_seed_jobs.py`

1. Add `cron_jobs.owner_agent_key TEXT NOT NULL DEFAULT 'bravo'` and a tenant/owner/active index.
2. Backfill the six verified Maven rows by exact name and update the live Maven carousel description to the GEN-10 contract in the same ledgered migration.
3. Add explicit `owner_agent_key` metadata to every seed, with the six Maven jobs assigned to `maven` and all remaining current Empire jobs assigned to `bravo`.
4. Include ownership in seed inserts and documentation drift so new rows and existing rows cannot diverge silently.
5. Keep the retired Windows `MavenSchedulePosts` trigger disabled and do not create daemon duplicates.

Migration 108 is one-shot DDL because libSQL does not support `ADD COLUMN IF NOT EXISTS`. A normal rerun with the identical checksum is skipped by `schema_migrations`. If execution is interrupted after the column is added but before the ledger receipt is written, do not blindly rerun the `ADD COLUMN`: verify `owner_agent_key` with `PRAGMA table_info(cron_jobs)`, apply the remaining tenant-scoped updates and index statement individually, verify ownership/description drift is zero, then reconcile the migration ledger with the file's actual checksum and statement count.

## Task 3: Repair the Command Center read and control paths

**Files:**

- Modify: `oasis-command-center/lib/operator-credentials.ts`
- Modify: `oasis-command-center/lib/cron-empire-row.ts`
- Modify: `oasis-command-center/app/api/cron-jobs/route.ts`
- Modify: `oasis-command-center/app/api/cron-jobs/[id]/route.ts`
- Modify: `oasis-command-center/components/automations/CronJobsManager.tsx`
- Modify: `oasis-command-center/lib/agent-catalog.ts`

1. Recognize the canonical, configured, and admin operator emails as a union.
2. Select and prefer `owner_agent_key`; retain inference only for legacy rows.
3. Fail the complete inventory request if the Empire lane fails instead of returning a plausible partial success.
4. Require the PATCH `source`, scope every Empire read/update/readback by tenant, and refuse non-operator Empire writes.
5. Verify the persisted active state before returning success and write a tenant audit event for both off and on transitions.
6. Parse the authoritative PATCH response in the UI, replace the row with the persisted representation, and surface ambiguous/offline/permission failures.
7. Show the real `next_run_at` value and replace Maven's stale static scheduled-task catalogue with the current registered jobs.

## Task 4: Record the fleet inventory and apply the live migration safely

**Files:**

- Create: `docs/audits/2026-09-16-command-center-automation-inventory.md`

1. Record Turso, seed, Cloudflare/Vercel, Windows, and supervisor inventories with runner, owner, schedule/time zone, active state, and source of truth.
2. Create and verify a pre-migration Turso restore point.
3. Dry-run then apply migration `bravo__108`.
4. Seed only `Carousel Media Retention`; do not reinsert or duplicate existing jobs.
5. Query the live table to prove 37 Empire rows, durable owner counts, GEN-10 description, and the expected active count.

## Task 5: Verify, review, and ship both repositories

1. Run targeted tests, full affected suites, lint/typecheck, and the production build.
2. Inspect both diffs for secrets, tenant isolation, fail-closed behavior, stale comments, and unrelated edits.
3. Run the mandatory independent Codex audit and validator gate.
4. Add changelog entries and explicit rollback notes.
5. Commit and push both feature branches, create/merge reviewed PRs, and deploy the Command Center through its Cloudflare main-branch workflow.

## Task 6: Prove the production behavior through the operator path

1. Capture the pre-fix API result (4 total / 1 active) and post-fix result (41 distinct / 35 active, subject to no concurrent operator changes).
2. In CC's authenticated operator context, verify the grouped UI shows Bravo and Maven and that Maven's card displays schedule, state, last run, next run, run count, and result.
3. Toggle Maven off, refresh/read back `cron_jobs.is_active=0`, prove an audit row exists, and confirm it is excluded from the scheduler's claim query.
4. Toggle Maven back on, refresh/read back `cron_jobs.is_active=1`, and prove the second audit row exists.
5. Capture a production screenshot, check console/network errors, and verify the background-worker surface remains separate and truthful.
6. Sync shared state/session memory and release all coordination leases.

## Rollback Plan

- **Application:** revert the Command Center merge commit and redeploy the previous Cloudflare Worker version.
- **Database:** the new ownership column is additive. If application rollback is required, leave it in place; old code ignores it. Restore the pre-migration snapshot only if migration verification shows data corruption.
- **New schedule:** disable or delete only the newly inserted `Carousel Media Retention` row if its first live execution exposes a runner defect. Do not alter other scheduler rows.
- **Trigger:** roll back immediately for broken auth, cross-tenant visibility, failed toggle persistence/auditing, API 5xx on the operator inventory, or a material Worker error-rate increase.
