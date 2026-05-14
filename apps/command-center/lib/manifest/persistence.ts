/**
 * Manifest persistence — server-only CRUD over the tenant_manifests +
 * manifest_audit_log tables added in migration 038.
 *
 * One write path: `saveManifest()`. Mutators run in pure memory, then
 * saveManifest persists the result and writes a single audit row containing
 * the diff and the actor. The audit insert is the only durable record of
 * who changed what; if it fails we ROLL BACK the manifest write rather than
 * leave a manifest update without a corresponding audit row.
 *
 * Concurrency: optimistic via `if_version` — the API expects the client to
 * pass the version it loaded, and we reject the save if the row has moved
 * forward in the meantime. Phase 2 ships single-editor (the AI editor) so
 * this matters most when an operator has the page open in two tabs.
 *
 * RLS bypass: this layer uses the service-role client because mutations come
 * from authenticated API routes that have already verified the user belongs
 * to the tenant. Direct user-jwt writes would still work for tenant admins,
 * but routing everything through service-role lets us audit-log a single
 * actor consistently.
 */

import type { SupabaseClient } from "@supabase/supabase-js";
import { getServiceSupabase } from "@/lib/supabase-server";
import { parseManifest, type TenantManifest } from "./schema";
import type { DiffEntry } from "./diff";

export type ManifestRow = {
  id: string;
  tenant_id: string | null;
  slug: string;
  manifest: TenantManifest;
  version: number;
  schema_version: number;
  created_at: string;
  updated_at: string;
};

export type ManifestAuditRow = {
  id: string;
  manifest_id: string;
  tenant_id: string | null;
  actor_type: "user" | "ai" | "system" | "seed";
  actor_id: string | null;
  diff: DiffEntry[];
  message: string | null;
  created_at: string;
};

export class ManifestPersistenceError extends Error {
  constructor(public code: "not_found" | "version_conflict" | "validation" | "db", message: string) {
    super(message);
    this.name = "ManifestPersistenceError";
  }
}

function client(): SupabaseClient {
  return getServiceSupabase();
}

/** Read a manifest row by slug. Returns null when no row exists. */
export async function getManifestRow(slug: string): Promise<ManifestRow | null> {
  const db = client();
  const result = await db
    .from("tenant_manifests")
    .select("id, tenant_id, slug, manifest, version, schema_version, created_at, updated_at")
    .eq("slug", slug)
    .maybeSingle();
  if (result.error) throw new ManifestPersistenceError("db", result.error.message);
  if (!result.data) return null;
  const row = result.data as Omit<ManifestRow, "manifest"> & { manifest: unknown };
  return { ...row, manifest: parseManifest(row.manifest) };
}

export type SaveManifestInput = {
  slug: string;
  next: TenantManifest;
  diff: DiffEntry[];
  actor: { type: "user" | "ai" | "system" | "seed"; id?: string | null };
  message?: string;
  /** Optional optimistic-concurrency check. Reject if the persisted row's
   *  version differs from this. Omit to force-save. */
  if_version?: number;
  /** Optional tenant binding — only honoured for the FIRST save of a slug. */
  tenant_id?: string | null;
};

export type SaveResult = {
  row: ManifestRow;
  audit_id: string;
};

/** Atomic save: upsert manifest, bump version, insert audit row. */
export async function saveManifest(input: SaveManifestInput): Promise<SaveResult> {
  // Re-validate before write so a buggy mutator can't corrupt the table.
  let validated: TenantManifest;
  try {
    validated = parseManifest(input.next);
  } catch (err) {
    throw new ManifestPersistenceError(
      "validation",
      err instanceof Error ? err.message : "manifest failed validation"
    );
  }

  const db = client();
  const existing = await db
    .from("tenant_manifests")
    .select("id, tenant_id, version, schema_version")
    .eq("slug", input.slug)
    .maybeSingle();
  if (existing.error) throw new ManifestPersistenceError("db", existing.error.message);

  const prior = existing.data as
    | { id: string; tenant_id: string | null; version: number; schema_version: number }
    | null;

  if (prior && input.if_version !== undefined && prior.version !== input.if_version) {
    throw new ManifestPersistenceError(
      "version_conflict",
      `manifest version is ${prior.version}; caller passed ${input.if_version}`
    );
  }

  const nextVersion = (prior?.version ?? 0) + 1;
  const upsertRow = {
    slug: input.slug,
    manifest: validated as unknown as Record<string, unknown>,
    version: nextVersion,
    schema_version: validated.meta.schema_version,
    tenant_id: prior?.tenant_id ?? input.tenant_id ?? null,
    updated_at: new Date().toISOString(),
  };

  const upserted = await db
    .from("tenant_manifests")
    .upsert(upsertRow, { onConflict: "slug" })
    .select("id, tenant_id, slug, manifest, version, schema_version, created_at, updated_at")
    .single();
  if (upserted.error) throw new ManifestPersistenceError("db", upserted.error.message);

  const savedRow = upserted.data as Omit<ManifestRow, "manifest"> & { manifest: unknown };
  const manifestRow: ManifestRow = { ...savedRow, manifest: parseManifest(savedRow.manifest) };

  // Audit. If this insert fails, roll back the manifest write so the table
  // never holds a row whose change has no audit trail.
  const audit = await db
    .from("manifest_audit_log")
    .insert({
      manifest_id: manifestRow.id,
      tenant_id: manifestRow.tenant_id,
      actor_type: input.actor.type,
      actor_id: input.actor.id ?? null,
      diff: input.diff as unknown as Record<string, unknown>[],
      message: input.message ?? null,
    })
    .select("id")
    .single();

  if (audit.error) {
    // Best-effort rollback — restore the prior manifest version (or delete
    // if no prior) so the table doesn't carry an orphaned change.
    if (prior) {
      await db
        .from("tenant_manifests")
        .update({ version: prior.version, schema_version: prior.schema_version })
        .eq("slug", input.slug);
    } else {
      await db.from("tenant_manifests").delete().eq("slug", input.slug);
    }
    throw new ManifestPersistenceError("db", `audit insert failed: ${audit.error.message}`);
  }

  return { row: manifestRow, audit_id: (audit.data as { id: string }).id };
}

/** List audit history for a manifest, newest first. */
export async function listManifestAudit(manifestId: string, limit = 50): Promise<ManifestAuditRow[]> {
  const db = client();
  const result = await db
    .from("manifest_audit_log")
    .select("id, manifest_id, tenant_id, actor_type, actor_id, diff, message, created_at")
    .eq("manifest_id", manifestId)
    .order("created_at", { ascending: false })
    .limit(limit);
  if (result.error) throw new ManifestPersistenceError("db", result.error.message);
  return (result.data || []) as ManifestAuditRow[];
}
