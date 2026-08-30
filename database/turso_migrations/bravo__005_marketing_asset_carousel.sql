-- ============================================================================
-- bravo__005 — carousels are one post with N slides, and every asset has an author
--
-- WHAT THE LIBRARY ACTUALLY HAS (measured, 2026-08-14)
-- Six carousels are registered as one row each with EXACTLY ONE media row. The
-- other four slides of each were never uploaded — they sit on disk at
-- CMO-Agent/output/carousels/<slug>/slide_1..5.png with a manifest listing all
-- five. The "01/05 · swipe →" a reviewer sees is artwork printed on the cover,
-- promising slides the database has never held.
--
-- THIS IS NOT "SPLIT SLIDE ROWS THAT NEED GROUPING"
-- The task described grouping split rows by title prefix. There are none, and
-- doing it would have been destructive: the six 4:5 rows sharing the "OASIS
-- Oasis" prefix are six DIFFERENT posts — ai-myths, manual-ops-cost,
-- owner-dependency, repetition-01, tried-and-failed, what-we-automate — each
-- with its own slug and its own subject. Merging them by prefix would have
-- collapsed six campaigns into one and lost five of them.
--
-- So the shape added here describes a carousel honestly, and
-- scripts/migrate_carousels.py fills it from the manifests rather than from a
-- guess about titles.
--
-- ---------------------------------------------------------------------------
-- TRANSLATION NOTES
--   asset_type    Deliberately NOT a CHECK. SQLite cannot widen one later
--                 without a full table rebuild, and this vocabulary will grow
--                 (story, reel, thread). marketing_asset.channel is exactly that
--                 mistake already — its CHECK is unwidenable on this backend.
--                 Validated in lib/founders-marketing-core.ts instead, where it
--                 can change with a deploy.
--   media_urls    TEXT holding a JSON array of storage paths in slide order.
--                 The ORDER is the payload — a carousel read out of order is a
--                 different post.
--   author_email  Provenance. Defaults to CC because every row that exists
--                 today predates this column and is his; new rows are stamped
--                 explicitly by the writer. A default is a floor, not a policy.
-- ============================================================================

alter table marketing_asset add column asset_type TEXT NOT NULL DEFAULT 'single_image';
alter table marketing_asset add column media_urls TEXT NOT NULL DEFAULT '[]';
alter table marketing_asset add column slide_count INTEGER NOT NULL DEFAULT 1;
alter table marketing_asset add column author_email TEXT NOT NULL DEFAULT 'conaugh@oasisai.work';

-- Existing rows: describe what they demonstrably are, from `format`, not from a
-- guess. Video is video; everything else is a single image until
-- migrate_carousels.py proves otherwise from a manifest.
update marketing_asset
   set asset_type = case when format = 'video' then 'video' else 'single_image' end
 where asset_type = 'single_image';

-- The Library reads carousels by type; the drain reads slide order.
create index if not exists idx_marketing_asset_type
  on marketing_asset (tenant_id, asset_type, created_at desc);
