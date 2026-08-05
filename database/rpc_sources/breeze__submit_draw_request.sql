CREATE OR REPLACE FUNCTION public.submit_draw_request(p_tenant_id uuid, p_merchant_id uuid, p_submitted_by_user_id uuid, p_advance_id uuid, p_requested_cents bigint, p_purpose text, p_merchant_note text, p_bank_account_id uuid, p_idempotency_key text)
 RETURNS TABLE(id uuid, deduped boolean)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_committed          bigint;
  v_principal          bigint;
  v_available          bigint;
  v_existing_id        uuid;
  v_existing_merchant  uuid;
  v_existing_advance   uuid;
  v_existing_cents     bigint;
  v_existing_purpose   text;
  v_existing_note      text;
  v_existing_bank      uuid;
  v_new_id             uuid;
  v_status             text;
begin
  if p_tenant_id is null or p_merchant_id is null then
    raise exception 'not a merchant user';
  end if;
  if p_idempotency_key is null
     or pg_catalog.length(p_idempotency_key) < 8
     or pg_catalog.length(p_idempotency_key) > 80 then
    raise exception 'invalid idempotency key';
  end if;

  -- Serialize the same tenant/key before the existence check. This makes two
  -- simultaneous retries return one row instead of racing into a unique error.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(p_tenant_id::text || ':' || p_idempotency_key, 0)
  );

  select
    dr.id,
    dr.merchant_id,
    dr.advance_id,
    dr.requested_cents,
    dr.purpose,
    dr.merchant_note,
    dr.bank_account_id
  into
    v_existing_id,
    v_existing_merchant,
    v_existing_advance,
    v_existing_cents,
    v_existing_purpose,
    v_existing_note,
    v_existing_bank
  from public.draw_requests dr
  where dr.tenant_id = p_tenant_id
    and dr.idempotency_key = p_idempotency_key
  limit 1;

  if v_existing_id is not null then
    if v_existing_merchant is distinct from p_merchant_id
       or v_existing_advance is distinct from p_advance_id
       or v_existing_cents is distinct from p_requested_cents
       or v_existing_purpose is distinct from p_purpose
       or v_existing_note is distinct from p_merchant_note
       or v_existing_bank is distinct from p_bank_account_id then
      raise exception 'idempotency key already used for a different draw request';
    end if;
    return query select v_existing_id, true;
    return;
  end if;

  select a.advance_amount_cents, a.repayment_status
    into v_principal, v_status
  from public.advances a
  where a.id = p_advance_id
    and a.tenant_id = p_tenant_id
    and a.merchant_id = p_merchant_id
  for update;
  if not found then raise exception 'advance not found'; end if;
  if v_status not in ('pending', 'active') then
    raise exception 'advance is not active';
  end if;

  select coalesce(
      sum(coalesce(dr.approved_cents, dr.requested_cents)),
      0
    )
    into v_committed
  from public.draw_requests dr
  where dr.advance_id = p_advance_id
    and dr.status in ('pending', 'approved', 'awaiting_signature', 'funded');

  v_available := v_principal - v_committed;
  if p_requested_cents <= 0 then
    raise exception 'requested amount must be positive';
  end if;
  if p_requested_cents > v_available then
    raise exception 'requested % exceeds available %', p_requested_cents, v_available;
  end if;

  insert into public.draw_requests (
    tenant_id,
    advance_id,
    merchant_id,
    requested_cents,
    status,
    purpose,
    merchant_note,
    bank_account_id,
    idempotency_key,
    submitted_by_user_id,
    submitted_at
  ) values (
    p_tenant_id,
    p_advance_id,
    p_merchant_id,
    p_requested_cents,
    'pending',
    p_purpose,
    p_merchant_note,
    p_bank_account_id,
    p_idempotency_key,
    p_submitted_by_user_id,
    pg_catalog.now()
  )
  returning draw_requests.id into v_new_id;

  return query select v_new_id, false;
end;
$function$
