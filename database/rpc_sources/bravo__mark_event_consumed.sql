CREATE OR REPLACE FUNCTION public.mark_event_consumed(p_event_id uuid, p_agent text)
 RETURNS boolean
 LANGUAGE plpgsql
AS $function$
DECLARE
    already BOOLEAN;
BEGIN
    SELECT p_agent = ANY(consumed_by) INTO already
    FROM agent_events WHERE id = p_event_id;

    IF already IS TRUE THEN RETURN FALSE; END IF;

    UPDATE agent_events
    SET consumed_by = array_append(consumed_by, p_agent)
    WHERE id = p_event_id;
    RETURN TRUE;
END $function$
