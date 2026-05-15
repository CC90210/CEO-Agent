/**
 * Manifest record events — emit agent_events rows when stage / status
 * fields transition on manifest-defined records (leads, offers,
 * applications, renewals).
 *
 * Phase 2 of the SunBiz CRM build (2026-05-15). The drip-campaign engine
 * in Phase 4 subscribes to these events and fires the next sequence step.
 * Decoupling the publisher from the subscriber means cron jobs, the
 * dashboard UI, Solara's tool calls, and direct DB scripts all generate
 * the same event shape — the sequence runner consumes them uniformly.
 *
 * Event shape (agent_events row):
 *
 *   event_type:        "BRAVO_RECORD_STATUS_CHANGED"
 *   publisher_agent:   "manifest-data" (or whatever caller passes)
 *   severity:          "info"
 *   correlation_id:    tenant_id (matches lib/action-log.ts pattern so
 *                       /feed and /runs filters work without schema debt)
 *   payload:           { entity, record_id, field, from, to, data }
 *
 * `data` is the full post-update record so subscribers don't have to
 * fetch — drip variable substitution (`{{lead.first_name}}`) reads
 * straight from the payload.
 *
 * Best-effort by design — emission failures must never block the
 * underlying record update. Caller wraps in try/catch and logs.
 */

import { getServiceSupabase } from "../supabase-server";

/**
 * Fields we treat as status fields for change-detection. Keep this list
 * tight — adding a new value means the drip-trigger surface grows.
 *   "stage"  → lead.stage, offer.stage (the funding-shop progression)
 *   "status" → application.status, renewal.status
 */
export const STATUS_FIELDS = ["stage", "status"] as const;
export type StatusField = (typeof STATUS_FIELDS)[number];

export type StatusChangePublish = {
  tenantId: string;
  entity: string;
  recordId: string;
  field: StatusField;
  from: unknown;
  to: unknown;
  /** Full post-update record data — subscribers read directly. */
  data: Record<string, unknown>;
  /** Caller identifier — defaults to "manifest-data" for the records API. */
  publisher?: string;
};

/**
 * Insert a BRAVO_RECORD_STATUS_CHANGED row. Best-effort: any DB error is
 * swallowed so the caller's update path doesn't crash on a transient
 * Postgres blip. Errors are logged via console so they show up in the
 * server log without paging anyone.
 */
export async function publishStatusChange(input: StatusChangePublish): Promise<void> {
  try {
    const db = getServiceSupabase();
    await db.from("agent_events").insert({
      event_type: "BRAVO_RECORD_STATUS_CHANGED",
      publisher_agent: input.publisher || "manifest-data",
      severity: "info",
      payload: {
        entity: input.entity,
        record_id: input.recordId,
        field: input.field,
        from: input.from ?? null,
        to: input.to ?? null,
        data: input.data,
        tenant_id: input.tenantId,
      },
      correlation_id: input.tenantId,
    });
  } catch (err) {
    // Logged but not re-thrown — record updates must not depend on
    // event emission. Phase 4's sequence runner has its own retry
    // semantics if it misses a single event.
    console.error("[manifest.events.publishStatusChange]", err);
  }
}

/**
 * Diff a record's `before` and `after` data for any status-field
 * transitions. Returns one entry per changed field. Used by createRecord
 * + updateRecord to decide whether to emit a BRAVO_RECORD_STATUS_CHANGED
 * row — callers fire the event for every entry returned.
 *
 * Treats undefined-on-before as a real transition (so creating a lead
 * with stage="cold" fires `{from: null, to: "cold"}` — the drip engine
 * needs that signal to start the new-lead sequence).
 */
export function detectStatusTransitions(
  before: Record<string, unknown> | null,
  after: Record<string, unknown>,
): Array<{ field: StatusField; from: unknown; to: unknown }> {
  const out: Array<{ field: StatusField; from: unknown; to: unknown }> = [];
  for (const field of STATUS_FIELDS) {
    const next = after[field];
    if (next === undefined) continue;
    const prev = before ? before[field] : undefined;
    if (prev !== next) {
      out.push({ field, from: prev ?? null, to: next });
    }
  }
  return out;
}
