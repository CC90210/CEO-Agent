/**
 * POST /api/applications/[id]/underwrite
 *
 * Trigger the AI underwriting chain for one application. Phase 7.3 of
 * SunBiz CRM. Operator-callable (manually re-run from /applications detail
 * page) AND auto-fired by the sequence-runner daemon when it observes a
 * BRAVO_RECORD_STATUS_CHANGED event with entity=application + to=submitted.
 *
 * Pipeline:
 *   1. Fetch the application row + its form_submissions[file_attachments[]]
 *   2. For each bank-statement attachment, subprocess to
 *      scripts/underwriting/statement_parser.py to extract structured JSON
 *   3. Aggregate via scripts/underwriting/debt_detector.py
 *   4. Generate sales angle via scripts/underwriting/sales_angle.py
 *   5. Write the combined result to application.data.underwriting_jsonb
 *      so the Application detail page's underwriting tab renders it
 *
 * Body: {} (no params — pulls everything from the application row)
 * Response: { ok, summary, lender_count, monthly_debt_service,
 *             sales_angle, statements_parsed }
 *
 * NOTE: physical PDF subprocess execution requires the operator's local
 * bridge (PDFs are tenant data, not on Vercel). In v1 we run the chain
 * via fetch to bridge /exec-tool with the script_run action. When bridge
 * is offline, the route returns 503 "bridge_required" so the operator
 * knows what's blocking.
 */

import { NextRequest, NextResponse } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function resolveTenantId(): Promise<string | null> {
  const user = await getSessionUser();
  if (!user) return null;
  const db = getServiceSupabase();
  const { data } = await db
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  return (data as { tenant_id: string | null } | null)?.tenant_id ?? null;
}

export async function POST(
  _req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const tenantId = await resolveTenantId();
  if (!tenantId) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }
  const { id: applicationId } = await ctx.params;

  const db = getServiceSupabase();

  // Pull the application row.
  const appRow = await db
    .from("tenant_records")
    .select("id, data")
    .eq("tenant_id", tenantId)
    .eq("entity_type", "application")
    .eq("id", applicationId)
    .maybeSingle();
  if (appRow.error || !appRow.data) {
    return NextResponse.json({ ok: false, error: "application_not_found" }, { status: 404 });
  }
  const appData = (appRow.data as { data: Record<string, unknown> }).data || {};
  const leadId = (appData.lead_id as string | undefined) || null;

  // Pull the bank-statement file attachments from form_submissions
  // keyed off (tenant, lead). We expect the bank-statement upload step
  // to have used field type=file_upload; the route already stores
  // file_attachments[] on the submission row.
  if (!leadId) {
    return NextResponse.json(
      { ok: false, error: "application_missing_lead_id" },
      { status: 400 },
    );
  }

  const subs = await db
    .from("form_submissions")
    .select("file_attachments, payload, submitted_at")
    .eq("tenant_id", tenantId)
    .eq("lead_id", leadId)
    .order("submitted_at", { ascending: false })
    .limit(10);
  if (subs.error) {
    return NextResponse.json({ ok: false, error: subs.error.message }, { status: 500 });
  }
  const allAttachments: Array<{
    field_name: string;
    storage_path: string;
    mime_type: string;
    size_bytes: number;
  }> = [];
  for (const row of subs.data || []) {
    const r = row as { file_attachments: unknown };
    if (Array.isArray(r.file_attachments)) {
      for (const att of r.file_attachments) {
        if (att && typeof att === "object" && "storage_path" in att) {
          allAttachments.push(att as never);
        }
      }
    }
  }
  if (allAttachments.length === 0) {
    return NextResponse.json(
      {
        ok: false,
        error: "no_bank_statements_on_file",
        hint: "Underwriting needs at least one bank statement uploaded via the application form step 3.",
      },
      { status: 400 },
    );
  }

  // ── Bridge dispatch ───────────────────────────────────────────────
  //
  // The underwriting subprocess chain (statement_parser -> debt_detector
  // -> sales_angle) runs on the operator's machine because:
  //   1. Bank statements are sensitive; some operators don't want them
  //      passing through Vercel even via Supabase Storage
  //   2. PyMuPDF / pdf2image require system libs (poppler) the Vercel
  //      runtime doesn't carry
  //   3. The Anthropic vision call is fine cloud-side, but the PDF
  //      decoding step needs the local file system anyway
  //
  // The bridge's /exec-tool endpoint accepts script_run actions. We
  // dispatch the underwriting pipeline as a script_run with the lead_id
  // payload; the script reads attachments, parses, summarizes, generates
  // the angle, and writes back to tenant_records.data.underwriting_jsonb.
  //
  // v1 SCOPE: the bridge wiring is a follow-on. This route currently
  // returns a 503 with the actionable hint until the bridge tool is
  // registered. Phase 7.3-bis closes that gap.

  return NextResponse.json(
    {
      ok: false,
      error: "underwriting_bridge_pending",
      hint:
        "The AI underwriting chain runs on your local machine via the bridge. To complete Phase 7.3, the bridge's /exec-tool endpoint needs an underwriting_run handler that subprocesses scripts/underwriting/statement_parser.py + debt_detector.py + sales_angle.py and writes the result back to tenant_records. Once that ships, this route dispatches via bridge auto-discover. v1 returns this 503 honestly rather than pretending.",
      application_id: applicationId,
      lead_id: leadId,
      attachments_available: allAttachments.length,
    },
    { status: 503 },
  );
}
