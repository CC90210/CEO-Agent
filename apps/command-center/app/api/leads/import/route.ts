/**
 * POST /api/leads/import — bulk-insert leads from a parsed CSV (or any
 * JSON array of {name,email,phone,company,...}). Dedupes against
 * existing leads in the same tenant by email or phone (case-insensitive
 * for email, digits-only for phone) so re-uploads don't create
 * duplicates — the most common operator complaint with naive CSV
 * importers.
 *
 * Operator flow:
 *   1. /import page parses the operator's CSV/paste client-side and
 *      shows a preview.
 *   2. Operator confirms → POSTs { rows: [...], dedup_by: [...] } here.
 *   3. We resolve the operator's tenant, fetch existing leads for that
 *      tenant (capped — see DEDUP_LOOKBACK), build a Set of normalized
 *      keys, then for each incoming row decide insert / skip-duplicate
 *      / skip-malformed.
 *   4. Surviving rows go through a single `.insert([...])` call so we
 *      pay one round-trip even on a 1k-lead upload.
 *
 * Response:
 *   { ok, inserted: N, skipped_duplicate: M, skipped_malformed: K,
 *     duplicate_keys: [], errors: [] }
 *
 * Hard caps: 5,000 rows per request (anything bigger should be a
 * background job — Phase 13). Operator gets a clean 413 with a hint
 * if they exceed it.
 */

import { NextRequest, NextResponse } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_ROWS = 5_000;
// Existing-leads window for dedup. We don't scan every lead the tenant
// has ever owned (could be 100k); we scan the most recent
// DEDUP_LOOKBACK by updated_at. Beyond that the dedup is the next
// daily nurture-sweep's problem.
const DEDUP_LOOKBACK = 20_000;

type IncomingRow = {
  name?: string | null;
  email?: string | null;
  phone?: string | null;
  company?: string | null;
  source?: string | null;
  notes?: string | null;
  tags?: string[] | null;
};

function normEmail(s: string | null | undefined): string | null {
  const e = (s || "").trim().toLowerCase();
  return e || null;
}

function normPhone(s: string | null | undefined): string | null {
  const digits = (s || "").replace(/\D+/g, "");
  // 11-digit US numbers starting with "1" → 10-digit form so
  // "+1 555 123 4567" matches "5551234567" matches "(555) 123-4567".
  if (digits.length === 11 && digits.startsWith("1")) return digits.slice(1);
  return digits || null;
}

export async function POST(req: NextRequest) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const db = getServiceSupabase();
  const profileRes = await db
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const tenantId = (profileRes.data as { tenant_id: string | null } | null)?.tenant_id ?? null;
  if (!tenantId) return NextResponse.json({ ok: false, error: "no_tenant" }, { status: 401 });

  let body: { rows?: IncomingRow[]; dedup_by?: string[]; default_source?: string };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const rows = Array.isArray(body.rows) ? body.rows : [];
  if (rows.length === 0) {
    return NextResponse.json({ ok: false, error: "no_rows" }, { status: 400 });
  }
  if (rows.length > MAX_ROWS) {
    return NextResponse.json(
      {
        ok: false,
        error: "too_many_rows",
        message: `Max ${MAX_ROWS.toLocaleString()} rows per import. Split the file.`,
      },
      { status: 413 },
    );
  }

  const dedupBy = Array.isArray(body.dedup_by) && body.dedup_by.length > 0
    ? body.dedup_by.filter((k): k is string => typeof k === "string")
    : ["email", "phone"];
  const defaultSource = body.default_source || "csv_import";

  // Dedup against the SAME table we're writing to. Imports go to
  // tenant_records (entity_type='lead') so they show up on the
  // manifest-driven Kanban + drill-down detail routes that every
  // tenant's UI consumes. Pre-2026-05-15 we wrote to a dedicated
  // public.leads table, but that diverged from the manifest reads
  // and silently hid imported leads from the operator's view.
  //
  // tenant_records.data is JSONB; the dedup query extracts the
  // email + phone fields server-side via the ->> operator. We pull
  // a denormalized projection (record id stays in id, email/phone
  // come out as top-level columns) so the dedup logic stays
  // shape-identical to the prior dedicated-table version.
  const existingRes = await db
    .from("tenant_records")
    .select("data")
    .eq("tenant_id", tenantId)
    .eq("entity_type", "lead")
    .order("updated_at", { ascending: false })
    .limit(DEDUP_LOOKBACK);
  if (existingRes.error) {
    return NextResponse.json(
      { ok: false, error: "dedup_lookup_failed", detail: existingRes.error.message },
      { status: 500 },
    );
  }
  const existingEmails = new Set<string>();
  const existingPhones = new Set<string>();
  for (const r of (existingRes.data || []) as Array<{ data: Record<string, unknown> | null }>) {
    const d = r.data || {};
    const e = normEmail(typeof d.email === "string" ? d.email : null);
    if (e) existingEmails.add(e);
    const p = normPhone(typeof d.phone === "string" ? d.phone : null);
    if (p) existingPhones.add(p);
  }

  // tenant_records insert shape — each row carries tenant_id +
  // entity_type ('lead') + the full lead profile in data JSONB. The
  // manifest's data_model.lead.fields determines which keys land
  // where; we send the operator-visible columns + a few sensible
  // defaults (stage='imported', score=0, status='new' for back-compat
  // with anything still reading the legacy status field).
  const toInsert: Array<{
    tenant_id: string;
    entity_type: string;
    data: Record<string, unknown>;
  }> = [];
  let skippedDuplicate = 0;
  let skippedMalformed = 0;
  const duplicateKeys: string[] = [];
  const errors: string[] = [];

  // Track within-batch duplicates too — if the operator's CSV has the
  // same email twice we only insert once.
  const seenEmails = new Set<string>();
  const seenPhones = new Set<string>();

  for (const [i, raw] of rows.entries()) {
    const name = (raw.name || "").trim().slice(0, 200) || null;
    const email = normEmail(raw.email);
    const phone = normPhone(raw.phone);
    const company = (raw.company || "").trim().slice(0, 200) || null;
    const notes = (raw.notes || "").trim().slice(0, 2000) || null;
    const source = (raw.source || "").trim().slice(0, 64) || defaultSource;
    const tags = Array.isArray(raw.tags) ? raw.tags.filter((t) => typeof t === "string").slice(0, 12) : null;

    // Need at least one identifier — otherwise we can't dedup the
    // import on its second run and the row is functionally useless.
    if (!email && !phone && !name) {
      skippedMalformed += 1;
      errors.push(`row ${i + 1}: no name, email, or phone`);
      continue;
    }

    let isDupe = false;
    let dupeKey = "";
    if (dedupBy.includes("email") && email) {
      if (existingEmails.has(email) || seenEmails.has(email)) {
        isDupe = true;
        dupeKey = email;
      }
    }
    if (!isDupe && dedupBy.includes("phone") && phone) {
      if (existingPhones.has(phone) || seenPhones.has(phone)) {
        isDupe = true;
        dupeKey = phone;
      }
    }
    if (isDupe) {
      skippedDuplicate += 1;
      if (duplicateKeys.length < 50) duplicateKeys.push(dupeKey);
      continue;
    }

    if (email) seenEmails.add(email);
    if (phone) seenPhones.add(phone);

    toInsert.push({
      tenant_id: tenantId,
      entity_type: "lead",
      data: {
        name,
        email,
        phone,
        company,
        source,
        notes,
        ...(tags && tags.length > 0 ? { tags } : {}),
        // Salesforce-parity Lead Pipeline starts at 'imported' (per
        // SUN_SEED, 2026-05-17 rework). Bulk-imported leads land here;
        // operator promotes to hot_lead / follow_up / etc.
        stage: "imported",
        // Legacy status field — kept for backward-compat with any
        // code path still reading status. Phase 2 reconciled
        // stage as the canonical pipeline field; remove this once
        // every reader migrates.
        status: "new",
        score: 0,
      },
    });
  }

  let inserted = 0;
  if (toInsert.length > 0) {
    // Single bulk insert into tenant_records. The kanban + table
    // primitives read from this same table via listRecords() so
    // imported leads appear on /t/<slug>/leads immediately.
    const insRes = await db.from("tenant_records").insert(toInsert).select("id");
    if (insRes.error) {
      return NextResponse.json(
        {
          ok: false,
          error: "insert_failed",
          detail: insRes.error.message,
          // Surface the partial counts so the operator knows how many
          // were skipped vs failed BEFORE the insert exploded.
          would_have_inserted: toInsert.length,
          skipped_duplicate: skippedDuplicate,
          skipped_malformed: skippedMalformed,
        },
        { status: 500 },
      );
    }
    inserted = (insRes.data || []).length;
  }

  return NextResponse.json({
    ok: true,
    inserted,
    skipped_duplicate: skippedDuplicate,
    skipped_malformed: skippedMalformed,
    duplicate_keys: duplicateKeys,
    errors: errors.slice(0, 20),
  });
}
