CREATE OR REPLACE FUNCTION public.reap_stuck_events()
 RETURNS integer
 LANGUAGE plpgsql
AS $function$
DECLARE n INT;
BEGIN
    WITH reaped AS (
        UPDATE agent_events
        SET    status = 'pending',
               visibility_until = NULL,
               retry_count = retry_count + 1,
               last_error = COALESCE(last_error, '') || ' | visibility-timeout-reaped'
        WHERE  status = 'processing'
          AND  visibility_until <= NOW()
        RETURNING id
    )
    SELECT COUNT(*) INTO n FROM reaped;
    RETURN n;
END $function$
