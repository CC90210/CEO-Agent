-- Migration 032 — bridge_pair_codes
--
-- One-time, time-limited codes the operator generates from /settings →
-- Devices to pair a new machine without copy-pasting tokens. Flow:
--
--   1. Logged-in user clicks "Generate code" → POST /api/auth/pair-code
--      mints a row here (15 min TTL, tied to their tenant + auth user).
--   2. User runs `bravo setup` on the new machine, pastes the 9-char
--      code (xxx-xxx-xxx). The CLI hits POST /api/auth/pair-code/redeem
--      which marks consumed_at + consumed_by_pairing_id and returns the
--      bridge token.
--   3. Code is single-use; second redemption returns 410. Expired codes
--      return 404.
--
-- The code itself is high-entropy (9 alphanumeric chars, ~46 bits of
-- entropy across the alphabet we use — see /api/auth/pair-code/route.ts).
-- Stored plaintext (not hashed) because we need to look up by code; the
-- 15-min window + single-use semantics keep the leak window tight.

CREATE TABLE IF NOT EXISTS bridge_pair_codes (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code                     TEXT NOT NULL UNIQUE,
  tenant_id                UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  auth_user_id             UUID NOT NULL,
  email                    TEXT NOT NULL,
  expires_at               TIMESTAMPTZ NOT NULL,
  consumed_at              TIMESTAMPTZ,
  consumed_by_pairing_id   UUID REFERENCES bridge_pairings(id),
  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bridge_pair_codes_code_active
  ON bridge_pair_codes(code)
  WHERE consumed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_bridge_pair_codes_tenant
  ON bridge_pair_codes(tenant_id, created_at DESC);

-- RLS: only the issuing user can see their own codes via the dashboard.
-- The redeem endpoint uses the service role; codes never get returned via
-- a session-authed API outside of that.
ALTER TABLE bridge_pair_codes ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'bridge_pair_codes'
      AND policyname = 'pair_codes_owner_select'
  ) THEN
    EXECUTE $POL$
      CREATE POLICY pair_codes_owner_select ON bridge_pair_codes
        FOR SELECT
        TO authenticated
        USING (auth.uid() = auth_user_id)
    $POL$;
  END IF;
END
$$;

COMMENT ON TABLE bridge_pair_codes IS
  'One-time, 15-minute pair codes for adding a new bridge device without token copy-paste. See /api/auth/pair-code/* routes.';
