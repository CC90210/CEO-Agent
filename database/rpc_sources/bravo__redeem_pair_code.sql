CREATE OR REPLACE FUNCTION public.redeem_pair_code(p_code text, p_token_hash text, p_label text, p_fingerprint text)
 RETURNS TABLE(pairing_id uuid, tenant_id uuid, auth_user_id uuid, profile_id uuid)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
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
$function$
