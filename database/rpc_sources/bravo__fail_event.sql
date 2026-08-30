CREATE OR REPLACE FUNCTION public.fail_event(p_event_id uuid, p_agent text, p_error text, p_max_retries integer DEFAULT 3)
 RETURNS text
 LANGUAGE plpgsql
AS $function$
DECLARE
    new_count INT;
    new_status TEXT;
BEGIN
    UPDATE agent_events
    SET    retry_count = retry_count + 1,
           last_error  = p_error,
           processed_by = p_agent
    WHERE  id = p_event_id
    RETURNING retry_count INTO new_count;

    IF new_count >= p_max_retries THEN
        new_status := 'dead';
    ELSE
        new_status := 'pending';
    END IF;

    UPDATE agent_events
    SET    status = new_status,
           visibility_until = NULL
    WHERE  id = p_event_id;

    RETURN new_status;
END $function$
