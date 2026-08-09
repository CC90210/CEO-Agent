-- Extracted from Supabase project phctllmtsogkovoilwos before cancellation.
-- Signature: heartbeat_texttorrent_partition(p_tenant_id uuid, p_partition_key text, p_worker_id text, p_lease_seconds integer)
-- This PL/pgSQL existed ONLY in the live database.
CREATE OR REPLACE FUNCTION public.heartbeat_texttorrent_partition(p_tenant_id uuid, p_partition_key text, p_worker_id text, p_lease_seconds integer DEFAULT 60)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare changed integer;
begin
  update sunbiz_processing_leases set heartbeat_at=now(),
    expires_at=now()+make_interval(secs=>p_lease_seconds)
  where tenant_id=p_tenant_id and partition_key=p_partition_key
    and owner_id=p_worker_id and expires_at>now();
  get diagnostics changed=row_count; return changed>0;
end $function$
