-- Extracted from Supabase project phctllmtsogkovoilwos before cancellation.
-- Signature: texttorrent_runtime_health(p_worker_id text)
-- This PL/pgSQL existed ONLY in the live database.
CREATE OR REPLACE FUNCTION public.texttorrent_runtime_health(p_worker_id text)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  select jsonb_build_object('worker_id',p_worker_id,'now',now(),
    'active_leases',(select count(*) from sunbiz_processing_leases where owner_id=p_worker_id and expires_at>now()),
    'pending',(select count(*) from texttorrent_inbound_work where status='pending'),
    'running',(select count(*) from texttorrent_inbound_work where status='running'),
    'dead',(select count(*) from texttorrent_dead_letters where resolved_at is null),
    'oldest_pending_at',(select min(created_at) from texttorrent_inbound_work where status='pending'));
$function$
