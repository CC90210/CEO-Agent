import Link from "next/link";

const LINKS = [
  { href: "/", label: "Today" },
  { href: "/decisions", label: "Decisions" },
  { href: "/inbound", label: "Inbound" },
  { href: "/outbound", label: "Outbound" },
  { href: "/leads", label: "Leads" },
  { href: "/agents", label: "Agents" },
];

export function Nav() {
  return (
    <nav className="border-b border-bg-border bg-bg-panel">
      <div className="mx-auto max-w-6xl px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-fg font-bold tracking-wide">BRAVO</span>
          <span className="text-accent font-bold tracking-wide">COMMAND CENTER</span>
        </div>
        <ul className="flex gap-6 text-sm">
          {LINKS.map((l) => (
            <li key={l.href}>
              <Link
                href={l.href}
                className="text-fg-muted hover:text-accent transition-colors"
              >
                {l.label}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
