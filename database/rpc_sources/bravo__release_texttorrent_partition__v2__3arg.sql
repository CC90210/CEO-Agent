-- Extracted from Supabase project phctllmtsogkovoilwos before cancellation.
-- Signature: release_texttorrent_partition(p_tenant_id uuid, p_partition_key text, p_worker_id text)
-- This PL/pgSQL existed ONLY in the live database.
CREATE OR REPLACE FUNCTION public.release_texttorrent_partition(p_tenant_id uuid, p_partition_key text, p_worker_id text)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare changed integer;
begin
  delete from sunbiz_processing_leases where tenant_id=p_tenant_id
    and partition_key=p_partition_key and owner_id=p_worker_id;
  get diagnostics changed=row_count; return changed>0;
end $function$
