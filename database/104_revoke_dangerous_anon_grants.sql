-- ============================================================
-- Migration 104: Revoke dangerous anon-role grants (defense in depth)
-- ============================================================
-- Empire DB (phctllmtsogkovoilwos). Security audit 2026-06-21 (P1-3):
-- the `anon` role held ALL seven table privileges (SELECT, INSERT, UPDATE,
-- DELETE, TRUNCATE, REFERENCES, TRIGGER) on 98 public tables — the broad
-- default-GRANT pattern. RLS is the real gate, but anon should NEVER be able to
-- DELETE / TRUNCATE / create FKs (REFERENCES) / create TRIGGERs. We keep SELECT,
-- INSERT, UPDATE (RLS-gated public read/submit/edit flows) and revoke the rest.
-- Reversible (re-GRANT). New tables are covered by the ALTER DEFAULT PRIVILEGES.
-- ============================================================

REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON ALL TABLES IN SCHEMA public
  FROM anon;

-- Prevent recurrence on tables created later (best-effort; applies to objects
-- created by the role that runs this statement).
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLES FROM anon;
