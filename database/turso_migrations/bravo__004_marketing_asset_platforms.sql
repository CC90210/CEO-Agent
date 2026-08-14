-- ============================================================================
-- bravo__004 — marketing_asset.platforms: where a piece ACTUALLY went
--
-- CC: "it's only posting to Instagram." Maven's handover named the cause:
-- every backfilled row reads INSTAGRAM because `channel` is a single value and
-- a queue item that goes to all six platforms has no channel it can honestly
-- declare, so it takes 'organic-instagram' and the true list survives only in a
-- media label.
--
-- WHY NOT "JUST WIDEN THE CHECK"
-- Two reasons, and the first is fatal on its own:
--
--   1. It does not fix the problem. `channel` holds ONE value. Adding
--      'organic-linkedin' lets an asset claim LinkedIn INSTEAD of Instagram —
--      it still cannot say "this went to six places". The report stays wrong,
--      just wrong in a new direction.
--
--   2. It is not reachable safely. SQLite has no ALTER TABLE ADD CONSTRAINT, so
--      widening a CHECK means rebuilding the table: seven indexes, a STORED
--      generated column (`track`) whose CASE would also need extending, and
--      seven child tables holding foreign keys into it. scripts/
--      apply_turso_migration.py blocks DROP TABLE by design, and going around
--      that guard to reshape a live 43-row table with live children is not a
--      trade worth making for a fix that does not fix anything.
--
-- So `channel` keeps its meaning — the PRIMARY channel, and the input to the
-- generated `track` column that the Studio pipeline groups by — and `platforms`
-- carries the truth about distribution.
--
-- ---------------------------------------------------------------------------
-- TRANSLATION NOTES
--   jsonb        TEXT holding a JSON array, same as marketing_publish_intent.
--                platforms. Readers already accept either an array or a JSON
--                string.
--   DEFAULT '[]' An empty array means "nowhere yet", which is true of a draft
--                and is a different fact from NULL ("we never recorded it").
--                Writers still supply the real value — a default is a floor,
--                not a policy. Learned from tenant_invites.expires_at, whose
--                Postgres default did not survive its port and silently broke
--                every invite for months.
-- ============================================================================

alter table marketing_asset add column platforms TEXT NOT NULL DEFAULT '[]';

-- Backfill from the only truth the old schema captured: the primary channel.
-- Deliberately NOT inventing a six-platform list for historic rows — Maven's
-- cron did send several of them wider than this, but which ones is not
-- recoverable from the data, and a plausible fabricated list is worse than an
-- honest narrow one. Rows published from here on are stamped by the drain with
-- the platforms that actually accepted them.
update marketing_asset
   set platforms = case channel
         when 'organic-instagram' then '["instagram"]'
         when 'organic-facebook'  then '["facebook"]'
         when 'organic-tiktok'    then '["tiktok"]'
         when 'organic-youtube'   then '["youtube"]'
         when 'paid-meta'         then '["meta"]'
         when 'paid-google'       then '["google"]'
         else '[]'
       end
 where platforms = '[]';

-- The drain and the Library both read this per asset.
create index if not exists idx_marketing_asset_platforms
  on marketing_asset (tenant_id, published_at desc)
  where published_at is not null;
