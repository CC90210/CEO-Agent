-- 074_tenant_records_last_contact_sync.sql
--
-- Keep tenant_records.data.last_contacted_at in sync with the newest
-- row in lead_interactions for that lead. The dashboard pipeline reads
-- the denormalized field to compute SLA staleness, but the three
-- dashboard write paths (notes, email, stage-event) plus every Python
-- email send write to lead_interactions without touching the parent
-- record. The result is leads that look untouched in the UI even after
-- a fresh interaction.
--
-- Approach:
--   1. AFTER-INSERT trigger on lead_interactions that bumps the parent
--      tenant_records row's data.last_contacted_at if the new
--      interaction is the freshest one seen. Updates touch only the
--      JSONB key; the rest of `data` is preserved.
--   2. One-time backfill that walks every lead_id with at least one
--      interaction and sets data.last_contacted_at to the max
--      lead_interactions.created_at for that lead.
--
-- Outbound or inbound — both count as a touch. Direction-aware filtering
-- (e.g. "ignore queued-but-not-sent") happens at the application layer
-- if needed; for SLA staleness any logged interaction is signal.

CREATE OR REPLACE FUNCTION public.bump_tenant_record_last_contact()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  current_last_contact timestamptz;
  new_touch_at timestamptz := COALESCE(NEW.sent_at, NEW.created_at, now());
BEGIN
  -- Skip when there's no parent lead_id (defensive — should never happen)
  IF NEW.lead_id IS NULL THEN
    RETURN NEW;
  END IF;

  SELECT (data->>'last_contacted_at')::timestamptz
    INTO current_last_contact
    FROM public.tenant_records
   WHERE id = NEW.lead_id
   FOR UPDATE;

  -- Only bump forward — older replays (Gmail reconcile, backfill, etc.)
  -- can't move the field backward.
  IF current_last_contact IS NULL OR new_touch_at > current_last_contact THEN
    UPDATE public.tenant_records
       SET data = jsonb_set(
             COALESCE(data, '{}'::jsonb),
             '{last_contacted_at}',
             to_jsonb(new_touch_at)
           ),
           updated_at = now()
     WHERE id = NEW.lead_id;
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS lead_interactions_bump_last_contact
  ON public.lead_interactions;

CREATE TRIGGER lead_interactions_bump_last_contact
AFTER INSERT ON public.lead_interactions
FOR EACH ROW
EXECUTE FUNCTION public.bump_tenant_record_last_contact();

-- ---------------------------------------------------------------------
-- Backfill: walk every distinct lead_id in lead_interactions and stamp
-- tenant_records.data.last_contacted_at with the latest interaction
-- timestamp. Only updates rows where the existing value is older /
-- missing so a manual edit isn't clobbered.
-- ---------------------------------------------------------------------
DO $$
DECLARE
  rec record;
  rows_updated bigint := 0;
BEGIN
  FOR rec IN
    SELECT lead_id, MAX(COALESCE(sent_at, created_at)) AS latest_touch
      FROM public.lead_interactions
     WHERE lead_id IS NOT NULL
     GROUP BY lead_id
  LOOP
    UPDATE public.tenant_records
       SET data = jsonb_set(
             COALESCE(data, '{}'::jsonb),
             '{last_contacted_at}',
             to_jsonb(rec.latest_touch)
           ),
           updated_at = now()
     WHERE id = rec.lead_id
       AND (
         (data->>'last_contacted_at') IS NULL
         OR (data->>'last_contacted_at')::timestamptz < rec.latest_touch
       );
    IF FOUND THEN
      rows_updated := rows_updated + 1;
    END IF;
  END LOOP;

  RAISE NOTICE 'migration 074 backfilled last_contacted_at on % tenant_records rows', rows_updated;
END $$;
