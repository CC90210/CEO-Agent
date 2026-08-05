CREATE OR REPLACE FUNCTION public.approve_draw_request(p_draw_request_id uuid, p_tenant_id uuid, p_approved_cents bigint, p_decided_by_user_id uuid, p_decision_note text)
 RETURNS text
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
declare
  v_advance_id  uuid;
  v_req_status  text;
  v_principal   bigint;
  v_adv_status  text;
  v_committed   bigint;
  v_available   bigint;
begin
  if p_approved_cents <= 0 then
    raise exception 'approved amount must be positive';
  end if;

  -- Lock the request; it must still be pending.
  select advance_id, status into v_advance_id, v_req_status
    from public.draw_requests
   where id = p_draw_request_id and tenant_id = p_tenant_id
   for update;
  if not found then
    raise exception 'draw request not found';
  end if;
  if v_req_status <> 'pending' then
    raise exception 'request is no longer pending';
  end if;

  -- Lock the advance and recompute committed INSIDE the lock so concurrent
  -- approvals serialize and each sees the other's reservation.
  select advance_amount_cents, repayment_status into v_principal, v_adv_status
    from public.advances
   where id = v_advance_id and tenant_id = p_tenant_id
   for update;
  if not found then
    raise exception 'advance not found';
  end if;
  if v_adv_status not in ('pending','active') then
    raise exception 'advance is not active';
  end if;

  select coalesce(sum(coalesce(approved_cents, requested_cents)), 0) into v_committed
    from public.draw_requests
   where advance_id = v_advance_id
     and status in ('pending','approved','awaiting_signature','funded')
     and id <> p_draw_request_id;

  v_available := v_principal - v_committed;
  if p_approved_cents > v_available then
    raise exception 'approved % exceeds available %', p_approved_cents, v_available;
  end if;

  update public.draw_requests
     set status             = 'awaiting_signature',
         approved_cents     = p_approved_cents,
         decided_at         = now(),
         decided_by_user_id = p_decided_by_user_id,
         decision_note      = p_decision_note,
         updated_at         = now()
   where id = p_draw_request_id and status = 'pending';
  if not found then
    raise exception 'request is no longer pending';
  end if;

  return 'awaiting_signature';
end;
$function$
