/**
 * POST /api/applications/[id]/shop-out
 *
 * Operator triggers a multi-lender outreach for one application.
 * Phase 6.3 of SunBiz CRM. Body:
 *
 *   {
 *     lender_ids: string[],
 *     cc_emails: string[],
 *     attachments: Array<{filename, storage_path, mime_type, size_bytes}>,
 *     subject_template?: string,   // optional override
 *     body_template?: string,
 *     dry_run?: boolean             // if true, returns the plan only
 *                                   // without firing any sends
 *   }
 *
 * Response:
 *   {
 *     ok: true,
 *     plan: ShopOutPlanRow[],  // what would have / did go out
 *     sent: number,
 *     failed: number,
 *     missing_recipients: string[]  // lenders without contact email
 *   }
 *
 * Side effects (when dry_run=false):
 *   - One email per lender via the operator's send_gateway (CASL +
 *     cooldown enforced; attachments included). Phase 6 future work
 *     to wire the actual physical-send subprocess; v1 inserts the
 *     application_lender_threads row at status=pending and surfaces
 *     a TODO for the operator to send manually until that lands.
 *   - One application_lender_threads row per lender (status=sent on
 *     success, =error on failure).
 *
 * Auth: session cookie + tenant_id match on the application row.
 */

import { NextRequest, NextResponse } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { buildShopOutPlan, recordShopOutThreads } from "@/lib/lenders/shop-out";

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
  req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const tenantId = await resolveTenantId();
  if (!tenantId) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }
  const { id: applicationId } = await ctx.params;

  let body: {
    lender_ids?: string[];
    cc_emails?: string[];
    attachments?: Array<{ filename: string; storage_path: string; mime_type: string; size_bytes: number }>;
    subject_template?: string;
    body_template?: string;
    dry_run?: boolean;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const lenderIds = Array.isArray(body.lender_ids) ? body.lender_ids.filter((s) => typeof s === "string") : [];
  if (lenderIds.length === 0) {
    return NextResponse.json(
      { ok: false, error: "lender_ids_required" },
      { status: 400 },
    );
  }
  if (lenderIds.length > 20) {
    return NextResponse.json(
      { ok: false, error: "too_many_lenders", hint: "Max 20 lenders per shop-out. Re-shop unfunded leads next month with a different cohort." },
      { status: 400 },
    );
  }

  const ccEmails = Array.isArray(body.cc_emails)
    ? body.cc_emails.filter((s) => typeof s === "string" && s.includes("@"))
    : [];
  const attachments = Array.isArray(body.attachments) ? body.attachments : [];

  // Pull the application row to confirm tenant + extract the profile
  // for match scoring. Application is a tenant_records row with the
  // lead's monthly_revenue / time_in_business / FICO / requested_amount
  // fields denormalized at form-submission time.
  const db = getServiceSupabase();
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
  const application = {
    id: applicationId,
    monthly_revenue: typeof appData.monthly_revenue === "number" ? appData.monthly_revenue : undefined,
    time_in_business_months: typeof appData.time_in_business_months === "number" ? appData.time_in_business_months : undefined,
    applicant_fico: typeof appData.applicant_fico === "number" ? appData.applicant_fico : undefined,
    requested_amount: typeof appData.requested_amount === "number" ? appData.requested_amount : undefined,
    desired_product: typeof appData.desired_product === "string" ? appData.desired_product : undefined,
  };

  // Build the plan first — operator sees this on dry_run and we use
  // it for the actual send pass below.
  const planResult = await buildShopOutPlan({
    tenant_id: tenantId,
    application,
    lender_ids: lenderIds,
    cc_emails: ccEmails,
    attachments,
    subject_template: body.subject_template,
    body_template: body.body_template,
  });
  if (!planResult.ok) {
    return NextResponse.json({ ok: false, error: planResult.error }, { status: 500 });
  }

  // Dry-run path: return the plan without firing.
  if (body.dry_run) {
    return NextResponse.json({
      ok: true,
      dry_run: true,
      plan: planResult.plan,
      sent: 0,
      failed: 0,
      missing_recipients: planResult.missing_recipients,
    });
  }

  // Actual send pass.
  //
  // v1 approach: insert application_lender_threads at status=pending
  // BEFORE the physical send. The dashboard surfaces "n lender emails
  // queued; awaiting send-engine confirmation". Phase 6.4's response
  // classifier picks up Gmail thread IDs once the send engine ships
  // them back.
  //
  // The physical send itself is operator-machine-bound — bank statements
  // attached via Supabase Storage URLs (or the operator's machine via
  // bridge /exec-tool with write_file when paranoia is enabled). The
  // route schedules; the bridge or a cloud worker does the physical
  // SMTP. v1 stops at "queued" so the data plumbing ships without the
  // full per-attachment subprocess wiring; Phase 6.3-bis (next sub-phase
  // if needed) closes that.
  const entries = planResult.plan.map((row) => ({
    lender_id: row.lender_id,
    subject: row.rendered_subject,
    sent: !!row.recipient_email && row.blockers.length === 0,
    error: !row.recipient_email
      ? "missing lender contact email"
      : row.blockers.length > 0
        ? `match blocker(s): ${row.blockers.join("; ")}`
        : undefined,
  }));

  const inserted = await recordShopOutThreads({
    tenant_id: tenantId,
    application_id: applicationId,
    cc_emails: ccEmails,
    entries,
  });
  if (!inserted.ok) {
    return NextResponse.json({ ok: false, error: inserted.error }, { status: 500 });
  }

  const sent = entries.filter((e) => e.sent).length;
  const failed = entries.length - sent;
  return NextResponse.json({
    ok: true,
    plan: planResult.plan,
    sent,
    failed,
    missing_recipients: planResult.missing_recipients,
  });
}
