CREATE OR REPLACE FUNCTION public.register_incoming_webhook_event(p_provider text, p_event_id text, p_payload_hash text DEFAULT NULL::text, p_ttl_seconds integer DEFAULT 86400)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  inserted_count integer;
BEGIN
  IF p_provider IS NULL OR btrim(p_provider) = '' OR p_event_id IS NULL OR btrim(p_event_id) = '' THEN
    RAISE EXCEPTION 'Invalid webhook identity';
  END IF;

  DELETE FROM public.incoming_webhook_events WHERE expires_at < now();
  INSERT INTO public.incoming_webhook_events (provider, event_id, payload_hash, expires_at)
  VALUES (p_provider, p_event_id, p_payload_hash, now() + make_interval(secs => greatest(COALESCE(p_ttl_seconds, 86400), 60)))
  ON CONFLICT (provider, event_id) DO NOTHING;
  GET DIAGNOSTICS inserted_count = ROW_COUNT;
  RETURN inserted_count = 1;
END;
$function$
