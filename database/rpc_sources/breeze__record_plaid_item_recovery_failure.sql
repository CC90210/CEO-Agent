CREATE OR REPLACE FUNCTION public.record_plaid_item_recovery_failure(p_tenant_id uuid, p_plaid_item_id text, p_last_error text)
 RETURNS void
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  update public.plaid_items
  set status = 'error',
      retry_count = retry_count + 1,
      last_attempt_at = now(),
      last_error = left(p_last_error, 1000)
  where tenant_id = p_tenant_id
    and plaid_item_id = p_plaid_item_id
    and status <> 'active';
$function$
