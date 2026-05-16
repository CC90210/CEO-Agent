/**
 * /api/sequences/[id]/state — visibility into in-flight sequence_state rows.
 *
 * GET → list every (lead, step) row for this sequence. Used by the
 *       /sequences/[id] detail page to show operators the in-flight
 *       enrollments + their status / scheduled_for / errors.
 *
 * The Python daemon writes sequence_state rows directly with the
 * service-role connection; this route is read-only operator UX.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { resolveTenantId } from "@/lib/api-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const tenantId = await resolveTenantId();
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const { id } = await ctx.params;

  // Optional ?status=scheduled,sent,failed filter so the UI can show
  // active vs completed views separately.
  const statusParam = req.nextUrl.searchParams.get("status") || "";
  const statuses = statusParam
    .split(",")
    .map((s) => s.trim())
    .filter((s) => ["scheduled", "sent", "failed", "cancelled", "skipped"].includes(s));

  const db = getServiceSupabase();
  let q = db
    .from("sequence_state")
    .select(
      "id, lead_id, step_index, scheduled_for, status, attempt_count, last_attempt_at, last_error, created_at",
    )
    .eq("sequence_id", id)
    .eq("tenant_id", tenantId)
    .order("created_at", { ascending: false })
    .limit(200);
  if (statuses.length > 0) {
    q = q.in("status", statuses);
  }
  const { data, error } = await q;
  if (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, rows: data || [] });
}
