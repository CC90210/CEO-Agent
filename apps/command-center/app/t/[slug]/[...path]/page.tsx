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
import { StagePipelineBar } from "@/components/manifest/StagePipelineBar";
import { PipelineSearchableTable } from "@/components/manifest/PipelineSearchableTable";
import { PIPELINE_COLUMNS, formatPipelineCell, pipelineLinkBase } from "@/lib/pipeline-display";
import { LEAD_PIPELINE_STAGES, OPPORTUNITY_PIPELINE_STAGES, findStage } from "@/lib/sunbiz-stage-meta";
import { humanize } from "@/lib/manifest/humanize";
import { getRecord, listRecords } from "@/lib/manifest/data";
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
  searchParams?: Promise<{ view?: string; stage?: string; opp_stage?: string }>;
}) {
  const { slug, path } = await params;
  const sp = (await searchParams) || {};
  const viewOverride: "table" | "kanban" | null =
    sp.view === "table" ? "table" : sp.view === "kanban" ? "kanban" : null;
  const stageFilter = typeof sp.stage === "string" && sp.stage ? sp.stage : null;
  const oppStageFilter = typeof sp.opp_stage === "string" && sp.opp_stage ? sp.opp_stage : null;
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
                  Auto-detected from the lender&apos;s reply. Clear an item by editing this lead&apos;s
                  <span className="font-mono"> missing_info</span> field once the doc is sent.
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
      <PageBody
        slug={normalised}
        tenantId={dataTenantId}
        page={pageDef}
        manifest={manifest}
        viewOverride={viewOverride}
        stageFilter={stageFilter}
        oppStageFilter={oppStageFilter}
      />
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
    case "pipeline_entity": return page.entity ? `${humanizeEntity(page.entity)} by stage` : "Pipeline";
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
  stageFilter,
  oppStageFilter,
}: {
  slug: string;
  tenantId: string | null;
  page: ManifestPageDef;
  manifest: Awaited<ReturnType<typeof getManifest>>;
  viewOverride: "table" | "kanban" | null;
  stageFilter: string | null;
  oppStageFilter: string | null;
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
      // Stacked superview — Lead Pipeline above Opportunity Pipeline.
      // Each section has its own chevron bar + filtered table. Filter
      // params are independent so both bars work in parallel.
      return (
        <PipelineSuperview
          slug={slug}
          tenantId={tenantId}
          page={page}
          manifest={manifest}
          stageFilter={stageFilter}
          oppStageFilter={oppStageFilter}
        />
      );
    }
    case "pipeline_entity": {
      // Single-entity chevron pipeline — used by /leads (entity=lead) and
      // /applications (entity=application). Reads `stage_field` from
      // page.config (defaults to "stage"; applications use "status").
      // Filter via ?stage=<key>.
      const cfg = (page.config || {}) as { stage_field?: string };
      const stageField = cfg.stage_field || "stage";
      const entityName = page.entity || "";
      const entity = (manifest.data_model || []).find((e) => e.name === entityName);
      if (!entity) {
        return (
          <div className="rounded-2xl border border-amber-300/25 bg-amber-300/10 p-5 text-sm text-amber-100 leading-relaxed">
            Pipeline entity <code>{entityName}</code> isn&apos;t defined in this manifest.
          </div>
        );
      }
      return (
        <SingleEntityPipeline
          slug={slug}
          tenantId={tenantId}
          page={page}
          entity={entity}
          stageField={stageField}
          stageFilter={stageFilter}
        />
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

/**
 * PipelineSuperview — Salesforce-replacement two-pipeline page renderer.
 *
 * Renders the Lead Pipeline chevron bar + filtered record table, then
 * the Opportunity Pipeline chevron bar + filtered record table. Each
 * chevron is clickable; clicking applies a URL filter (stage= or
 * opp_stage=) so the operator can drill into one stage without losing
 * sight of the other pipeline.
 *
 * Per-stage record counts are pre-computed server-side from listRecords
 * so the chevrons render with badges showing "how many in this stage."
 */
async function PipelineSuperview({
  slug,
  tenantId,
  page,
  manifest,
  stageFilter,
  oppStageFilter,
}: {
  slug: string;
  tenantId: string | null;
  page: ManifestPageDef;
  manifest: Awaited<ReturnType<typeof getManifest>>;
  stageFilter: string | null;
  oppStageFilter: string | null;
}) {
  const cfg = (page.config || {}) as { lead_entity?: string; opportunity_entity?: string };
  const leadName = cfg.lead_entity || "lead";
  const oppName = cfg.opportunity_entity || "application";
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

  // Resolve the stage field per entity. lead uses `stage`; application
  // uses `status` (Salesforce naming kept on the application entity);
  // offer also uses `stage`. Lookup keys on the row's data jsonb.
  const leadStageField = "stage";
  const oppStageField = oppName === "application" ? "status" : "stage";

  // Fetch every record for each pipeline once; partition client-side
  // into stage buckets. Cheaper than N round-trips (one per stage) and
  // gives us accurate counts for the chevron badges in the same query.
  const [leadRowsRes, oppRowsRes] = await Promise.all([
    tenantId
      ? listRecords({ tenant_id: tenantId, entity: leadName, limit: 500 }).catch(() => ({ rows: [], total: 0 }))
      : Promise.resolve({ rows: [], total: 0 }),
    tenantId
      ? listRecords({ tenant_id: tenantId, entity: oppName, limit: 500 }).catch(() => ({ rows: [], total: 0 }))
      : Promise.resolve({ rows: [], total: 0 }),
  ]);

  const leadCounts: Record<string, number> = {};
  for (const r of leadRowsRes.rows) {
    const s = String((r.data as Record<string, unknown>)[leadStageField] || "");
    if (s) leadCounts[s] = (leadCounts[s] || 0) + 1;
  }
  const oppCounts: Record<string, number> = {};
  for (const r of oppRowsRes.rows) {
    const s = String((r.data as Record<string, unknown>)[oppStageField] || "");
    if (s) oppCounts[s] = (oppCounts[s] || 0) + 1;
  }

  const leadVisible = stageFilter
    ? leadRowsRes.rows.filter((r) => String((r.data as Record<string, unknown>)[leadStageField] || "") === stageFilter)
    : leadRowsRes.rows;
  const oppVisible = oppStageFilter
    ? oppRowsRes.rows.filter((r) => String((r.data as Record<string, unknown>)[oppStageField] || "") === oppStageFilter)
    : oppRowsRes.rows;

  return (
    <div className="space-y-10">
      <section className="space-y-4">
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="text-lg font-bold text-fg">Lead Pipeline</h2>
          <div className="text-[11px] text-fg-dim font-mono">
            {stageFilter ? `${leadVisible.length} in ${findStage("lead", stageFilter)?.label || stageFilter}` : `${leadRowsRes.rows.length} total`}
          </div>
        </div>
        <StagePipelineBar
          stages={LEAD_PIPELINE_STAGES}
          activeKey={stageFilter}
          basePath={`/t/${slug}/${page.path}`}
          counts={leadCounts}
        />
        <PipelineRecordList
          slug={slug}
          entityName={leadName}
          stageField={leadStageField}
          rows={leadVisible}
          activeStageLabel={stageFilter ? findStage("lead", stageFilter)?.label || stageFilter : "All stages"}
        />
      </section>

      <section className="space-y-4">
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="text-lg font-bold text-fg">Opportunity Pipeline</h2>
          <div className="text-[11px] text-fg-dim font-mono">
            {oppStageFilter ? `${oppVisible.length} in ${findStage(oppName, oppStageFilter)?.label || oppStageFilter}` : `${oppRowsRes.rows.length} total`}
          </div>
        </div>
        <StagePipelineBar
          stages={OPPORTUNITY_PIPELINE_STAGES}
          activeKey={oppStageFilter}
          basePath={`/t/${slug}/${page.path}`}
          counts={oppCounts}
          paramName="opp_stage"
        />
        <PipelineRecordList
          slug={slug}
          entityName={oppName}
          stageField={oppStageField}
          rows={oppVisible}
          activeStageLabel={oppStageFilter ? findStage(oppName, oppStageFilter)?.label || oppStageFilter : "All opportunities"}
        />
      </section>
    </div>
  );
}

/**
 * PipelineRecordList — compact table rendered below each pipeline bar.
 *
 * Salesforce shows a tabular layout under each pipeline stage filter.
 * We do the same — name + key contact fields + stage tag. Empty state
 * renders explicitly so a fresh tenant doesn't see a blank container.
 */
function PipelineRecordList({
  slug,
  entityName,
  stageField,
  rows,
  activeStageLabel,
}: {
  slug: string;
  entityName: string;
  stageField: string;
  rows: { id: string; data: Record<string, unknown> }[];
  activeStageLabel: string;
}) {
  if (rows.length === 0) {
    return (
      <div className="rounded-2xl border border-bg-border bg-bg-deep/40 p-6 text-center text-sm text-fg-dim italic">
        No records in {activeStageLabel}.
      </div>
    );
  }

  // Display columns + link base resolved from the shared
  // lib/pipeline-display module — single source of truth, shared with
  // PipelineSearchableTable. Adding a column once propagates to both
  // the searchable variant and the unsearchable superview-side list.
  const cols = PIPELINE_COLUMNS[entityName] || [];
  const linkBase = pipelineLinkBase(slug, entityName);

  return (
    <div className="overflow-x-auto rounded-2xl border border-bg-border bg-bg-deep/30">
      <table className="w-full text-[12.5px]">
        <thead>
          <tr className="text-left text-fg-dim border-b border-bg-border">
            {cols.map((c) => (
              <th key={c.key} className="px-3 py-2 font-medium">{c.label}</th>
            ))}
            <th className="px-3 py-2 font-medium">Stage</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const stage = String(r.data[stageField] || "");
            const stageMeta = findStage(entityName, stage);
            return (
              <tr key={r.id} className="border-b border-bg-border/40 last:border-b-0 hover:bg-bg-elev/30">
                {cols.map((c, idx) => (
                  <td key={c.key} className={`px-3 py-2 ${idx === 0 ? "font-medium text-fg" : "text-fg-muted"}`}>
                    {idx === 0 ? (
                      <Link href={`${linkBase}/${r.id}`} className="hover:underline">
                        {formatPipelineCell(r.data[c.key], c.key)}
                      </Link>
                    ) : (
                      formatPipelineCell(r.data[c.key], c.key)
                    )}
                  </td>
                ))}
                <td className="px-3 py-2">
                  {stageMeta ? (
                    <span
                      className="inline-block px-2 py-0.5 rounded text-[11px] font-semibold"
                      style={{ background: stageMeta.bg, color: stageMeta.fg }}
                    >
                      {stageMeta.label}
                    </span>
                  ) : (
                    <span className="text-fg-dim font-mono">{stage || "—"}</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * SingleEntityPipeline — the chevron bar + filtered table for ONE entity.
 *
 * Used by /leads (lead entity, Lead Pipeline) and /applications
 * (application entity, Opportunity Pipeline). Mirrors what each section
 * of the PipelineSuperview renders, just standalone with one entity's
 * chevron chain.
 */
async function SingleEntityPipeline({
  slug,
  tenantId,
  page,
  entity,
  stageField,
  stageFilter,
}: {
  slug: string;
  tenantId: string | null;
  page: ManifestPageDef;
  entity: { name: string; label: string; fields: { name: string; type: string }[] };
  stageField: string;
  stageFilter: string | null;
}) {
  const stages = entity.name === "lead"
    ? LEAD_PIPELINE_STAGES
    : entity.name === "application" || entity.name === "offer"
      ? OPPORTUNITY_PIPELINE_STAGES
      : [];

  if (stages.length === 0) {
    return (
      <div className="rounded-2xl border border-amber-300/25 bg-amber-300/10 p-5 text-sm text-amber-100 leading-relaxed">
        No Salesforce-parity pipeline stages registered for entity <code>{entity.name}</code>.
      </div>
    );
  }

  const rowsRes = tenantId
    ? await listRecords({ tenant_id: tenantId, entity: entity.name, limit: 500 }).catch(() => ({ rows: [], total: 0 }))
    : { rows: [], total: 0 };

  const counts: Record<string, number> = {};
  for (const r of rowsRes.rows) {
    const s = String((r.data as Record<string, unknown>)[stageField] || "");
    if (s) counts[s] = (counts[s] || 0) + 1;
  }

  const visible = stageFilter
    ? rowsRes.rows.filter((r) => String((r.data as Record<string, unknown>)[stageField] || "") === stageFilter)
    : rowsRes.rows;

  const activeLabel = stageFilter
    ? findStage(entity.name, stageFilter)?.label || stageFilter
    : `All ${entity.label.toLowerCase()}s`;

  // Resolve display columns + link base from the shared
  // lib/pipeline-display module so adding a column or tweaking a
  // formatter is one edit, not three (was duplicated across
  // PipelineRecordList and this component prior to 2026-05-17 cleanup).
  const localCols = PIPELINE_COLUMNS[entity.name] || [];
  const localLinkBase = pipelineLinkBase(slug, entity.name);
  // Build a plain stage_key -> StageMeta map for the client component.
  // Cannot pass `findStage` directly because functions are not
  // serializable across the Next.js server/client boundary — that's
  // what crashed every pipeline page on the prior deploy.
  const stageMap: Record<string, typeof stages[number]> = Object.fromEntries(
    stages.map((s) => [s.key, s]),
  );

  return (
    <div className="space-y-4">
      <div className="text-[11px] text-fg-dim font-mono">
        {stageFilter ? `${visible.length} in ${activeLabel}` : `${rowsRes.rows.length} total`}
      </div>
      <StagePipelineBar
        stages={stages}
        activeKey={stageFilter}
        basePath={`/t/${slug}/${page.path}`}
        counts={counts}
      />
      <PipelineSearchableTable
        slug={slug}
        entityName={entity.name}
        entityLabel={entity.label}
        stageField={stageField}
        rows={visible}
        columns={localCols}
        stageMap={stageMap}
        linkBase={localLinkBase}
        activeStageLabel={activeLabel}
      />
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
