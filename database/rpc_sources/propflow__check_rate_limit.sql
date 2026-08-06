CREATE OR REPLACE FUNCTION public.check_rate_limit(p_scope text, p_limit integer, p_window_seconds integer DEFAULT 60)
 RETURNS TABLE(allowed boolean, current_count integer, reset_at timestamp with time zone)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  current_time timestamptz := now();
  seconds integer := greatest(COALESCE(p_window_seconds, 60), 1);
  bucket_start timestamptz;
BEGIN
  IF p_scope IS NULL OR btrim(p_scope) = '' OR p_limit < 1 THEN
    RAISE EXCEPTION 'Invalid rate-limit parameters';
  END IF;

  DELETE FROM public.api_rate_limits WHERE expires_at < current_time;
  bucket_start := to_timestamp(floor(extract(epoch FROM current_time) / seconds) * seconds);

  INSERT INTO public.api_rate_limits (scope, window_start, count, expires_at)
  VALUES (p_scope, bucket_start, 1, bucket_start + make_interval(secs => seconds * 2))
  ON CONFLICT (scope, window_start) DO UPDATE
  SET count = public.api_rate_limits.count + 1, updated_at = current_time
  RETURNING count INTO current_count;

  allowed := current_count <= p_limit;
  reset_at := bucket_start + make_interval(secs => seconds);
  RETURN NEXT;
END;
$function$
