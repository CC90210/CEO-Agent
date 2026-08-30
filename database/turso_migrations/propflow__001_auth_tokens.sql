-- propflow__001_auth_tokens
--
-- Turso-native table (no Postgres counterpart, so the introspecting transpiler
-- cannot emit it into 000). Holds the single-use tokens that replace Supabase
-- Auth's password-recovery OTP now that PropFlow runs on EMPIRE_AUTH_BACKEND=turso.
--
-- Written by  src/app/api/auth/turso-reset-request/route.ts  (sha256 of the token
-- only -- the raw value exists solely in the email we send) and consumed by
-- src/app/api/auth/turso-reset-confirm/route.ts via a compare-and-swap UPDATE on
-- used_at, which is what makes a link genuinely single-use under concurrency.
--
-- Same shape as the breeze/bravo _auth_tokens so the three apps stay diffable.

CREATE TABLE IF NOT EXISTS "_auth_tokens" (
  "token_hash" TEXT PRIMARY KEY,
  "email" TEXT NOT NULL,
  "purpose" TEXT NOT NULL,
  "expires_at" TEXT NOT NULL,
  "used_at" TEXT,
  "created_at" TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS "_auth_tokens_email_purpose_idx" ON "_auth_tokens" (email, purpose);
