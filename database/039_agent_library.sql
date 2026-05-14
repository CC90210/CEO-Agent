-- ============================================================================
-- Migration 039 — Agent Library (Phase 3 marketplace foundation)
--
-- One global table of agent templates that any tenant can browse, subscribe
-- to, and personalize through their manifest. The manifest.agents[] array
-- (already in lib/manifest/schema.ts) remains the source of truth for which
-- agents are enabled per tenant + how they're customised; this table is the
-- LIBRARY of agent definitions every tenant draws from.
--
-- Design choices:
--   - Single agents table — not "agent_templates" + "agent_subscriptions"
--     split — because the manifest already tracks subscriptions. Avoids
--     redundant state and the sync bugs that come with it.
--   - is_oasis_managed flag separates platform-built agents (bravo, atlas,
--     maven, aura, solara, the generic SDR/QA/Research templates) from
--     user-built customs. Platform agents survive even if the creator
--     leaves; user customs cascade-delete on creator removal.
--   - is_public + RLS = anyone authenticated can read public agents;
--     creators read+write their own; service-role bypasses for the
--     marketplace API which validates auth upstream.
--
-- Seeds: NONE in this migration. Same posture as 038 — code seeds in
-- lib/agents/library.ts are the source of truth until a Phase 3.1
-- promotion step writes them into the DB on demand. Keeps the agent
-- catalogue under tsc supervision instead of awkward escaped-JSON SQL.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.agents (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                text NOT NULL UNIQUE,
    name                text NOT NULL,
    category            text NOT NULL CHECK (category IN (
                            'ceo','cfo','cmo','coo','operations',
                            'sales','support','research','content',
                            'engineering','finance','legal',
                            'industry_real_estate','industry_funding',
                            'industry_ecommerce','industry_agency',
                            'custom'
                        )),
    short_description   text NOT NULL,
    description         text,
    base_prompt         text NOT NULL,
    required_tools      text[] NOT NULL DEFAULT '{}',
    suggested_model     text,
    pricing             jsonb NOT NULL DEFAULT '{"tier":"free"}'::jsonb,
    is_public           boolean NOT NULL DEFAULT true,
    is_oasis_managed    boolean NOT NULL DEFAULT false,
    created_by          uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    tenant_id           uuid REFERENCES public.tenants(id) ON DELETE CASCADE,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agents_category ON public.agents (category);
CREATE INDEX IF NOT EXISTS idx_agents_public ON public.agents (is_public) WHERE is_public = true;
CREATE INDEX IF NOT EXISTS idx_agents_tenant ON public.agents (tenant_id) WHERE tenant_id IS NOT NULL;

ALTER TABLE public.agents ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- RLS — public agents readable by every authed user; private agents readable
-- only by their creator's tenant. Writes are creator-only OR service-role
-- (marketplace API enforces auth upstream).
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='agents'
          AND policyname='agents_public_select'
    ) THEN
        CREATE POLICY agents_public_select ON public.agents
            FOR SELECT TO authenticated
            USING (is_public = true OR tenant_id = public.current_tenant_id());
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='agents'
          AND policyname='agents_creator_write'
    ) THEN
        CREATE POLICY agents_creator_write ON public.agents
            FOR ALL TO authenticated
            USING (tenant_id = public.current_tenant_id() AND is_oasis_managed = false)
            WITH CHECK (tenant_id = public.current_tenant_id() AND is_oasis_managed = false);
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- updated_at trigger
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.agents_touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS agents_set_updated_at ON public.agents;
CREATE TRIGGER agents_set_updated_at
    BEFORE UPDATE ON public.agents
    FOR EACH ROW EXECUTE FUNCTION public.agents_touch_updated_at();
