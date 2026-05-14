import { Card, PageHeader } from "@/components/Card";
import { Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";

/**
 * Phase 1 stub page. Renders the full sidebar shell so Sun's click-through
 * never hits a 404, but tells the operator the feature is wired and pending.
 *
 * Phase 2 turns each stub into a real list view backed by migrations
 * 037-047. Replacing a stub: swap `<ComingSoon ... />` for the actual
 * page content — the nav-config entry stays untouched.
 */
export function ComingSoon({
  title,
  subtitle,
  icon: Icon,
  phase2Bullets,
  related,
}: {
  title: string;
  subtitle: string;
  icon?: LucideIcon;
  phase2Bullets: string[];
  related?: { href: string; label: string }[];
}) {
  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader title={title} subtitle={subtitle} />

      <Card>
        <div className="flex items-start gap-4 py-2">
          <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-accent-soft border border-accent/30 flex items-center justify-center text-accent">
            {Icon ? <Icon size={20} /> : <Sparkles size={20} />}
          </div>
          <div className="flex-1 space-y-3">
            <div>
              <div className="text-fg text-base font-semibold mb-1">Coming Soon</div>
              <p className="text-fg-muted text-sm">
                This page is ready in the Sun Biz Funding Command Center.
                Solara's deeper workflow for this area is queued next, and the links below are the parts your team can use today.
              </p>
            </div>

            <div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold mb-2">
                Planned upgrades
              </div>
              <ul className="space-y-1.5">
                {phase2Bullets.map((b, i) => (
                  <li key={i} className="text-fg text-sm flex gap-2">
                    <span className="text-accent flex-shrink-0">·</span>
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
            </div>

            {related && related.length > 0 && (
              <div>
                <div className="text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold mb-2">
                  Working today
                </div>
                <div className="flex flex-wrap gap-2">
                  {related.map((r) => (
                    <a
                      key={r.href}
                      href={r.href}
                      className="px-3 py-1.5 rounded-md bg-bg-elev border border-bg-border text-fg-muted text-xs font-medium hover:bg-bg-hover hover:text-fg transition-colors"
                    >
                      {r.label} →
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
