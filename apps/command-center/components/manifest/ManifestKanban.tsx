import { Card, Tag } from "@/components/Card";
import { listRecords, groupRecordsBy, formatFieldValue, type TenantRecord } from "@/lib/manifest/data";
import type { ManifestEntityDef, ManifestPageDef } from "@/lib/manifest/schema";

type Props = {
  tenantSlug: string;
  tenantId: string | null;
  entity: ManifestEntityDef;
  page: ManifestPageDef;
  demoRows?: TenantRecord[];
};

/**
 * Kanban view — group entity rows by a single field (typically `stage`)
 * and render one column per value. The grouping field comes from
 * `page.config.group_by`; falls back to the first `enum` field, or
 * "stage" if no enum exists.
 *
 * Column ordering uses the field's enum_values when grouping by an
 * enum field — so the columns render in business-meaningful order
 * (new → qualified → won) instead of alphabetical.
 */
export async function ManifestKanban({
  tenantSlug,
  tenantId,
  entity,
  page,
  demoRows,
}: Props) {
  const groupBy =
    (typeof page.config?.group_by === "string" && page.config.group_by) ||
    entity.fields.find((f) => f.type === "enum")?.name ||
    "stage";

  const rows = tenantId
    ? (await listRecords({
        tenant_id: tenantId,
        entity: entity.name,
        limit: 500,
      }).catch(() => ({ rows: [], total: 0 }))).rows
    : demoRows || [];

  const grouped = groupRecordsBy(rows, groupBy);
  const groupingField = entity.fields.find((f) => f.name === groupBy);
  const orderedKeys: string[] =
    groupingField?.type === "enum" && groupingField.enum_values
      ? [...groupingField.enum_values]
      : Object.keys(grouped).sort();
  // Add any orphan keys that don't appear in the enum (legacy values, etc.)
  for (const k of Object.keys(grouped)) {
    if (!orderedKeys.includes(k)) orderedKeys.push(k);
  }

  const titleField =
    entity.fields.find((f) => f.name === "name")?.name ||
    entity.fields.find((f) => f.name === "title")?.name ||
    entity.fields.find((f) => f.name === "label")?.name ||
    entity.fields[0]?.name ||
    "id";

  return (
    <Card
      title={page.label || entity.label}
      subtitle={`${rows.length} ${entity.label.toLowerCase()}${rows.length === 1 ? "" : "s"} · grouped by ${groupBy}`}
    >
      <div className="grid auto-cols-[minmax(260px,1fr)] grid-flow-col gap-3 overflow-x-auto pb-2">
        {orderedKeys.map((key) => {
          const items = grouped[key] || [];
          return (
            <section
              key={key}
              className="rounded-xl border border-bg-border bg-bg-elev/40 p-3 min-h-[180px]"
            >
              <div className="flex items-center justify-between mb-2">
                <Tag tone="accent">{key === "(unset)" ? "no stage" : key}</Tag>
                <span className="text-[10px] text-fg-dim font-mono">{items.length}</span>
              </div>
              <ul className="space-y-2">
                {items.map((row) => (
                  <li
                    key={row.id}
                    className="rounded-lg border border-bg-border bg-bg-deep/60 px-3 py-2 hover:border-accent/40 transition-colors"
                  >
                    <div className="font-medium text-sm text-fg truncate">
                      {formatFieldValue(row.data[titleField]) || "Untitled"}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-fg-dim">
                      {entity.fields
                        .filter(
                          (f) =>
                            f.name !== titleField &&
                            f.name !== groupBy &&
                            row.data[f.name] !== undefined
                        )
                        .slice(0, 2)
                        .map((f) => (
                          <span
                            key={f.name}
                            className="rounded-md border border-bg-border bg-bg-elev/60 px-1.5 py-0.5 font-mono"
                          >
                            {f.name}: {formatFieldValue(row.data[f.name])}
                          </span>
                        ))}
                    </div>
                  </li>
                ))}
                {items.length === 0 && (
                  <li className="text-[11px] text-fg-faint italic px-1 py-2">
                    empty
                  </li>
                )}
              </ul>
            </section>
          );
        })}
      </div>
      {/* Reserved for the Phase 5.1 "Add card" affordance per column —
          will write through POST /api/manifest/${tenantSlug}/records/${entity.name}. */}
    </Card>
  );
}
