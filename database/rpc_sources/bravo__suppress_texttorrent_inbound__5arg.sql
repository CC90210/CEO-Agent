-- Extracted from Supabase project phctllmtsogkovoilwos before cancellation.
-- Signature: suppress_texttorrent_inbound(p_inbound_work_id uuid, p_tenant_id uuid, p_account_id uuid, p_reason text, p_worker_id text)
-- This PL/pgSQL existed ONLY in the live database.
CREATE OR REPLACE FUNCTION public.suppress_texttorrent_inbound(p_inbound_work_id uuid, p_tenant_id uuid, p_account_id uuid, p_reason text, p_worker_id text)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare w texttorrent_inbound_work; state_id uuid; phone10 text;
begin
  select * into w from texttorrent_inbound_work where id=p_inbound_work_id
    and tenant_id=p_tenant_id and account_id=p_account_id and status='running'
    and lease_owner=p_worker_id for update;
  if not found then return false; end if;
  phone10:=right(regexp_replace(coalesce(w.conversation->>'to_phone',''),'\D','','g'),10);
  if length(phone10)<>10 then return false; end if;
  insert into sunbiz_phone_suppressions(tenant_id,phone_last10,reason,source,source_work_id,updated_at)
  values(w.tenant_id,phone10,p_reason,'texttorrent_runtime',w.id,now())
  on conflict(tenant_id,phone_last10) do update set reason=excluded.reason,
    source=excluded.source,source_work_id=excluded.source_work_id,updated_at=now();
  insert into sunbiz_conversation_state(tenant_id,provider,provider_conversation_id,lead_id,
    agent_account_id,qualification_state,last_intent,last_action,automation_paused,knowledge_version)
  select w.tenant_id,'texttorrent',coalesce(w.provider_conversation_id,w.provider_message_id),
    nullif(w.conversation->>'lead_id','')::uuid,w.account_id,'{}',p_reason,'suppressed',true,a.knowledge_version
  from sunbiz_agent_accounts a where a.id=w.account_id
  on conflict(tenant_id,provider,provider_conversation_id) do update set
    last_intent=excluded.last_intent,last_action='suppressed',automation_paused=true,updated_at=now()
  returning id into state_id;
  update scheduled_sends set status='cancelled'
  where tenant_id=w.tenant_id and channel='sms' and status='pending'
    and (thread_key=w.conversation->>'thread_key'
      or right(regexp_replace(coalesce(to_phone,''),'\D','','g'),10)=phone10);
  update texttorrent_inbound_work set status='suppressed',
    decision=jsonb_build_object('intent',p_reason,'shouldSuppress',true),
    lease_owner=null,lease_expires_at=null,completed_at=now(),last_error=null where id=w.id;
  return true;
end $function$
