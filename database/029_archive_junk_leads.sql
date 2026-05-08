-- ============================================================
-- BRAVO V6 — Migration 029: archive existing junk leads
-- ============================================================
-- PURPOSE
-- The Pipeline page was showing leads like noreply@kraken.com,
-- test@example.com, and cold-outreach addresses that never replied
-- (created by the outbound gateway's auto-create path). These are
-- not real leads — they pollute the active count and hide the few
-- real opportunities.
--
-- This migration:
--   1. Archives every lead whose email is a known no-reply or test
--      address (kraken, example.com, noreply@*, test@*).
--   2. Archives every lead whose source = 'outbound_gateway' or
--      'gateway_autocreate' that has NO inbound interaction (never
--      responded). These were auto-created when CC sent them an email,
--      not because they're actually a lead. Real leads come back via
--      n8n_inbound or are added manually with score >= 50.
--
-- Both actions set status='archived' (not deleted) so the data is
-- preserved for audit. Rollback: UPDATE leads SET status='new' WHERE
-- updated_at = '<now>' AND status = 'archived'.
-- ============================================================

BEGIN;

-- 1. Archive obvious junk addresses
UPDATE public.leads
SET    status     = 'archived',
       updated_at = NOW(),
       custom_fields = COALESCE(custom_fields, '{}'::jsonb)
                       || jsonb_build_object('archived_reason', 'junk_sender_v029',
                                             'archived_at', NOW()::text)
WHERE  status NOT IN ('archived', 'won')
  AND  (
        lower(email) LIKE 'noreply@%'
     OR lower(email) LIKE 'no-reply@%'
     OR lower(email) LIKE 'donotreply@%'
     OR lower(email) LIKE 'do-not-reply@%'
     OR lower(email) LIKE 'notifications@%'
     OR lower(email) LIKE 'mailer-daemon@%'
     OR lower(email) LIKE 'bounces@%'
     OR lower(email) LIKE 'postmaster@%'
     OR lower(email) LIKE 'receipts@%'
     OR lower(email) LIKE 'invoices@%'
     OR lower(email) LIKE 'billing@%'
     OR lower(email) LIKE 'auto@%'
     OR lower(email) LIKE 'system@%'
     OR lower(email) LIKE 'test@%'
     OR lower(email) LIKE 'example@%'
     OR lower(email) LIKE '%@example.com'
     OR lower(email) LIKE '%@example.org'
     OR lower(email) LIKE '%@test.com'
     OR lower(email) LIKE '%@kraken.com'
     OR lower(email) LIKE '%@stripe.com'
     OR lower(email) LIKE '%@github.com'
     OR lower(email) LIKE '%@vercel.com'
     OR lower(email) LIKE '%@cloudflare.com'
     OR lower(email) LIKE '%@supabase.io'
     OR lower(email) LIKE '%@openrouter.ai'
     OR lower(email) LIKE '%@anthropic.com'
     OR lower(email) LIKE '%@openai.com'
  );

-- 2. Archive outbound-gateway-only leads that never responded.
-- A lead is considered "never responded" if there are zero inbound
-- interactions (email_received / email_reply / dm_received) for that
-- lead. These leads exist only because we sent them an email, not
-- because they engaged.
UPDATE public.leads l
SET    status     = 'archived',
       updated_at = NOW(),
       custom_fields = COALESCE(custom_fields, '{}'::jsonb)
                       || jsonb_build_object('archived_reason', 'outbound_only_no_response_v029',
                                             'archived_at', NOW()::text)
WHERE  l.status = 'new'
  AND  l.source IN ('outbound_gateway', 'gateway_autocreate')
  AND  NOT EXISTS (
         SELECT 1 FROM public.lead_interactions li
         WHERE  li.lead_id = l.id
           AND  li.type IN ('email_received', 'email_reply', 'dm_received')
       );

-- 3. Sanity check — log what we touched (visible in apply_migration output).
DO $$
DECLARE
  junk_count int;
  outbound_count int;
BEGIN
  SELECT COUNT(*) INTO junk_count FROM public.leads
  WHERE custom_fields->>'archived_reason' = 'junk_sender_v029';
  SELECT COUNT(*) INTO outbound_count FROM public.leads
  WHERE custom_fields->>'archived_reason' = 'outbound_only_no_response_v029';
  RAISE NOTICE 'Migration 029: archived % junk-sender leads, % outbound-only-no-response leads',
               junk_count, outbound_count;
END $$;

COMMIT;
