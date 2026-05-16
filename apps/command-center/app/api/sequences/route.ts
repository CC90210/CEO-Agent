/**
 * /api/sequences — operator-facing CRUD for drip sequences (Phase 4.2).
 *
 * GET  → list this tenant's sequences (RLS-scoped via the authed user).
 * POST → create a new sequence. Body:
 *          { name, description?, trigger_event?,
 *            trigger_filter, steps, enabled?, one_per_lead? }
 *
 * Per-row update / delete live at /api/sequences/[id].
 *
 * The sequence_runner.py daemon on the operator's machine reads
 * directly from drip_sequences (service-role) and ignores these
 * routes; they're operator UX only.
 */

import { NextRequest, NextResponse } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { resolveTenantId } from "@/lib/api-auth";
import { isMissingTableError, missingTablePayload } from "@/lib/api-helpers";
import {
  parseDripSteps,
  parseDripTriggerFilter,
  DripDefinitionError,
} from "@/lib/drips/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function resolveUserId(): Promise<string | null> {
  const user = await getSessionUser();
  return user?.id ?? null;
}

export async function GET() {
  const tenantId = await resolveTenantId();
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });

  const db = getServiceSupabase();
  const { data, error } = await db
    .from("drip_sequences")
    .select(
      "id, name, description, trigger_event, trigger_filter, steps, enabled, one_per_lead, created_by, created_at, updated_at",
    )
    .eq("tenant_id", tenantId)
    .order("created_at", { ascending: false });

  if (error) {
    if (isMissingTableError(error, "public.drip_sequences")) {
      return NextResponse.json(
        missingTablePayload({
          migration: "database/043_drip_sequences.sql",
          feature: "Drip Sequences",
        }),
        { status: 503 },
      );
    }
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, sequences: data || [] });
}

export async function POST(req: NextRequest) {
  const tenantId = await resolveTenantId();
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const userId = await resolveUserId();

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const name = String(body.name || "").trim();
  if (!name) {
    return NextResponse.json({ ok: false, error: "name_required" }, { status: 400 });
  }

  let steps, triggerFilter;
  try {
    steps = parseDripSteps(body.steps);
    triggerFilter = parseDripTriggerFilter(body.trigger_filter);
  } catch (err) {
    if (err instanceof DripDefinitionError) {
      return NextResponse.json(
        { ok: false, error: "invalid_definition", path: err.path, reason: err.reason },
        { status: 400 },
      );
    }
    throw err;
  }

  const triggerEvent = String(body.trigger_event || "BRAVO_RECORD_STATUS_CHANGED");

  const db = getServiceSupabase();
  const { data, error } = await db
    .from("drip_sequences")
    .insert({
      tenant_id: tenantId,
      name: name.slice(0, 200),
      description: body.description ? String(body.description).slice(0, 1000) : null,
      trigger_event: triggerEvent,
      trigger_filter: triggerFilter,
      steps,
      enabled: body.enabled !== false,
      one_per_lead: body.one_per_lead !== false,
      created_by: userId,
    })
    .select()
    .single();

  if (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, sequence: data });
}
