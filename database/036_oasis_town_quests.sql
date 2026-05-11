-- ============================================================================
-- Migration 036 — OASIS Town Quest Log (Phase 5 gamification).
--
-- Mirrors the bucketed task list from memory/ACTIVE_TASKS.md into a Supabase
-- table so the OASIS Town frontend can render a live "Quest Log" panel.
-- The publisher (scripts/quest_publisher.py) parses the markdown at every
-- PostToolUse Edit/Write hook on ACTIVE_TASKS.md and upserts here.
--
-- Service-role only writes; OASIS Town reads via the Vercel /api/quests
-- public endpoint (same "public for proof-of-life, harden later" pattern
-- as /api/event-feed and /api/exec-override).
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.oasis_quests (
    id              text PRIMARY KEY,
    bucket          text NOT NULL,
    title           text NOT NULL,
    owner           text,
    status          text NOT NULL DEFAULT 'open',
    source_file     text NOT NULL DEFAULT 'memory/ACTIVE_TASKS.md',
    source_line     int,
    first_seen_at   timestamptz NOT NULL DEFAULT now(),
    completed_at    timestamptz,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_oasis_quests_status
    ON public.oasis_quests (status, bucket);

CREATE INDEX IF NOT EXISTS idx_oasis_quests_updated
    ON public.oasis_quests (updated_at DESC);

ALTER TABLE public.oasis_quests ENABLE ROW LEVEL SECURITY;

CREATE POLICY oasis_quests_service_role_all
    ON public.oasis_quests
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
