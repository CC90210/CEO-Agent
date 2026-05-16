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
import { getServiceSupabase } from "@/lib/supabase-server";
import { resolveTenantId } from "@/lib/api-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

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
  // The underwriting subprocess chain (statement_parser → debt_detector
  // → sales_angle) runs on the operator's machine because:
  //   1. Bank statements are sensitive; operators don't want them
  //      passing through Vercel even via Supabase Storage.
  //   2. PyMuPDF / pdf2image require system libs (poppler) the Vercel
  //      runtime doesn't carry.
  //   3. The Anthropic vision call is fine cloud-side, but PDF decoding
  //      needs the local file system anyway.
  //
  // Vercel CAN'T reach the bridge's localhost:9100 directly. The
  // operator triggers the chain by asking Solara (who has the
  // underwriting_run bridge tool — bravo_cli/bridge_tools.py
  // _tool_underwriting_run). Solara emits a tool_use; the
  // ChatWidget proxies it to /exec-tool; the bridge runs the chain
  // and writes underwriting_jsonb back to tenant_records.
  //
  // 2026-05-16 Round 3 R3-3: bridge handler is live. This route
  // returns a 200 with the actionable instruction + the exact tool
  // payload the operator's UI can pre-fill into a chat message.
  // The dashboard application detail page surfaces a one-click
  // "Run underwriting" button that POSTs this payload to /api/chat
  // with agent_key='solara'.

  const bridgeToolPayload = {
    tool: "underwriting_run",
    input: {
      application_id: applicationId,
      bank_statement_paths: allAttachments.map((a) => a.storage_path),
    },
  };
  const operatorPrompt =
    `Please run underwriting on application ${applicationId.slice(0, 8)}… ` +
    `(${allAttachments.length} bank statement${allAttachments.length === 1 ? "" : "s"} on file). ` +
    `Use your underwriting_run tool with the application_id and the storage_paths.`;

  return NextResponse.json(
    {
      ok: true,
      mode: "bridge_tool",
      application_id: applicationId,
      lead_id: leadId,
      attachments_available: allAttachments.length,
      // The dashboard application-detail page wires this into a
      // "Run underwriting" button. Clicking it pre-fills a chat
      // turn to Solara with operator_prompt + bridge_tool_payload
      // as a system hint; Solara emits the tool_use directly.
      bridge_tool_payload: bridgeToolPayload,
      operator_prompt: operatorPrompt,
      hint:
        "Underwriting runs on your local machine through Solara's bridge tool. " +
        "Open the SunBiz agent chat and paste the operator_prompt above, or click " +
        "the 'Run underwriting' button on the application detail page. Solara will " +
        "subprocess statement_parser → debt_detector → sales_angle and write the " +
        "underwriting_jsonb back to this application within ~60s.",
    },
    { status: 200 },
  );
}
