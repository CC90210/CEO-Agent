CREATE OR REPLACE FUNCTION public.increment_promo_uses(promo_id uuid)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
  UPDATE promo_codes SET uses_count = uses_count + 1 WHERE id = promo_id;
END;
$function$
