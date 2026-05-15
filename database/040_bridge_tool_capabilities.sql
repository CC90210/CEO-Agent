-- Migration 040 — Bridge tool capabilities advertisement
--
-- Adds tool_capabilities jsonb to bridge_pairings so the local bridge
-- daemon can report which tools its installation supports (Phase F of
-- giggly-reef). The dashboard reads this column when assembling the
-- TOOL_DEFINITIONS palette for /api/chat — bridge tools not in the
-- advertised list get filtered out of what's sent to Anthropic.
--
-- Why a column on bridge_pairings (not a new table): tool capabilities
-- are 1:1 with a paired bridge (one bridge per machine, one tool
-- registry per bridge install). When the bridge revokes, the
-- capabilities go with it. JSONB so the shape can evolve (currently
-- string[], future could be objects with version + metadata).
--
-- Default empty array (`[]`) means "bridge hasn't reported yet" —
-- dashboard treats as a no-op (all bridge tools allowed) so existing
-- pairings don't lose capability until they ping next.
--
-- Apply via: python scripts/apply_migration.py database/040_bridge_tool_capabilities.sql

BEGIN;

ALTER TABLE public.bridge_pairings
  ADD COLUMN IF NOT EXISTS tool_capabilities jsonb NOT NULL DEFAULT '[]'::jsonb;

-- Index for quick lookups (filtering bridge tools by what the live
-- pairing actually supports). GIN index because the JSONB shape is
-- "array of strings" and we may want containment queries later.
CREATE INDEX IF NOT EXISTS bridge_pairings_tool_capabilities_idx
  ON public.bridge_pairings USING gin (tool_capabilities);

COMMENT ON COLUMN public.bridge_pairings.tool_capabilities IS
  'Array of tool-name strings the operator''s local bridge advertises. '
  'Reported by the bridge daemon on each /api/bridge/ping heartbeat. '
  'Empty array = not yet reported; dashboard treats as no filter. '
  'See bravo_cli/bridge_tools.py:TOOL_REGISTRY for the producer side, '
  'and apps/command-center/lib/cloud-tool-runner.ts TOOL_DEFINITIONS '
  'for the dashboard-side palette.';

COMMIT;
