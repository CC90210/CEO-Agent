import { Card, Stat, Tag } from "@/components/Card";
import { listRecords, type TenantRecord } from "@/lib/manifest/data";
import type { TenantManifest } from "@/lib/manifest/schema";

type Props = {
  manifest: TenantManifest;
  tenantId: string | null;
  /** Per-entity sample rows for the demo mode. */
  demoRowsByEntity?: Record<string, TenantRecord[]>;
};

/**
 * Default dashboard view — manifest-aware metrics over every entity in
 * the data_model. One stat tile per entity showing count + "updated
 * recently" badge. Phase 5.1 will let `page.config` specify which
 * entities to surface and which fields to aggregate (sum / avg / max).
 *
 * Empty state is genuinely informative: zero entities means the
 * manifest hasn't been populated yet, and we link the operator to the
 * AI editor to add some.
 */
export async function ManifestDashboard({ manifest, tenantId, demoRowsByEntity }: Props) {
  const entities = manifest.data_model || [];

  if (entities.length === 0) {
    return (
      <Card title="Dashboard">
        <div className="text-sm text-fg-muted leading-relaxed">
          This manifest has no data model defined yet. Open the AI editor
          and ask: <em>&quot;Add a lead entity with name, phone, and stage fields.&quot;</em>
        </div>
      </Card>
    );
  }

  // Pull counts in parallel.
  const counts = await Promise.all(
    entities.map(async (entity) => {
      if (!tenantId) {
        const rows = demoRowsByEntity?.[entity.name] || [];
        return { entity, total: rows.length, rows };
      }
      const result = await listRecords({
        tenant_id: tenantId,
        entity: entity.name,
        limit: 1,
      }).catch(() => ({ rows: [], total: 0 }));
      return { entity, total: result.total, rows: result.rows };
    })
  );

  return (
    <div className="space-y-4">
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {counts.map(({ entity, total }) => (
          <Stat
            key={entity.name}
            label={entity.label}
            value={String(total)}
            hint={`${entity.fields.length} fields`}
          />
        ))}
      </section>

      <Card
        title="Live entities"
        subtitle="Every data type defined in this tenant's manifest."
      >
        <ul className="grid gap-2 sm:grid-cols-2">
          {counts.map(({ entity, total }) => (
            <li
              key={entity.name}
              className="rounded-lg border border-bg-border bg-bg-elev/40 px-3 py-2"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm text-fg">{entity.label}</span>
                <Tag tone="neutral">{total}</Tag>
              </div>
              <div className="mt-1 flex flex-wrap gap-1 text-[10px] text-fg-dim">
                {entity.fields.slice(0, 6).map((f) => (
                  <span
                    key={f.name}
                    className="rounded-md border border-bg-border bg-bg-deep/40 px-1.5 py-0.5 font-mono"
                  >
                    {f.name}
                    {f.required ? "*" : ""}
                  </span>
                ))}
                {entity.fields.length > 6 && (
                  <span className="text-fg-faint">+{entity.fields.length - 6}</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
