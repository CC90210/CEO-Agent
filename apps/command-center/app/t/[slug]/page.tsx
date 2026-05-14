import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight, Sparkles } from "lucide-react";
import { Card, PageHeader, Tag } from "@/components/Card";
import { getManifest, manifestExists } from "@/lib/manifest/loader";

export const dynamic = "force-dynamic";

/**
 * Tenant landing for `/t/<slug>/`.
 *
 * Phase 1 ships a manifest-aware overview card. The catch-all
 * `/t/[slug]/[...path]/page.tsx` is what Phase 2's renderer will fill
 * with kind-specific pages (tables, kanbans, dashboards, forms).
 *
 * Auth: handled by middleware. Demo previews continue to flow through
 * `/demo/<slug>`; bare `/t/<slug>` requires a session.
 */
export default async function TenantLandingPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const normalised = slug.toLowerCase();
  if (!(await manifestExists(normalised))) notFound();

  const manifest = await getManifest(normalised);
  const enabledAgents = manifest.agents.filter((a) => a.enabled);
  const navGroups = Array.from(new Set(manifest.nav.map((n) => n.group)));

  return (
    <div className="space-y-8 animate-fade-in">
      <PageHeader
        title={manifest.brand.name}
        subtitle={manifest.brand.subtitle}
        action={<Tag tone="accent">manifest v{manifest.version}</Tag>}
      />

      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
        <Card title="Agents" subtitle={`${enabledAgents.length} enabled`}>
          <div className="space-y-2.5">
            {enabledAgents.map((agent) => (
              <div key={agent.slug} className="flex items-center justify-between text-sm">
                <span className="font-medium text-fg">{agent.display_name}</span>
                <span className="text-xs uppercase tracking-wider text-fg-dim">
                  {agent.primary ? "primary" : "enabled"}
                </span>
              </div>
            ))}
            {enabledAgents.length === 0 && (
              <div className="text-sm text-fg-muted">No agents enabled in this manifest yet.</div>
            )}
          </div>
        </Card>

        <Card title="Navigation" subtitle={`${manifest.nav.length} items across ${navGroups.length} groups`}>
          <div className="space-y-1.5">
            {navGroups.map((group) => {
              const items = manifest.nav.filter((n) => n.group === group);
              return (
                <div key={group} className="text-sm">
                  <span className="text-xs uppercase tracking-wider text-fg-dim font-semibold">{group}</span>
                  <span className="ml-2 text-fg-muted">{items.map((i) => i.label).join(", ")}</span>
                </div>
              );
            })}
          </div>
        </Card>

        <Card title="Industry" subtitle={manifest.onboarding_industry || "custom"}>
          <div className="text-sm text-fg-muted leading-relaxed">
            Backed by <span className="font-mono text-fg">{manifest.data_backend || "supabase"}</span> in{" "}
            <span className="font-mono text-fg">{manifest.deployment_mode || "shared"}</span> mode.
            {manifest.permissions && (
              <div className="mt-3 text-xs text-fg-dim">
                Permissions —{" "}
                {[
                  manifest.permissions.local_files && "local files",
                  manifest.permissions.computer_control && "computer control",
                  manifest.permissions.web_access && "web access",
                ]
                  .filter(Boolean)
                  .join(", ") || "none"}
              </div>
            )}
          </div>
        </Card>
      </div>

      <section className="rounded-2xl border border-accent/25 bg-accent/5 p-5">
        <div className="flex items-start gap-3">
          <Sparkles className="mt-1 h-5 w-5 text-accent" />
          <div>
            <div className="font-bold text-fg">Phase 2 — Manifest-driven pages</div>
            <p className="mt-1 text-sm text-fg-muted leading-relaxed">
              This namespace renders this tenant&apos;s manifest. The catch-all renderer for tables,
              kanbans, dashboards, and forms is the next milestone — same shell, different data,
              configurable through the embedded AI editor.
            </p>
            <Link
              href={`/t/${normalised}/leads`}
              className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-accent hover:text-accent/80"
            >
              Preview a manifest page <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
