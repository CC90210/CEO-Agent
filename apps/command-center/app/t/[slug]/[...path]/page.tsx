import { notFound } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { ManifestTable } from "@/components/manifest/ManifestTable";
import { ManifestKanban } from "@/components/manifest/ManifestKanban";
import { ManifestMarkdown } from "@/components/manifest/ManifestMarkdown";
import { ManifestDashboard } from "@/components/manifest/ManifestDashboard";
import { ManifestRecordForm } from "@/components/manifest/ManifestRecordForm";
import { Card, PageHeader, Tag } from "@/components/Card";
import { getManifest, manifestExists } from "@/lib/manifest/loader";
import { getManifestRow } from "@/lib/manifest/persistence";
import { resolveClientProfileSlug } from "@/lib/client-profiles";
import { getTenant } from "@/lib/queries";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import type { ManifestPageDef } from "@/lib/manifest/schema";

/**
 * Resolve which tenant_id the manifest primitives should query records
 * for. The rule:
 *
 *   - If the manifest has a DB row whose tenant_id matches the caller's
 *     tenant_id → grant data access (this is the operator's claimed slug).
 *   - If the manifest is a code seed (no DB row) AND the caller's home
 *     tenant_slug matches this URL slug → grant data access (legacy
 *     pre-wizard tenants).
 *   - Otherwise → null. The primitives render in preview mode: shells
 *     visible, data empty. Prevents the data-bleed where CC visiting
 *     /t/sun/leads would see OASIS leads rendered in SunBiz columns.
 */
async function resolveDataTenant(
  slug: string,
  userTenantId: string | null
): Promise<string | null> {
  if (!userTenantId) return null;
  const row = await getManifestRow(slug).catch(() => null);
  if (row?.tenant_id && row.tenant_id === userTenantId) return userTenantId;
  if (!row) {
    // Code-seed manifest: fall back to slug↔tenant.custom_fields match.
    const tenant = await getTenant(userTenantId).catch(() => null);
    const userSlug = resolveClientProfileSlug(tenant || null);
    if (userSlug && userSlug.toLowerCase() === slug.toLowerCase()) {
      return userTenantId;
    }
  }
  return null;
}

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

  // /new flag: when the trailing segment is "new", the operator wants to
  // create a record for the page's entity. Strip "/new" off the path
  // and resolve the underlying page, then render the form instead of
  // the list/kanban primitive.
  const isNewForm = subPath === "new" || subPath.endsWith("/new");
  const lookupPath = isNewForm
    ? (subPath === "new" ? "" : subPath.slice(0, -("/new".length)))
    : subPath;

  // Find the matching page by exact path match. If the caller passed
  // `/t/sun/leads/new` and the manifest only has a page at "leads",
  // we still match after stripping /new. The fallback startsWith
  // handles deeper detail-page paths future phases will add.
  const pageDef =
    manifest.pages?.find((p) => p.path === lookupPath) ||
    manifest.pages?.find((p) => lookupPath !== "" && lookupPath.startsWith(`${p.path}/`)) ||
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
  const userTenantId = (profileRes.data as { tenant_id: string | null } | null)?.tenant_id ?? null;
  // Resolve which tenant_id should scope record reads. If the caller
  // isn't the owner of this manifest, dataTenantId is null and the
  // primitives render in preview mode — shells visible, data empty.
  // Closes the cross-shell data-bleed bug.
  const dataTenantId = await resolveDataTenant(normalised, userTenantId);
  const isPreview = !!userTenantId && dataTenantId === null;

  // Create-form view — the actual functional "New <entity>" button target.
  if (isNewForm && pageDef.entity) {
    const entity = (manifest.data_model || []).find((e) => e.name === pageDef.entity);
    if (!entity) {
      return (
        <div className="space-y-4 animate-fade-in">
          <PageHeader title={`New ${pageDef.label}`} subtitle="Entity not in manifest" />
          <Card>
            <div className="text-sm text-fg-muted">
              This page references entity <span className="font-mono text-fg">{pageDef.entity}</span> but
              the manifest&apos;s data_model doesn&apos;t define it. Open the AI editor to add the entity.
            </div>
          </Card>
        </div>
      );
    }
    if (isPreview) {
      // Creating records in someone else's shell would write to YOUR
      // tenant's records under their entity_type — wrong on every axis.
      return (
        <div className="space-y-4 animate-fade-in">
          <PageHeader
            title={`New ${entity.label.toLowerCase()}`}
            subtitle="Preview mode — record creation disabled"
            action={
              <Link
                href={`/t/${normalised}/${lookupPath}`}
                className="btn-secondary inline-flex items-center gap-2 !px-3 !py-1.5 text-xs"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Back
              </Link>
            }
          />
          <div className="rounded-2xl border border-amber-300/25 bg-amber-300/10 p-4 text-sm leading-relaxed text-amber-100">
            You&apos;re previewing the <strong className="text-fg">{manifest.brand.name}</strong> shell.
            Records can only be created by the tenant that owns this slug.
          </div>
        </div>
      );
    }
    return (
      <div className="space-y-4 animate-fade-in">
        <PageHeader
          title={`New ${entity.label.toLowerCase()}`}
          subtitle={`${manifest.brand.name} · ${entity.fields.length} fields`}
          action={
            <Link
              href={`/t/${normalised}/${lookupPath}`}
              className="btn-secondary inline-flex items-center gap-2 !px-3 !py-1.5 text-xs"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Back
            </Link>
          }
        />
        <ManifestRecordForm
          tenantSlug={normalised}
          entity={entity}
          backPath={lookupPath}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title={pageDef.label}
        subtitle={renderSubtitle(manifest.brand.name, pageDef)}
        action={
          <div className="flex items-center gap-2">
            {isPreview && <Tag tone="warm">preview</Tag>}
            <Tag tone="accent">{pageDef.kind}</Tag>
          </div>
        }
      />
      {isPreview && (
        <div className="rounded-2xl border border-amber-300/25 bg-amber-300/10 p-4 text-sm leading-relaxed text-amber-100">
          You&apos;re viewing the <strong className="text-fg">{manifest.brand.name}</strong> shell
          in preview mode. Your tenant doesn&apos;t own this slug, so no live records render —
          but the manifest structure, navigation, and entity schemas are exactly what a real{" "}
          <span className="font-mono">/t/{normalised}</span> tenant would see.
        </div>
      )}
      <PageBody slug={normalised} tenantId={dataTenantId} page={pageDef} manifest={manifest} />
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
