/**
 * Navigation primitives for the command-center shell.
 *
 * Each client/product profile (see lib/client-profiles.ts) picks one of
 * these nav arrays and can layer its own branding, runtime, and transport
 * rules on top. Sidebar.tsx stays fully tenant-agnostic.
 *
 * Keep icons as string keys. These profiles are resolved in a Server
 * Component and then passed to the client Sidebar; passing icon functions
 * across that boundary crashes production rendering.
 */

export type NavIconKey =
  | "LayoutDashboard"
  | "GitBranch"
  | "Brain"
  | "BookOpen"
  | "Bot"
  | "BarChart3"
  | "Plug"
  | "Settings"
  | "Activity"
  | "Inbox"
  | "History"
  | "ShieldCheck"
  | "ShieldAlert"
  | "Radio"
  | "Users"
  | "BookUser"
  | "FileText"
  | "Upload"
  | "HandCoins"
  | "BadgeDollarSign"
  | "RefreshCcw"
  | "DollarSign"
  | "MessageSquare"
  | "Mail"
  | "Landmark"
  | "FileCode2"
  | "UsersRound"
  | "Code2"
  | "Megaphone"
  | "ShoppingBag"
  | "Heart"
  | "Sparkles";

/**
 * NavItem - one entry in the sidebar.
 *
 * `group` is a free-form string label rendered as the uppercase group
 * heading. Items with the same group cluster together while preserving the
 * order in which they first appear in the array.
 */
export type NavItem = {
  href: string;
  label: string;
  icon: NavIconKey;
  group: string;
  badgeKey?: string;
  expandable?: boolean;
};

/**
 * CC's empire command center nav.
 *
 * Routes intentionally hidden from this sidebar:
 *   - /inbox  — cross-agent inbox; useful substrate but no human nav slot
 *   - /runs   — developer-side activity tape; Event Feed serves the same UX
 *   - /system-health — V6 guard-substrate monitor; only meaningful when the
 *     state-api daemon is reachable from this deploy. On the public Vercel
 *     it's always "Off" by design, which CC reads (correctly) as noise.
 *     Reach it by direct URL when the local stack is up.
 * All three routes still resolve by direct URL for agents + scripts; they
 * just don't earn a sidebar slot in CC's day-to-day view.
 */
export const CC_NAV: NavItem[] = [
  // Operations group — daily-use pages CC opens to run the business.
  { group: "Operations", href: "/", label: "Today", icon: "LayoutDashboard" },
  { group: "Operations", href: "/pipeline", label: "Pipeline", icon: "GitBranch" },
  { group: "Operations", href: "/agents", label: "Agents", icon: "Bot" },
  { group: "Operations", href: "/reasoning", label: "Reasoning", icon: "Brain" },
  { group: "Operations", href: "/playbook", label: "Playbook", icon: "BookOpen" },
  // System group — observability + control surfaces.
  { group: "System", href: "/operations", label: "Operations", icon: "Activity" },
  { group: "System", href: "/automations", label: "Automations", icon: "RefreshCcw" },
  { group: "System", href: "/health", label: "Health", icon: "ShieldCheck" },
  { group: "System", href: "/overrides", label: "Overrides", icon: "ShieldAlert" },
  { group: "System", href: "/analytics", label: "Analytics", icon: "BarChart3" },
  { group: "System", href: "/settings", label: "Settings", icon: "Settings" },
  // Nav arc on CC's empire sidebar:
  //   - 13 entries → 7  (Phase 2, 2026-05-16: blunt consolidation, no merge)
  //   - 7 → 10          (Phase 7: restore Reasoning + Health + Overrides
  //                      after CC pointed out Phase 2 was too aggressive)
  //   - 10 → 11         (V6.8.5, 2026-05-17: restore /playbook — V6.8.3
  //                      shipped INTEGRATE_NEW_TOOL at /playbook/prompts
  //                      so the playbook surface is daily-use now, not
  //                      reference. Phase 2's "fold into /settings/playbook"
  //                      plan was never implemented — that path doesn't exist.)
  //
  // Routes reachable by direct URL but intentionally NOT in this sidebar:
  //   /integrations  — apps/command-center/app/integrations/page.tsx exists
  //                    and is functional, but it's setup-time work (paste a
  //                    Stripe key once), not daily. Reach via direct URL or
  //                    deep-link from /settings.
  //   /feed          — apps/command-center/app/feed/page.tsx exists and
  //                    renders the agent_events stream. /operations shows
  //                    the same stream styled as an Activity Tape; CC reads
  //                    that one, so /feed stays URL-only.
  //   /inbox         — cross-agent inbox, useful substrate, no human nav slot.
  //   /runs          — developer-side activity tape; /operations covers it.
  //   /system-health — V6 guard-substrate monitor; only meaningful when the
  //                    state-api daemon is reachable. On public Vercel it's
  //                    always "Off" by design (noise without the local stack).
  //
  // /forms + /sequences intentionally absent — SunBiz CRM features that
  // surface only on the SunBiz tenant nav (see SUN_NAV below).
];

/**
 * Sun Biz Funding nav - funding-ops sidebar.
 *
 * Industry-relevant only: SMS, Email, CRM (Leads/Contacts/Applications), Deals,
 * Playbook + Reasoning (operating manual + decision log). The OASIS-internal
 * agent-handoff inbox (/inbox) is intentionally absent — clients don't need
 * to see agent-to-agent message routing.
 */
export const SUN_NAV: NavItem[] = [
  // Operations — daily-use core. /pipeline is the new Salesforce-parity
  // superview (Lead Pipeline + Opportunity Pipeline stacked with arrow
  // chevron bars per Adon's 2026-05-16 screenshots).
  { group: "Operations", href: "/", label: "Dashboard", icon: "LayoutDashboard" },
  { group: "Operations", href: "/pipeline", label: "Pipeline", icon: "GitBranch" },
  { group: "Operations", href: "/agent", label: "Agents", icon: "Bot" },
  { group: "Operations", href: "/reasoning", label: "Reasoning", icon: "Brain" },
  { group: "Operations", href: "/playbook", label: "Playbook", icon: "BookOpen" },
  // Pipeline — per-entity boards behind the unified /pipeline view.
  // Contacts dropped 2026-05-17 — was a speculative scaffold; the lead
  // record itself carries contact_name + phone + email so a separate
  // Contacts surface is dead weight until Adon asks for it.
  { group: "Pipeline", href: "/leads", label: "Leads", icon: "Users" },
  { group: "Pipeline", href: "/applications", label: "Applications", icon: "FileText", badgeKey: "applications" },
  { group: "Pipeline", href: "/import", label: "Import", icon: "Upload" },
  { group: "Pipeline", href: "/forms", label: "Forms", icon: "FileCode2" },
  // Deals — Opportunity-side records.
  { group: "Deals", href: "/offers", label: "Offers", icon: "HandCoins" },
  { group: "Deals", href: "/funded-deals", label: "Funded Deals", icon: "BadgeDollarSign" },
  { group: "Deals", href: "/renewals", label: "Renewals", icon: "RefreshCcw" },
  { group: "Deals", href: "/commissions", label: "Commissions", icon: "DollarSign" },
  // Outreach — drip + blast cadence surfaces.
  { group: "Outreach", href: "/sequences", label: "Sequences", icon: "Sparkles" },
  { group: "Outreach", href: "/sms", label: "SMS", icon: "MessageSquare", expandable: true },
  { group: "Outreach", href: "/email-blast", label: "Email Blast", icon: "Mail" },
  // Network — lender book + templates.
  { group: "Network", href: "/lenders", label: "Lenders", icon: "Landmark" },
  { group: "Network", href: "/templates", label: "Templates", icon: "FileCode2" },
  // System — config + ops.
  { group: "System", href: "/team", label: "Team", icon: "UsersRound" },
  { group: "System", href: "/automations", label: "Automations", icon: "RefreshCcw" },
  { group: "System", href: "/health", label: "Health", icon: "ShieldCheck" },
  { group: "System", href: "/embed", label: "Embed", icon: "Code2" },
  { group: "System", href: "/settings", label: "Settings", icon: "Settings" },
];

/**
 * Suga Sean O'Malley nav — fan-ops + brand sidebar (Phase 1 scaffold).
 *
 * Placeholder routes that mostly point to /agent or generic stubs until the
 * Suga Sean agent ships its own pages. Mirrors SUN_NAV's structure so the
 * sidebar UX stays consistent across client agents.
 */
export const SUGA_NAV: NavItem[] = [
  { group: "Operations", href: "/", label: "Dashboard", icon: "LayoutDashboard" },
  { group: "Operations", href: "/agent", label: "Agents", icon: "Bot" },
  { group: "Operations", href: "/reasoning", label: "Reasoning", icon: "Brain" },
  { group: "Operations", href: "/playbook", label: "Playbook", icon: "BookOpen" },
  { group: "Fans", href: "/subscribers", label: "Subscribers", icon: "Users" },
  { group: "Fans", href: "/segments", label: "Segments", icon: "Sparkles" },
  { group: "Brand", href: "/posts", label: "Posts", icon: "Megaphone" },
  { group: "Brand", href: "/drafts", label: "Drafts", icon: "FileText" },
  // /forms intentionally NOT in SUGA nav — the form builder shipped
  // in Phase 3 of the SunBiz CRM build is funding-shop-flavored
  // (multi-step funnels, bank statement upload, stage_outcomes mapping
  // to funding lead.stage values). SUGA's brand workflow uses a
  // different model (fan signups via Late/Zernio + Square). If SUGA
  // ever needs a generic form builder, that's a separate add.
  { group: "Brand", href: "/queue", label: "Queue", icon: "RefreshCcw" },
  { group: "Commerce", href: "/merch", label: "Merch", icon: "ShoppingBag" },
  { group: "Commerce", href: "/orders", label: "Orders", icon: "BadgeDollarSign" },
  { group: "Commerce", href: "/affiliates", label: "Affiliates", icon: "Heart" },
  { group: "Sponsorship", href: "/sponsorship", label: "Pipeline", icon: "HandCoins" },
  { group: "Sponsorship", href: "/contracts", label: "Contracts", icon: "FileCode2" },
  { group: "System", href: "/team", label: "Team", icon: "UsersRound" },
  { group: "System", href: "/automations", label: "Automations", icon: "RefreshCcw" },
  { group: "System", href: "/embed", label: "Embed", icon: "Code2" },
  { group: "System", href: "/settings", label: "Settings", icon: "Settings" },
];
