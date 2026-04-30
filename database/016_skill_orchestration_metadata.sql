-- 016_skill_orchestration_metadata.sql
-- Add routable metadata to the runtime skill registry.
--
-- Existing skills_registry rows keep their usage_count/success_count history.
-- This migration only adds columns and indexes so agents can select the right
-- skill by trigger, tier, owner, risk, and source hash.

ALTER TABLE skills_registry
  ADD COLUMN IF NOT EXISTS triggers TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS tier TEXT DEFAULT 'standard',
  ADD COLUMN IF NOT EXISTS owner_agent TEXT DEFAULT 'bravo',
  ADD COLUMN IF NOT EXISTS when_to_use TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS inputs JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS outputs JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS preconditions TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS side_effects TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS cli_entry TEXT,
  ADD COLUMN IF NOT EXISTS risk_level TEXT DEFAULT 'normal',
  ADD COLUMN IF NOT EXISTS requires_approval BOOLEAN DEFAULT false,
  ADD COLUMN IF NOT EXISTS source_hash TEXT,
  ADD COLUMN IF NOT EXISTS frontmatter JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS spec JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS orchestration_notes TEXT;

CREATE INDEX IF NOT EXISTS idx_skills_registry_category
  ON skills_registry (category);

CREATE INDEX IF NOT EXISTS idx_skills_registry_tier
  ON skills_registry (tier);

CREATE INDEX IF NOT EXISTS idx_skills_registry_owner_agent
  ON skills_registry (owner_agent);

CREATE INDEX IF NOT EXISTS idx_skills_registry_risk_level
  ON skills_registry (risk_level);

CREATE INDEX IF NOT EXISTS idx_skills_registry_triggers_gin
  ON skills_registry USING GIN (triggers);

CREATE INDEX IF NOT EXISTS idx_skills_registry_tags_gin
  ON skills_registry USING GIN (tags);

COMMENT ON COLUMN skills_registry.triggers IS
  'Plain-English phrases and keywords used by agents to activate this skill.';

COMMENT ON COLUMN skills_registry.tier IS
  'Skill loading tier: core, standard, specialized, or dormant.';

COMMENT ON COLUMN skills_registry.owner_agent IS
  'Best owner for this skill: bravo, codex, atlas, maven, or aura.';

COMMENT ON COLUMN skills_registry.risk_level IS
  'normal, approval, sensitive, or destructive. Agents must fail closed on sensitive/destructive skills.';

COMMENT ON COLUMN skills_registry.source_hash IS
  'SHA-256 hash of SKILL.md + optional spec.yaml so registry drift is detectable.';
