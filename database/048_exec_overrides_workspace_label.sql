-- ============================================================================
-- Migration 048 — Workspace labelling on exec_overrides.
--
-- Problem (2026-05-16): the /overrides page is global. When a Bravo session
-- working on SunBiz client code (cwd ~ Marketing-Agent or touching
-- text_torrent/kixie) blocks on exec_guard, the resulting override request
-- lands in the same row pool that CC's OASIS HQ dashboard reads — so a
-- "[SunBiz] commit TextTorrent + Kixie integration" approval prompt was
-- surfacing on the empire-tenant view as if CC needed to approve his own
-- client-side work in a context that didn't make sense.
--
-- Fix: every exec_overrides row carries a workspace_label tag derived from
-- the cwd the agent was running in when the block fired. The dashboard
-- filters by workspace_label so each tenant view only shows its own slice.
--
-- workspace_label values:
--   'empire'          — Business-Empire-Agent (OASIS HQ code)
--   'sunbiz_client'   — Marketing-Agent or any path that names SunBiz
--                       integrations (text_torrent, kixie, /t/sun/, etc.)
--   'suga_client'     — CMO-Agent (Suga Sean brand)
--   'propflow_client' — APPS/propflow (future tenant fork)
--   'unknown'         — couldn't classify; surface on the empire view by
--                       default since it's most likely empire code in a
--                       weird cwd
--
-- Backfill rule: for rows already in the table, classify by regex against
-- the `command` field (the cwd field doesn't exist yet, so we have to infer).
-- Forward-going rows get the explicit cwd_path written by exec_guard.
-- ============================================================================

ALTER TABLE public.exec_overrides
    ADD COLUMN IF NOT EXISTS cwd_path        text,
    ADD COLUMN IF NOT EXISTS workspace_label text NOT NULL DEFAULT 'unknown';

-- Backfill for existing rows ships as a separate one-off script
-- (scripts/backfill_exec_overrides_workspace.py) because apply_migration.py's
-- safety guardrail blocks UPDATE inside migrations. New rows get
-- workspace_label written at insert time by exec_override_mirror.py.

-- Allow the partial index to keep working — workspace_label has a default,
-- so all existing rows have a value and the predicate is satisfied.
CREATE INDEX IF NOT EXISTS idx_exec_overrides_workspace
    ON public.exec_overrides (workspace_label, ts DESC);

COMMENT ON COLUMN public.exec_overrides.workspace_label IS
    'Classification of which workspace the override request came from: empire | sunbiz_client | suga_client | propflow_client | unknown. Derived from cwd_path at write time; backfilled by regex from command for rows older than migration 048.';
COMMENT ON COLUMN public.exec_overrides.cwd_path IS
    'Raw cwd of the agent process when exec_guard fired. Used as the source-of-truth for workspace_label; preserved so the operator can audit the inference.';
