/**
 * Tenant records CRUD — the data plane behind manifest-driven pages.
 *
 * Every tenant's user-visible data (leads, applications, offers, etc.)
 * lives in `tenant_records` as JSONB wide-rows, keyed by (tenant_id,
 * entity_type). The manifest's `data_model[]` declares the field schema
 * but the table itself is schemaless — fields can be added or removed
 * via the AI editor without a Postgres migration.
 *
 * Tradeoffs:
 *   - PRO: schema changes are instant; multi-tenant indexing is uniform;
 *     RLS is one policy that covers every entity.
 *   - CON: no foreign keys at the DB layer (we enforce in code); JSONB
 *     queries can be slower than native columns at very large row counts
 *     (>1M per tenant). Acceptable until any single tenant proves that
 *     wrong.
 *
 * All exports are server-only. RLS on tenant_records already restricts
 * to current_tenant_id(), so even if a route forgets the explicit
 * tenant filter, Postgres won't return other tenants' rows. Service-role
 * paths still pass tenant_id explicitly because that's the auth-checked
 * value from the route handler — never the value the client requested.
 */

import { getServiceSupabase } from "@/lib/supabase-server";
import { detectStatusTransitions, publishStatusChange } from "./events";

export class RecordsError extends Error {
  constructor(
    public code: "validation" | "not_found" | "forbidden" | "db",
    message: string
  ) {
    super(message);
    this.name = "RecordsError";
  }
}

export type TenantRecord = {
  id: string;
  tenant_id: string;
  entity_type: string;
  data: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

const ENTITY_RE = /^[a-z][a-z0-9_]{0,62}$/;

function assertEntity(entity: string): void {
  if (!ENTITY_RE.test(entity)) {
    throw new RecordsError(
      "validation",
      `entity name must match /^[a-z][a-z0-9_]{0,62}$/, got "${entity}"`
    );
  }
}

export type ListRecordsInput = {
  tenant_id: string;
  entity: string;
  /** Sort by data->>field or created_at/updated_at. Prefix with `-` for descending. */
  sort?: string;
  limit?: number;
  offset?: number;
  /** Equality filters on top-level data keys. Values are coerced to strings. */
  where?: Record<string, string | number | boolean | null>;
};

export type ListRecordsResult = {
  rows: TenantRecord[];
  total: number;
};

export async function listRecords(input: ListRecordsInput): Promise<ListRecordsResult> {
  assertEntity(input.entity);
  const limit = Math.max(1, Math.min(input.limit ?? 100, 500));
  const offset = Math.max(0, input.offset ?? 0);
  const db = getServiceSupabase();

  let q = db
    .from("tenant_records")
    .select("id, tenant_id, entity_type, data, created_at, updated_at", { count: "exact" })
    .eq("tenant_id", input.tenant_id)
    .eq("entity_type", input.entity);

  // Apply data-shape filters. We coerce values to strings because JSONB
  // top-level equality through PostgREST's `data->>key.eq.value` syntax
  // returns text-typed values.
  if (input.where) {
    for (const [k, v] of Object.entries(input.where)) {
      if (v === null) {
        q = q.is(`data->>${k}`, null);
      } else {
        q = q.eq(`data->>${k}`, String(v));
      }
    }
  }

  if (input.sort) {
    const desc = input.sort.startsWith("-");
    const col = (desc ? input.sort.slice(1) : input.sort).trim();
    if (col === "created_at" || col === "updated_at") {
      q = q.order(col, { ascending: !desc });
    } else {
      // Sort by a JSONB field via PostgREST's `data->>field` ordering.
      q = q.order(`data->>${col}`, { ascending: !desc });
    }
  } else {
    q = q.order("updated_at", { ascending: false });
  }

  q = q.range(offset, offset + limit - 1);

  const result = await q;
  if (result.error) throw new RecordsError("db", result.error.message);
  return {
    rows: (result.data || []) as TenantRecord[],
    total: result.count || 0,
  };
}

export async function getRecord(input: { tenant_id: string; entity: string; id: string }): Promise<TenantRecord | null> {
  assertEntity(input.entity);
  const db = getServiceSupabase();
  const result = await db
    .from("tenant_records")
    .select("id, tenant_id, entity_type, data, created_at, updated_at")
    .eq("tenant_id", input.tenant_id)
    .eq("entity_type", input.entity)
    .eq("id", input.id)
    .maybeSingle();
  if (result.error) throw new RecordsError("db", result.error.message);
  return (result.data || null) as TenantRecord | null;
}

export type CreateRecordInput = {
  tenant_id: string;
  entity: string;
  data: Record<string, unknown>;
};

export async function createRecord(input: CreateRecordInput): Promise<TenantRecord> {
  assertEntity(input.entity);
  if (!input.data || typeof input.data !== "object") {
    throw new RecordsError("validation", "data must be an object");
  }
  const db = getServiceSupabase();
  const result = await db
    .from("tenant_records")
    .insert({
      tenant_id: input.tenant_id,
      entity_type: input.entity,
      data: input.data,
    })
    .select("id, tenant_id, entity_type, data, created_at, updated_at")
    .single();
  if (result.error) throw new RecordsError("db", result.error.message);
  const row = result.data as TenantRecord;

  // Phase 2: emit BRAVO_RECORD_STATUS_CHANGED for the initial stage/status
  // value so the drip engine (Phase 4) can fire the "new lead" sequence
  // when a lead lands with stage="cold". detectStatusTransitions treats
  // before=null as a real transition for this case.
  const transitions = detectStatusTransitions(null, row.data);
  for (const t of transitions) {
    await publishStatusChange({
      tenantId: input.tenant_id,
      entity: input.entity,
      recordId: row.id,
      field: t.field,
      from: t.from,
      to: t.to,
      data: row.data,
    });
  }

  return row;
}

export type UpdateRecordInput = {
  tenant_id: string;
  entity: string;
  id: string;
  patch: Record<string, unknown>;
};

export async function updateRecord(input: UpdateRecordInput): Promise<TenantRecord> {
  assertEntity(input.entity);
  const existing = await getRecord({ tenant_id: input.tenant_id, entity: input.entity, id: input.id });
  if (!existing) throw new RecordsError("not_found", "record not found");
  const merged = { ...existing.data, ...input.patch };
  const db = getServiceSupabase();
  const result = await db
    .from("tenant_records")
    .update({ data: merged, updated_at: new Date().toISOString() })
    .eq("id", input.id)
    .eq("tenant_id", input.tenant_id)
    .eq("entity_type", input.entity)
    .select("id, tenant_id, entity_type, data, created_at, updated_at")
    .single();
  if (result.error) throw new RecordsError("db", result.error.message);
  const row = result.data as TenantRecord;

  // Phase 2: emit BRAVO_RECORD_STATUS_CHANGED on every stage/status
  // transition. Drip engine (Phase 4) subscribes to fire next sequence
  // step; /feed surfaces them as live signals. Diffing against the
  // pre-update row's data — so a patch that doesn't touch stage/status
  // produces zero events (the loop body never runs).
  const transitions = detectStatusTransitions(existing.data, row.data);
  for (const t of transitions) {
    await publishStatusChange({
      tenantId: input.tenant_id,
      entity: input.entity,
      recordId: row.id,
      field: t.field,
      from: t.from,
      to: t.to,
      data: row.data,
    });
  }

  return row;
}

export async function deleteRecord(input: { tenant_id: string; entity: string; id: string }): Promise<void> {
  assertEntity(input.entity);
  const db = getServiceSupabase();
  // Round 3 R3-9: ask for an exact row count so a no-op delete (id
  // doesn't match, or tenant scope is wrong) surfaces as a "not_found"
  // error instead of silently returning ok. Mirrors the pattern from
  // commit fcec21d that closed the same gap on /api/sequences and
  // /api/forms — the catch-all manifest DELETE route was missed.
  const result = await db
    .from("tenant_records")
    .delete({ count: "exact" })
    .eq("id", input.id)
    .eq("tenant_id", input.tenant_id)
    .eq("entity_type", input.entity);
  if (result.error) throw new RecordsError("db", result.error.message);
  if (!result.count) {
    throw new RecordsError("not_found", "record not found or not in tenant scope");
  }
}

/** Convenience — group records by a top-level data key for kanban views. */
export function groupRecordsBy(
  rows: TenantRecord[],
  field: string
): Record<string, TenantRecord[]> {
  const out: Record<string, TenantRecord[]> = {};
  for (const row of rows) {
    const key = String(row.data[field] ?? "(unset)");
    if (!out[key]) out[key] = [];
    out[key].push(row);
  }
  return out;
}

/**
 * Render a JSONB value as a display string for the table cells. Keeps the
 * table primitive simple — it never has to deserialise complex shapes.
 */
export function formatFieldValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(formatFieldValue).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
