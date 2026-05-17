import { notFound } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { ManifestTable } from "@/components/manifest/ManifestTable";
import { ManifestKanban } from "@/components/manifest/ManifestKanban";
import { ManifestMarkdown } from "@/components/manifest/ManifestMarkdown";
import { ManifestDashboard } from "@/components/manifest/ManifestDashboard";
import { ManifestRecordForm } from "@/components/manifest/ManifestRecordForm";
import { ManifestReasoning } from "@/components/manifest/ManifestReasoning";
import { LeadsImportClient } from "@/components/leads/LeadsImportClient";
import { LeadTimelinePanel } from "@/components/leads/LeadTimelinePanel";
import { humanize } from "@/lib/manifest/humanize";
import { getRecord } from "@/lib/manifest/data";
import { Card, PageHeader, Tag } from "@/components/Card";
import { getManifest, manifestExists } from "@/lib/manifest/loader";
import { resolveDataTenant } from "@/lib/manifest/tenant-scope";
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
  searchParams,
}: {
  params: Promise<{ slug: string; path: string[] }>;
  searchParams?: Promise<{ view?: string }>;
}) {
  const { slug, path } = await params;
  const sp = (await searchParams) || {};
  const viewOverride: "table" | "kanban" | null =
    sp.view === "table" ? "table" : sp.view === "kanban" ? "kanban" : null;
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

  // Record-detail path: `/t/sun/leads/<uuid>`. Detected when the last
  // segment is a UUID and stripping it lands on a real page path.
  // Renders the ManifestRecordForm in edit mode with pre-populated
  // values — gives operators a clickable drill-down from Kanban cards
  // without building a separate detail-view primitive.
  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const subPathSegs = subPath.split("/").filter(Boolean);
  const lastSeg = subPathSegs[subPathSegs.length - 1] || "";
  const isRecordDetail = !isNewForm && UUID_RE.test(lastSeg);
  const recordDetailId = isRecordDetail ? lastSeg : null;
  const recordDetailPath = isRecordDetail
    ? subPathSegs.slice(0, -1).join("/")
    : null;

  // Find the matching page by exact path match. If the caller passed
  // `/t/sun/leads/new` and the manifest only has a page at "leads",
  // we still match after stripping /new. Same logic handles
  // record-detail paths (`/t/sun/leads/<uuid>` matches the leads page).
  const lookupForPage = recordDetailPath ?? lookupPath;
  const pageDef =
    manifest.pages?.find((p) => p.path === lookupForPage) ||
    manifest.pages?.find((p) => lookupForPage !== "" && lookupForPage.startsWith(`${p.path}/`)) ||
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

  // Record-detail view — opened when an operator clicks a Kanban card or
  // a row in a manifest table. Reuses ManifestRecordForm in edit mode so
  // every field on the record is visible + editable on one screen
  // without building a separate detail primitive.
  if (recordDetailId && pageDef.entity) {
    const entity = (manifest.data_model || []).find((e) => e.name === pageDef.entity);
    if (entity && dataTenantId) {
      const record = await getRecord({
        tenant_id: dataTenantId,
        entity: entity.name,
        id: recordDetailId,
      }).catch(() => null);
      if (!record) {
        return (
          <div className="space-y-4 animate-fade-in">
            <PageHeader
              title="Record not found"
              subtitle={`No ${entity.label.toLowerCase()} with id ${recordDetailId.slice(0, 8)}…`}
              action={
                <Link
                  href={`/t/${normalised}/${recordDetailPath}`}
                  className="btn-secondary inline-flex items-center gap-2 !px-3 !py-1.5 text-xs"
                >
                  <ArrowLeft className="h-3.5 w-3.5" />
                  Back to {pageDef.label.toLowerCase()}
                </Link>
              }
            />
          </div>
        );
      }
      // Resolve a sensible display title from the record's data —
      // tries `name` / `title` / `business_name` in that order, then
      // falls back to the short id.
      const title =
        (typeof record.data.name === "string" && record.data.name) ||
        (typeof record.data.title === "string" && record.data.title) ||
        (typeof record.data.business_name === "string" && record.data.business_name) ||
        `${entity.label} ${recordDetailId.slice(0, 8)}`;
      return (
        <div className="space-y-4 animate-fade-in">
          <PageHeader
            title={title}
            subtitle={`${entity.label} · ${entity.fields.length} fields`}
            action={
              <Link
                href={`/t/${normalised}/${recordDetailPath}`}
                className="btn-secondary inline-flex items-center gap-2 !px-3 !py-1.5 text-xs"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Back to {pageDef.label.toLowerCase()}
              </Link>
            }
          />
          {(() => {
            // Missing-info banner — surfaces Phase 20 classifier output
            // at the top of the lead detail so the operator sees what's
            // owed before reading any other field. Only on the `lead`
            // entity; other entities don't carry missing_info.
            if (entity.name !== "lead") return null;
            const mi = (record.data as Record<string, unknown>)?.missing_info;
            const items = Array.isArray(mi)
              ? (mi as unknown[]).filter((x): x is string => typeof x === "string")
              : [];
            if (items.length === 0) return null;
            return (
              <div className="rounded-2xl border border-red-500/40 bg-red-500/10 p-4 text-sm leading-relaxed text-red-200">
                <div className="font-semibold text-red-100 mb-1">
                  🔴 Lender asked for additional documentation
                </div>
                <div className="font-mono text-[12.5px]">
                  Missing: {items.join(", ")}
                </div>
                <div className="text-[11.5px] text-red-200/80 mt-1.5">
                  Upload the matching document via the lead&apos;s docs panel (queued) or forward the lender thread to the
                  classifier inbox once received.
                </div>
              </div>
            );
          })()}
          <ManifestRecordForm
            tenantSlug={normalised}
            entity={entity}
            backPath={recordDetailPath!}
            initial={record.data}
            editId={recordDetailId}
          />
          {entity.name === "lead" && (
            <LeadTimelinePanel leadId={recordDetailId} />
          )}
        </div>
      );
    }
  }

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
        // Only the preview-mode tag is operator-relevant here. The
        // page.kind tag ("kanban" / "table" / "form") used to live in
        // this slot but was a leak of internal manifest vocabulary
        // into the operator UI — operators asked "what does kanban
        // mean? is that a signal reference?" The view toggle below
        // the header already exposes the kanban-vs-table choice
        // visually, so the tag was redundant on top of being confusing.
        action={isPreview ? <Tag tone="warm">preview</Tag> : null}
      />
      {isPreview && (
        <div className="rounded-2xl border border-amber-300/25 bg-amber-300/10 p-4 text-sm leading-relaxed text-amber-100">
          You&apos;re viewing the <strong className="text-fg">{manifest.brand.name}</strong> shell
          in preview mode. Your tenant doesn&apos;t own this slug, so no live records render —
          but the manifest structure, navigation, and entity schemas are exactly what a real{" "}
          <span className="font-mono">/t/{normalised}</span> tenant would see.
        </div>
      )}
      <PageBody slug={normalised} tenantId={dataTenantId} page={pageDef} manifest={manifest} viewOverride={viewOverride} />
    </div>
  );
}

function renderSubtitle(brand: string, page: ManifestPageDef): string {
  switch (page.kind) {
    case "dashboard": return `${brand} · live snapshot`;
    case "table": return page.entity ? `${humanizeEntity(page.entity)}` : "Table view";
    case "kanban": return page.entity ? `${humanizeEntity(page.entity)} by stage` : "Kanban view";
    case "form": return page.entity ? `Form for ${humanizeEntity(page.entity)}` : "Form";
    case "markdown": return "Reference page";
    case "reasoning": return "Click an action to send it straight to chat.";
    case "import": return "Paste a CSV or drop a file. Duplicate-check is automatic.";
    case "pipeline": return "Lead Pipeline and Opportunity Pipeline — Salesforce-parity overview.";
    default: return brand;
  }
}

function humanizeEntity(name: string): string {
  return humanize(name) + "s";
}

async function PageBody({
  slug,
  tenantId,
  page,
  manifest,
  viewOverride,
}: {
  slug: string;
  tenantId: string | null;
  page: ManifestPageDef;
  manifest: Awaited<ReturnType<typeof getManifest>>;
  viewOverride: "table" | "kanban" | null;
}) {
  switch (page.kind) {
    case "markdown":
      return <ManifestMarkdown page={page} />;
    case "reasoning":
      return <ManifestReasoning manifest={manifest} tenantSlug={slug} />;
    case "dashboard":
      return <ManifestDashboard manifest={manifest} tenantId={tenantId} />;
    case "import":
      // The import page reads the operator's tenant_id server-side via
      // /api/leads/import; no extra props needed. Tenant_id check
      // happens inside the API route so a viewer in preview-mode can't
      // accidentally bulk-insert into someone else's leads table.
      return <LeadsImportClient />;
    case "pipeline": {
      // Two-pipeline superview — Lead Pipeline stacked over Opportunity
      // Pipeline. Salesforce-replacement view per the 2026-05-16 meeting.
      // Each section reuses ManifestKanban; the only thing this kind
      // contributes is the layout shell + the "graduation" caption between
      // them so operators see the submitted→offered handoff clearly.
      const cfg = (page.config || {}) as { lead_entity?: string; opportunity_entity?: string };
      const leadName = cfg.lead_entity || "lead";
      const oppName = cfg.opportunity_entity || "offer";
      const leadEntity = (manifest.data_model || []).find((e) => e.name === leadName);
      const oppEntity = (manifest.data_model || []).find((e) => e.name === oppName);
      if (!leadEntity || !oppEntity) {
        return (
          <div className="rounded-2xl border border-amber-300/25 bg-amber-300/10 p-5 text-sm text-amber-100 leading-relaxed">
            Pipeline superview references entities <code>{leadName}</code> and <code>{oppName}</code> — at least one
            isn&apos;t defined in the manifest&apos;s <code>data_model</code>.
          </div>
        );
      }
      const leadPage: ManifestPageDef = { path: page.path + "/leads", label: "Leads", kind: "kanban", entity: leadName, config: { group_by: "stage" } };
      const oppPage: ManifestPageDef = { path: page.path + "/offers", label: "Offers", kind: "kanban", entity: oppName, config: { group_by: "stage" } };
      return (
        <div className="space-y-6">
          <div>
            <div className="flex items-baseline justify-between mb-3">
              <h2 className="text-sm uppercase tracking-wider text-fg-muted">Lead Pipeline</h2>
              <Link href={`/t/${slug}/leads`} className="text-xs text-fg-muted hover:text-fg">Open full board →</Link>
            </div>
            <ManifestKanban tenantSlug={slug} tenantId={tenantId} entity={leadEntity} page={leadPage} />
          </div>
          <div className="flex items-center gap-3 py-2">
            <div className="h-px flex-1 bg-border" />
            <div className="text-xs uppercase tracking-wider text-fg-muted">↓ Application submitted · Opportunity opens ↓</div>
            <div className="h-px flex-1 bg-border" />
          </div>
          <div>
            <div className="flex items-baseline justify-between mb-3">
              <h2 className="text-sm uppercase tracking-wider text-fg-muted">Opportunity Pipeline</h2>
              <Link href={`/t/${slug}/offers`} className="text-xs text-fg-muted hover:text-fg">Open full board →</Link>
            </div>
            <ManifestKanban tenantSlug={slug} tenantId={tenantId} entity={oppEntity} page={oppPage} />
          </div>
        </div>
      );
    }
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
      // `view` query param overrides the manifest's default kind for
      // table-vs-kanban entities. Lets the operator flip between a
      // dense sortable table and the stage-Kanban without an admin
      // changing the manifest. Form pages don't have a "kanban"
      // alternative, so the override only applies to kanban/table.
      const effectiveKind: "kanban" | "table" =
        page.kind === "form"
          ? "table"
          : viewOverride
            ? viewOverride
            : (page.kind as "kanban" | "table");

      // Toggle bar — rendered above the body so the operator can flip
      // views without leaving the page. Only meaningful when the entity
      // has a group-by-able field (otherwise the Kanban renders as one
      // big column and the toggle is pointless).
      const supportsKanban =
        page.kind === "kanban" ||
        entity.fields.some((f) => f.type === "enum") ||
        entity.fields.some((f) => f.name === "stage" || f.name === "status");

      const toggle = supportsKanban ? (
        <ViewToggle slug={slug} path={page.path} current={effectiveKind} />
      ) : null;

      if (effectiveKind === "kanban") {
        return (
          <>
            {toggle}
            <ManifestKanban tenantSlug={slug} tenantId={tenantId} entity={entity} page={page} />
          </>
        );
      }
      return (
        <>
          {toggle}
          <ManifestTable tenantSlug={slug} tenantId={tenantId} entity={entity} page={page} canCreate />
        </>
      );
    }
    default:
      return (
        <div className="rounded-2xl border border-bg-border bg-bg-elev/40 p-5 text-sm text-fg-muted">
          Unknown page kind: <span className="font-mono">{(page as ManifestPageDef).kind}</span>
        </div>
      );
  }
}

/**
 * ViewToggle — small two-button toolbar above the body that lets the
 * operator switch a manifest page between Kanban and Table views.
 *
 * Why server-side links instead of a client toggle: this whole route is
 * a server component, and the underlying ManifestKanban / ManifestTable
 * both fetch their own data. A `?view=` URL param keeps the bookmark /
 * back-button behavior natural (e.g. an operator can email a teammate
 * a link to "/t/sun/leads?view=table" and they land on the same view).
 */
function ViewToggle({
  slug,
  path,
  current,
}: {
  slug: string;
  path: string;
  current: "kanban" | "table";
}) {
  return (
    <div className="flex items-center gap-1 mb-3">
      <Link
        href={`/t/${slug}/${path}?view=kanban`}
        className={`text-[10px] uppercase tracking-wider px-2.5 py-1 rounded-md border ${
          current === "kanban"
            ? "border-accent/50 bg-accent/10 text-accent"
            : "border-bg-border bg-bg-elev/40 text-fg-muted hover:text-fg"
        }`}
      >
        Kanban
      </Link>
      <Link
        href={`/t/${slug}/${path}?view=table`}
        className={`text-[10px] uppercase tracking-wider px-2.5 py-1 rounded-md border ${
          current === "table"
            ? "border-accent/50 bg-accent/10 text-accent"
            : "border-bg-border bg-bg-elev/40 text-fg-muted hover:text-fg"
        }`}
      >
        Table
      </Link>
    </div>
  );
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
