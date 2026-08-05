CREATE OR REPLACE FUNCTION public.consume_texttorrent_rate_token(p_bucket text, p_worker_id text, p_priority integer, p_limit integer DEFAULT 60, p_window_seconds integer DEFAULT 60)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare tid uuid; changed integer; effective_limit integer;
begin
  -- Bucket format is <tenant_uuid>:parent-sid. Every account, runtime worker,
  -- poller and approved-reply dispatcher sharing that parent credential MUST
  -- consume this same tenant bucket.
  if p_bucket !~ '^[0-9a-fA-F-]{36}:parent-sid$' then return false; end if;
  tid := split_part(p_bucket,':',1)::uuid;
  -- Reserve capacity for urgent work instead of allowing analytics/backfills
  -- to consume the entire parent-SID window. Priority 90+ (compliance) may
  -- use all tokens; approved replies retain five; normal inbound retains ten;
  -- low-priority analytics/backfills retain twenty for higher-priority work.
  effective_limit := greatest(1, least(p_limit, case
    when p_priority >= 90 then p_limit
    when p_priority >= 80 then p_limit - 5
    when p_priority >= 50 then p_limit - 10
    else p_limit - 20
  end));
  insert into sunbiz_provider_rate_state(bucket,tenant_id,provider,window_started_at,request_count)
  values(p_bucket,tid,'texttorrent',now(),1)
  on conflict(bucket) do update set
    window_started_at=case when sunbiz_provider_rate_state.window_started_at < now()-make_interval(secs=>p_window_seconds)
      then now() else sunbiz_provider_rate_state.window_started_at end,
    request_count=case when sunbiz_provider_rate_state.window_started_at < now()-make_interval(secs=>p_window_seconds)
      then 1 else sunbiz_provider_rate_state.request_count+1 end, updated_at=now()
  where sunbiz_provider_rate_state.window_started_at < now()-make_interval(secs=>p_window_seconds)
    or sunbiz_provider_rate_state.request_count < effective_limit;
  get diagnostics changed = row_count; return changed > 0;
end $function$
