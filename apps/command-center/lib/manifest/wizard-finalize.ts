/**
 * Wizard finaliser — fold collected onboarding answers into a starter
 * template, producing a complete TenantManifest ready for persistence.
 *
 * Pure logic. The HTTP route handler calls this, validates the result via
 * parseManifest, then writes through saveManifest. Keeping the answer-→-
 * mutation mapping in one file makes it easy to add new wizard questions
 * (just extend WIZARD_QUESTIONS in templates.ts and add a case here).
 */

import type { ManifestAgentBinding, TenantManifest } from "./schema";
import {
  TEMPLATES,
  type TemplateKey,
} from "./templates";
import {
  addFieldToEntity,
  updateAgent,
  updateBrand,
} from "./mutators";
import { AGENT_REGISTRY } from "../agents";

export type WizardAnswers = Record<string, string | string[] | number | undefined>;

export type FinalizeInput = {
  template: TemplateKey;
  slug: string;
  answers: WizardAnswers;
};

const SLUG_RE = /^[a-z0-9][a-z0-9_-]{1,62}$/;

/** Slugify a brand name into a URL-safe tenant slug. */
export function slugifyBrand(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 62) || "tenant";
}

export function isValidSlug(slug: string): boolean {
  return SLUG_RE.test(slug);
}

function parseExtraFields(raw: string | string[] | undefined): string[] {
  if (!raw) return [];
  const text = Array.isArray(raw) ? raw.join(",") : raw;
  return text
    .split(/[\n,]+/)
    .map((s) => s.trim().toLowerCase().replace(/\s+/g, "_"))
    .filter((s) => /^[a-z][a-z0-9_]{0,62}$/.test(s));
}

/**
 * Apply answers to a template. The mapping is small and intentionally
 * declarative — each template owns which answer keys it consumes.
 */
export function finalizeManifestFromWizard(input: FinalizeInput): TenantManifest {
  const slug = input.slug.trim().toLowerCase();
  if (!isValidSlug(slug)) {
    throw new Error(`invalid_slug:${slug}`);
  }
  const base: TenantManifest = JSON.parse(JSON.stringify(TEMPLATES[input.template]));
  // Re-anchor the slug to the operator's chosen one.
  base.tenant_slug = slug;

  // Rewrite nav hrefs to point at /t/<slug>/<path>. Templates ship bare
  // paths ("/", "/leads", "/reasoning") which would otherwise route to
  // the OASIS legacy bare-path pages when a new tenant clicks around.
  // Maps:
  //   "/"                  → "/t/<slug>"
  //   "/leads"             → "/t/<slug>/leads"
  //   "/t/whatever/leads"  → "/t/<slug>/leads"  (re-prefixed)
  //   "https://..."        → left untouched (external link)
  base.nav = base.nav.map((n) => {
    if (/^[a-z]+:\/\//i.test(n.href)) return n;
    if (n.href === "/" || n.href === "") return { ...n, href: `/t/${slug}` };
    const tenantPrefixed = n.href.match(/^\/t\/[a-z0-9_-]+\/(.*)$/i);
    if (tenantPrefixed) return { ...n, href: `/t/${slug}/${tenantPrefixed[1]}` };
    if (n.href.startsWith("/")) return { ...n, href: `/t/${slug}${n.href}` };
    return { ...n, href: `/t/${slug}/${n.href}` };
  });

  const answers = input.answers;
  const brandName = typeof answers.brand_name === "string" ? answers.brand_name.trim() : "";
  const tagline = typeof answers.tagline === "string" ? answers.tagline.trim() : "";

  let manifest: TenantManifest = base;
  if (brandName) {
    manifest = updateBrand(manifest, {
      name: brandName,
      footer_label: `${brandName} · powered by OASIS AI`,
    });
  }
  if (tagline) {
    manifest = updateBrand(manifest, { footer_tagline: tagline });
  }

  // Honor the user's agent multi-select from the wizard agents step.
  // The template ships a sensible default agents[] but the user may have
  // added or removed entries. Rebuild agents[] from the selection so the
  // resulting manifest reflects what the user actually chose.
  //
  // Primary preservation: if the template's primary agent is still selected,
  // keep it primary. Otherwise the first selected agent becomes primary.
  if (Array.isArray(answers.selected_agents) && answers.selected_agents.length > 0) {
    const picks = answers.selected_agents.filter((s): s is string => typeof s === "string");
    const templatePrimary = base.agents.find((a) => a.primary)?.slug;
    const primarySlug = picks.includes(templatePrimary || "") ? templatePrimary! : picks[0];
    const nextAgents: ManifestAgentBinding[] = picks.map((slug) => {
      const existing = base.agents.find((a) => a.slug === slug);
      const registryInfo = AGENT_REGISTRY[slug];
      return {
        slug,
        display_name: existing?.display_name || registryInfo?.label || slug,
        enabled: true,
        primary: slug === primarySlug,
      };
    });
    manifest = { ...manifest, agents: nextAgents };
  } else if (Array.isArray(answers.selected_agents) && answers.selected_agents.length === 0) {
    // User explicitly cleared all agents — respect that. The shell renders
    // with no agents until they add some in Settings.
    manifest = { ...manifest, agents: [] };
  }

  switch (input.template) {
    case "real_estate": {
      const extras = parseExtraFields(answers.extra_fields as string | undefined);
      for (const fieldName of extras) {
        // Skip names that already exist on the lead entity (mutator would throw).
        const lead = manifest.data_model?.find((e) => e.name === "lead");
        if (!lead || lead.fields.some((f) => f.name === fieldName)) continue;
        manifest = addFieldToEntity(manifest, {
          entity: "lead",
          field: { name: fieldName, type: "string" },
        });
      }
      break;
    }
    case "business_funding": {
      // Primary (operational) — renames Solara
      const primaryName = typeof answers.primary_agent_name === "string"
        ? answers.primary_agent_name.trim()
        : typeof answers.agent_name === "string" // legacy fallback for in-flight wizards
          ? answers.agent_name.trim()
          : "";
      if (primaryName) {
        manifest = updateAgent(manifest, {
          slug: "solara",
          changes: { display_name: primaryName },
        });
      }
      // Sales-facing — renames Helios
      const salesName = typeof answers.sales_agent_name === "string"
        ? answers.sales_agent_name.trim()
        : "";
      if (salesName) {
        manifest = updateAgent(manifest, {
          slug: "helios",
          changes: { display_name: salesName },
        });
      }
      break;
    }
    case "ecommerce":
    case "agency":
    case "custom":
      // Defaults are already strong; no template-specific answer folding yet.
      // Phase 2.1 can add e.g. platform-specific integrations for ecommerce.
      break;
  }

  return manifest;
}
