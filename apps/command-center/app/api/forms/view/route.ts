/**
 * POST /api/forms/view
 *
 * Public-facing view-tracking endpoint. The personalized form page POSTs
 * here on mount; we record a form_views row + transition the lead's
 * stage to `viewed_application` if it isn't already past that point.
 * Rate-limited at the DB level (one view per lead per hour) so a page
 * refresh doesn't re-fire the drip 50 times.
 *
 * Auth: same HMAC token from the URL. No session cookie.
 *
 * Body: { token: string }
 * Response: { ok, viewed_application_fired: boolean }
 *
 * The boolean tells the public form page whether the drip kicked off so
 * it can render an appropriate UX confirmation (rare — usually invisible).
 */

import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { verifyFormLink, type FormLinkPayload } from "@/lib/form-links";
import { rateLimit } from "@/lib/rate-limit";
import { updateRecord, RecordsError } from "@/lib/manifest/data";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Stages that count as "past viewed_application" — re-firing the drip
 * after a prospect has moved deeper is wrong (it'd undo progress).
 * Ordered from earliest to latest in the funnel.
 */
const POST_VIEWED_STAGES = new Set([
  "viewed_application",
  "signed_application",
  "submitted",
  "declined",
  "default",
]);

export async function POST(req: NextRequest) {
  let body: { token?: string };
  try {
    body = (await req.json()) as { token?: string };
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const sigResult = verifyFormLink(body.token);
  if (!sigResult.ok) {
    return NextResponse.json(
      { ok: false, error: `token_${sigResult.reason}` },
      { status: sigResult.reason === "server_misconfigured" ? 503 : 400 },
    );
  }
  const link: FormLinkPayload = sigResult.payload;

  // Per-token rate limit — 4 view-pings per minute is more than enough
  // for legitimate page refreshes; abusive bots would be capped at the
  // route layer well before the once-per-hour DB rule kicks in.
  const limit = rateLimit({
    key: `forms-view:${link.lead_id}:${link.form_id}`,
    capacity: 4,
    refillPerSec: 1 / 15,
  });
  if (!limit.allowed) {
    return NextResponse.json(
      { ok: false, error: "rate_limited", retry_in_sec: limit.resetIn },
      { status: 429 },
    );
  }

  const db = getServiceSupabase();

  // Resolve the form's tenant_id from the form row (don't trust the
  // token's tenant slug for DB writes — only the form_id is the FK
  // boundary we need).
  const formRow = await db
    .from("forms")
    .select("id, tenant_id, enabled")
    .eq("id", link.form_id)
    .maybeSingle();
  if (formRow.error || !formRow.data) {
    return NextResponse.json({ ok: false, error: "form_not_found" }, { status: 404 });
  }
  const form = formRow.data as { id: string; tenant_id: string; enabled: boolean };
  if (!form.enabled) {
    return NextResponse.json({ ok: false, error: "form_disabled" }, { status: 400 });
  }

  // DB-level dedup: only record + fire the drip if no view from this lead
  // in the last hour. Cheap query because the form_views index is
  // (tenant_id, lead_id, viewed_at DESC).
  const recentCutoff = new Date(Date.now() - 60 * 60 * 1000).toISOString();
  const recentRow = await db
    .from("form_views")
    .select("id")
    .eq("tenant_id", form.tenant_id)
    .eq("lead_id", link.lead_id)
    .gte("viewed_at", recentCutoff)
    .limit(1)
    .maybeSingle();
  if (recentRow.data) {
    // Already counted this view in the last hour — record nothing,
    // return false for the dripped flag.
    return NextResponse.json({ ok: true, viewed_application_fired: false });
  }

  // Insert the form_views row first so we have an audit trail even if
  // the stage-transition fails downstream.
  const ipHeader =
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || null;
  const userAgent = req.headers.get("user-agent")?.slice(0, 500) || null;
  await db.from("form_views").insert({
    form_id: form.id,
    tenant_id: form.tenant_id,
    lead_id: link.lead_id,
    ip_address: ipHeader,
    user_agent: userAgent,
  });

  // Now the stage transition. Read the lead first — only patch if the
  // lead is at `sent_application` (the natural pre-viewed stage).
  // Earlier-stage leads (`cold` / `follow_up`) being viewed is anomalous
  // and we don't want to skip stages; later-stage leads have moved past
  // viewed_application already and shouldn't be rolled back.
  const leadRow = await db
    .from("tenant_records")
    .select("data")
    .eq("id", link.lead_id)
    .eq("tenant_id", form.tenant_id)
    .eq("entity_type", "lead")
    .maybeSingle();
  if (leadRow.error || !leadRow.data) {
    return NextResponse.json({ ok: true, viewed_application_fired: false });
  }
  const currentStage = ((leadRow.data as { data: Record<string, unknown> }).data?.stage ||
    "") as string;
  if (POST_VIEWED_STAGES.has(currentStage)) {
    // Lead is already past viewed_application — do not regress.
    return NextResponse.json({ ok: true, viewed_application_fired: false });
  }
  if (currentStage !== "sent_application") {
    // Lead hasn't been sent the application yet — viewing happened
    // anomalously (operator forwarded the link manually, etc.). Skip
    // the transition; let operator manually advance if appropriate.
    return NextResponse.json({ ok: true, viewed_application_fired: false });
  }

  try {
    await updateRecord({
      tenant_id: form.tenant_id,
      entity: "lead",
      id: link.lead_id,
      patch: { stage: "viewed_application" },
    });
  } catch (err) {
    const reason = err instanceof RecordsError ? err.code : "unknown";
    console.error("[forms.view.stage_transition]", { lead_id: link.lead_id, reason });
    return NextResponse.json({ ok: true, viewed_application_fired: false });
  }

  return NextResponse.json({ ok: true, viewed_application_fired: true });
}
