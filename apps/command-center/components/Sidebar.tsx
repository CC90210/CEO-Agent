"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  GitBranch,
  Brain,
  BookOpen,
  Bot,
  BarChart3,
  Plug,
  Settings,
  LogOut,
  Activity,
  Inbox,
  History,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  group: "ops" | "system";
};

const ITEMS: NavItem[] = [
  { href: "/", label: "Today", icon: LayoutDashboard, group: "ops" },
  { href: "/pipeline", label: "Pipeline", icon: GitBranch, group: "ops" },
  { href: "/reasoning", label: "Reasoning", icon: Brain, group: "ops" },
  { href: "/playbook", label: "Playbook", icon: BookOpen, group: "ops" },
  { href: "/agents", label: "Agents", icon: Bot, group: "system" },
  { href: "/inbox", label: "Inbox", icon: Inbox, group: "system" },
  { href: "/runs", label: "Runs", icon: History, group: "system" },
  { href: "/operations", label: "Operations", icon: Activity, group: "system" },
  { href: "/analytics", label: "Analytics", icon: BarChart3, group: "system" },
  { href: "/integrations", label: "Integrations", icon: Plug, group: "system" },
  { href: "/settings", label: "Settings", icon: Settings, group: "system" },
];

export function Sidebar({
  brand = "OASIS AI",
  operatorName,
  operatorEmail,
  primaryAgent = "bravo",
  primaryAgentLive = false,
  bridgeOnline = false,
  inboxUnread = 0,
}: {
  brand?: string;
  operatorName?: string;
  operatorEmail?: string;
  primaryAgent?: string;
  primaryAgentLive?: boolean;
  bridgeOnline?: boolean;
  inboxUnread?: number;
}) {
  const pathname = usePathname();
  const opsItems = ITEMS.filter((i) => i.group === "ops");
  const systemItems = ITEMS.filter((i) => i.group === "system");

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-60 border-r border-bg-border bg-bg-panel flex flex-col z-20">
      {/* Brand block */}
      <div className="px-5 py-5 border-b border-bg-border relative">
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="relative">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/oasis-logo.svg"
              alt="OASIS AI"
              width={36}
              height={36}
              className="rounded-md shadow-glow ring-1 ring-accent/30 group-hover:ring-accent/60 transition-all"
            />
            <div className="absolute -inset-0.5 rounded-md bg-accent/20 blur opacity-50 -z-10" />
          </div>
          <div className="leading-tight">
            <div className="text-fg font-bold text-sm tracking-tight">
              {brand}
            </div>
            <div className="text-fg-dim text-[10px] uppercase tracking-[0.18em] font-semibold">
              Agent Command Center
            </div>
          </div>
        </Link>
        {/* Animated thin accent line under brand */}
        <div className="absolute bottom-0 left-0 right-0 top-glow" />
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 overflow-y-auto">
        <NavGroup label="Operations">
          {opsItems.map((item) => (
            <NavLink key={item.href} item={item} pathname={pathname} />
          ))}
        </NavGroup>
        <NavGroup label="System">
          {systemItems.map((item) => (
            <NavLink
              key={item.href}
              item={item}
              pathname={pathname}
              badgeCount={item.href === "/inbox" ? inboxUnread : 0}
            />
          ))}
        </NavGroup>
      </nav>

      {/* Operator */}
      <div className="border-t border-bg-border px-4 py-3 space-y-2">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-full bg-bg-elev border border-bg-border flex items-center justify-center text-fg-muted text-xs font-bold">
            {(operatorName || "U").charAt(0).toUpperCase()}
          </div>
          <div className="flex-1 leading-tight min-w-0">
            <div className="text-fg text-xs font-medium truncate">
              {operatorName || "Operator"}
            </div>
            <div className="text-fg-dim text-[10px] truncate font-mono">
              {operatorEmail || ""}
            </div>
          </div>
        </div>
        <div className="flex items-center justify-between text-[10px] uppercase tracking-wider">
          <span className="text-fg-dim flex items-center gap-1.5" title={primaryAgentLive ? `${primaryAgent} ticked in the last 15 min` : `${primaryAgent} hasn't ticked recently`}>
            <span className={primaryAgentLive ? "text-status-engaged animate-pulse-slow" : "text-fg-faint"}>●</span>
            <span>{primaryAgent}</span>
            <span className={primaryAgentLive ? "text-status-engaged" : "text-fg-faint"}>
              {primaryAgentLive ? "live" : "idle"}
            </span>
          </span>
          <form action="/api/auth/signout" method="post">
            <button
              type="submit"
              className="text-fg-dim hover:text-status-hot transition-colors flex items-center gap-1"
            >
              <LogOut size={11} />
              <span>Sign out</span>
            </button>
          </form>
        </div>
        <div
          className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-fg-dim"
          title={bridgeOnline
            ? "Local bridge daemon pinged within last 5 min"
            : "Local bridge offline — run `bravo bridge start`"}
        >
          <span className={bridgeOnline ? "text-accent animate-pulse-slow" : "text-fg-faint"}>◆</span>
          <span>local bridge</span>
          <span className={bridgeOnline ? "text-accent" : "text-fg-faint"}>
            {bridgeOnline ? "online" : "offline"}
          </span>
        </div>
      </div>
    </aside>
  );
}

function NavGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="px-3 mb-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-fg-faint">
        {label}
      </div>
      <ul className="space-y-0.5">{children}</ul>
    </div>
  );
}

function NavLink({
  item,
  pathname,
  badgeCount = 0,
}: {
  item: NavItem;
  pathname: string;
  badgeCount?: number;
}) {
  const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
  const Icon = item.icon;
  return (
    <li>
      <Link
        href={item.href}
        prefetch={true}  // Next.js prefetches on viewport — instant nav
        className={`group flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-all relative ${
          active
            ? "bg-accent-soft text-accent shadow-[inset_0_0_0_1px_rgba(59,130,246,0.25)]"
            : "text-fg-muted hover:bg-bg-hover hover:text-fg"
        }`}
      >
        {active && (
          <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-accent rounded-r-full shadow-glow" />
        )}
        <Icon
          size={16}
          className={active ? "text-accent" : "text-fg-dim group-hover:text-fg-muted"}
          strokeWidth={2}
        />
        <span className="font-medium flex-1">{item.label}</span>
        {badgeCount > 0 && (
          <span
            className="ml-auto px-1.5 py-0.5 rounded-full bg-accent text-bg-deep text-[10px] font-bold leading-none min-w-[16px] text-center"
            title={`${badgeCount} unread`}
          >
            {badgeCount > 99 ? "99+" : badgeCount}
          </span>
        )}
      </Link>
    </li>
  );
}
