-- ============================================================================
-- Migration 037b — Manual sidecar for 037_team_roles_and_invites.sql
--
-- scripts/apply_migration.py refuses UPDATE/GRANT/REVOKE by design. These
-- statements must be applied manually via the Supabase Dashboard SQL editor
-- AFTER 037 has been applied. They are safe + idempotent.
--
-- Alternative for the backfill: scripts/supabase_tool.py update user_profiles
--   '{"is_owner": true, "team_role": "owner"}' --match '{"tenant_id": "<id>"}'
-- For multi-tenant deployments, audit first:
--   SELECT tenant_id, count(*) FROM user_profiles GROUP BY 1;
-- ============================================================================

-- Backfill: first user_profile per tenant becomes owner.
WITH first_per_tenant AS (
    SELECT DISTINCT ON (tenant_id) id
    FROM public.user_profiles
    WHERE tenant_id IS NOT NULL
    ORDER BY tenant_id, joined_at ASC, created_at ASC
)
UPDATE public.user_profiles
SET is_owner = true, team_role = 'owner'
WHERE id IN (SELECT id FROM first_per_tenant) AND is_owner = false;

-- Lock down redeem_tenant_invite — service-role only.
REVOKE ALL ON FUNCTION public.redeem_tenant_invite(text, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.redeem_tenant_invite(text, uuid) TO service_role;
