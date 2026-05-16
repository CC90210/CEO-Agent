/**
 * /api/cron-jobs/[id] — per-row PATCH / DELETE for tenant cron jobs.
 *
 * RLS-scoped via the session cookie (same model as /api/cron-jobs GET/POST).
 */

import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { resolveTenantId } from "@/lib/api-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Reuse the validators from the parent route by re-declaring inline
// (don't want to expand the export surface of /api/cron-jobs unnecessarily).
const CRON_FIELD = /^(\*|\*\/\d+|\d+(-\d+)?(\/\d+)?(,\d+(-\d+)?(\/\d+)?)*)$/;
function isValidCron(expr: string): boolean {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return false;
  return parts.every((p) => CRON_FIELD.test(p));
}

export async function PATCH(
  req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const tenantId = await resolveTenantId();
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const { id } = await ctx.params;

  let body: any;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  // Patch is intentionally narrow — only the fields operators commonly toggle.
  // Changing action_type / action_payload on an existing row is rare enough
  // that "delete and recreate" is the right UX; keeps validation simple.
  const update: Record<string, unknown> = {};
  if (typeof body.name === "string") {
    update.name = body.name.trim().slice(0, 80);
    if (!update.name) {
      return NextResponse.json({ ok: false, error: "name_cannot_be_empty" }, { status: 400 });
    }
  }
  if (typeof body.description === "string" || body.description === null) {
    update.description = body.description ? String(body.description).slice(0, 500) : null;
  }
  if (typeof body.schedule === "string") {
    if (!isValidCron(body.schedule)) {
      return NextResponse.json({ ok: false, error: "invalid_cron_expression" }, { status: 400 });
    }
    update.schedule = body.schedule.trim();
  }
  if (typeof body.enabled === "boolean") {
    update.enabled = body.enabled;
  }
  if (typeof body.agent_key === "string") {
    update.agent_key = body.agent_key.toLowerCase();
  }
  if (Object.keys(update).length === 0) {
    return NextResponse.json({ ok: false, error: "no_editable_fields_supplied" }, { status: 400 });
  }

  const db = getServiceSupabase();
  const { data, error } = await db
    .from("tenant_cron_jobs")
    .update(update)
    .eq("id", id)
    .eq("tenant_id", tenantId)
    .select()
    .maybeSingle();
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  if (!data) return NextResponse.json({ ok: false, error: "not_found_or_forbidden" }, { status: 404 });
  return NextResponse.json({ ok: true, job: data });
}

export async function DELETE(
  _req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const tenantId = await resolveTenantId();
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const { id } = await ctx.params;

  const db = getServiceSupabase();
  const { error, count } = await db
    .from("tenant_cron_jobs")
    .delete({ count: "exact" })
    .eq("id", id)
    .eq("tenant_id", tenantId);
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  if (!count) return NextResponse.json({ ok: false, error: "not_found_or_forbidden" }, { status: 404 });
  return NextResponse.json({ ok: true });
}
