/**
 * POST /api/automations/draft
 *
 * Phase 10.3 — operator types a plain-English description of an
 * automation, Claude returns a draft Python script + cron config. The
 * draft is REVIEWABLE — nothing writes to disk or to cron_jobs here.
 * The next step (save-draft) is what persists.
 *
 * Body: { description: string }
 * Response 200: { ok: true, draft: AutomationDraft }
 * Response 4xx: { ok: false, error, message? }
 */

import { NextRequest, NextResponse } from "next/server";
import { resolveTenantId } from "@/lib/api-auth";
import { draftAutomation } from "@/lib/ai-automation-drafter";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const tenantId = await resolveTenantId();
  if (!tenantId) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  let body: { description?: unknown };
  try {
    body = (await req.json()) as { description?: unknown };
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }
  const description = typeof body.description === "string" ? body.description.trim() : "";
  if (description.length < 10) {
    return NextResponse.json(
      { ok: false, error: "description_too_short", message: "Describe in at least one sentence what the automation should do." },
      { status: 400 },
    );
  }
  if (description.length > 2000) {
    return NextResponse.json(
      { ok: false, error: "description_too_long", message: "Keep the description under 2000 characters." },
      { status: 400 },
    );
  }

  try {
    const draft = await draftAutomation(description);
    return NextResponse.json({ ok: true, draft });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (message === "anthropic_key_missing") {
      return NextResponse.json(
        { ok: false, error: "ai_unavailable", message: "BRAVO_ANTHROPIC_API_KEY not set on the dashboard" },
        { status: 503 },
      );
    }
    if (message.startsWith("automation_draft_parse_failed") || message.startsWith("automation_draft_missing_field") || message.startsWith("automation_draft_bad_filename")) {
      return NextResponse.json(
        { ok: false, error: "draft_invalid", message },
        { status: 502 },
      );
    }
    return NextResponse.json(
      { ok: false, error: "ai_failed", message },
      { status: 500 },
    );
  }
}
