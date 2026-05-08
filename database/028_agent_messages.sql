-- ============================================================
-- BRAVO V6 — Migration 028: agent_messages (Supabase-backed inbox)
-- ============================================================
-- PURPOSE
-- Move the agent inbox from filesystem JSON files (tmp/agent_inbox/*) to
-- a real Supabase table so:
--   1. Multi-machine: messages posted from one machine are visible on the
--      dashboard regardless of which client laptop you opened.
--   2. Real-time UI: a sidebar unread badge can subscribe via Supabase
--      Realtime instead of polling the filesystem.
--   3. Tenant-scoped: every row carries tenant_id so a multi-tenant deploy
--      keeps each operator's inbox isolated by RLS.
--   4. Auditable: created_at + read_at timestamps survive a wipe of tmp/.
--
-- The filesystem path stays as a SECONDARY mirror — local agents that
-- post via scripts/agent_inbox.py still write JSON for backward compat,
-- and a future hook syncs those to this table. Today's read path is
-- Supabase-first with filesystem fallback.
-- ============================================================

CREATE TABLE IF NOT EXISTS agent_messages (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Short id from scripts/agent_inbox.py (uuid4().hex[:12]). Kept for
  -- cross-reference with filesystem JSON files during the dual-write
  -- period. Indexed unique within tenant so a re-post is idempotent.
  message_id    TEXT        NOT NULL,
  tenant_id     UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  from_agent    TEXT        NOT NULL,
  to_agent      TEXT        NOT NULL,
  subject       TEXT,
  body          TEXT        NOT NULL,
  priority      TEXT        NOT NULL DEFAULT 'normal'
                            CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
  requires_response BOOLEAN NOT NULL DEFAULT false,
  in_reply_to   TEXT,
  thread_id     TEXT,
  read_at       TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, message_id)
);

-- Hot-path index: "what's unread for agent X in tenant T, urgent first".
-- Covers the sidebar badge query + /inbox unread tab.
CREATE INDEX IF NOT EXISTS agent_messages_tenant_to_unread_idx
  ON agent_messages (tenant_id, to_agent, priority, created_at DESC)
  WHERE read_at IS NULL;

-- Secondary index for the archived ("Read") tab — sorted newest-first.
CREATE INDEX IF NOT EXISTS agent_messages_tenant_to_read_idx
  ON agent_messages (tenant_id, to_agent, created_at DESC)
  WHERE read_at IS NOT NULL;

-- Thread lookup for reply-chain reconstruction.
CREATE INDEX IF NOT EXISTS agent_messages_thread_idx
  ON agent_messages (tenant_id, thread_id);

-- ────────────────────────────────────────────────────────────────────
-- RLS — tenant isolation
-- ────────────────────────────────────────────────────────────────────
-- Every row scoped to tenant_id. Service-role bypasses RLS (the dashboard
-- uses service-role today; switch to authed RLS once /inbox uses session
-- supabase client). Owner CAN see their own tenant's messages.

ALTER TABLE agent_messages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "agent_messages_select_own_tenant" ON agent_messages;
CREATE POLICY "agent_messages_select_own_tenant"
  ON agent_messages
  FOR SELECT
  TO authenticated
  USING (
    tenant_id IN (
      SELECT tenant_id
      FROM user_profiles
      WHERE auth_user_id = auth.uid()
    )
  );

DROP POLICY IF EXISTS "agent_messages_insert_own_tenant" ON agent_messages;
CREATE POLICY "agent_messages_insert_own_tenant"
  ON agent_messages
  FOR INSERT
  TO authenticated
  WITH CHECK (
    tenant_id IN (
      SELECT tenant_id
      FROM user_profiles
      WHERE auth_user_id = auth.uid()
    )
  );

DROP POLICY IF EXISTS "agent_messages_update_own_tenant" ON agent_messages;
CREATE POLICY "agent_messages_update_own_tenant"
  ON agent_messages
  FOR UPDATE
  TO authenticated
  USING (
    tenant_id IN (
      SELECT tenant_id
      FROM user_profiles
      WHERE auth_user_id = auth.uid()
    )
  );

COMMENT ON TABLE agent_messages IS
  'Cross-agent async messaging. Replaces the filesystem JSON queue at '
  'tmp/agent_inbox/ for multi-machine + tenant-scoped delivery. Created '
  '2026-05-08 as part of CC inbox-migration push.';
