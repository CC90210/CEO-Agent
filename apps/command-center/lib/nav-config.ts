/**
 * Navigation primitives for the command-center shell.
 *
 * Each client/product profile (see lib/client-profiles.ts) picks one of
 * these nav arrays and can layer its own branding, runtime, and transport
 * rules on top. Sidebar.tsx stays fully tenant-agnostic.
 */

import {
  // CC empire nav (existing — lifted from Sidebar.tsx)
  LayoutDashboard,
  GitBranch,
  Brain,
  BookOpen,
  Bot,
  BarChart3,
  Plug,
  Settings,
  Activity,
  Inbox,
  History,
  ShieldCheck,
  ShieldAlert,
  Radio,
  // Sun Biz funding-ops nav
  Users,
  BookUser,
  FileText,
  Upload,
  HandCoins,
  BadgeDollarSign,
  RefreshCcw,
  DollarSign,
  MessageSquare,
  Mail,
  Landmark,
  FileCode2,
  UsersRound,
  Code2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

/**
 * NavItem — one entry in the sidebar.
 *
 * `group` is a free-form string label (rendered as the uppercase group
 * heading in the sidebar). Items with the same group cluster together,
 * preserving the order in which they first appear in the array.
 *
 * `badgeKey` (optional) names a counter the layout passes through — the
 * Sidebar component looks it up in its `badges` prop map. Today only
 * "inbox" is wired; "applications" lands when the applications table
 * exists (Phase 2 migration 039).
 *
 * `expandable` (optional) draws a chevron — Phase 1 visual only; the
 * sub-nav (e.g. SMS providers) is not actually expandable yet.
 */
export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  group: string;
  badgeKey?: string;
  expandable?: boolean;
};

/**
 * CC's empire command center nav (the existing default).
 * If you add a new empire-side page, add it here AND in
 * components/Sidebar.tsx tests if any reference the order.
 */
export const CC_NAV: NavItem[] = [
  { group: "Operations", href: "/", label: "Today", icon: LayoutDashboard },
  { group: "Operations", href: "/pipeline", label: "Pipeline", icon: GitBranch },
  { group: "Operations", href: "/reasoning", label: "Reasoning", icon: Brain },
  { group: "Operations", href: "/playbook", label: "Playbook", icon: BookOpen },
  { group: "System", href: "/agents", label: "Agents", icon: Bot },
  { group: "System", href: "/inbox", label: "Inbox", icon: Inbox, badgeKey: "inbox" },
  { group: "System", href: "/runs", label: "Runs", icon: History },
  { group: "System", href: "/operations", label: "Operations", icon: Activity },
  { group: "System", href: "/system-health", label: "System Health", icon: ShieldCheck },
  { group: "System", href: "/overrides", label: "Overrides", icon: ShieldAlert },
  { group: "System", href: "/feed", label: "Event Feed", icon: Radio },
  { group: "System", href: "/analytics", label: "Analytics", icon: BarChart3 },
  { group: "System", href: "/integrations", label: "Integrations", icon: Plug },
  { group: "System", href: "/settings", label: "Settings", icon: Settings },
];

/**
 * Sun Biz Funding nav — funding-ops sidebar. Matches the layout Sun
 * referenced from the "Bluestone" screenshots (Dashboard / Leads /
 * Contacts / Applications + count badge / Import / Offers / Funded
 * Deals / Renewals / Commissions / Inbox / SMS w/ expand / Email Blast
 * / Lenders / Templates / Team / Embed / Settings).
 */
export const SUN_NAV: NavItem[] = [
  { group: "Operations", href: "/", label: "Dashboard", icon: LayoutDashboard },
  { group: "Pipeline", href: "/leads", label: "Leads", icon: Users },
  { group: "Pipeline", href: "/contacts", label: "Contacts", icon: BookUser },
  { group: "Pipeline", href: "/applications", label: "Applications", icon: FileText, badgeKey: "applications" },
  { group: "Pipeline", href: "/import", label: "Import", icon: Upload },
  { group: "Deals", href: "/offers", label: "Offers", icon: HandCoins },
  { group: "Deals", href: "/funded-deals", label: "Funded Deals", icon: BadgeDollarSign },
  { group: "Deals", href: "/renewals", label: "Renewals", icon: RefreshCcw },
  { group: "Deals", href: "/commissions", label: "Commissions", icon: DollarSign },
  { group: "Outreach", href: "/inbox", label: "Inbox", icon: Inbox, badgeKey: "inbox" },
  { group: "Outreach", href: "/sms", label: "SMS", icon: MessageSquare, expandable: true },
  { group: "Outreach", href: "/email-blast", label: "Email Blast", icon: Mail },
  { group: "Network", href: "/lenders", label: "Lenders", icon: Landmark },
  { group: "Network", href: "/templates", label: "Templates", icon: FileCode2 },
  { group: "System", href: "/team", label: "Team", icon: UsersRound },
  { group: "System", href: "/embed", label: "Embed", icon: Code2 },
  { group: "System", href: "/settings", label: "Settings", icon: Settings },
];
