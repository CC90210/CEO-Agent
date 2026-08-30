CREATE OR REPLACE FUNCTION public.get_portal_logs(target_automation_id uuid DEFAULT NULL::uuid, target_user_id uuid DEFAULT NULL::uuid, log_limit integer DEFAULT 50)
 RETURNS SETOF automation_logs
 LANGUAGE plpgsql
 SECURITY DEFINER
AS $function$
BEGIN
    -- Security Match: Return data if user is an ADMIN or OWN the data
    IF EXISTS (
        SELECT 1 FROM public.profiles 
        WHERE id = auth.uid() 
        AND (role IN ('admin', 'super_admin') OR is_admin = true OR is_owner = true)
    ) OR (target_user_id = auth.uid()) OR (
        target_automation_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM public.client_automations 
            WHERE id = target_automation_id AND user_id = auth.uid()
        )
    ) THEN
        RETURN QUERY
        SELECT * FROM public.automation_logs
        WHERE (target_automation_id IS NULL OR automation_id = target_automation_id)
        AND (target_user_id IS NULL OR user_id = target_user_id)
        ORDER BY created_at DESC
        LIMIT log_limit;
    END IF;
END;
$function$
