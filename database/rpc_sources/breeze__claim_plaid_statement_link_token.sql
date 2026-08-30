CREATE OR REPLACE FUNCTION public.claim_plaid_statement_link_token(p_request_id uuid, p_tenant_id uuid, p_merchant_id uuid)
 RETURNS TABLE(action text, encrypted_link_token text, expires_at timestamp with time zone, lease_id uuid)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_encrypted_link_token text;
  v_expires_at timestamptz;
  v_lease_id uuid;
  v_lease_at timestamptz;
  v_new_lease_id uuid;
begin
  perform 1
  from public.plaid_statement_requests
  where id = p_request_id
    and tenant_id = p_tenant_id
    and merchant_id = p_merchant_id
    and status = 'pending_consent'
  for update;

  if not found then
    return query select 'invalid'::text, null::text, null::timestamptz, null::uuid;
    return;
  end if;

  select t.encrypted_link_token, t.expires_at, t.lease_id, t.lease_at
    into v_encrypted_link_token, v_expires_at, v_lease_id, v_lease_at
  from public.plaid_statement_link_tokens t
  where t.request_id = p_request_id
  for update;

  if v_encrypted_link_token is not null
     and v_expires_at > now() + interval '60 seconds' then
    return query
      select 'reuse'::text, v_encrypted_link_token, v_expires_at, null::uuid;
    return;
  end if;

  -- Once an external creation attempt begins, only the application path that
  -- receives a definitive Plaid rejection may clear this lease. Time passing
  -- is not proof that the paid request failed.
  if v_lease_id is not null then
    return query select
      case
        when v_lease_at > now() - interval '60 seconds' then 'busy'::text
        else 'blocked'::text
      end,
      null::text,
      null::timestamptz,
      null::uuid;
    return;
  end if;

  v_new_lease_id := gen_random_uuid();
  insert into public.plaid_statement_link_tokens (
    request_id,
    encrypted_link_token,
    expires_at,
    lease_id,
    lease_at
  ) values (
    p_request_id,
    null,
    null,
    v_new_lease_id,
    now()
  )
  on conflict (request_id) do update
    set encrypted_link_token = null,
        expires_at = null,
        lease_id = excluded.lease_id,
        lease_at = excluded.lease_at;

  return query select 'issue'::text, null::text, null::timestamptz, v_new_lease_id;
end;
$function$
