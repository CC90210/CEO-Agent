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
  { group: "Operations", href: "/", label: "Today", icon: "LayoutDashboard" },
  { group: "Operations", href: "/pipeline", label: "Pipeline", icon: "GitBranch" },
  { group: "Operations", href: "/reasoning", label: "Reasoning", icon: "Brain" },
  { group: "Operations", href: "/playbook", label: "Playbook", icon: "BookOpen" },
  { group: "System", href: "/agents", label: "Agents", icon: "Bot" },
  { group: "System", href: "/operations", label: "Operations", icon: "Activity" },
  { group: "System", href: "/automations", label: "Automations", icon: "RefreshCcw" },
  { group: "System", href: "/forms", label: "Forms", icon: "FileText" },
  { group: "System", href: "/feed", label: "Event Feed", icon: "Radio" },
  { group: "System", href: "/overrides", label: "Overrides", icon: "ShieldAlert" },
  { group: "System", href: "/analytics", label: "Analytics", icon: "BarChart3" },
  { group: "System", href: "/integrations", label: "Integrations", icon: "Plug" },
  { group: "System", href: "/settings", label: "Settings", icon: "Settings" },
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
  { group: "Operations", href: "/", label: "Dashboard", icon: "LayoutDashboard" },
  { group: "Operations", href: "/agent", label: "Agents", icon: "Bot" },
  { group: "Operations", href: "/reasoning", label: "Reasoning", icon: "Brain" },
  { group: "Operations", href: "/playbook", label: "Playbook", icon: "BookOpen" },
  { group: "Pipeline", href: "/leads", label: "Leads", icon: "Users" },
  { group: "Pipeline", href: "/contacts", label: "Contacts", icon: "BookUser" },
  { group: "Pipeline", href: "/applications", label: "Applications", icon: "FileText", badgeKey: "applications" },
  { group: "Pipeline", href: "/forms", label: "Forms", icon: "FileCode2" },
  { group: "Pipeline", href: "/import", label: "Import", icon: "Upload" },
  { group: "Deals", href: "/offers", label: "Offers", icon: "HandCoins" },
  { group: "Deals", href: "/funded-deals", label: "Funded Deals", icon: "BadgeDollarSign" },
  { group: "Deals", href: "/renewals", label: "Renewals", icon: "RefreshCcw" },
  { group: "Deals", href: "/commissions", label: "Commissions", icon: "DollarSign" },
  { group: "Outreach", href: "/sms", label: "SMS", icon: "MessageSquare", expandable: true },
  { group: "Outreach", href: "/email-blast", label: "Email Blast", icon: "Mail" },
  { group: "Network", href: "/lenders", label: "Lenders", icon: "Landmark" },
  { group: "Network", href: "/templates", label: "Templates", icon: "FileCode2" },
  { group: "System", href: "/team", label: "Team", icon: "UsersRound" },
  { group: "System", href: "/automations", label: "Automations", icon: "RefreshCcw" },
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
  { group: "Brand", href: "/forms", label: "Forms", icon: "FileCode2" },
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
