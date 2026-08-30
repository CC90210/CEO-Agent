CREATE OR REPLACE FUNCTION public.claim_events(p_agent text, p_max integer DEFAULT 10, p_visibility_seconds integer DEFAULT 30)
 RETURNS SETOF agent_events
 LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    UPDATE agent_events e
    SET    status           = 'processing',
           processed_by     = p_agent,
           visibility_until = NOW() + (p_visibility_seconds || ' seconds')::INTERVAL
    WHERE  e.id IN (
        SELECT e2.id
        FROM   agent_events e2
        WHERE  e2.status = 'pending'
          AND  (e2.target_agent = p_agent OR e2.target_agent IS NULL)
          AND  (e2.visibility_until IS NULL OR e2.visibility_until <= NOW())
        ORDER BY e2.published_at
        LIMIT p_max
        FOR UPDATE SKIP LOCKED
    )
    RETURNING e.*;
END $function$
