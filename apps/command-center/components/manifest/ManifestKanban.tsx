import { Plus, Inbox } from "lucide-react";
import Link from "next/link";
import { Card, Tag } from "@/components/Card";
import { listRecords, groupRecordsBy, formatFieldValue, type TenantRecord } from "@/lib/manifest/data";
import type { ManifestEntityDef, ManifestEntityField, ManifestPageDef } from "@/lib/manifest/schema";
import { OfferCardActions } from "./OfferCardActions";
import { ApplicationCardActions } from "./ApplicationCardActions";
import { humanize } from "@/lib/manifest/humanize";

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

  // Per-entity title resolution. For domain entities (offer / lead /
  // application / funded_deal / renewal / lender) the "best" title field
  // is rarely fields[0] — it's a domain-specific header like the
  // amount-formatted-as-currency, the business name, etc. The
  // ENTITY_TITLE_PRIORITY registry below lists the preferred title
  // fields for each entity in priority order; first one that exists
  // on the entity wins. Falls back to the previous heuristic (name /
  // title / label / first field) for unrecognized entities.
  const titleField =
    ENTITY_TITLE_PRIORITY[entity.name]?.find((n) =>
      entity.fields.find((f) => f.name === n),
    ) ||
    entity.fields.find((f) => f.name === "name")?.name ||
    entity.fields.find((f) => f.name === "title")?.name ||
    entity.fields.find((f) => f.name === "label")?.name ||
    entity.fields[0]?.name ||
    "id";

  // Every operator-relevant field on the card — no slice cap. The
  // operator entered these values for a reason; hiding them on a
  // card-density argument is the wrong tradeoff (per 2026-05-16
  // feedback: "they should be stacked on top of each other. Just
  // look at proper data storage and how it should be displayed").
  // Excludes the title (already the heading), the group_by (already
  // the column), and obvious meta / FK-only fields the operator
  // doesn't read at a glance.
  const cardFields: ManifestEntityField[] = entity.fields.filter(
    (f) =>
      f.name !== titleField &&
      f.name !== groupBy &&
      !["id", "tenant_id", "created_at", "updated_at"].includes(f.name),
  );

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
      <div className="grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {orderedKeys.map((key) => {
          const items = grouped[key] || [];
          return (
            <section
              key={key}
              // Fixed height keeps the grid balanced — long columns
              // scroll internally instead of stretching the row. Sticky
              // header so the column label + count stay visible while
              // scrolling. 520px ≈ 6-7 compact cards visible before
              // scroll kicks in, which matches Trello's feel.
              className="rounded-xl border border-bg-border bg-bg-elev/40 flex flex-col max-h-[520px]"
            >
              <header className="sticky top-0 z-10 flex items-center justify-between px-3 py-2 border-b border-bg-border bg-bg-elev/95 backdrop-blur rounded-t-xl">
                <Tag tone="accent">{key === "(unset)" ? "no stage" : humanize(key)}</Tag>
                <span className="text-[10px] text-fg-dim font-mono">
                  {items.length}
                </span>
              </header>
              <ul className="flex-1 overflow-y-auto p-2 space-y-2">
                {items.map((row) => (
                  <KanbanCard
                    key={row.id}
                    row={row}
                    titleField={titleField}
                    cardFields={cardFields}
                    entity={entity}
                    tenantSlug={tenantSlug}
                    pagePath={page.path}
                  />
                ))}
                {items.length === 0 && (
                  <li className="flex flex-col items-center justify-center text-fg-faint text-[10px] py-8">
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

/**
 * KanbanCard — single record summary inside a Kanban column.
 *
 * Click target: navigates to /t/<slug>/<page.path>/<row.id> which the
 * catch-all router renders as the record-detail edit form. Per-entity
 * actions (Accept/Decline for offers, Recommended Lenders for
 * applications) stay below the link so the operator can act without
 * leaving the Kanban for routine moves.
 *
 * Field rendering: every entity field with a value shows up on the
 * card as a labeled `dt/dd` row, currency / percent / date formatted
 * appropriately. Pre-2026-05-16 the card capped at 2 preview fields
 * to keep dense columns scannable; operator feedback flipped that
 * decision — "they should be stacked on top of each other. Just look
 * at proper data storage and how it should be displayed." Density is
 * now achieved via column scroll, not by hiding data the operator
 * already entered.
 */
function KanbanCard({
  row,
  titleField,
  cardFields,
  entity,
  tenantSlug,
  pagePath,
}: {
  row: TenantRecord;
  titleField: string;
  cardFields: ManifestEntityField[];
  entity: ManifestEntityDef;
  tenantSlug: string;
  pagePath: string;
}) {
  // Every field with a non-empty value. Operator entered these for a
  // reason; show them all. Empty fields silently drop so a half-
  // filled lead doesn't show "Notes: —" filler.
  const populatedFields = cardFields.filter(
    (f) =>
      row.data[f.name] !== undefined &&
      row.data[f.name] !== null &&
      row.data[f.name] !== "",
  );

  // Domain-aware title rendering. The title field (e.g. amount for
  // offer) gets formatted with the appropriate unit so the card's
  // headline reads operator-naturally — "$3,435,435" instead of the
  // raw "3435435".
  const titleFieldDef = entity.fields.find((f) => f.name === titleField);
  const titleValue = formatCardField(titleField, row.data[titleField], titleFieldDef);

  return (
    <li className="rounded-md border border-bg-border bg-bg-deep/60 hover:border-accent/40 hover:bg-bg-deep/80 transition-colors">
      <Link
        href={`/t/${tenantSlug}/${pagePath}/${row.id}`}
        className="block px-3 py-2.5"
      >
        <div className="font-bold text-[14px] text-fg break-words leading-snug">
          {titleValue || "Untitled"}
        </div>
        {populatedFields.length > 0 && (
          <dl className="mt-2 space-y-0.5 text-[11px]">
            {populatedFields.map((f) => (
              <div key={f.name} className="flex items-baseline gap-2">
                <dt className="text-fg-dim shrink-0 min-w-[88px]">
                  {humanize(f.name)}
                </dt>
                <dd className="text-fg-muted break-words font-mono">
                  {formatCardField(f.name, row.data[f.name], f)}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </Link>
      {/* Per-entity inline actions live outside the Link so clicking
          Accept / Decline / Recommended lenders doesn't also fire the
          card-level navigation. */}
      {entity.name === "offer" && typeof row.data.stage === "string" && (
        <div className="px-3 pb-2.5">
          <OfferCardActions
            tenantSlug={tenantSlug}
            offerId={row.id}
            stage={row.data.stage}
          />
        </div>
      )}
      {entity.name === "application" && (
        <div className="px-3 pb-2.5">
          <ApplicationCardActions applicationId={row.id} />
        </div>
      )}
    </li>
  );
}

/**
 * Per-entity title field priorities. First match wins. For domain
 * entities the "best" title isn't the manifest's fields[0] — it's a
 * domain-specific header (amount for offer; business_name for
 * application; etc.). Unlisted entities fall through to the generic
 * heuristic in the caller.
 */
const ENTITY_TITLE_PRIORITY: Record<string, string[]> = {
  lead: ["name", "contact_name", "business_name", "first_name", "email", "phone"],
  application: ["business_name", "company", "name", "contact_name", "lead_id"],
  offer: ["amount", "lender_id", "lead_id"],
  funded_deal: ["amount_funded", "lender_id", "lead_id"],
  renewal: ["funded_deal_id", "due_date"],
  lender: ["name", "company"],
  commission: ["amount", "name"],
  task: ["title", "name"],
};

/**
 * Format a card field value with currency / percent / date / number
 * units based on field name heuristics + the manifest type. The unit
 * inference is intentionally name-based because the manifest field
 * type ("number") doesn't carry semantics (is 1.35 a factor rate or
 * a count?). For SunBiz the field names are stable, so this works.
 *
 * Examples:
 *   amount / amount_funded / max_funded_amount / min_monthly_revenue
 *     → "$3,435,435"
 *   factor_rate / rate → "1.35"  (plain number — factor rates aren't %)
 *   fico / fico_floor / score → "650"
 *   *_at / *_date → "May 16, 2026"
 *   *_months → "12 mo"
 *   default → formatFieldValue (em-dash for empty, JSON for objects)
 */
function formatCardField(
  name: string,
  value: unknown,
  fieldDef?: ManifestEntityField,
): string {
  if (value === undefined || value === null || value === "") return "—";
  const n = name.toLowerCase();

  // Currency — explicit currency-ish field names. Operator-facing
  // numbers worth showing as money: amount, amount_funded, revenue,
  // funded, price, commission, fee.
  if (
    typeof value === "number" &&
    (n.includes("amount") ||
      n.includes("revenue") ||
      n.includes("funded") ||
      n === "price" ||
      n.includes("commission") ||
      n === "fee" ||
      n === "cost")
  ) {
    return "$" + value.toLocaleString("en-US", { maximumFractionDigits: 0 });
  }

  // Months — operator-friendly suffix.
  if (typeof value === "number" && n.includes("months")) {
    return `${value} mo`;
  }

  // FICO / score — integer, no decimals.
  if (typeof value === "number" && (n === "fico" || n.endsWith("_fico") || n === "score" || n.includes("fico_floor"))) {
    return value.toString();
  }

  // Factor rate — 2-decimal display.
  if (typeof value === "number" && (n === "factor_rate" || n === "rate")) {
    return value.toFixed(2);
  }

  // Date / datetime fields — manifest type wins, falls back to name.
  if (
    fieldDef?.type === "date" ||
    fieldDef?.type === "datetime" ||
    n.endsWith("_at") ||
    n.endsWith("_date")
  ) {
    if (typeof value === "string" && value) {
      const d = new Date(value);
      if (!Number.isNaN(d.getTime())) {
        return d.toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
        });
      }
    }
  }

  return formatFieldValue(value);
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
