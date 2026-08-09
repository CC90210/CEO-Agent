-- Extracted from Supabase project phctllmtsogkovoilwos before cancellation.
-- Signature: heartbeat_texttorrent_partition(p_partition_key text, p_worker_id text, p_lease_seconds integer)
-- This PL/pgSQL existed ONLY in the live database.
CREATE OR REPLACE FUNCTION public.heartbeat_texttorrent_partition(p_partition_key text, p_worker_id text, p_lease_seconds integer DEFAULT 60)
 RETURNS boolean
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  select public.heartbeat_texttorrent_partition(
    (select tenant_id from sunbiz_agent_accounts where id::text=split_part(p_partition_key,':',1)),
    p_partition_key,p_worker_id,p_lease_seconds);
$function$
