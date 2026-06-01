-- ============================================================================
-- Migration 088 — shopping_threads (round-level shop-out tracking)
--
-- One row per shopping ROUND (a single fan-out of a loan file to N lenders).
-- Distinct from application_lender_threads (migration 044 in SunBiz-Agent),
-- which tracks per-(application, lender) state. The round-level row owns:
--   - the References anchor every per-lender outbound shares (so Gmail
--     groups all N sends + all N replies as one conversation in the
--     initiating agent's CC'd inbox)
--   - the round_number for the lead (1 = first shop, 2 = re-shop, etc.)
--   - the agent who fired the round
--   - per-lender status snapshot (lenders[].status) so the tracking
--     agent can read one row to see the whole round
--
-- Re-shopping a file produces a NEW shopping_threads row with a NEW
-- root_message_id — that's how lenders added later land on a separate
-- email thread instead of polluting the first round's conversation.
--
-- Idempotent. Re-runnable.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.shopping_threads (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    -- The lead this round belongs to. Stored as text because lead rows
    -- live in tenant_records (V6 universal JSONB wide-row pattern) — no
    -- FK target column exists at the public.leads level.
    lead_id           text NOT NULL,
    -- Sequential round counter per (tenant, lead). 1 = first fan-out,
    -- 2 = re-shop, etc. The tool computes this server-side on insert
    -- (one-statement INSERT ... SELECT COALESCE(MAX(round_number),0)+1
    -- so concurrent rounds for the same lead don't collide).
    round_number      integer NOT NULL,
    -- RFC-822 angle-bracketed Message-ID synthesized at round creation.
    -- Every per-lender outbound carries this in its References header
    -- so Gmail/Outlook group them as one conversation for the CC'd
    -- agent. Format: '<round-{uuid}@oasis>'.
    root_message_id   text NOT NULL,
    -- auth.users.id of the agent who fired this round. Used as the
    -- automatic CC on every outbound + surfaced in the tracking UI as
    -- "shopped by ...".
    agent_user_id     uuid NOT NULL REFERENCES auth.users(id) ON DELETE SET NULL,
    -- Per-lender state snapshot. Each element:
    --   {
    --     "lender_id":       "...",          -- tenant_records lender id
    --     "lender_name":     "...",
    --     "recipient_email": "...",
    --     "message_id":      "<round-{uuid}-lender-{id}@oasis>",
    --     "interaction_id":  "...",          -- send_gateway lead_interactions id
    --     "status":          "pending|sent|error|replied|no_response",
    --     "error":           "..." | null,
    --     "sent_at":         iso8601 | null,
    --     "last_response_at":iso8601 | null
    --   }
    -- jsonb so the tracking tool reads one row to render the whole round.
    lenders           jsonb NOT NULL DEFAULT '[]'::jsonb,
    -- Round-level lifecycle:
    --   pending   — row created, dispatch not yet started
    --   sending   — at least one per-lender send in flight
    --   sent      — every lender reached 'sent' or 'error'
    --   error     — every lender failed to send (no recoveries)
    status            text NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'sending', 'sent', 'error')),
    subject           text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, lead_id, round_number)
);

CREATE INDEX IF NOT EXISTS idx_shopping_threads_lead
    ON public.shopping_threads (tenant_id, lead_id, round_number DESC);
CREATE INDEX IF NOT EXISTS idx_shopping_threads_agent
    ON public.shopping_threads (tenant_id, agent_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shopping_threads_status
    ON public.shopping_threads (tenant_id, status, created_at DESC);

CREATE TRIGGER trg_shopping_threads_updated_at
    BEFORE UPDATE ON public.shopping_threads
    FOR EACH ROW EXECUTE FUNCTION public.touch_user_profiles_updated_at();

ALTER TABLE public.shopping_threads ENABLE ROW LEVEL SECURITY;

CREATE POLICY shopping_threads_tenant_all ON public.shopping_threads
    FOR ALL USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

COMMENT ON TABLE public.shopping_threads IS
  'Round-level shop-out tracking. One row per fan-out of a loan file to '
  'N lenders. The root_message_id anchors the email thread for the '
  'initiating agent CC. Re-shop creates a new row with a new anchor.';
