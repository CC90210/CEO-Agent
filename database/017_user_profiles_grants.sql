-- Companion grants for migration 017. Run manually in Supabase Dashboard
-- SQL editor (the apply_migration.py tool refuses GRANT statements by design).
GRANT EXECUTE ON FUNCTION public.record_inbound_from_n8n_v2 TO service_role;
GRANT EXECUTE ON FUNCTION public.ping_integration TO service_role;
