CREATE OR REPLACE FUNCTION public.should_suppress(p_email text, p_tenant_id uuid, p_brand text)
 RETURNS boolean
 LANGUAGE sql
 STABLE
AS $function$
  select exists (
    select 1 from public.email_suppressions
    where lower(email) = lower(p_email)
      and (tenant_id is null or tenant_id = p_tenant_id)
      and (brand is null or brand = p_brand)
  );
$function$
