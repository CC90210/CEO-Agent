import { notFound } from "next/navigation";
import { ManifestTable } from "@/components/manifest/ManifestTable";
import { ManifestKanban } from "@/components/manifest/ManifestKanban";
import { ManifestMarkdown } from "@/components/manifest/ManifestMarkdown";
import { ManifestDashboard } from "@/components/manifest/ManifestDashboard";
import { PageHeader, Tag } from "@/components/Card";
import { getManifest, manifestExists } from "@/lib/manifest/loader";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import type { ManifestPageDef } from "@/lib/manifest/schema";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Catch-all manifest renderer at `/t/<slug>/<...path>`.
 *
 * Phase 5 production replacement for the Phase 2 placeholder. Looks up
 * the matching `manifest.pages[]` entry by `path`, resolves the entity
 * (if any), and dispatches to the right primitive component based on
 * `page.kind`. Auth-gated by middleware; the per-action mutations live
 * inside each primitive's data layer and re-check tenant scope on
 * every write.
 *
 * Renders 404 for paths not in the manifest, so an operator who deletes
 * a page via the AI editor gets clean failure instead of a stale view.
 */
export default async function TenantCatchAllPage({
  params,
}: {
  params: Promise<{ slug: string; path: string[] }>;
}) {
  const { slug, path } = await params;
  const normalised = slug.toLowerCase();
  if (!(await manifestExists(normalised))) notFound();

  const manifest = await getManifest(normalised);
  const subPath = path.join("/");

  // Find the matching page by exact path match. If the caller passed
  // `/t/sun/leads/new` and the manifest only has a page at "leads",
  // we still match — the trailing path segment is a route the page
  // primitive owns (e.g. ManifestTable's "new" CTA).
  const pageDef =
    manifest.pages?.find((p) => p.path === subPath) ||
    manifest.pages?.find((p) => subPath.startsWith(`${p.path}/`)) ||
    null;

  if (!pageDef) {
    return <UnknownPath slug={normalised} subPath={subPath} />;
  }

  const user = await getSessionUser();
  const service = getServiceSupabase();
  const profileRes = user
    ? await service
        .from("user_profiles")
        .select("tenant_id")
        .eq("auth_user_id", user.id)
        .maybeSingle()
    : { data: null };
  const tenantId = (profileRes.data as { tenant_id: string | null } | null)?.tenant_id ?? null;
  // The renderer NEVER trusts a non-matching tenant_id — RLS on
  // tenant_records does the actual gate. tenantId here just decides
  // whether to render live data or the demo-rows fallback.

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title={pageDef.label}
        subtitle={renderSubtitle(manifest.brand.name, pageDef)}
        action={<Tag tone="accent">{pageDef.kind}</Tag>}
      />
      <PageBody slug={normalised} tenantId={tenantId} page={pageDef} manifest={manifest} />
    </div>
  );
}

function renderSubtitle(brand: string, page: ManifestPageDef): string {
  switch (page.kind) {
    case "dashboard": return `${brand} · live snapshot`;
    case "table": return page.entity ? `Table view of ${page.entity}` : "Table view";
    case "kanban": return page.entity ? `Kanban for ${page.entity}` : "Kanban view";
    case "form": return page.entity ? `Form for ${page.entity}` : "Form";
    case "markdown": return "Reference page";
    default: return brand;
  }
}

async function PageBody({
  slug,
  tenantId,
  page,
  manifest,
}: {
  slug: string;
  tenantId: string | null;
  page: ManifestPageDef;
  manifest: Awaited<ReturnType<typeof getManifest>>;
}) {
  switch (page.kind) {
    case "markdown":
      return <ManifestMarkdown page={page} />;
    case "dashboard":
      return <ManifestDashboard manifest={manifest} tenantId={tenantId} />;
    case "table":
    case "kanban":
    case "form": {
      const entity = (manifest.data_model || []).find((e) => e.name === page.entity);
      if (!entity) {
        return (
          <div className="rounded-2xl border border-amber-300/25 bg-amber-300/10 p-5 text-sm text-amber-100 leading-relaxed">
            This page references an entity <span className="font-mono text-fg">{page.entity || "(none)"}</span> that
            isn&apos;t defined in the manifest&apos;s <code>data_model</code>. Open the AI editor
            and add it, or remove the page reference.
          </div>
        );
      }
      if (page.kind === "kanban") {
        return <ManifestKanban tenantSlug={slug} tenantId={tenantId} entity={entity} page={page} />;
      }
      if (page.kind === "form") {
        // Form view is just a single-record table view for now; the
        // create/edit modal is Phase 5.1. Renders the entity's
        // field list so the operator can see the shape.
        return <ManifestTable tenantSlug={slug} tenantId={tenantId} entity={entity} page={page} canCreate />;
      }
      return <ManifestTable tenantSlug={slug} tenantId={tenantId} entity={entity} page={page} canCreate />;
    }
    default:
      return (
        <div className="rounded-2xl border border-bg-border bg-bg-elev/40 p-5 text-sm text-fg-muted">
          Unknown page kind: <span className="font-mono">{(page as ManifestPageDef).kind}</span>
        </div>
      );
  }
}

function UnknownPath({ slug, subPath }: { slug: string; subPath: string }) {
  return (
    <div className="space-y-4 animate-fade-in">
      <PageHeader title="Not in this manifest" subtitle={`/t/${slug}/${subPath}`} />
      <div className="rounded-2xl border border-bg-border bg-bg-elev/40 p-5 text-sm text-fg-muted leading-relaxed">
        The manifest for <code className="text-accent">{slug}</code> doesn&apos;t have a page
        at <code className="text-accent">/{subPath}</code>. Open the AI editor to add one,
        or browse the existing routes from the sidebar.
      </div>
    </div>
  );
}
