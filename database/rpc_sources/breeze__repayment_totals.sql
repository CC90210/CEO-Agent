CREATE OR REPLACE FUNCTION public.repayment_totals(p_tenant_id uuid, p_merchant_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(total_cents bigint, entry_count bigint)
 LANGUAGE sql
 STABLE
 SET search_path TO 'public'
AS $function$
  select
    coalesce(sum(r.amount_cents), 0)::bigint as total_cents,
    count(*)::bigint as entry_count
  from public.repayments r
  where r.tenant_id = p_tenant_id
    and (p_merchant_id is null or r.merchant_id = p_merchant_id);
$function$
