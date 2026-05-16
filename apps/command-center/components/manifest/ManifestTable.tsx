import { Card, EmptyState, Tag } from "@/components/Card";
import { listRecords, formatFieldValue, type TenantRecord } from "@/lib/manifest/data";
import type { ManifestEntityDef, ManifestEntityField, ManifestPageDef } from "@/lib/manifest/schema";
import { Plus, ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { humanize } from "@/lib/manifest/humanize";

/** Same value formatter the kanban uses — currency / months / FICO /
 *  factor-rate / date heuristics so tables read operator-naturally
 *  instead of dumping raw JSON numbers. Inline here (not shared in a
 *  helper file yet) because both call sites are server components and
 *  we'd want a single export once we add a third caller. */
function formatTableCell(
  name: string,
  value: unknown,
  fieldDef?: ManifestEntityField,
): string {
  if (value === undefined || value === null || value === "") return "—";
  const n = name.toLowerCase();
  if (
    typeof value === "number" &&
    (n.includes("amount") || n.includes("revenue") || n.includes("funded") ||
      n === "price" || n.includes("commission") || n === "fee" || n === "cost")
  ) {
    return "$" + value.toLocaleString("en-US", { maximumFractionDigits: 0 });
  }
  if (typeof value === "number" && n.includes("months")) return `${value} mo`;
  if (typeof value === "number" && (n === "fico" || n === "score" || n.includes("fico_floor"))) {
    return value.toString();
  }
  if (typeof value === "number" && (n === "factor_rate" || n === "rate")) {
    return value.toFixed(2);
  }
  if (
    fieldDef?.type === "date" || fieldDef?.type === "datetime" ||
    n.endsWith("_at") || n.endsWith("_date")
  ) {
    if (typeof value === "string" && value) {
      const d = new Date(value);
      if (!Number.isNaN(d.getTime())) {
        return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
      }
    }
  }
  return formatFieldValue(value);
}

type Props = {
  tenantSlug: string;
  tenantId: string | null;
  entity: ManifestEntityDef;
  page: ManifestPageDef;
  /** Optional sample rows to show when tenantId is null (demo mode). */
  demoRows?: TenantRecord[];
  canCreate?: boolean;
};

/**
 * Server-rendered table view for a manifest entity. Renders every field
 * in the entity's schema as a column, plus created_at. Empty cells show
 * an em-dash via formatFieldValue. Enum fields render as Tags for the
 * visual cue.
 *
 * Read-only for v1. The Phase 5.1 inline editor / "Create record" modal
 * lands once we settle on the form-field UX. POST/PATCH/DELETE endpoints
 * already exist at /api/manifest/<slug>/records/<entity>.
 */
export async function ManifestTable({
  tenantSlug,
  tenantId,
  entity,
  page,
  demoRows,
  canCreate,
}: Props) {
  // Read either from DB (real tenant) or the supplied demo set. When
  // tenantId is null AND no demoRows were provided we still render the
  // empty state so the page surface is consistent.
  const rows = tenantId
    ? (await listRecords({
        tenant_id: tenantId,
        entity: entity.name,
        limit: 200,
      }).catch(() => ({ rows: [], total: 0 }))).rows
    : demoRows || [];

  // The columns the table renders. Reads `config.columns` if the
  // manifest specifies a subset; otherwise renders every field.
  const configCols = Array.isArray(page.config?.columns)
    ? (page.config!.columns as string[]).filter((c) =>
        entity.fields.some((f) => f.name === c)
      )
    : null;
  const columns = configCols && configCols.length > 0
    ? entity.fields.filter((f) => configCols.includes(f.name))
    : entity.fields;

  return (
    <Card
      title={page.label || entity.label}
      subtitle={`${rows.length} ${entity.label.toLowerCase()}${rows.length === 1 ? "" : "s"}`}
      noPadding
      action={
        canCreate ? (
          <Link
            href={`/t/${tenantSlug}/${page.path}/new`}
            className="btn-send inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
          >
            <Plus className="h-3.5 w-3.5" />
            New {entity.label.toLowerCase()}
          </Link>
        ) : undefined
      }
    >
      {rows.length === 0 ? (
        <div className="p-5">
          <EmptyState
            message={
              tenantId
                ? `No ${entity.label.toLowerCase()} records yet. Use the AI editor to add seed data or hook up an integration.`
                : `This is a preview of how the ${entity.label.toLowerCase()} table will render once your tenant is provisioned.`
            }
          />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-bg-elev/60 border-b border-bg-border">
              <tr>
                {columns.map((col) => (
                  <th
                    key={col.name}
                    className="px-4 py-2.5 text-left text-[10px] uppercase tracking-[0.14em] font-bold text-fg-dim whitespace-nowrap"
                  >
                    {humanize(col.name)}
                  </th>
                ))}
                <th className="px-4 py-2.5 text-left text-[10px] uppercase tracking-[0.14em] font-bold text-fg-dim">
                  Updated
                </th>
                <th className="px-2 py-2.5 text-right">
                  <span className="sr-only">Open</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-bg-border">
              {rows.map((row) => (
                <tr key={row.id} className="group hover:bg-bg-elev/40 transition-colors">
                  {columns.map((col) => {
                    const v = row.data[col.name];
                    if (col.type === "enum" && typeof v === "string" && v) {
                      return (
                        <td key={col.name} className="px-4 py-2.5">
                          <Tag tone="accent">{humanize(v)}</Tag>
                        </td>
                      );
                    }
                    if (col.type === "boolean") {
                      return (
                        <td key={col.name} className="px-4 py-2.5 text-fg-muted">
                          {v ? "✓" : "—"}
                        </td>
                      );
                    }
                    return (
                      <td
                        key={col.name}
                        className="px-4 py-2.5 text-fg-muted whitespace-nowrap"
                      >
                        {formatTableCell(col.name, v, col)}
                      </td>
                    );
                  })}
                  <td className="px-4 py-2.5 text-xs text-fg-dim whitespace-nowrap">
                    {new Date(row.updated_at).toLocaleDateString()}
                  </td>
                  <td className="px-2 py-2.5 text-right">
                    <Link
                      href={`/t/${tenantSlug}/${page.path}/${row.id}`}
                      className="inline-flex items-center gap-1 text-fg-dim hover:text-accent text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Open record"
                    >
                      Open
                      <ArrowUpRight className="h-3 w-3" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
