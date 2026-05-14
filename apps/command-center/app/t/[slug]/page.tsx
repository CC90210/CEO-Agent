import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight, Sparkles } from "lucide-react";
import { Card, PageHeader, Tag } from "@/components/Card";
import { ManifestTable } from "@/components/manifest/ManifestTable";
import { ManifestKanban } from "@/components/manifest/ManifestKanban";
import { ManifestMarkdown } from "@/components/manifest/ManifestMarkdown";
import { ManifestDashboard } from "@/components/manifest/ManifestDashboard";
import { getManifest, manifestExists } from "@/lib/manifest/loader";
import { getManifestRow } from "@/lib/manifest/persistence";
import { resolveClientProfileSlug } from "@/lib/client-profiles";
import { getTenant } from "@/lib/queries";
import { CATEGORY_LABELS } from "@/lib/agents/library";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";

/** Mirror of resolveDataTenant in [...path]/page.tsx — kept inline so the
 *  root and catch-all share the same data-scoping rule. If this drifts it
 *  becomes a cross-shell data-bleed bug, so we'd promote to lib/. */
async function resolveDataTenant(
  slug: string,
  userTenantId: string | null
): Promise<string | null> {
  if (!userTenantId) return null;
  const row = await getManifestRow(slug).catch(() => null);
  if (row?.tenant_id && row.tenant_id === userTenantId) return userTenantId;
  if (!row) {
    const tenant = await getTenant(userTenantId).catch(() => null);
    const userSlug = resolveClientProfileSlug(tenant || null);
    if (userSlug && userSlug.toLowerCase() === slug.toLowerCase()) {
      return userTenantId;
    }
  }
  return null;
}

export const dynamic = "force-dynamic";

/**
 * Tenant root at `/t/<slug>/`.
 *
 * Phase 5: if the manifest declares a page at path "" or "/", we render
 * THAT page via the same primitive dispatcher the catch-all uses — so
 * a tenant can have "Dashboard" as their home view. If no root page is
 * declared, falls back to the generic manifest-summary card.
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
  const rootPage =
    manifest.pages?.find((p) => p.path === "" || p.path === "/") ||
    null;

  if (rootPage) {
    return <RootPageRenderer slug={normalised} page={rootPage} manifest={manifest} />;
  }

  return <GenericSummary slug={normalised} manifest={manifest} />;
}

async function RootPageRenderer({
  slug,
  page,
  manifest,
}: {
  slug: string;
  page: NonNullable<Awaited<ReturnType<typeof getManifest>>["pages"]>[number];
  manifest: Awaited<ReturnType<typeof getManifest>>;
}) {
  const user = await getSessionUser();
  const service = getServiceSupabase();
  const profileRes = user
    ? await service
        .from("user_profiles")
        .select("tenant_id")
        .eq("auth_user_id", user.id)
        .maybeSingle()
    : { data: null };
  const userTenantId = (profileRes.data as { tenant_id: string | null } | null)?.tenant_id ?? null;
  const dataTenantId = await resolveDataTenant(slug, userTenantId);
  const isPreview = !!userTenantId && dataTenantId === null;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title={page.label || manifest.brand.name}
        subtitle={manifest.brand.subtitle}
        action={
          <div className="flex items-center gap-2">
            {isPreview && <Tag tone="warm">preview</Tag>}
            <Tag tone="accent">{page.kind}</Tag>
          </div>
        }
      />
      {isPreview && (
        <div className="rounded-2xl border border-amber-300/25 bg-amber-300/10 p-4 text-sm leading-relaxed text-amber-100">
          Preview mode — your tenant doesn&apos;t own this slug, so no live records render here.
          The manifest structure, navigation, and entity schemas are exactly what a real{" "}
          <span className="font-mono">/t/{slug}</span> tenant would see.
        </div>
      )}
      {page.kind === "markdown" && <ManifestMarkdown page={page} />}
      {page.kind === "dashboard" && (
        <ManifestDashboard manifest={manifest} tenantId={dataTenantId} />
      )}
      {(page.kind === "table" || page.kind === "form") && (() => {
        const entity = (manifest.data_model || []).find((e) => e.name === page.entity);
        if (!entity) return <UnknownEntity name={page.entity} />;
        return <ManifestTable tenantSlug={slug} tenantId={dataTenantId} entity={entity} page={page} canCreate />;
      })()}
      {page.kind === "kanban" && (() => {
        const entity = (manifest.data_model || []).find((e) => e.name === page.entity);
        if (!entity) return <UnknownEntity name={page.entity} />;
        return <ManifestKanban tenantSlug={slug} tenantId={dataTenantId} entity={entity} page={page} />;
      })()}
    </div>
  );
}

function UnknownEntity({ name }: { name?: string }) {
  return (
    <div className="rounded-2xl border border-amber-300/25 bg-amber-300/10 p-5 text-sm text-amber-100 leading-relaxed">
      This page references an entity <span className="font-mono text-fg">{name || "(none)"}</span> that
      isn&apos;t defined in the manifest&apos;s <code>data_model</code>.
    </div>
  );
}

function GenericSummary({
  slug,
  manifest,
}: {
  slug: string;
  manifest: Awaited<ReturnType<typeof getManifest>>;
}) {
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
            <div className="font-bold text-fg">No root page defined</div>
            <p className="mt-1 text-sm text-fg-muted leading-relaxed">
              This tenant&apos;s manifest doesn&apos;t declare a page at the root path.
              Open the AI editor and ask it to add a dashboard page at path &quot;/&quot;,
              or browse the existing routes from the sidebar.
            </p>
            <div className="mt-3 flex gap-3">
              <Link
                href={`/t/${slug}/editor`}
                className="inline-flex items-center gap-2 text-sm font-semibold text-accent hover:text-accent/80"
              >
                Open editor <ArrowRight className="h-3.5 w-3.5" />
              </Link>
              <Link
                href={`/t/${slug}/marketplace`}
                className="inline-flex items-center gap-2 text-sm font-semibold text-fg-muted hover:text-fg"
              >
                Marketplace
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

// CATEGORY_LABELS is imported above for type-side use, but we don't render
// the agent category label on this page in the new path. Keep the import so
// the markup is consistent with the rest of the manifest pages.
void CATEGORY_LABELS;
