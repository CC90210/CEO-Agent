CREATE OR REPLACE FUNCTION public.generate_invoice_number(p_company_id uuid)
 RETURNS text
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  next_number bigint;
  prefix text;
BEGIN
  IF p_company_id <> public.get_user_company_id()
     AND auth.role() IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'Forbidden';
  END IF;

  UPDATE public.companies
  SET next_invoice_number = next_invoice_number + 1
  WHERE id = p_company_id
  RETURNING next_invoice_number - 1, invoice_prefix INTO next_number, prefix;

  IF next_number IS NULL THEN RAISE EXCEPTION 'Company not found'; END IF;
  RETURN prefix || lpad(next_number::text, 5, '0');
END;
$function$
