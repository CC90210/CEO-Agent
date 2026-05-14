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

// OASIS AI — CC's own home tenant. Nav still uses bare-path legacy routes
// (which work because the rest of the dashboard has legacy pages at those
// paths) but the manifest now declares pages + entities so /t/oasis renders
// real manifest-driven content for cross-tenant consistency. When the
// legacy bare-path pages get migrated to manifest-driven, we flip the nav
// hrefs to /t/oasis/<path> too.
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
  data_model: [
    {
      name: "lead",
      label: "Lead",
      fields: [
        { name: "name", type: "string", required: true },
        { name: "company", type: "string" },
        { name: "source", type: "enum", enum_values: ["referral", "inbound", "outbound", "event", "other"] },
        { name: "stage", type: "enum", enum_values: ["new", "qualified", "proposal", "won", "lost"], required: true },
        { name: "value_estimate", type: "number" },
      ],
    },
    {
      name: "task",
      label: "Task",
      fields: [
        { name: "title", type: "string", required: true },
        { name: "agent_slug", type: "string" },
        { name: "status", type: "enum", enum_values: ["pending", "in_progress", "blocked", "done"], required: true },
        { name: "due_date", type: "date" },
      ],
    },
  ],
  pages: [
    { path: "", label: "Today", kind: "dashboard" },
    { path: "leads", label: "Leads (manifest view)", kind: "kanban", entity: "lead", config: { group_by: "stage" } },
    { path: "tasks", label: "Tasks", kind: "kanban", entity: "task", config: { group_by: "status" } },
  ],
  default_prompts: [
    { agent_slug: "bravo", label: "Daily standup", prompt: "Give me a 5-bullet brief: hot leads, deals closing this week, today's blocks, top priority, anything past-due." },
    { agent_slug: "maven", label: "Draft content drop", prompt: "Pick the highest-leverage move from this week's pipeline and draft a social post in my voice." },
    { agent_slug: "atlas", label: "Cash position", prompt: "Net MRR, current burn, projected runway, anything that looks off in the last 7 days." },
  ],
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

// SunBiz Funding — fully populated tenant. Used at /t/sun/* as the
// authoritative source. The nav hrefs target the /t/sun/<path> namespace
// so every click lands on a manifest-driven page; the catch-all renderer
// dispatches by `pages[].kind`.
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
  nav: [
    { href: "/t/sun", label: "Dashboard", icon: "LayoutDashboard", group: "Operations" },
    { href: "/t/sun/reasoning", label: "Reasoning", icon: "Brain", group: "Operations" },
    { href: "/t/sun/playbook", label: "Playbook", icon: "BookOpen", group: "Operations" },
    { href: "/t/sun/leads", label: "Leads", icon: "Users", group: "Pipeline" },
    { href: "/t/sun/applications", label: "Applications", icon: "FileText", group: "Pipeline" },
    { href: "/t/sun/offers", label: "Offers", icon: "HandCoins", group: "Deals" },
    { href: "/t/sun/funded-deals", label: "Funded Deals", icon: "BadgeDollarSign", group: "Deals" },
    { href: "/t/sun/renewals", label: "Renewals", icon: "RefreshCcw", group: "Deals" },
    { href: "/t/sun/commissions", label: "Commissions", icon: "DollarSign", group: "Deals" },
    { href: "/t/sun/lenders", label: "Lenders", icon: "Landmark", group: "Network" },
    { href: "/t/sun/settings", label: "Settings", icon: "Settings", group: "System" },
  ],
  data_model: [
    {
      name: "lead",
      label: "Lead",
      fields: [
        { name: "business_name", type: "string", required: true },
        { name: "contact_name", type: "string" },
        { name: "phone", type: "string" },
        { name: "email", type: "string" },
        { name: "monthly_revenue", type: "number" },
        { name: "stage", type: "enum", enum_values: ["new", "qualified", "application_sent", "approved", "funded", "lost"], required: true },
      ],
    },
    {
      name: "application",
      label: "Application",
      fields: [
        { name: "lead_id", type: "string", required: true },
        { name: "lender_id", type: "string" },
        { name: "requested_amount", type: "number" },
        { name: "submitted_at", type: "datetime" },
        { name: "status", type: "enum", enum_values: ["draft", "submitted", "in_review", "approved", "declined"] },
      ],
    },
    {
      name: "offer",
      label: "Offer",
      fields: [
        { name: "application_id", type: "string", required: true },
        { name: "lender_id", type: "string" },
        { name: "amount", type: "number" },
        { name: "term_months", type: "number" },
        { name: "factor_rate", type: "number" },
        { name: "accepted", type: "boolean" },
      ],
    },
    {
      name: "funded_deal",
      label: "Funded Deal",
      fields: [
        { name: "lead_id", type: "string", required: true },
        { name: "lender_id", type: "string" },
        { name: "amount_funded", type: "number" },
        { name: "funded_at", type: "date" },
        { name: "term_months", type: "number" },
      ],
    },
    {
      name: "renewal",
      label: "Renewal",
      fields: [
        { name: "funded_deal_id", type: "string", required: true },
        { name: "due_date", type: "date" },
        { name: "status", type: "enum", enum_values: ["upcoming", "due", "overdue", "renewed", "lost"], required: true },
      ],
    },
    {
      name: "commission",
      label: "Commission",
      fields: [
        { name: "funded_deal_id", type: "string", required: true },
        { name: "broker_share_pct", type: "number" },
        { name: "amount", type: "number" },
        { name: "paid", type: "boolean" },
      ],
    },
    {
      name: "lender",
      label: "Lender",
      fields: [
        { name: "name", type: "string", required: true },
        { name: "contact", type: "string" },
        { name: "product_types", type: "string" },
      ],
    },
  ],
  pages: [
    { path: "", label: "Solara — Today", kind: "dashboard" },
    { path: "leads", label: "Leads", kind: "kanban", entity: "lead", config: { group_by: "stage" } },
    { path: "applications", label: "Applications", kind: "table", entity: "application" },
    { path: "offers", label: "Offers", kind: "table", entity: "offer" },
    { path: "funded-deals", label: "Funded Deals", kind: "table", entity: "funded_deal" },
    { path: "renewals", label: "Renewals", kind: "kanban", entity: "renewal", config: { group_by: "status" } },
    { path: "commissions", label: "Commissions", kind: "table", entity: "commission" },
    { path: "lenders", label: "Lenders", kind: "table", entity: "lender" },
    { path: "playbook", label: "Operating Manual", kind: "markdown", config: { body: "Solara is your funding-shop agent. She watches inbound leads from JotForm, drafts follow-ups in your voice via Text Torrent, and surfaces renewal windows before they close.\n\nDay-to-day rhythm:\n\n1. Open Leads. Move the hot ones to qualified. Solara drafts the next outreach.\n2. When a lender returns a term sheet, log it under Offers and mark accepted=true to roll it into Funded Deals.\n3. Renewals tab is the revenue lane. Anything within 60 days of due_date is where Solara puts the day's outreach focus." } },
  ],
  default_prompts: [
    { agent_slug: "solara", label: "Morning briefing", prompt: "Pull leads that haven't been touched in 24h, applications waiting on docs, and offers expiring this week." },
    { agent_slug: "solara", label: "Renewal sweep", prompt: "Which funded deals are within 60 days of renewal? Draft the outreach for the top 3." },
    { agent_slug: "solara", label: "Lender match", prompt: "For the top 3 qualified leads, recommend the best-fit lender based on monthly revenue and product type." },
  ],
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
  nav: [
    { href: "/t/suga", label: "Dashboard", icon: "LayoutDashboard", group: "Operations" },
    { href: "/t/suga/subscribers", label: "Subscribers", icon: "Users", group: "Fans" },
    { href: "/t/suga/posts", label: "Posts", icon: "Megaphone", group: "Brand" },
    { href: "/t/suga/drafts", label: "Drafts", icon: "FileText", group: "Brand" },
    { href: "/t/suga/merch", label: "Merch", icon: "ShoppingBag", group: "Commerce" },
    { href: "/t/suga/sponsorship", label: "Sponsorships", icon: "HandCoins", group: "Sponsorship" },
    { href: "/t/suga/settings", label: "Settings", icon: "Settings", group: "System" },
  ],
  data_model: [
    {
      name: "subscriber",
      label: "Subscriber",
      fields: [
        { name: "email", type: "string", required: true },
        { name: "name", type: "string" },
        { name: "tier", type: "enum", enum_values: ["free", "vip", "patron"] },
      ],
    },
    {
      name: "post",
      label: "Post",
      fields: [
        { name: "title", type: "string", required: true },
        { name: "platform", type: "enum", enum_values: ["instagram", "x", "tiktok", "youtube", "email"] },
        { name: "status", type: "enum", enum_values: ["draft", "scheduled", "published"], required: true },
      ],
    },
    {
      name: "merch_drop",
      label: "Merch Drop",
      fields: [
        { name: "name", type: "string", required: true },
        { name: "stock", type: "number" },
        { name: "status", type: "enum", enum_values: ["upcoming", "live", "sold_out", "archived"] },
      ],
    },
    {
      name: "sponsorship",
      label: "Sponsorship",
      fields: [
        { name: "brand", type: "string", required: true },
        { name: "value", type: "number" },
        { name: "stage", type: "enum", enum_values: ["outreach", "negotiating", "signed", "delivered", "lost"], required: true },
      ],
    },
  ],
  pages: [
    { path: "", label: "Fans · Today", kind: "dashboard" },
    { path: "subscribers", label: "Subscribers", kind: "table", entity: "subscriber" },
    { path: "posts", label: "Posts", kind: "kanban", entity: "post", config: { group_by: "status" } },
    { path: "drafts", label: "Drafts", kind: "table", entity: "post" },
    { path: "merch", label: "Merch Drops", kind: "kanban", entity: "merch_drop", config: { group_by: "status" } },
    { path: "sponsorship", label: "Sponsorships", kind: "kanban", entity: "sponsorship", config: { group_by: "stage" } },
  ],
  default_prompts: [
    { agent_slug: "suga_sean", label: "Fan check-in", prompt: "Pull the most engaged 10 subscribers this week. Suggest a personalised DM I can send." },
    { agent_slug: "suga_sean", label: "Post idea", prompt: "What's a high-engagement post angle I haven't run this month?" },
  ],
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
