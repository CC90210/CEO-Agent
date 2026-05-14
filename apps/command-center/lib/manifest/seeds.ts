/**
 * Seed manifests — in-code source of truth that mirrors the legacy
 * lib/client-profiles.ts registry. These are the manifests we serve when:
 *
 *   1. the `tenant_manifests` Supabase table is empty (fresh install), OR
 *   2. the DB is unreachable from a Vercel function for this request, OR
 *   3. the requested slug isn't in the DB but we want a sensible default.
 *
 * Once Phase 2's AI editor lands and writes to Supabase, seeds become the
 * "shipped defaults" — the DB row overrides per tenant. Until then, the seeds
 * ARE the manifests, just loaded through the same pipeline a DB-backed
 * manifest would use, so the cutover in 1b is a no-op for the renderer.
 */

import { CC_NAV, SUGA_NAV, SUN_NAV, type NavItem } from "../nav-config";
import {
  MANIFEST_SCHEMA_VERSION,
  type ManifestNavItem,
  type TenantManifest,
} from "./schema";

function navToManifest(items: NavItem[]): ManifestNavItem[] {
  return items.map((item) => ({
    href: item.href,
    label: item.label,
    icon: item.icon,
    group: item.group,
    badge_key: item.badgeKey,
    expandable: item.expandable,
  }));
}

const FROZEN_AT = "2026-05-13T00:00:00.000Z";

export const OASIS_SEED: TenantManifest = {
  version: 1,
  tenant_slug: "oasis",
  brand: {
    name: "OASIS AI",
    logo: "oasis",
    subtitle: "Agent Command Center",
    footer_label: "OASIS AI · Agent Command Center · v1.0",
    footer_tagline: '"Only good things from now on."',
  },
  agents: [
    { slug: "bravo", display_name: "Bravo", enabled: true, primary: true },
    { slug: "atlas", display_name: "Atlas", enabled: true },
    { slug: "maven", display_name: "Maven", enabled: true },
    { slug: "aura", display_name: "Aura", enabled: false },
  ],
  nav: navToManifest(CC_NAV),
  data_backend: "supabase",
  deployment_mode: "shared",
  permissions: { local_files: true, computer_control: true, web_access: true },
  onboarding_industry: "custom",
  meta: {
    created_at: FROZEN_AT,
    updated_at: FROZEN_AT,
    schema_version: MANIFEST_SCHEMA_VERSION,
  },
};

export const SUN_SEED: TenantManifest = {
  version: 1,
  tenant_slug: "sun",
  brand: {
    name: "Sun Biz Funding",
    logo: "sunbiz",
    subtitle: "Command Center",
    footer_label: "Sun Biz Funding · Command Center · v1.0",
    footer_tagline: "Funded deals over noise.",
  },
  agents: [
    { slug: "solara", display_name: "Solara", enabled: true, primary: true },
  ],
  nav: navToManifest(SUN_NAV),
  data_backend: "turso",
  deployment_mode: "dedicated",
  permissions: { local_files: true, computer_control: false, web_access: true },
  onboarding_industry: "business_funding",
  integrations: [
    { kind: "jotform", enabled: true, credential_env_key: "SUNBIZ_AGENT_API_URL" },
    { kind: "twilio", enabled: true, credential_env_key: "SUNBIZ_AGENT_HMAC_SECRET" },
    { kind: "turso", enabled: true },
  ],
  meta: {
    created_at: FROZEN_AT,
    updated_at: FROZEN_AT,
    schema_version: MANIFEST_SCHEMA_VERSION,
  },
};

export const SUGA_SEED: TenantManifest = {
  version: 1,
  tenant_slug: "suga",
  brand: {
    name: "Suga Sean O'Malley",
    logo: "suga",
    subtitle: "Brand Command",
    footer_label: "Suga · Brand Command · v0.1",
    footer_tagline: "Fans first. Always.",
  },
  agents: [
    { slug: "suga_sean", display_name: "Suga", enabled: true, primary: true },
  ],
  nav: navToManifest(SUGA_NAV),
  data_backend: "turso",
  deployment_mode: "dedicated",
  permissions: { local_files: false, computer_control: false, web_access: true },
  onboarding_industry: "agency",
  meta: {
    created_at: FROZEN_AT,
    updated_at: FROZEN_AT,
    schema_version: MANIFEST_SCHEMA_VERSION,
  },
};

/**
 * Slug map for synchronous lookups. The loader uses this as the fallback when
 * Supabase has no row for a slug; the AI editor writes new manifests to DB,
 * never to this map.
 */
export const SEED_MANIFESTS: Record<string, TenantManifest> = {
  default: OASIS_SEED,
  oasis: OASIS_SEED,
  sun: SUN_SEED,
  suga: SUGA_SEED,
};

export function getSeedManifest(slug: string | null | undefined): TenantManifest {
  const key = (slug || "").trim().toLowerCase();
  return SEED_MANIFESTS[key] || OASIS_SEED;
}
