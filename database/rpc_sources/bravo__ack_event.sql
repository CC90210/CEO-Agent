CREATE OR REPLACE FUNCTION public.ack_event(p_event_id uuid, p_agent text)
 RETURNS boolean
 LANGUAGE plpgsql
AS $function$
BEGIN
    UPDATE agent_events
    SET    status = 'done',
           processed_at = NOW(),
           processed_by = p_agent
    WHERE  id = p_event_id
      AND  status IN ('processing', 'pending');
    RETURN FOUND;
END $function$
