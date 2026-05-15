/**
 * lenders/shop-out.ts — multi-lender email distributor.
 *
 * Phase 6.3 of the SunBiz CRM build (2026-05-15). Given (application, [lenders],
 * [cc_emails]), this helper:
 *   1. Builds a structured per-lender email with the bank statements
 *      attached (or referenced via the operator's chosen storage path)
 *   2. Sends each via send_gateway.send(channel="email", ...) so CASL +
 *      cooldown + daily-cap enforcement apply uniformly
 *   3. Inserts an application_lender_threads row per lender at status=sent
 *      so Phase 6.4's response classifier daemon can correlate replies
 *
 * Email send happens via the dashboard-side Python subprocess pattern
 * /api/sms/send uses today: dispatchSmsThroughClientAgent's email twin
 * lives in scripts/email_engine.py. We invoke that through the
 * dashboard's existing client-agent layer when one is configured, or
 * fall back to /api/forms-style direct send when running OASIS HQ.
 *
 * NOTE: actual fan-out happens server-side in /api/applications/[id]/shop-out.
 * This module is the planning + audit helper imported by that route.
 */

import { getServiceSupabase } from "@/lib/supabase-server";
import type { LenderProfile, ApplicationProfile } from "./match-fitness";
import { scoreLenderMatch } from "./match-fitness";

export type ShopOutAttachment = {
  /** Display filename — e.g. "bank-statements-mar-may.pdf". */
  filename: string;
  /** Storage path for retrieval. Supabase Storage path or inline base64. */
  storage_path: string;
  mime_type: string;
  size_bytes: number;
};

export type ShopOutPlanInput = {
  tenant_id: string;
  application: ApplicationProfile;
  lender_ids: string[];
  cc_emails: string[];
  /** Bank statements + supporting docs. Each gets attached to every lender email. */
  attachments: ShopOutAttachment[];
  /** Optional operator override for the email body. {{lender.name}} substitution. */
  subject_template?: string;
  body_template?: string;
};

const DEFAULT_SUBJECT = "Funding application — {{application.business_name}}";
const DEFAULT_BODY = `Hi {{lender.name}} team,

We've got a strong submission for your review. Quick summary:

  Business: {{application.business_name}}
  Monthly revenue: {{application.monthly_revenue}}
  Time in business: {{application.time_in_business_months}} months
  Requested: {{application.requested_amount}}

Bank statements attached. Looking forward to your offer.

— Solara, SunBiz Funding
`;

function renderSimple(template: string, vars: Record<string, unknown>): string {
  return template.replace(/\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}/g, (_m, path: string) => {
    const parts = path.split(".");
    let cur: unknown = vars;
    for (const p of parts) {
      if (typeof cur !== "object" || cur === null) return "";
      cur = (cur as Record<string, unknown>)[p];
    }
    if (cur === null || cur === undefined) return "";
    return typeof cur === "string" ? cur : String(cur);
  });
}

export type ShopOutPlanRow = {
  lender_id: string;
  lender_name: string;
  match_score: number;
  blockers: string[];
  rendered_subject: string;
  rendered_body: string;
  recipient_email: string | null;
};

/**
 * Build the plan without sending. Useful for the operator confirmation
 * step ("here's what's about to go to 5 lenders — review before send").
 */
export async function buildShopOutPlan(input: ShopOutPlanInput): Promise<{
  ok: true;
  plan: ShopOutPlanRow[];
  missing_recipients: string[];
} | { ok: false; error: string }> {
  const db = getServiceSupabase();

  // Fetch each lender row from tenant_records.
  const lenderRows = await db
    .from("tenant_records")
    .select("id, data")
    .eq("tenant_id", input.tenant_id)
    .eq("entity_type", "lender")
    .in("id", input.lender_ids);
  if (lenderRows.error) {
    return { ok: false, error: lenderRows.error.message };
  }

  const subjectTemplate = input.subject_template || DEFAULT_SUBJECT;
  const bodyTemplate = input.body_template || DEFAULT_BODY;
  const plan: ShopOutPlanRow[] = [];
  const missing_recipients: string[] = [];

  for (const row of lenderRows.data || []) {
    const r = row as { id: string; data: Record<string, unknown> };
    const data = r.data || {};
    const lender: LenderProfile = {
      id: r.id,
      name: String(data.name || "(unnamed)"),
      product_types: data.product_types as LenderProfile["product_types"],
      min_monthly_revenue: typeof data.min_monthly_revenue === "number" ? data.min_monthly_revenue : undefined,
      max_funded_amount: typeof data.max_funded_amount === "number" ? data.max_funded_amount : undefined,
      min_time_in_business_months: typeof data.min_time_in_business_months === "number" ? data.min_time_in_business_months : undefined,
      fico_floor: typeof data.fico_floor === "number" ? data.fico_floor : undefined,
      sla_response_days: typeof data.sla_response_days === "number" ? data.sla_response_days : undefined,
    };
    const recipient = typeof data.contact === "string" ? data.contact : null;
    if (!recipient) missing_recipients.push(lender.name);

    const score = scoreLenderMatch(lender, input.application);
    const vars = { lender, application: input.application };

    plan.push({
      lender_id: lender.id,
      lender_name: lender.name,
      match_score: score.score,
      blockers: score.blockers,
      rendered_subject: renderSimple(subjectTemplate, vars),
      rendered_body: renderSimple(bodyTemplate, vars),
      recipient_email: recipient,
    });
  }

  return { ok: true, plan, missing_recipients };
}

/**
 * Insert the application_lender_threads rows for a shop-out batch.
 * Called by /api/applications/[id]/shop-out.
 *
 * NOTE on status semantics: rows land at 'pending' (NOT 'sent') because
 * the physical SMTP send is Phase 6.3-bis. A row only moves to 'sent'
 * once the bridge-side send_gateway invocation succeeds + stamps
 * gmail_thread_id. If `entries[i].error` is set (missing contact /
 * match blocker), the row lands at 'error' so operators see what went
 * wrong without polluting their pending queue.
 *
 * The status column's CHECK constraint covers: pending, sent,
 * responded, approved, declined, info_requested, no_response, error
 * (per migration 044).
 */
export async function recordShopOutThreads(input: {
  tenant_id: string;
  application_id: string;
  cc_emails: string[];
  entries: Array<{ lender_id: string; subject: string; sent: boolean; error?: string }>;
}): Promise<{ ok: true; inserted: number } | { ok: false; error: string }> {
  if (input.entries.length === 0) return { ok: true, inserted: 0 };
  const db = getServiceSupabase();
  const rows = input.entries.map((e) => ({
    application_id: input.application_id,
    lender_id: e.lender_id,
    tenant_id: input.tenant_id,
    subject: e.subject.slice(0, 500),
    cc_emails: input.cc_emails,
    // Errors (missing contact, match blocker) -> 'error'. Otherwise
    // 'pending' until Phase 6.3-bis flips it to 'sent' on real SMTP
    // success. Never 'sent' from this route — that would lie to the
    // operator about what actually happened.
    status: e.error ? "error" : "pending",
    last_error: e.error || null,
    sent_at: null,
  }));
  const { error } = await db.from("application_lender_threads").insert(rows);
  if (error) {
    return { ok: false, error: error.message };
  }
  return { ok: true, inserted: rows.length };
}
