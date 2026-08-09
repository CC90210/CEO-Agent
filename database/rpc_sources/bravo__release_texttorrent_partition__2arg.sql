-- Extracted from Supabase project phctllmtsogkovoilwos before cancellation.
-- Signature: release_texttorrent_partition(p_partition_key text, p_worker_id text)
-- This PL/pgSQL existed ONLY in the live database.
CREATE OR REPLACE FUNCTION public.release_texttorrent_partition(p_partition_key text, p_worker_id text)
 RETURNS boolean
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  select public.release_texttorrent_partition(
    (select tenant_id from sunbiz_agent_accounts where id::text=split_part(p_partition_key,':',1)),
    p_partition_key,p_worker_id);
$function$
