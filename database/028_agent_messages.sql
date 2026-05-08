-- ============================================================
-- BRAVO V6 — Migration 028: agent_messages (Supabase-backed inbox)
-- ============================================================
-- PURPOSE
-- Move the agent inbox from filesystem JSON files (tmp/agent_inbox/*) to
-- a Supabase table for multi-machine, tenant-scoped, auditable delivery.
-- Filesystem path stays as a SECONDARY mirror so local agents that post
-- via scripts/agent_inbox.py keep working through the dual-write period.
-- ============================================================

CREATE TABLE IF NOT EXISTS agent_messages (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
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

CREATE INDEX IF NOT EXISTS agent_messages_tenant_to_unread_idx
  ON agent_messages (tenant_id, to_agent, priority, created_at DESC)
  WHERE read_at IS NULL;

CREATE INDEX IF NOT EXISTS agent_messages_tenant_to_read_idx
  ON agent_messages (tenant_id, to_agent, created_at DESC)
  WHERE read_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS agent_messages_thread_idx
  ON agent_messages (tenant_id, thread_id);

ALTER TABLE agent_messages ENABLE ROW LEVEL SECURITY;

-- Use DO blocks to create policies idempotently — pg_policies lookup so
-- re-running this migration is a no-op instead of erroring.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'agent_messages'
      AND policyname = 'agent_messages_select_own_tenant'
  ) THEN
    CREATE POLICY "agent_messages_select_own_tenant"
      ON agent_messages
      FOR SELECT
      TO authenticated
      USING (
        tenant_id IN (
          SELECT tenant_id FROM user_profiles WHERE auth_user_id = auth.uid()
        )
      );
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'agent_messages'
      AND policyname = 'agent_messages_insert_own_tenant'
  ) THEN
    CREATE POLICY "agent_messages_insert_own_tenant"
      ON agent_messages
      FOR INSERT
      TO authenticated
      WITH CHECK (
        tenant_id IN (
          SELECT tenant_id FROM user_profiles WHERE auth_user_id = auth.uid()
        )
      );
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'agent_messages'
      AND policyname = 'agent_messages_update_own_tenant'
  ) THEN
    CREATE POLICY "agent_messages_update_own_tenant"
      ON agent_messages
      FOR UPDATE
      TO authenticated
      USING (
        tenant_id IN (
          SELECT tenant_id FROM user_profiles WHERE auth_user_id = auth.uid()
        )
      );
  END IF;
END $$;

COMMENT ON TABLE agent_messages IS
  'Cross-agent async messaging. Replaces tmp/agent_inbox filesystem queue '
  'for multi-machine tenant-scoped delivery. Created 2026-05-08.';
