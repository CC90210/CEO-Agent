/**
 * Manifest loader — single async entry point the layout and routes call to
 * resolve "what's this tenant's Command Center supposed to look like."
 *
 * Lookup order:
 *   1. Supabase `tenant_manifests` row keyed by slug (Phase 1b on once
 *      migration 038 is applied; until then this call returns null fast).
 *   2. In-code seed manifests in ./seeds.ts (OASIS, SUN, SUGA + default).
 *
 * The loader NEVER throws. Invalid stored manifests (malformed JSON, schema
 * drift) log via safe() and fall back to seeds, so a bad row in DB can't
 * 500 the whole shell. The audit log captures the failure for follow-up.
 *
 * Caching: Next.js Server Components already de-dupe identical fetches within
 * a single render. We additionally memoize per-request via a Map so multiple
 * server components in the same request share one parse + DB hit.
 */

import { cache } from "react";
import { safe } from "@/lib/api-helpers";
import { getServiceSupabase } from "@/lib/supabase-server";
import type { NavItem } from "@/lib/nav-config";
import { safeParseManifest, type ManifestNavItem, type TenantManifest, primaryAgent } from "./schema";
import { getSeedManifest, SEED_MANIFESTS } from "./seeds";

type ManifestRow = {
  slug: string;
  manifest: unknown;
  version: number;
  updated_at: string;
};

async function fetchManifestFromSupabase(slug: string): Promise<TenantManifest | null> {
  return safe(
    "manifest.loader.supabase",
    (async () => {
      const db = getServiceSupabase();
      const result = await db
        .from("tenant_manifests")
        .select("slug, manifest, version, updated_at")
        .eq("slug", slug)
        .maybeSingle();
      const row = (result.data || null) as ManifestRow | null;
      if (!row?.manifest) return null;
      const parsed = safeParseManifest(row.manifest);
      if (!parsed.ok) {
        // Don't throw — log via the wrapper, fall back to seed. Surface the
        // parse error path so the audit log makes the failure searchable.
        console.warn(
          `[manifest.loader] stored manifest for slug="${slug}" failed validation: ${parsed.error.message}`
        );
        return null;
      }
      return parsed.manifest;
    })(),
    null as TenantManifest | null
  );
}

export const getManifest = cache(async (slug: string | null | undefined): Promise<TenantManifest> => {
  const key = (slug || "").trim().toLowerCase() || "default";
  const fromDb = await fetchManifestFromSupabase(key);
  if (fromDb) return fromDb;
  return getSeedManifest(key);
});

/**
 * Adapter — convert a manifest nav array (snake_case, source-of-truth) into
 * the existing Sidebar's NavItem shape (lowerCamelCase). Phase 2 will replace
 * the Sidebar with a manifest-native component and retire this.
 */
export function manifestNavToNavItems(items: ManifestNavItem[]): NavItem[] {
  return items.map((item) => ({
    href: item.href,
    label: item.label,
    icon: item.icon,
    group: item.group,
    badgeKey: item.badge_key,
    expandable: item.expandable,
  }));
}

/**
 * True when a slug exists in either the in-code seeds or the
 * tenant_manifests table. Used by routes that need to 404 for genuinely
 * unknown tenants (vs. transparently falling back to the default seed).
 */
export async function manifestExists(slug: string | null | undefined): Promise<boolean> {
  const key = (slug || "").trim().toLowerCase();
  if (!key) return false;
  if (SEED_MANIFESTS[key]) return true;
  const row = await safe(
    "manifest.loader.exists",
    (async () => {
      const db = getServiceSupabase();
      const result = await db
        .from("tenant_manifests")
        .select("slug")
        .eq("slug", key)
        .maybeSingle();
      return !!result.data;
    })(),
    false
  );
  return row;
}

/** Sidebar logo prop is a closed enum. "custom" manifests fall back to "oasis". */
export function manifestLogoToSidebarLogo(
  logo: TenantManifest["brand"]["logo"]
): "oasis" | "sunbiz" | "suga" {
  if (logo === "sunbiz" || logo === "suga" || logo === "oasis") return logo;
  return "oasis";
}

/**
 * Pull the slug that drives a tenant's manifest — same precedence the old
 * layout used (demo cookie/path > tenant custom field > tenant slug > default).
 */
export function manifestPrimaryAgentSlug(m: TenantManifest): string {
  return primaryAgent(m)?.slug || "bravo";
}

