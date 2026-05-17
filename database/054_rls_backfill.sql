-- ============================================================================
-- Migration 054 - audit RPC hardening + defensive RLS backfill
--
-- The RLS audit on 2026-05-17 found no live tenant_id table gaps on main,
-- but this migration makes the check self-healing for future tables that
-- accidentally land with tenant_id and no policy. It also hardens
-- log_tenant_event() so authenticated callers can only log against their
-- own tenant; actor_user_id continues to come from auth.uid().
-- ============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION public.log_tenant_event(
    p_tenant_id     uuid,
    p_action_type   text,
    p_target_table  text DEFAULT NULL,
    p_target_id     text DEFAULT NULL,
    p_before        jsonb DEFAULT NULL,
    p_after         jsonb DEFAULT NULL,
    p_ip_hash       text DEFAULT NULL,
    p_user_agent    text DEFAULT NULL,
    p_metadata      jsonb DEFAULT '{}'::jsonb
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_id uuid;
    v_actor_email text;
BEGIN
    IF p_tenant_id IS NULL THEN
        RAISE EXCEPTION 'tenant_id required';
    END IF;

    IF auth.role() <> 'service_role' THEN
        IF auth.uid() IS NULL THEN
            RAISE EXCEPTION 'authenticated user required';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM public.user_profiles up
            WHERE up.auth_user_id = auth.uid()
              AND up.tenant_id = p_tenant_id
        ) THEN
            RAISE EXCEPTION 'cannot log audit events for another tenant';
        END IF;
    END IF;

    SELECT email INTO v_actor_email
    FROM auth.users
    WHERE id = auth.uid()
    LIMIT 1;

    INSERT INTO public.tenant_audit_log (
        tenant_id, actor_user_id, actor_email,
        action_type, target_table, target_id,
        before, after, ip_hash, user_agent, metadata
    ) VALUES (
        p_tenant_id, auth.uid(), v_actor_email,
        p_action_type, p_target_table, p_target_id,
        p_before, p_after, p_ip_hash, p_user_agent, COALESCE(p_metadata, '{}'::jsonb)
    )
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION public.log_tenant_event(uuid, text, text, text, jsonb, jsonb, text, text, jsonb) IS
  'SOC2-style audit logger. Authenticated callers may only log events for '
  'their own tenant; actor_user_id is stamped from auth.uid().';

DO $$
DECLARE
    r record;
    v_policy_name text;
BEGIN
    FOR r IN
        WITH tenant_tables AS (
            SELECT
                c.oid,
                n.nspname AS schema_name,
                c.relname AS table_name,
                c.relrowsecurity AS rls_enabled,
                COUNT(p.polname)::int AS policy_count
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN information_schema.columns col
              ON col.table_schema = n.nspname
             AND col.table_name = c.relname
             AND col.column_name = 'tenant_id'
            LEFT JOIN pg_policy p ON p.polrelid = c.oid
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'p')
              AND c.relname <> 'tenant_audit_log'
            GROUP BY c.oid, n.nspname, c.relname, c.relrowsecurity
        )
        SELECT *
        FROM tenant_tables
        WHERE NOT rls_enabled OR policy_count = 0
    LOOP
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', r.schema_name, r.table_name);

        IF r.policy_count = 0 THEN
            v_policy_name := left('tenant_select_own_' || r.table_name, 60);
            EXECUTE format(
                'CREATE POLICY %I ON %I.%I FOR SELECT TO authenticated USING (tenant_id = public.current_tenant_id())',
                v_policy_name,
                r.schema_name,
                r.table_name
            );
        END IF;
    END LOOP;
END $$;

COMMIT;
