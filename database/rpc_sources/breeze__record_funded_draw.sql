CREATE OR REPLACE FUNCTION public.record_funded_draw(p_draw_request_id uuid, p_tenant_id uuid, p_approved_cents bigint, p_decided_by_user_id uuid, p_decision_note text, p_expected_orig_fee bigint DEFAULT NULL::bigint, p_expected_total_repay bigint DEFAULT NULL::bigint)
 RETURNS TABLE(draw_id uuid, origination_fee_cents bigint, net_funded_cents bigint, total_repayment_cents bigint, deduped boolean)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
declare
  v_advance_id uuid; v_merchant_id uuid; v_bank_acct_id uuid; v_req_status text;
  v_principal bigint; v_adv_status text; v_committed bigint; v_available bigint;
  v_orig_pct numeric(5,4); v_monthly_rate numeric(5,4); v_term integer;
  v_orig_fee bigint; v_total_repay bigint; v_new_draw_id uuid; v_existing record;
  v_now timestamptz := now();
begin
  if p_approved_cents <= 0 then raise exception 'approved amount must be positive'; end if;
  select advance_id, merchant_id, bank_account_id, status
    into v_advance_id, v_merchant_id, v_bank_acct_id, v_req_status
    from public.draw_requests where id = p_draw_request_id and tenant_id = p_tenant_id for update;
  if not found then raise exception 'draw request not found'; end if;
  if v_req_status = 'funded' then
    select d.id, d.platform_fee_cents, d.net_deposit_cents, d.total_repayment_cents
      into v_existing from public.draws d where d.draw_request_id = p_draw_request_id limit 1;
    if found then
      return query select v_existing.id, v_existing.platform_fee_cents,
        v_existing.net_deposit_cents, v_existing.total_repayment_cents, true; return;
    end if;
    raise warning 'record_funded_draw: request % funded with no draw row — recovering', p_draw_request_id;
  elsif v_req_status not in ('pending','awaiting_signature') then
    raise exception 'cannot fund a % request', v_req_status;
  end if;
  select advance_amount_cents, repayment_status, origination_fee_pct, monthly_rate_pct, term_months
    into v_principal, v_adv_status, v_orig_pct, v_monthly_rate, v_term
    from public.advances where id = v_advance_id and tenant_id = p_tenant_id for update;
  if not found then raise exception 'advance not found'; end if;
  if v_adv_status not in ('pending','active') then raise exception 'advance is not active'; end if;
  select coalesce(sum(coalesce(approved_cents, requested_cents)), 0) into v_committed
    from public.draw_requests
   where advance_id = v_advance_id
     and status in ('pending','approved','awaiting_signature','funded')
     and id <> p_draw_request_id;
  v_available := v_principal - v_committed;
  if p_approved_cents > v_available then
    raise exception 'approved % exceeds available %', p_approved_cents, v_available;
  end if;
  v_orig_fee := least(p_approved_cents, floor(p_approved_cents::numeric * coalesce(v_orig_pct, 0))::bigint);
  v_total_repay := round(p_approved_cents::numeric * (1 + coalesce(v_monthly_rate,0) * coalesce(v_term,0)))::bigint;

  -- Agreement = source of truth: if the caller passed the SIGNED economics and
  -- the advance's live terms have since drifted, refuse to fund. The whole tx
  -- rolls back, so the draw stays awaiting_signature on the originally-signed terms.
  if p_expected_orig_fee is not null and p_expected_orig_fee <> v_orig_fee then
    raise exception 'agreement terms changed since signing (origination fee % vs signed %)',
      v_orig_fee, p_expected_orig_fee;
  end if;
  if p_expected_total_repay is not null and p_expected_total_repay <> v_total_repay then
    raise exception 'agreement terms changed since signing (total % vs signed %)',
      v_total_repay, p_expected_total_repay;
  end if;

  update public.draw_requests
     set status = 'funded', approved_cents = p_approved_cents, decided_at = v_now,
         decided_by_user_id = p_decided_by_user_id, decision_note = p_decision_note, updated_at = now()
   where id = p_draw_request_id;
  insert into public.draws
    (tenant_id, draw_request_id, advance_id, merchant_id, funded_cents, platform_fee_cents,
     origination_fee_pct, monthly_rate_pct, term_months, total_repayment_cents, funded_at, bank_account_id)
  values
    (p_tenant_id, p_draw_request_id, v_advance_id, v_merchant_id, p_approved_cents, v_orig_fee,
     coalesce(v_orig_pct,0), coalesce(v_monthly_rate,0), coalesce(v_term,0), v_total_repay, v_now, v_bank_acct_id)
  returning id into v_new_draw_id;
  return query select v_new_draw_id, v_orig_fee, (p_approved_cents - v_orig_fee), v_total_repay, false;
end;
$function$
