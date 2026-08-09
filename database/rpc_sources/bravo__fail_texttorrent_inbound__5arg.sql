-- Extracted from Supabase project phctllmtsogkovoilwos before cancellation.
-- Signature: fail_texttorrent_inbound(p_work_id uuid, p_worker_id text, p_error_code text, p_max_attempts integer, p_next_attempt_at timestamp with time zone)
-- This PL/pgSQL existed ONLY in the live database.
CREATE OR REPLACE FUNCTION public.fail_texttorrent_inbound(p_work_id uuid, p_worker_id text, p_error_code text, p_max_attempts integer, p_next_attempt_at timestamp with time zone)
 RETURNS text
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare w texttorrent_inbound_work; next_attempts integer; next_status text;
begin
  if p_max_attempts < 1 or p_error_code is null or p_error_code = '' then return null; end if;
  select * into w from texttorrent_inbound_work where id=p_work_id and status='running'
    and lease_owner=p_worker_id for update;
  if not found then return null; end if;
  next_attempts := w.attempts + 1;
  next_status := case when next_attempts >= p_max_attempts then 'dead_letter' else 'pending' end;
  if next_status='dead_letter' then
    insert into texttorrent_dead_letters(inbound_work_id,tenant_id,account_id,failure_code,attempts,sanitized_metadata)
    values(w.id,w.tenant_id,w.account_id,left(p_error_code,120),next_attempts,
      jsonb_build_object('provider_message_id',w.provider_message_id))
    on conflict do nothing;
  end if;
  update texttorrent_inbound_work set status=next_status,attempts=next_attempts,
    next_attempt_at=case when next_status='pending' then coalesce(p_next_attempt_at,now()) else next_attempt_at end,
    lease_owner=null,lease_expires_at=null,last_error=left(p_error_code,120),
    completed_at=case when next_status='dead_letter' then now() else null end
  where id=w.id;
  return next_status;
end $function$
