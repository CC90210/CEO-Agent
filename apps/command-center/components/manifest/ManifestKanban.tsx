import { Plus, Inbox } from "lucide-react";
import Link from "next/link";
import { Card, Tag } from "@/components/Card";
import { listRecords, groupRecordsBy, formatFieldValue, type TenantRecord } from "@/lib/manifest/data";
import type { ManifestEntityDef, ManifestEntityField, ManifestPageDef } from "@/lib/manifest/schema";

type Props = {
  tenantSlug: string;
  tenantId: string | null;
  entity: ManifestEntityDef;
  page: ManifestPageDef;
  demoRows?: TenantRecord[];
};

/**
 * Kanban view — group entity rows by a single field (typically `stage`)
 * and render one column per value.
 *
 * 2026-05-15 rebuild: prior version rendered 5 narrow columns on wide
 * screens with 2 monospace `field: value` badges per card. Operator
 * feedback at the Adon meeting: "boxes are too small. When there are
 * thousands of leads, we need to build proper infrastructure and UI
 * mapping for the according tasks." This version:
 *
 *   - Caps at 4 columns on the widest breakpoint (xl) so each card has
 *     room to breathe and surface more fields.
 *   - Renders up to 5 entity fields per card as proper labeled lines
 *     (not monospace tags). Filters out the title + group-by fields
 *     plus internal fields like id / tenant_id.
 *   - Bigger title text and more vertical padding so high-traffic
 *     entities (leads / applications / offers) read like a real CRM
 *     card, not a chiclet.
 *   - Per-column "+ Add" link so the operator can create a record
 *     directly into a target stage instead of always landing on the
 *     default. Phase 13 will deep-link the create form to pre-populate
 *     the group_by field; today the link just opens the form.
 *
 * Column ordering uses the field's enum_values when grouping by an
 * enum field — so the columns render in business-meaningful order
 * (cold → follow_up → sent_application → ...) instead of alphabetical.
 */
export async function ManifestKanban({
  tenantSlug,
  tenantId,
  entity,
  page,
  demoRows,
}: Props) {
  // Two ways to pick the grouping key:
  //   1. page.config.compute_group_by — name of a server-side computer
  //      that derives a synthetic stage from a row's data (e.g. funded
  //      deal renewal_window: upcoming / due / overdue / renewed / lost
  //      computed from funded_at + term_months). The computed column is
  //      stamped into the row's data under the synthetic key so the
  //      regular grouping pipeline below still works unchanged.
  //   2. page.config.group_by — explicit field name on the entity.
  //   3. Fallback: first enum field, then "stage".
  // (1) wins when present so an entity without a literal `stage` column
  // can still surface a Kanban view organized by business logic.
  const computeGroupBy =
    (typeof page.config?.compute_group_by === "string" && page.config.compute_group_by) || null;
  const groupBy = computeGroupBy
    ? `__${computeGroupBy}`
    : (typeof page.config?.group_by === "string" && page.config.group_by) ||
      entity.fields.find((f) => f.type === "enum")?.name ||
      "stage";

  const rawRows = tenantId
    ? (await listRecords({
        tenant_id: tenantId,
        entity: entity.name,
        limit: 500,
      }).catch(() => ({ rows: [], total: 0 }))).rows
    : demoRows || [];

  // Stamp the synthetic group_by onto each row's data so groupRecordsBy
  // can use it. We don't mutate the caller's array — clone the rows.
  const rows = computeGroupBy
    ? rawRows.map((r) => ({
        ...r,
        data: { ...r.data, [groupBy]: computeRowGroup(computeGroupBy, r) },
      }))
    : rawRows;

  const grouped = groupRecordsBy(rows, groupBy);
  const groupingField = entity.fields.find((f) => f.name === groupBy);
  const computedOrder = computeGroupBy ? COMPUTED_GROUP_ORDER[computeGroupBy] : null;
  const orderedKeys: string[] =
    computedOrder
      ? [...computedOrder]
      : groupingField?.type === "enum" && groupingField.enum_values
        ? [...groupingField.enum_values]
        : Object.keys(grouped).sort();
  // Add any orphan keys that don't appear in the canonical order
  // (legacy values, unknown buckets, etc.).
  for (const k of Object.keys(grouped)) {
    if (!orderedKeys.includes(k)) orderedKeys.push(k);
  }

  const titleField =
    entity.fields.find((f) => f.name === "name")?.name ||
    entity.fields.find((f) => f.name === "title")?.name ||
    entity.fields.find((f) => f.name === "label")?.name ||
    entity.fields[0]?.name ||
    "id";

  // Fields the operator sees on each card. Excludes the title (already
  // the heading), the group_by (already the column), and obvious meta
  // fields. Caps at 5 so a card stays scannable; the rest live on the
  // record detail page.
  const cardFields: ManifestEntityField[] = entity.fields
    .filter(
      (f) =>
        f.name !== titleField &&
        f.name !== groupBy &&
        !["id", "tenant_id", "created_at", "updated_at"].includes(f.name)
    )
    .slice(0, 5);

  return (
    <Card
      title={page.label || entity.label}
      subtitle={`${rows.length} ${entity.label.toLowerCase()}${rows.length === 1 ? "" : "s"} · grouped by ${humanize(groupBy)}`}
      action={
        <Link
          href={`/t/${tenantSlug}/${page.path}/new`}
          className="btn-send inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
        >
          <Plus className="h-3.5 w-3.5" />
          New {entity.label.toLowerCase()}
        </Link>
      }
    >
      <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {orderedKeys.map((key) => {
          const items = grouped[key] || [];
          return (
            <section
              key={key}
              className="rounded-xl border border-bg-border bg-bg-elev/40 p-4 min-h-[220px] flex flex-col"
            >
              <header className="flex items-center justify-between mb-3 pb-2 border-b border-bg-border">
                <Tag tone="accent">{key === "(unset)" ? "no stage" : humanize(key)}</Tag>
                <span className="text-[10px] text-fg-dim font-mono">
                  {items.length} card{items.length === 1 ? "" : "s"}
                </span>
              </header>
              <ul className="space-y-2.5 flex-1">
                {items.map((row) => (
                  <li
                    key={row.id}
                    className="rounded-lg border border-bg-border bg-bg-deep/60 p-3 hover:border-accent/40 transition-colors"
                  >
                    <div className="font-bold text-sm text-fg break-words">
                      {formatFieldValue(row.data[titleField]) || "Untitled"}
                    </div>
                    {cardFields.length > 0 && (
                      <dl className="mt-2 space-y-1 text-[11px]">
                        {cardFields
                          .filter((f) => row.data[f.name] !== undefined && row.data[f.name] !== null && row.data[f.name] !== "")
                          .map((f) => (
                            <div key={f.name} className="flex items-start gap-2">
                              <dt className="text-fg-dim shrink-0 min-w-[80px]">
                                {humanize(f.name)}
                              </dt>
                              <dd className="text-fg-muted break-words">
                                {formatFieldValue(row.data[f.name])}
                              </dd>
                            </div>
                          ))}
                      </dl>
                    )}
                  </li>
                ))}
                {items.length === 0 && (
                  <li className="flex flex-col items-center justify-center text-fg-faint text-[11px] py-6">
                    <Inbox className="h-4 w-4 mb-1" />
                    <span className="italic">empty</span>
                  </li>
                )}
              </ul>
            </section>
          );
        })}
      </div>
    </Card>
  );
}

/** snake_case_or_lowercase → "Title Case" for human-friendly labels.
 *  Mirrors the helper in ManifestRecordForm — kept inline rather than
 *  shared to avoid a circular import; both are 3-line functions. */
function humanize(name: string): string {
  if (!name) return "";
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Canonical column order for each compute_group_by mode. Keep this
 * registry in sync with the matching branch in computeRowGroup —
 * adding a bucket here without producing it from the computer would
 * leave an always-empty column; producing a bucket the computer
 * emits but isn't listed here pushes it to the end as an orphan
 * (still visible, just at the end).
 */
const COMPUTED_GROUP_ORDER: Record<string, string[]> = {
  renewal_window: ["upcoming", "due", "overdue", "renewed", "lost"],
};

/**
 * Derive a synthetic group_by value for a row.
 *
 * `renewal_window` — for `funded_deal` records. Reads `funded_at`
 * (date) + `term_months` (number) and computes how far the deal is
 * into its term as of now. Buckets per the meeting decision:
 *
 *   - upcoming: 0–40% through. Renewal sequence hasn't opened yet.
 *   - due: 40–50%. Renewal window is open; drip should be enrolling.
 *   - overdue: 50–100% with no renewal record. Solara missed it.
 *   - renewed: deal carries `renewed: true` or status === "renewed".
 *     (TBD: also detect from a related renewal record once Phase 15
 *     creates them — for now we trust an operator-set flag.)
 *   - lost: deal carries `lost: true` or status === "lost".
 *
 * Missing `funded_at` or `term_months` → "(unset)" so the row still
 * renders in a clearly-flagged column instead of throwing.
 */
function computeRowGroup(mode: string, row: { data: Record<string, unknown> }): string {
  if (mode === "renewal_window") {
    const d = row.data;
    if (d.renewed === true || d.status === "renewed") return "renewed";
    if (d.lost === true || d.status === "lost") return "lost";
    const fundedAt = typeof d.funded_at === "string" ? d.funded_at : null;
    const termMonths = typeof d.term_months === "number" ? d.term_months : null;
    if (!fundedAt || !termMonths || termMonths <= 0) return "(unset)";
    const fundedMs = Date.parse(fundedAt);
    if (Number.isNaN(fundedMs)) return "(unset)";
    const termMs = termMonths * 30 * 24 * 60 * 60 * 1000;
    const elapsed = (Date.now() - fundedMs) / termMs;
    if (elapsed < 0.4) return "upcoming";
    if (elapsed < 0.5) return "due";
    if (elapsed < 1.0) return "overdue";
    // Past the term entirely with no renewal recorded — also overdue
    // from a sales perspective (the deal lapsed without us pitching).
    return "overdue";
  }
  return "(unset)";
}
