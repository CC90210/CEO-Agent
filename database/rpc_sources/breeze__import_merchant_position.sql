CREATE OR REPLACE FUNCTION public.import_merchant_position(p_tenant_id uuid, p_actor_id uuid, p_payload jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
declare
  v_merchant_id      uuid;
  v_advance_id       uuid;
  v_advance          jsonb;
  v_lender_ref       text;
  v_paid_cents       bigint;
  v_amount_cents     bigint;
  v_orig_pct         numeric(5,4);
  v_monthly_rate     numeric(5,4);
  v_term             integer;
  v_total_repay      bigint;
  v_funded_at        timestamptz;
  v_draw_request_id  uuid;
  v_draw_id          uuid;
begin
  if p_tenant_id is null then
    raise exception 'tenant id is required';
  end if;
  if p_payload is null or jsonb_typeof(p_payload) <> 'object' then
    raise exception 'payload must be an object';
  end if;
  if nullif(trim(p_payload->>'business_name'), '') is null then
    raise exception 'business_name is required';
  end if;
  if nullif(trim(p_payload->>'email'), '') is null then
    raise exception 'email is required';
  end if;

  insert into public.merchants (
    tenant_id, business_name, dba, primary_contact_name, primary_contact_email,
    primary_contact_phone, ein_last4, city, state_region, industry, status
  )
  values (
    p_tenant_id,
    trim(p_payload->>'business_name'),
    nullif(trim(coalesce(p_payload->>'dba', '')), ''),
    nullif(trim(coalesce(p_payload->>'contact_name', '')), ''),
    lower(trim(p_payload->>'email')),
    nullif(trim(coalesce(p_payload->>'phone', '')), ''),
    nullif(right(regexp_replace(coalesce(p_payload->>'ein_last4', ''), '\D', '', 'g'), 4), ''),
    nullif(trim(coalesce(p_payload->>'city', '')), ''),
    nullif(trim(coalesce(p_payload->>'state', '')), ''),
    nullif(trim(coalesce(p_payload->>'industry', '')), ''),
    'active'
  )
  returning id into v_merchant_id;

  v_advance := p_payload->'advance';
  if v_advance is not null and jsonb_typeof(v_advance) = 'object' then
    v_lender_ref   := nullif(trim(coalesce(v_advance->>'lender_ref', '')), '');
    v_paid_cents   := coalesce((v_advance->>'paid_cents')::bigint, 0);
    v_amount_cents := (v_advance->>'amount_cents')::bigint;
    v_orig_pct     := (v_advance->>'origination_fee_pct')::numeric;
    v_monthly_rate := (v_advance->>'monthly_rate_pct')::numeric;
    v_term         := (v_advance->>'term_months')::integer;
    v_funded_at    := (v_advance->>'funded_at')::timestamptz;

    insert into public.advances (
      tenant_id, merchant_id, advance_amount_cents, factor_rate, origination_fee_pct,
      monthly_rate_pct, term_months, term_days, daily_holdback_pct, funded_at,
      repayment_status, lender_ref_id, notes
    )
    values (
      p_tenant_id, v_merchant_id, v_amount_cents,
      (v_advance->>'factor_rate')::numeric, v_orig_pct, v_monthly_rate, v_term,
      (v_term * 30), (v_advance->>'daily_holdback_pct')::numeric, v_funded_at,
      'active', v_lender_ref,
      coalesce(nullif(trim(coalesce(v_advance->>'notes', '')), ''), 'Imported from CRM export.')
    )
    returning id into v_advance_id;

    -- Seed the drawn principal as a funded draw so capacity + totals are correct.
    if coalesce(v_amount_cents, 0) > 0 then
      -- total the merchant repays on this drawn position, same formula as
      -- record_funded_draw: funded * (1 + monthly_rate * term).
      v_total_repay := round(
        v_amount_cents::numeric * (1 + coalesce(v_monthly_rate, 0) * coalesce(v_term, 0))
      )::bigint;

      insert into public.draw_requests (
        tenant_id, advance_id, merchant_id, requested_cents, approved_cents, status,
        purpose, idempotency_key, submitted_by_user_id, submitted_at,
        decided_at, decided_by_user_id, decision_note
      )
      values (
        p_tenant_id, v_advance_id, v_merchant_id, v_amount_cents, v_amount_cents, 'funded',
        'Imported opening position',
        'CRM-IMPORT-DRAW-' || coalesce(v_lender_ref, v_advance_id::text),
        p_actor_id, v_funded_at, v_funded_at, p_actor_id, 'Imported from CRM export.'
      )
      returning id into v_draw_request_id;

      insert into public.draws (
        tenant_id, draw_request_id, advance_id, merchant_id, funded_cents,
        platform_fee_cents, origination_fee_pct, monthly_rate_pct, term_months,
        total_repayment_cents, funded_at, bank_account_id, lender_ref_id
      )
      values (
        p_tenant_id, v_draw_request_id, v_advance_id, v_merchant_id, v_amount_cents,
        0, coalesce(v_orig_pct, 0), coalesce(v_monthly_rate, 0), coalesce(v_term, 0),
        v_total_repay, v_funded_at, null, v_lender_ref
      )
      returning id into v_draw_id;
    end if;

    if v_paid_cents > 0 then
      insert into public.repayments (
        tenant_id, advance_id, merchant_id, draw_id, amount_cents, recorded_at,
        source, external_id, note, recorded_by_user_id
      )
      values (
        p_tenant_id, v_advance_id, v_merchant_id, v_draw_id, v_paid_cents, v_funded_at,
        'adjustment',
        'CRM-IMPORT-' || coalesce(v_lender_ref, v_advance_id::text),
        'Opening paid-to-date balance imported from CRM export.',
        p_actor_id
      );
    end if;
  end if;

  return jsonb_build_object(
    'merchant_id', v_merchant_id,
    'advance_id', v_advance_id
  );
end;
$function$
