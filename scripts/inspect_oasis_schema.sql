-- Read-only schema inspection — what's present on oasis?
-- Used to plan which migrations need re-applying.
SELECT
    'table:' || table_name AS object
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
      'tenants', 'tenant_users', 'agent_model_config',
      'lead_documents', 'lead_interactions', 'lead_stage_definitions',
      'tenant_integration_credentials', 'chat_attachments',
      'leads', 'profiles', 'user_profiles'
  )
UNION ALL
SELECT 'column:tenants.brand_logo_url'
WHERE EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'tenants'
      AND column_name = 'brand_logo_url'
)
UNION ALL
SELECT 'column:lead_interactions.' || column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'lead_interactions'
  AND column_name IN (
      'body', 'interaction_type',
      'email_from', 'email_to', 'email_subject', 'email_message_id'
  )
UNION ALL
SELECT 'policy:' || schemaname || '.' || tablename || '.' || policyname
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename IN ('agent_model_config', 'lead_documents')
  AND policyname IN ('amc_select_own_and_default', 'amc_select_any', 'ld_member_all')
ORDER BY 1;
