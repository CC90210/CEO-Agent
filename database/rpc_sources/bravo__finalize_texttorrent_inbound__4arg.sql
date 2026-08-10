-- Extracted from Supabase project phctllmtsogkovoilwos before cancellation.
-- Signature: finalize_texttorrent_inbound(p_work_id uuid, p_worker_id text, p_status text, p_decision jsonb)
-- This PL/pgSQL existed ONLY in the live database.
CREATE OR REPLACE FUNCTION public.finalize_texttorrent_inbound(p_work_id uuid, p_worker_id text, p_status text, p_decision jsonb)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare w texttorrent_inbound_work; a sunbiz_agent_accounts; state_id uuid; response text;
begin
  if p_status not in ('drafted','escalated') then return false; end if;
  select * into w from texttorrent_inbound_work where id=p_work_id and status='running'
    and lease_owner=p_worker_id for update;
  if not found then return false; end if;
  select * into a from sunbiz_agent_accounts where id=w.account_id and tenant_id=w.tenant_id;
  if not found then return false; end if;
  insert into sunbiz_conversation_state(tenant_id,provider,provider_conversation_id,lead_id,
    agent_account_id,qualification_state,last_intent,last_action,automation_paused,
    human_owner_id,knowledge_version,updated_at)
  values(w.tenant_id,'texttorrent',coalesce(w.provider_conversation_id,w.provider_message_id),
    nullif(w.conversation->>'lead_id','')::uuid,w.account_id,
    coalesce(p_decision->'qualification_updates','{}'::jsonb),p_decision->>'intent',p_status,
    false,case when p_status='escalated' then a.handoff_user_id else null end,a.knowledge_version,now())
  on conflict(tenant_id,provider,provider_conversation_id) do update set
    qualification_state=sunbiz_conversation_state.qualification_state || excluded.qualification_state,last_intent=excluded.last_intent,
    last_action=excluded.last_action,human_owner_id=coalesce(excluded.human_owner_id,sunbiz_conversation_state.human_owner_id),
    knowledge_version=excluded.knowledge_version,updated_at=now()
  returning id into state_id;
  response := nullif(btrim(p_decision->>'response'),'');
  if p_status='drafted' and response is not null then
    insert into sunbiz_reply_drafts(tenant_id,conversation_state_id,agent_account_id,lead_id,
      thread_key,to_phone,original_text,intent,confidence,model_id,model_version,
      knowledge_version,source_interaction_id,provider_message_id)
    values(w.tenant_id,state_id,w.account_id,nullif(w.conversation->>'lead_id','')::uuid,
      w.conversation->>'thread_key',w.conversation->>'to_phone',left(response,1600),
      coalesce(p_decision->>'intent','UNCERTAIN'),nullif(p_decision->>'confidence','')::numeric,
      p_decision->>'model_id',p_decision->>'model_version',a.knowledge_version,
      w.source_interaction_id,w.provider_message_id)
    on conflict(tenant_id,source_interaction_id) do nothing;
  elsif p_status='drafted' then
    return false;
  end if;
  update texttorrent_inbound_work set status=p_status,decision=p_decision,lease_owner=null,
    lease_expires_at=null,completed_at=now(),last_error=null where id=w.id;
  insert into agent_events(event_type,publisher_agent,severity,payload,correlation_id)
  values(case when p_status='drafted' then 'TEXTTORRENT_DRAFT_READY' else 'TEXTTORRENT_HANDOFF_REQUIRED' end,
    'texttorrent-runtime',case when p_status='drafted' then 'info' else 'warn' end,
    jsonb_build_object('tenant_id',w.tenant_id,'account_id',w.account_id,'work_id',w.id,
      'conversation_state_id',state_id,'intent',p_decision->>'intent'),w.tenant_id::text);
  return true;
end $function$
