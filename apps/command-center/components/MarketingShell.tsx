import Link from "next/link";
import type { ReactNode } from "react";

/** Public marketing chrome — header (with sign in CTA) + footer. */
export function MarketingShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col">
      <MarketingHeader />
      <main className="flex-1 relative z-10">{children}</main>
      <MarketingFooter />
    </div>
  );
}

function MarketingHeader() {
  return (
    <header className="sticky top-0 z-30 backdrop-blur bg-bg/80 border-b border-bg-border">
      <div className="mx-auto max-w-7xl px-6 py-4 flex items-center justify-between">
        <Link href="/welcome" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-md bg-gradient-to-br from-accent to-accent-muted flex items-center justify-center text-bg font-black text-sm shadow-glow">
            O
          </div>
          <div className="leading-tight">
            <div className="text-fg font-bold text-sm tracking-tight">OASIS AI</div>
            <div className="text-fg-dim text-[9px] uppercase tracking-[0.18em] font-semibold">
              Agent Operating System
            </div>
          </div>
        </Link>

        <nav className="hidden md:flex items-center gap-7 text-sm">
          <Link href="/pricing" className="text-fg-muted hover:text-fg transition-colors">
            Pricing
          </Link>
          <Link href="/about" className="text-fg-muted hover:text-fg transition-colors">
            About
          </Link>
          <Link href="/contact" className="text-fg-muted hover:text-fg transition-colors">
            Contact
          </Link>
        </nav>

        <div className="flex items-center gap-2">
          <Link
            href="/login"
            className="hidden sm:inline-block text-fg-muted hover:text-fg text-sm font-medium px-3 py-1.5 transition-colors"
          >
            Sign in
          </Link>
          <Link
            href="/pricing"
            className="bg-accent text-bg font-bold px-4 py-2 rounded-md hover:bg-accent-muted transition-colors text-sm shadow-glow"
          >
            Get started
          </Link>
        </div>
      </div>
    </header>
  );
}

function MarketingFooter() {
  return (
    <footer className="border-t border-bg-border mt-24">
      <div className="mx-auto max-w-7xl px-6 py-10 grid md:grid-cols-4 gap-8 text-sm">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <div className="w-7 h-7 rounded-md bg-gradient-to-br from-accent to-accent-muted flex items-center justify-center text-bg font-black text-xs">
              O
            </div>
            <span className="text-fg font-bold">OASIS AI</span>
          </div>
          <p className="text-fg-dim text-xs leading-relaxed">
            The operating system for AI agents. Your team's new operating layer.
          </p>
        </div>
        <FooterCol
          title="Product"
          links={[
            { href: "/pricing", label: "Pricing" },
            { href: "/login", label: "Sign in" },
            { href: "/signup", label: "Sign up" },
          ]}
        />
        <FooterCol
          title="Company"
          links={[
            { href: "/about", label: "About" },
            { href: "/contact", label: "Contact" },
          ]}
        />
        <FooterCol
          title="Legal"
          links={[
            { href: "/legal/privacy", label: "Privacy" },
            { href: "/legal/terms", label: "Terms" },
          ]}
        />
      </div>
      <div className="border-t border-bg-border">
        <div className="mx-auto max-w-7xl px-6 py-5 flex justify-between items-center text-xs text-fg-faint">
          <span>© {new Date().getFullYear()} OASIS AI Solutions</span>
          <span>"Only good things from now on."</span>
        </div>
      </div>
    </footer>
  );
}

function FooterCol({
  title,
  links,
}: {
  title: string;
  links: Array<{ href: string; label: string }>;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.16em] font-bold text-fg-faint mb-3">
        {title}
      </div>
      <ul className="space-y-2">
        {links.map((l) => (
          <li key={l.href}>
            <Link href={l.href} className="text-fg-muted hover:text-accent transition-colors">
              {l.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
