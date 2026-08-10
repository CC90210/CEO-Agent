-- Extracted from Supabase project phctllmtsogkovoilwos before cancellation.
-- Signature: claim_texttorrent_inbound(p_account_id uuid, p_worker_id text, p_lease_seconds integer)
-- This PL/pgSQL existed ONLY in the live database.
CREATE OR REPLACE FUNCTION public.claim_texttorrent_inbound(p_account_id uuid, p_worker_id text, p_lease_seconds integer DEFAULT 60)
 RETURNS SETOF texttorrent_inbound_work
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  update texttorrent_inbound_work w set status='running', lease_owner=p_worker_id, claimed_at=now(),
    lease_expires_at=now()+make_interval(secs=>p_lease_seconds)
  where w.id=(select id from texttorrent_inbound_work where account_id=p_account_id
    and (status='pending' or (status='running' and lease_expires_at<now())) and next_attempt_at<=now()
    order by priority asc, created_at asc for update skip locked limit 1)
  returning w.*;
$function$
