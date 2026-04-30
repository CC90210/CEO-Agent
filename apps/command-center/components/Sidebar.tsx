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
  { href: "/analytics", label: "Analytics", icon: BarChart3, group: "system" },
  { href: "/integrations", label: "Integrations", icon: Plug, group: "system" },
  { href: "/settings", label: "Settings", icon: Settings, group: "system" },
];

export function Sidebar({
  brand = "OASIS AI",
  operatorName,
  operatorEmail,
  primaryAgent = "bravo",
}: {
  brand?: string;
  operatorName?: string;
  operatorEmail?: string;
  primaryAgent?: string;
}) {
  const pathname = usePathname();
  const opsItems = ITEMS.filter((i) => i.group === "ops");
  const systemItems = ITEMS.filter((i) => i.group === "system");

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-60 border-r border-bg-border bg-bg-panel flex flex-col z-20">
      <div className="px-5 py-5 border-b border-bg-border">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-md bg-gradient-to-br from-accent to-accent-muted flex items-center justify-center text-bg font-black text-sm shadow-glow">
            O
          </div>
          <div className="leading-tight">
            <div className="text-fg font-bold text-sm tracking-tight">{brand}</div>
            <div className="text-fg-dim text-[10px] uppercase tracking-[0.18em] font-semibold">
              Agent Command Center
            </div>
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 overflow-y-auto">
        <NavGroup label="Operations">
          {opsItems.map((item) => (
            <NavLink key={item.href} item={item} pathname={pathname} />
          ))}
        </NavGroup>
        <NavGroup label="System">
          {systemItems.map((item) => (
            <NavLink key={item.href} item={item} pathname={pathname} />
          ))}
        </NavGroup>
      </nav>

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
          <span className="text-fg-dim">
            <span className="text-accent">●</span> {primaryAgent}
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

function NavLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
  const Icon = item.icon;
  return (
    <li>
      <Link
        href={item.href}
        className={`group flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors ${
          active
            ? "bg-accent-soft text-accent"
            : "text-fg-muted hover:bg-bg-hover hover:text-fg"
        }`}
      >
        <Icon
          size={16}
          className={active ? "text-accent" : "text-fg-dim group-hover:text-fg-muted"}
          strokeWidth={2}
        />
        <span className="font-medium">{item.label}</span>
      </Link>
    </li>
  );
}
