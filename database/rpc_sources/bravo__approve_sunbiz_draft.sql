CREATE OR REPLACE FUNCTION public.approve_sunbiz_draft(p_draft_id uuid, p_tenant_id uuid, p_user_id uuid, p_final_text text)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare d sunbiz_reply_drafts;a sunbiz_agent_accounts;send_id uuid;phone10 text;
begin
  if p_final_text is null or char_length(btrim(p_final_text)) not between 1 and 1600 then return null; end if;
  select * into d from sunbiz_reply_drafts where id=p_draft_id and tenant_id=p_tenant_id
    and status='pending' for update;
  if not found then return null; end if;
  select * into a from sunbiz_agent_accounts where id=d.agent_account_id and tenant_id=p_tenant_id
    and enabled=true and mode='semi' for update;
  if not found or (a.user_id<>p_user_id and not exists(select 1 from user_profiles
    where tenant_id=p_tenant_id and auth_user_id=p_user_id and (is_owner=true or team_role in ('owner','admin'))))
    then return null; end if;
  phone10:=right(regexp_replace(d.to_phone,'\D','','g'),10);
  if exists(select 1 from sunbiz_phone_suppressions where tenant_id=p_tenant_id and phone_last10=phone10)
    then return null; end if;
  if exists(select 1 from lead_interactions newer join lead_interactions source on source.id=d.source_interaction_id
    where newer.tenant_id=p_tenant_id and newer.direction='inbound'
      and (newer.lead_id=d.lead_id or right(regexp_replace(newer.from_phone,'\D','','g'),10)=phone10)
      and coalesce(newer.sent_at,newer.created_at)>coalesce(source.sent_at,source.created_at))
    then return null; end if;
  if (select count(*) from scheduled_sends where tenant_id=p_tenant_id and actor_user_id=a.user_id
    and channel='sms' and status in ('pending','sending','sent') and created_at>=date_trunc('day',now()))>=a.daily_cap
    then return null; end if;
  insert into scheduled_sends(tenant_id,lead_id,thread_key,channel,to_phone,body,actor_user_id,
    from_identity,scheduled_for,status)
  values(p_tenant_id,d.lead_id,d.thread_key,'sms',d.to_phone,btrim(p_final_text),a.user_id,
    a.from_number,now(),'pending') returning id into send_id;
  update sunbiz_reply_drafts set status='approved',final_text=btrim(p_final_text),approved_by=p_user_id,
    approved_at=now(),scheduled_send_id=send_id,updated_at=now() where id=d.id;
  return send_id;
end $function$
