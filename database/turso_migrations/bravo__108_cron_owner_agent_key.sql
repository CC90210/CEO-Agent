-- bravo__108_cron_owner_agent_key.sql
-- Durable C-suite ownership for the Empire cron registry.
--
-- `owner_machine` answers WHERE a row may execute. `owner_agent_key` answers
-- WHO owns the work in the operator UI. They are deliberately separate.

ALTER TABLE "cron_jobs"
  ADD COLUMN "owner_agent_key" TEXT NOT NULL DEFAULT 'bravo';

UPDATE "cron_jobs"
SET "owner_agent_key" = 'maven'
WHERE "name" IN (
  'Carousel Media Retention',
  'Library Post Linker',
  'Marketing Publish Drain',
  'Maven — Carousel Post',
  'Post Analytics Sync',
  'Training Corpus Ingest'
)
AND "tenant_id" = 'ef8d389e-3f15-43f2-ae00-3660f69a1452';

-- Reconcile the operator-facing contract while the row is already locked for
-- ownership backfill. This is documentation only; schedule/action stay intact.
UPDATE "cron_jobs"
SET "description" = 'Daily 08:00 ET — runs the complete GEN-10 posting chain: verify-published, watch, author-carousels, unstick, generate, plan, deliver-renders, then library-sync. Authors and renders only the six recognized creative families, then books up to two posts at 13:00 and 19:00 UTC for Instagram, LinkedIn and Threads. Family is selected before lane/system/slug and distinct same-day families are preferred; constrained inventory may repeat rather than leave a slot empty. Finished renders go to CC''s Telegram and the founders Library.'
WHERE "name" = 'Maven — Carousel Post'
  AND "tenant_id" = 'ef8d389e-3f15-43f2-ae00-3660f69a1452';

CREATE INDEX IF NOT EXISTS "idx_cron_jobs_tenant_owner_active"
  ON "cron_jobs" ("tenant_id", "owner_agent_key", "is_active");
