/**
 * POST /api/forms/submit
 *
 * Public-facing submission endpoint for a personalized form link.
 * Authenticated via HMAC bearer token in the request body (not a session
 * cookie) so prospects can submit without an OASIS account.
 *
 * Flow:
 *   1. Verify the HMAC token via lib/form-links.ts.
 *   2. Look up the form to confirm it's still enabled.
 *   3. Insert a form_submissions row (one per step completion).
 *   4. If form.step_outcomes maps this step_index to a lead.stage value,
 *      transition the lead via updateRecord. The Phase 2 publisher fires
 *      BRAVO_RECORD_STATUS_CHANGED automatically, which the Phase 4 drip
 *      engine consumes.
 *
 * Body:
 *   {
 *     token: string,         // the HMAC-signed lead_token from the URL
 *     step_index: number,    // 0-based index into form.steps
 *     payload: {...},        // field-name -> value map
 *     file_attachments?: [...]
 *   }
 *
 * Response: { ok, submission_id, next_step?, lead_stage? }
 *
 * Rate-limit: 30 submissions per minute per token (lead-bound). Hand-
 * rolled in-memory bucket so a runaway client can't flood the dashboard.
 * Tracks by token rather than IP because forms are personalized links —
 * one IP could legitimately submit forms for multiple leads.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { verifyFormLink, type FormLinkPayload } from "@/lib/form-links";
import {
  parseFormSteps,
  type FormStep,
  FormDefinitionError,
} from "@/lib/forms/types";
import { rateLimit } from "@/lib/rate-limit";
import { updateRecord, RecordsError } from "@/lib/manifest/data";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type SubmitBody = {
  token?: string;
  step_index?: number;
  payload?: Record<string, unknown>;
  file_attachments?: Array<{
    field_name: string;
    storage_path: string;
    mime_type: string;
    size_bytes: number;
  }>;
};

export async function POST(req: NextRequest) {
  let body: SubmitBody;
  try {
    body = (await req.json()) as SubmitBody;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  // Verify HMAC first — fast rejection before any DB work.
  const sigResult = verifyFormLink(body.token);
  if (!sigResult.ok) {
    return NextResponse.json(
      { ok: false, error: `token_${sigResult.reason}` },
      { status: sigResult.reason === "server_misconfigured" ? 503 : 400 },
    );
  }
  const link: FormLinkPayload = sigResult.payload;

  // Per-token rate limit. 30/min is roughly 1 submission every 2s, enough
  // for legitimate multi-step funnels (basic -> app -> upload) but well
  // below abusive-bot territory.
  const limit = rateLimit({
    key: `forms-submit:${link.lead_id}:${link.form_id}`,
    capacity: 30,
    refillPerSec: 0.5,
  });
  if (!limit.allowed) {
    return NextResponse.json(
      { ok: false, error: "rate_limited", retry_in_sec: limit.resetIn },
      { status: 429 },
    );
  }

  const stepIndex = Number(body.step_index);
  if (!Number.isInteger(stepIndex) || stepIndex < 0) {
    return NextResponse.json(
      { ok: false, error: "invalid_step_index" },
      { status: 400 },
    );
  }

  const payload =
    body.payload && typeof body.payload === "object" ? body.payload : {};
  const fileAttachments = Array.isArray(body.file_attachments)
    ? body.file_attachments
    : [];

  // Look up the form to confirm it's still enabled + step_index is in
  // range. Tenant scoping comes from the verified token's tenant slug;
  // we double-check the form's tenant_id row matches that slug to defeat
  // tenant-id forgery via a leaked token.
  const db = getServiceSupabase();
  const formRow = await db
    .from("forms")
    .select(
      "id, tenant_id, slug, steps, on_complete_stage, step_outcomes, enabled, redirect_url, tenant:tenants!inner(slug)",
    )
    .eq("id", link.form_id)
    .maybeSingle();
  if (formRow.error || !formRow.data) {
    return NextResponse.json({ ok: false, error: "form_not_found" }, { status: 404 });
  }
  const form = formRow.data as {
    id: string;
    tenant_id: string;
    slug: string;
    steps: unknown;
    on_complete_stage: string | null;
    step_outcomes: Record<string, string> | null;
    enabled: boolean;
    redirect_url: string | null;
    tenant: { slug: string } | { slug: string }[] | null;
  };
  if (!form.enabled) {
    return NextResponse.json({ ok: false, error: "form_disabled" }, { status: 400 });
  }
  const tenantRow = Array.isArray(form.tenant) ? form.tenant[0] : form.tenant;
  if (!tenantRow || tenantRow.slug !== link.tenant) {
    return NextResponse.json({ ok: false, error: "tenant_mismatch" }, { status: 400 });
  }

  // Parse the steps to validate step_index range. parseFormSteps throws
  // on malformed data — if a DB row is somehow corrupt we 500 cleanly.
  let steps: FormStep[];
  try {
    steps = parseFormSteps(form.steps);
  } catch (err) {
    if (err instanceof FormDefinitionError) {
      return NextResponse.json(
        { ok: false, error: "form_definition_corrupt", path: err.path, reason: err.reason },
        { status: 500 },
      );
    }
    throw err;
  }
  if (stepIndex >= steps.length) {
    return NextResponse.json(
      { ok: false, error: "step_index_out_of_range", max: steps.length - 1 },
      { status: 400 },
    );
  }

  // Insert the submission row. service-role write — RLS doesn't see this
  // path; HMAC token + tenant_id match is the auth boundary.
  const ipHeader =
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || null;
  const userAgent = req.headers.get("user-agent")?.slice(0, 500) || null;

  const insertRes = await db
    .from("form_submissions")
    .insert({
      form_id: form.id,
      tenant_id: form.tenant_id,
      lead_id: link.lead_id,
      step_index: stepIndex,
      payload,
      file_attachments: fileAttachments,
      ip_address: ipHeader,
      user_agent: userAgent,
    })
    .select("id")
    .single();
  if (insertRes.error) {
    return NextResponse.json(
      { ok: false, error: insertRes.error.message },
      { status: 500 },
    );
  }
  const submissionId = (insertRes.data as { id: string }).id;

  // Stage transition — if step_outcomes has a target for this step,
  // patch the lead via updateRecord. Phase 2's BRAVO_RECORD_STATUS_CHANGED
  // publisher fires automatically; the Phase 4 drip engine consumes it.
  // The final step also honors on_complete_stage as a fallback.
  let appliedStage: string | null = null;
  const stepOutcomes = form.step_outcomes || {};
  const isLastStep = stepIndex === steps.length - 1;
  const targetStage =
    stepOutcomes[String(stepIndex)] ||
    (isLastStep && form.on_complete_stage) ||
    null;

  // Round 3 R3-10: stage-transition failure used to swallow the error
  // and return ok:true, hiding from the operator that the drip never
  // fired. Now we capture the reason + surface it in the response so
  // the public form page can flag a partial success and the operator
  // sees in their /feed event tape that the lead landed but the
  // pipeline didn't advance.
  let stageWarning: { reason: string; target_stage: string } | null = null;
  if (targetStage) {
    try {
      await updateRecord({
        tenant_id: form.tenant_id,
        entity: "lead",
        id: link.lead_id,
        patch: { stage: targetStage },
      });
      appliedStage = targetStage;
    } catch (err) {
      const reason = err instanceof RecordsError ? err.code : "unknown";
      console.error("[forms.submit.stage_transition]", {
        lead_id: link.lead_id,
        target_stage: targetStage,
        reason,
      });
      stageWarning = { reason, target_stage: targetStage };
    }
  }

  return NextResponse.json({
    ok: true,
    submission_id: submissionId,
    next_step: isLastStep ? null : stepIndex + 1,
    lead_stage: appliedStage,
    redirect_url: isLastStep ? form.redirect_url : null,
    // Non-null when the prospect's submission landed but the lead's
    // stage didn't advance — drip didn't fire, operator needs to look
    // (typical causes: lead row was deleted between view + submit;
    // entity_type mismatch from a manifest edit mid-flight).
    stage_warning: stageWarning,
  });
}
