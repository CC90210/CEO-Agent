-- ============================================================================
-- Migration 075 — per-user agent display_name override
--
-- Phase 2 of the multi-employee personalization plan (2026-05-29).
--
-- Background: migration 052 added user_id to agent_model_config so each
-- employee on a tenant can override their own provider key, model, and
-- system_prompt without disturbing tenant defaults. This extends the
-- same row with a display_name_override so each employee can also
-- RENAME their agent on their personal dashboard — Alex might call his
-- Solara "Ada", Jordan might keep "Solara" — without affecting the
-- agent's reasoning, workflows, or backend daemon logs.
--
-- Per the planning decision, the rename is strictly a UI personalisation:
--   - Surfaces: chat header, persona self-introduction, sidebar nav label
--   - Out of scope: backend daemons (sequence_runner, etc.) keep
--     logging canonical agent names (Solara/Helios) for cross-employee
--     debugging consistency
--
-- RLS already enforces user-owned writes per migration 052; no policy
-- change needed. Re-runnable.
-- ============================================================================

BEGIN;

ALTER TABLE public.agent_model_config
    ADD COLUMN IF NOT EXISTS display_name_override TEXT;

COMMENT ON COLUMN public.agent_model_config.display_name_override IS
    'Per-user display name override for an agent. NULL = use the manifest / '
    'seed display_name. Only takes effect on user-facing UI surfaces (chat '
    'header, persona self-introduction, sidebar nav). Backend daemon logs '
    'always use the canonical agent_key for cross-employee debugging. '
    'Set via Settings → My Agents.';

COMMIT;
