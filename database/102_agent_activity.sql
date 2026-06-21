-- ============================================================
-- BRAVO — Migration 102: agent_activity (cross-org agent↔agent channel)
-- ============================================================
-- PURPOSE
-- Shared status table for the OASIS coordination collaboration between
-- Bravo (CC's agent) and APEX (Adon's agent, @KnutRPEbot). Telegram bots
-- cannot see each other's messages — this table is how the two agents read
-- each other. Humans never touch it; each agent also mirrors its status into
-- the OASIS Telegram group (-5165125484) so CC + Adon see who's doing what.
--
-- CONTRACT NOTE: the column shape below is the agreed interface APEX was
-- built against (see cc-agent-coordination-setup.md). Do NOT rename or drop
-- columns — APEX inserts against this exact schema. Additive changes only.
--
-- ACCESS: service-role ONLY. Both agents authenticate with the bravo project
-- service-role key. RLS is ENABLED + FORCED with ZERO policies, so anon and
-- authenticated are denied ALL rows (verified 2026-06-19: anon SELECT returns
-- empty, anon INSERT raises 42501). That is the ACTIVE gate. The REVOKE below
-- is belt-and-suspenders that also strips the table-level GRANTs — but the
-- exec_sql RPC refuses privilege changes, so it must be run ONCE MANUALLY in
-- the Supabase SQL editor. Until then, RLS-forced-no-policy already secures it.
--
-- NOTE: service_role bypasses RLS PROJECT-WIDE. Whoever holds the bravo
-- service-role key (incl. APEX) can read/write EVERY table in this project,
-- not just agent_activity. If that blast radius is unacceptable, issue APEX a
-- narrow credential / RPC scoped to this table instead of the shared key.
-- ============================================================

CREATE TABLE IF NOT EXISTS agent_activity (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  agent       TEXT        NOT NULL,                 -- 'apex' | 'cc-agent'
  status      TEXT        NOT NULL,                 -- 'start' | 'working' | 'done' | 'blocked'
  task        TEXT        NOT NULL,                 -- e.g. 'Batch 5 — delete documents'
  files       TEXT[],                               -- files/areas being touched (claim)
  branch      TEXT,                                 -- git branch
  detail      TEXT,                                 -- freeform note
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Primary read path: "what happened recently, newest first".
CREATE INDEX IF NOT EXISTS agent_activity_created_idx
  ON agent_activity (created_at DESC);

-- Secondary read path: "what has the OTHER agent done recently" + open claims.
CREATE INDEX IF NOT EXISTS agent_activity_agent_created_idx
  ON agent_activity (agent, created_at DESC);

-- service-role only (both agents use the service key); lock out client roles.
-- RLS enabled + forced + zero policies = anon/authenticated denied all rows.
ALTER TABLE agent_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_activity FORCE ROW LEVEL SECURITY;

-- MANUAL STEP (NOT in this migration on purpose): the belt-and-suspenders
-- privilege strip below is a privilege change, which scripts/apply_migration.py
-- HARD-BLOCKS — leaving it inline would abort the whole migration before the
-- table is created. Run it once by hand in the Supabase SQL editor:
--     REVOKE ALL ON agent_activity FROM anon, authenticated;
-- (RLS-forced-no-policy above already secures the table without it.)

COMMENT ON TABLE agent_activity IS
  'Cross-org agent<->agent coordination channel for the OASIS collaboration '
  '(Bravo + APEX). Service-role only; RLS forced. Mirrored to Telegram group '
  '-5165125484 for human visibility. Created 2026-06-19. Schema is a contract '
  'with APEX — additive changes only.';
