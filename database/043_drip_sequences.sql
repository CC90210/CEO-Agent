-- Migration 043 — Drip campaign sequence engine
--
-- Phase 4 of the SunBiz CRM build (2026-05-15). Closes the loop on the
-- pipeline-status work shipped in Phase 2: when lead.stage or
-- offer.stage transitions, the bridge-side sequence_runner.py daemon
-- looks for a drip_sequence whose trigger matches, enqueues the first
-- step into sequence_state, and fires it on schedule via send_gateway.
--
-- Architecture:
--
--   tenant_records UPDATE -> Phase 2 publisher -> agent_events row
--       (BRAVO_RECORD_STATUS_CHANGED, payload includes entity + to-stage)
--                                  |
--                                  v
--                       sequence_runner.py daemon
--                       (subscribes to agent_events,
--                        matches against drip_sequences,
--                        inserts sequence_state rows)
--                                  |
--                                  v
--                       Same daemon polls sequence_state
--                       for due rows, fires via send_gateway,
--                       schedules next step
--
-- Why two tables (sequences = definitions, state = in-flight rows):
--   - Definitions live in drip_sequences. Editable by the operator
--     from /sequences. Toggling enabled stops new lead enrollments
--     but doesn't cancel in-flight rows already in sequence_state.
--   - Each lead's progress through a sequence is a sequence_state row
--     (or chain of rows — one per step). Lets us cancel a single lead
--     out of a drip without touching the definition.
--
-- Apply via: python scripts/apply_migration.py database/043_drip_sequences.sql

BEGIN;

-- ============================================================================
-- drip_sequences — operator-designed drip definitions per tenant
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.drip_sequences (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    -- Operator-given name. Free text; shown in /sequences list.
    name            text NOT NULL,
    description     text,
    -- Event-bus event type that triggers enrollment. Today's only
    -- supported value is BRAVO_RECORD_STATUS_CHANGED (Phase 2 publisher).
    -- Future events (BRAVO_INBOUND_CLASSIFIED, BRAVO_OFFER_CREATED, etc.)
    -- can be added here without a schema change — the runner only needs
    -- to match string equality.
    trigger_event   text NOT NULL DEFAULT 'BRAVO_RECORD_STATUS_CHANGED',
    -- Additional filter on the event payload — all keys must match.
    -- Common shapes:
    --   { "entity": "lead", "field": "stage", "to": "viewed_application" }
    --   { "entity": "offer", "field": "stage", "to": "no_offer" }
    -- The runner does shallow equality on top-level keys against
    -- agent_events.payload. Deep matching is intentionally not
    -- supported in v1 — keep filters cheap and predictable.
    trigger_filter  jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- Ordered steps. Each step:
    --   {
    --     "channel": "sms" | "email",
    --     "delay_minutes": <int>,       // wait this long before sending
    --     "subject": "...",              // email only
    --     "body": "Hi {{lead.first_name}}, ...",
    --     "from_label"?: "Solara"        // optional sender label
    --   }
    -- Variable substitution: lib/drips/templates.ts. Lookups are
    -- dot-pathed against the lead row + the triggering event payload.
    steps           jsonb NOT NULL DEFAULT '[]'::jsonb,
    -- Toggle without delete. Disabled sequences don't enroll new leads
    -- but in-flight sequence_state rows continue to fire on schedule
    -- unless explicitly cancelled.
    enabled         boolean NOT NULL DEFAULT true,
    -- One lead can be enrolled in a sequence once. Re-trigger requires
    -- the operator to cancel the existing sequence_state row (or wait
    -- for it to complete). Prevents double-firing if the same status
    -- change fires twice (idempotency).
    one_per_lead    boolean NOT NULL DEFAULT true,
    created_by      uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_drip_sequences_tenant_enabled
    ON public.drip_sequences (tenant_id, enabled)
    WHERE enabled = true;
CREATE INDEX IF NOT EXISTS idx_drip_sequences_tenant_event
    ON public.drip_sequences (tenant_id, trigger_event)
    WHERE enabled = true;

CREATE TRIGGER trg_drip_sequences_updated_at
    BEFORE UPDATE ON public.drip_sequences
    FOR EACH ROW EXECUTE FUNCTION public.touch_user_profiles_updated_at();

-- ============================================================================
-- sequence_state — one row per (lead, sequence, step) in-flight
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.sequence_state (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sequence_id     uuid NOT NULL REFERENCES public.drip_sequences(id) ON DELETE CASCADE,
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    -- The lead this row targets. Stored as text to match tenant_records'
    -- schemaless model (no FK; the lead_id is the JSONB row's PK).
    lead_id         text NOT NULL,
    -- Zero-indexed step in the sequence.steps array.
    step_index      integer NOT NULL,
    -- When this step should fire. NULL means "due now" (used during
    -- enrollment for step 0 when delay_minutes is 0).
    scheduled_for   timestamptz NOT NULL,
    -- Lifecycle:
    --   scheduled  — waiting for scheduled_for to arrive
    --   sent       — fired successfully via send_gateway
    --   failed     — last attempt errored; daemon retries with backoff
    --   cancelled  — operator cancelled (or lead opted out)
    --   skipped    — operator skipped this step (advance without sending)
    status          text NOT NULL DEFAULT 'scheduled'
                    CHECK (status IN ('scheduled', 'sent', 'failed', 'cancelled', 'skipped')),
    -- Last fire attempt + error/output for debugging. Operators see
    -- these on /sequences/[id] detail page.
    attempt_count   integer NOT NULL DEFAULT 0,
    last_attempt_at timestamptz,
    last_error      text,
    -- Snapshot of the variable context the daemon used. Stored so the
    -- operator can audit exactly what {{lead.first_name}} resolved to
    -- without re-querying.
    context_snapshot jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- The hot path: daemon polls every N seconds for "scheduled rows where
-- scheduled_for <= now()". Partial index keeps the query against the
-- typically-small set of scheduled rows, not the cumulative history.
CREATE INDEX IF NOT EXISTS idx_sequence_state_due
    ON public.sequence_state (scheduled_for)
    WHERE status = 'scheduled';
-- Operator-facing lookup: "show me everything in flight for lead X".
CREATE INDEX IF NOT EXISTS idx_sequence_state_tenant_lead
    ON public.sequence_state (tenant_id, lead_id, created_at DESC);
-- one_per_lead enforcement (sequence_runner.py checks before enrolling).
CREATE INDEX IF NOT EXISTS idx_sequence_state_lead_seq_active
    ON public.sequence_state (sequence_id, lead_id)
    WHERE status IN ('scheduled', 'failed');

CREATE TRIGGER trg_sequence_state_updated_at
    BEFORE UPDATE ON public.sequence_state
    FOR EACH ROW EXECUTE FUNCTION public.touch_user_profiles_updated_at();

-- ============================================================================
-- RLS — operators see/edit only their tenant's sequences + state
-- ============================================================================
ALTER TABLE public.drip_sequences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sequence_state ENABLE ROW LEVEL SECURITY;

CREATE POLICY drip_sequences_tenant_all ON public.drip_sequences
    FOR ALL USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

CREATE POLICY sequence_state_tenant_all ON public.sequence_state
    FOR ALL USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- The daemon (sequence_runner.py) connects with the service-role key so
-- RLS doesn't restrict its reads/writes. Bearer-token-auth model isn't
-- needed here because the daemon runs on the operator's machine with
-- the tenant token from bridge_pairings; we already trust that path.

COMMENT ON TABLE public.drip_sequences IS
  'Operator-designed automated drips. trigger_event + trigger_filter '
  'match against agent_events rows (typically BRAVO_RECORD_STATUS_CHANGED); '
  'matching enrollment inserts a sequence_state row at step 0.';

COMMENT ON TABLE public.sequence_state IS
  'One row per (lead, sequence, step) in flight. sequence_runner.py '
  'daemon polls for scheduled rows where scheduled_for <= now(), fires '
  'via send_gateway, updates status, and enqueues the next step.';

COMMIT;
