-- 080_last_contact_trigger_update_coverage.sql
--
-- Extend the lead_interactions → last_contacted_at trigger to fire on
-- UPDATE as well as INSERT. Migration 074 covered INSERT only, which
-- is the common case — but the dashboard email queue flow does:
--
--   1. INSERT lead_interactions (type='email_queued', sent_at=NULL)
--      → trigger fires, last_contacted_at = NEW.created_at (queue time)
--   2. dashboard_email_consumer.py picks up the row, fires the actual
--      SMTP/Gmail send, then UPDATEs sent_at = now()
--      → trigger does NOT fire (it's AFTER INSERT only)
--      → last_contacted_at stays at queue time, not actual send time
--
-- For fresh queues queue-time ≈ send-time so the gap is invisible. For
-- delayed queues (network outage, daily cap hit, rate limiter backoff)
-- the gap can be hours. Pipeline staleness badges would show a lead as
-- last touched at queue time, ignoring that we actually got through to
-- them later.
--
-- Approach: re-create the trigger AFTER INSERT OR UPDATE OF sent_at.
-- The function itself already only bumps forward
-- (current_last_contact IS NULL OR new_touch_at > current_last_contact)
-- so an UPDATE that doesn't move sent_at later is a safe no-op.

DROP TRIGGER IF EXISTS lead_interactions_bump_last_contact
  ON public.lead_interactions;

CREATE TRIGGER lead_interactions_bump_last_contact
AFTER INSERT OR UPDATE OF sent_at ON public.lead_interactions
FOR EACH ROW
EXECUTE FUNCTION public.bump_tenant_record_last_contact();
