-- bravo__110_cron_owner_reconciliation.sql
-- Complete durable owner reconciliation after immutable migration 108.
--
-- Migration 108 introduced the non-null owner column and assigned the six
-- known Maven jobs. This forward migration covers recognizable Atlas, Aura,
-- and future Maven marker rows without changing an already explicit owner.

UPDATE "cron_jobs"
SET "owner_agent_key" = 'atlas'
WHERE "owner_agent_key" = 'bravo'
  AND (
    lower(coalesce("name", '')) LIKE 'atlas%'
    OR lower(coalesce("action_type", '')) LIKE 'atlas\_%' ESCAPE '\'
  );

UPDATE "cron_jobs"
SET "owner_agent_key" = 'aura'
WHERE "owner_agent_key" = 'bravo'
  AND (
    lower(coalesce("name", '')) LIKE 'aura%'
    OR lower(coalesce("name", '')) LIKE '%pow wow%'
    OR lower(coalesce("action_type", '')) LIKE 'morning\_powwow%' ESCAPE '\'
  );

UPDATE "cron_jobs"
SET "owner_agent_key" = 'maven'
WHERE "owner_agent_key" = 'bravo'
  AND (
    lower(coalesce("name", '')) LIKE 'maven%'
    OR lower(coalesce("action_type", '')) LIKE 'maven\_%' ESCAPE '\'
    OR lower(coalesce("name", '')) LIKE '%marketing%'
    OR lower(coalesce("name", '')) LIKE '%carousel media retention%'
    OR lower(coalesce("name", '')) LIKE '%post analytics%'
    OR lower(coalesce("name", '')) LIKE '%library post%'
    OR lower(coalesce("name", '')) LIKE '%training corpus%'
    OR lower(coalesce("name", '')) LIKE '%publish drain%'
    OR lower(coalesce("name", '')) LIKE '%content%'
    OR lower(coalesce("name", '')) LIKE '%caption%'
    OR lower(coalesce("name", '')) LIKE '%exemplar%'
  );
