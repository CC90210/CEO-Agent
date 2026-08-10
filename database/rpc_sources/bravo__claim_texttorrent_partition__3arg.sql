-- Extracted from Supabase project phctllmtsogkovoilwos before cancellation.
-- Signature: claim_texttorrent_partition(p_partition_key text, p_worker_id text, p_lease_seconds integer)
-- This PL/pgSQL existed ONLY in the live database.
CREATE OR REPLACE FUNCTION public.claim_texttorrent_partition(p_partition_key text, p_worker_id text, p_lease_seconds integer DEFAULT 60)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare changed integer;
begin
  insert into sunbiz_processing_leases(tenant_id,partition_key,owner_id,expires_at)
  select a.tenant_id, p_partition_key, p_worker_id, now()+make_interval(secs=>p_lease_seconds)
  from sunbiz_agent_accounts a where a.id::text=split_part(p_partition_key,':',1)
  on conflict (tenant_id,partition_key) do update set owner_id=excluded.owner_id,
    acquired_at=now(), heartbeat_at=now(), expires_at=excluded.expires_at
  where sunbiz_processing_leases.expires_at < now() or sunbiz_processing_leases.owner_id=p_worker_id;
  get diagnostics changed = row_count;
  return changed > 0;
end $function$
