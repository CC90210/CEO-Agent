-- ============================================================================
-- bravo__006 — post_analytics.measured_at
--
-- libSQL counterpart of oasis-command-center/database/145. Read that file for
-- the full reasoning; the short version is that this table cannot currently
-- express "dispatched, not yet measured".
--
-- Maven wants to write a post_analytics row at PUBLISH time carrying the
-- Late/Zernio ids and asset_id, so the hourly linker joins on an exact id
-- instead of reconstructing the link from caption text. Right call — it removes
-- both of the linker's honest gaps (LinkedIn rewrites captions, so there is no
-- shared text; 13 assets have hooks too short to bet a view count on).
--
-- But every metric column is `not null default 0`, so such a row does not have
-- "no metrics" — it has ZERO metrics, and zero is already a real value here: 18
-- of 103 live rows genuinely have views = 0. summarize() counts every row as a
-- post and sums every field, so each publish would instantly add a 0-view post
-- to the totals and to "Most seen". The tab would report failure where the truth
-- is "nobody has asked the platform yet".
--
-- last_synced_at cannot carry this: it is not-null with a now() default, so it
-- stamps itself on insert and would read "synced" immediately. It answers "when
-- did we last talk to the API", not "have numbers ever arrived".
--
-- SQLite notes:
--   - TEXT, not timestamptz. The transpiler maps Postgres timestamps to ISO-8601
--     TEXT throughout this database; every other timestamp column here is TEXT.
--   - ADD COLUMN is one of the few ALTERs SQLite supports without a table
--     rebuild, and a nullable column with no default needs no rewrite at all.
--   - No IF NOT EXISTS for ADD COLUMN in libSQL, so a re-run errors rather than
--     no-ops. That is acceptable for a one-shot forward migration and is why the
--     UPDATE below is written to be idempotent on its own.
-- ============================================================================

alter table post_analytics add column measured_at text;

-- Existing rows came FROM the analytics API and have therefore been measured.
-- Backfilling them to NULL would invent an unmeasured state for 103 rows that
-- are nothing of the kind. Idempotent: the WHERE makes a re-run a no-op.
update post_analytics
   set measured_at = last_synced_at
 where measured_at is null;

create index if not exists idx_post_analytics_measured
  on post_analytics (tenant_id, measured_at);
