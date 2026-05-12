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
  | "Code2";

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
 */
export const CC_NAV: NavItem[] = [
  { group: "Operations", href: "/", label: "Today", icon: "LayoutDashboard" },
  { group: "Operations", href: "/pipeline", label: "Pipeline", icon: "GitBranch" },
  { group: "Operations", href: "/reasoning", label: "Reasoning", icon: "Brain" },
  { group: "Operations", href: "/playbook", label: "Playbook", icon: "BookOpen" },
  { group: "System", href: "/agents", label: "Agents", icon: "Bot" },
  { group: "System", href: "/inbox", label: "Inbox", icon: "Inbox", badgeKey: "inbox" },
  { group: "System", href: "/runs", label: "Runs", icon: "History" },
  { group: "System", href: "/operations", label: "Operations", icon: "Activity" },
  { group: "System", href: "/system-health", label: "System Health", icon: "ShieldCheck" },
  { group: "System", href: "/overrides", label: "Overrides", icon: "ShieldAlert" },
  { group: "System", href: "/feed", label: "Event Feed", icon: "Radio" },
  { group: "System", href: "/analytics", label: "Analytics", icon: "BarChart3" },
  { group: "System", href: "/integrations", label: "Integrations", icon: "Plug" },
  { group: "System", href: "/settings", label: "Settings", icon: "Settings" },
];

/**
 * Sun Biz Funding nav - funding-ops sidebar.
 */
export const SUN_NAV: NavItem[] = [
  { group: "Operations", href: "/", label: "Dashboard", icon: "LayoutDashboard" },
  { group: "Pipeline", href: "/leads", label: "Leads", icon: "Users" },
  { group: "Pipeline", href: "/contacts", label: "Contacts", icon: "BookUser" },
  { group: "Pipeline", href: "/applications", label: "Applications", icon: "FileText", badgeKey: "applications" },
  { group: "Pipeline", href: "/import", label: "Import", icon: "Upload" },
  { group: "Deals", href: "/offers", label: "Offers", icon: "HandCoins" },
  { group: "Deals", href: "/funded-deals", label: "Funded Deals", icon: "BadgeDollarSign" },
  { group: "Deals", href: "/renewals", label: "Renewals", icon: "RefreshCcw" },
  { group: "Deals", href: "/commissions", label: "Commissions", icon: "DollarSign" },
  { group: "Outreach", href: "/inbox", label: "Inbox", icon: "Inbox", badgeKey: "inbox" },
  { group: "Outreach", href: "/sms", label: "SMS", icon: "MessageSquare", expandable: true },
  { group: "Outreach", href: "/email-blast", label: "Email Blast", icon: "Mail" },
  { group: "Network", href: "/lenders", label: "Lenders", icon: "Landmark" },
  { group: "Network", href: "/templates", label: "Templates", icon: "FileCode2" },
  { group: "System", href: "/team", label: "Team", icon: "UsersRound" },
  { group: "System", href: "/embed", label: "Embed", icon: "Code2" },
  { group: "System", href: "/settings", label: "Settings", icon: "Settings" },
];
