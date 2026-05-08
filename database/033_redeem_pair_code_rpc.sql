-- Migration 033 — atomic redeem_pair_code RPC
--
-- Codex adversarial review of the pair-code flow flagged that the
-- two-step "claim then insert pairing" approach in the JS handler is
-- race-prone under retries. Even with the consume-first ordering, a
-- network hiccup between (a) the bridge_pairings insert and (b) the
-- response delivery would burn the code without the client ever
-- receiving the token. The plaintext token is gone (only hash on file).
--
-- Fix: a single PL/pgSQL function does claim + insert + return in one
-- transaction. The JS route mints the plaintext token, hashes it, and
-- passes both to this function. If anything inside the function fails
-- (insert error, code already consumed, etc.) the whole transaction
-- rolls back and the code stays redeemable. The client retries with
-- a fresh token (the function generates and returns the pairing_id;
-- the JS layer holds the plaintext that hashes to bridge_token_hash).
--
-- Returns the bridge_pairings.id on success. Raises with a typed
-- error code on failure so the JS handler can map to HTTP 404 / 410 /
-- 500 cleanly:
--
--   PCODE_NOT_FOUND  -> code never existed (404)
--   PCODE_EXPIRED    -> exists but past expires_at (404)
--   PCODE_CONSUMED   -> already redeemed (410)
--
-- Idempotency: the function does NOT support replay. If the client
-- retries after a successful claim, the second call returns
-- PCODE_CONSUMED. To make redeem retry-safe at the client level the
-- caller would need an idempotency key (machine_fingerprint is the
-- natural choice — same machine retrying gets the existing pairing).
-- Deferred: clients can re-generate a code in 15 minutes.

CREATE OR REPLACE FUNCTION public.redeem_pair_code(
  p_code              TEXT,
  p_token_hash        TEXT,
  p_label             TEXT,
  p_fingerprint       TEXT
) RETURNS TABLE (
  pairing_id          UUID,
  tenant_id           UUID,
  auth_user_id        UUID,
  profile_id          UUID
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_code_id           UUID;
  v_tenant_id         UUID;
  v_auth_user_id      UUID;
  v_expires_at        TIMESTAMPTZ;
  v_consumed_at       TIMESTAMPTZ;
  v_pairing_id        UUID;
  v_profile_id        UUID;
BEGIN
  -- Lock the row for this transaction so concurrent redeemers serialize.
  SELECT id, bpc.tenant_id, bpc.auth_user_id, expires_at, consumed_at
  INTO v_code_id, v_tenant_id, v_auth_user_id, v_expires_at, v_consumed_at
  FROM bridge_pair_codes bpc
  WHERE code = p_code
  FOR UPDATE;

  IF v_code_id IS NULL THEN
    RAISE EXCEPTION 'PCODE_NOT_FOUND' USING ERRCODE = 'P0001';
  END IF;
  IF v_consumed_at IS NOT NULL THEN
    RAISE EXCEPTION 'PCODE_CONSUMED' USING ERRCODE = 'P0002';
  END IF;
  IF v_expires_at < NOW() THEN
    RAISE EXCEPTION 'PCODE_EXPIRED' USING ERRCODE = 'P0003';
  END IF;

  -- Insert the pairing in the same transaction as the consume update.
  INSERT INTO bridge_pairings (
    tenant_id, user_id, label, bridge_token_hash, machine_fingerprint, last_seen_at
  ) VALUES (
    v_tenant_id, v_auth_user_id, COALESCE(p_label, 'Local install'),
    p_token_hash, p_fingerprint, NOW()
  )
  RETURNING id INTO v_pairing_id;

  -- Stamp the code consumed AFTER insert succeeds. If insert raised, the
  -- whole transaction rolls back including this update — the code stays
  -- redeemable. Atomicity guarantees the client sees one of:
  --   * success: code consumed AND pairing exists
  --   * failure: code untouched AND no pairing
  UPDATE bridge_pair_codes
  SET consumed_at = NOW(), consumed_by_pairing_id = v_pairing_id
  WHERE id = v_code_id;

  -- Resolve profile_id for response shape parity with /api/auth/pair.
  SELECT id INTO v_profile_id
  FROM user_profiles
  WHERE user_profiles.auth_user_id = v_auth_user_id
  LIMIT 1;

  RETURN QUERY SELECT v_pairing_id, v_tenant_id, v_auth_user_id, v_profile_id;
END;
$$;

-- service_role bypasses RLS by default and SECURITY DEFINER lets it
-- execute regardless of grants, so an explicit GRANT EXECUTE isn't
-- strictly required for the supabase service role. The redeem endpoint
-- uses the service-role key (see redeem/route.ts:getServiceSupabase).

COMMENT ON FUNCTION public.redeem_pair_code IS
  'Atomic pair-code redeem: claim + insert bridge_pairings + return pairing details in one transaction. Raises PCODE_NOT_FOUND / PCODE_CONSUMED / PCODE_EXPIRED on failure. See app/api/auth/pair-code/redeem/route.ts.';
