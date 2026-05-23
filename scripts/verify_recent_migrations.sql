-- ============================================================================
-- verify_recent_migrations.sql
--
-- Diagnostic for the migrations shipped 2026-05-19 through 2026-05-23.
-- Earlier migrations (001-055) are foundational — if they weren't applied,
-- the dashboard wouldn't render. This script focuses on the recent batch
-- that's most likely to be in git but not yet applied to the live Supabase.
--
-- USAGE: paste into the Supabase SQL editor and run.
--   - Each row returns the migration id + a `status` label
--   - `applied` = the schema element exists; safe to assume the migration ran.
--   - `pending` = the schema element is missing; APPLY this migration.
--   - `partial` = some elements present, others missing; investigate.
--
-- READ-ONLY. Zero mutations. Idempotent. Re-runnable as often as needed.
-- ============================================================================

WITH checks AS (
    -- 056 — tenant_brand_logo column on tenants (actual column name: logo_url)
    SELECT
        '056_tenant_brand_logo' AS migration,
        'tenants.logo_url' AS verifies,
        CASE
            WHEN EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'tenants'
                  AND column_name = 'logo_url'
            ) THEN 'applied'
            ELSE 'pending'
        END AS status

    UNION ALL
    -- 057 — lead_documents.storage_path CHECK constraint
    SELECT
        '057_lead_documents_storage_path_check',
        'lead_documents.storage_path CHECK constraint',
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class cls ON cls.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = cls.relnamespace
                WHERE n.nspname = 'public'
                  AND cls.relname = 'lead_documents'
                  AND c.contype = 'c'
                  AND pg_get_constraintdef(c.oid) ILIKE '%storage_path%'
            ) THEN 'applied'
            ELSE 'pending'
        END

    UNION ALL
    -- 057b — drop of legacy member-all policy on lead_documents
    SELECT
        '057b_lead_documents_drop_member_all',
        'lead_documents → legacy ld_member_all policy is GONE',
        CASE
            WHEN NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = 'lead_documents'
                  AND policyname = 'ld_member_all'
            ) THEN 'applied'
            ELSE 'pending'
        END

    UNION ALL
    -- 058 — tenant_integration_credentials table exists
    SELECT
        '058_tenant_integration_credentials',
        'tenant_integration_credentials table',
        CASE
            WHEN EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'tenant_integration_credentials'
            ) THEN 'applied'
            ELSE 'pending'
        END

    UNION ALL
    -- 059 — lead_interactions.* new columns
    -- Verifies the 5 columns the migration actually adds:
    --   direction, content_preview, to_email, to_phone, sent_at
    SELECT
        '059_lead_interactions_unified_columns',
        'lead_interactions.{direction, content_preview, to_email, to_phone, sent_at}',
        CASE
            WHEN (
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'lead_interactions'
                  AND column_name IN (
                      'direction', 'content_preview',
                      'to_email', 'to_phone', 'sent_at'
                  )
            ) = 5 THEN 'applied'
            ELSE 'partial_or_pending'
        END

    UNION ALL
    -- 060 — lead_interactions legacy lead_id FK dropped
    -- "applied" only if the table exists AND the legacy FK is gone (an
    -- absent table means migration 023 / leads-schema is also missing,
    -- which is upstream of this drop — surface as pending so the operator
    -- applies the schema migrations first).
    SELECT
        '060_lead_interactions_drop_legacy_lead_fk',
        'lead_interactions.lead_id legacy FK to leads(id) is GONE',
        CASE
            WHEN NOT EXISTS (
                SELECT 1 FROM pg_class cls
                JOIN pg_namespace n ON n.oid = cls.relnamespace
                WHERE n.nspname = 'public' AND cls.relname = 'lead_interactions'
            ) THEN 'pending'
            WHEN NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class cls ON cls.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = cls.relnamespace
                WHERE n.nspname = 'public'
                  AND cls.relname = 'lead_interactions'
                  AND c.contype = 'f'
                  AND pg_get_constraintdef(c.oid) ILIKE '%REFERENCES%public.leads%'
            ) THEN 'applied'
            ELSE 'pending'
        END

    UNION ALL
    -- 061 — chat_attachments table exists
    SELECT
        '061_chat_attachments',
        'chat_attachments table',
        CASE
            WHEN EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'chat_attachments'
            ) THEN 'applied'
            ELSE 'pending'
        END

    UNION ALL
    -- 062 — OASIS lead lifecycle 7→11 stages
    -- The migration remaps tenant_records.data->>'stage' for the oasis tenant:
    --   old 'new'       -> 'new_contact'
    --   old 'contacted' -> 'outreach'
    --   old 'won'       -> 'active_client'
    -- "applied" = none of the old stage values remain for oasis leads (also
    -- vacuously true if there are zero oasis lead rows at all — that's fine,
    -- the remap is a no-op on empty data).
    SELECT
        '062_oasis_lead_lifecycle_v2',
        'no oasis lead rows still carry old stage values (new/contacted/won)',
        CASE
            WHEN NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'tenant_records'
            ) THEN 'pending'
            WHEN NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'tenants'
            ) THEN 'pending'
            WHEN EXISTS (
                SELECT 1
                FROM tenant_records tr
                JOIN tenants t ON t.id = tr.tenant_id
                WHERE t.slug = 'oasis'
                  AND tr.entity_type = 'lead'
                  AND tr.data->>'stage' IN ('new', 'contacted', 'won')
            ) THEN 'pending'
            ELSE 'applied'
        END

    UNION ALL
    -- 063 — agent_config_read_privacy (THE BIG ONE — multi-employee privacy)
    SELECT
        '063_agent_config_read_privacy',
        'amc_select_own_and_default RLS policy on agent_model_config',
        CASE
            WHEN EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = 'agent_model_config'
                  AND policyname = 'amc_select_own_and_default'
            ) THEN 'applied'
            ELSE 'pending'
        END
)
SELECT
    migration,
    status,
    verifies,
    CASE status
        WHEN 'applied' THEN '✓'
        WHEN 'pending' THEN '✗ APPLY THIS'
        ELSE '? INVESTIGATE'
    END AS verdict
FROM checks
ORDER BY migration;
