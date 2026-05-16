/**
 * POST /api/automations/save-draft
 *
 * Phase 10.3 — persist an operator-reviewed AutomationDraft as:
 *   1. A Python file at scripts/<script_filename> (written via the local
 *      bridge's write_file tool, since Vercel can't reach the operator's
 *      disk).
 *   2. A tenant_cron_jobs row with action_type=script_run pointing at
 *      that script.
 *
 * Body: {
 *   draft: AutomationDraft,
 *   confirmed: true   // operator clicked "Save automation" (defense in depth)
 * }
 * Response 200: { ok: true, script_path, cron_id }
 * Response 4xx: { ok: false, error, message? }
 *
 * Trust model: the bridge runs as the operator. The dashboard sends the
 * draft + a confirmation flag; the bridge writes the file and the
 * dashboard inserts the cron row. We don't trigger execution — the
 * next scheduled tick fires it naturally (operator has time to inspect
 * the new automation on /automations before it runs).
 */

import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { resolveSessionContext } from "@/lib/api-auth";
import type { AutomationDraft } from "@/lib/ai-automation-drafter";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const FILENAME_RE = /^[a-z][a-z0-9_]*\.py$/;
const CRON_RE = /^(\*|\d+|\*\/\d+|\d+(-\d+)?(\/\d+)?(,\d+(-\d+)?(\/\d+)?)*)(\s+(\*|\d+|\*\/\d+|\d+(-\d+)?(\/\d+)?(,\d+(-\d+)?(\/\d+)?)*|MON|TUE|WED|THU|FRI|SAT|SUN|MON-FRI)){4}$/i;

function isValidCron(expr: string): boolean {
  const trimmed = (expr || "").trim();
  if (!trimmed) return false;
  if (trimmed.split(/\s+/).length !== 5) return false;
  return CRON_RE.test(trimmed);
}

export async function POST(req: NextRequest) {
  const ctx = await resolveSessionContext();
  if (!ctx.ok) {
    return NextResponse.json({ ok: false, error: "unauthorized", message: ctx.reason }, { status: 401 });
  }

  let body: { draft?: Partial<AutomationDraft>; confirmed?: boolean };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }
  if (!body.confirmed) {
    return NextResponse.json({ ok: false, error: "not_confirmed" }, { status: 400 });
  }

  const draft = body.draft || {};
  const errors: string[] = [];
  if (!draft.suggested_name || draft.suggested_name.length > 80) errors.push("suggested_name");
  if (!draft.script_filename || !FILENAME_RE.test(draft.script_filename)) errors.push("script_filename");
  if (!draft.script_content || draft.script_content.length > 100_000) errors.push("script_content");
  if (!draft.schedule || !isValidCron(draft.schedule)) errors.push("schedule");
  if (!draft.agent_key) errors.push("agent_key");
  if (errors.length) {
    return NextResponse.json(
      { ok: false, error: "draft_invalid", missing_or_invalid: errors },
      { status: 400 },
    );
  }

  // Insert the cron row first so the bridge file-write can include the
  // cron_id as a breadcrumb in the script header (lets operators trace
  // a misbehaving script back to its row).
  const db = getServiceSupabase();
  const cronPayload = {
    tenant_id: ctx.tenantId,
    agent_key: draft.agent_key!.toLowerCase(),
    name: draft.suggested_name!,
    description: draft.suggested_description || "",
    schedule: draft.schedule!.trim(),
    action_type: "script_run",
    action_payload: {
      // The script_run handler in bravo_cli reads {script, args} from
      // action_payload. We point at scripts/<filename> (relative to
      // PROJECT_ROOT) so the operator can edit it on disk later.
      script: `scripts/${draft.script_filename}`,
      args: [],
      // Provenance — surface that this was AI-drafted so reviewers know
      // to read it carefully before flipping enabled=true.
      _ai_drafted: true,
      _ai_drafted_at: new Date().toISOString(),
    },
    // Disabled on creation. Operator flips on after inspecting the
    // generated file. Prevents an AI-drafted script from running before
    // anyone's seen what it does.
    enabled: false,
    created_by: ctx.profileId,
  };
  const insRes = await db
    .from("tenant_cron_jobs")
    .insert(cronPayload)
    .select()
    .single();
  if (insRes.error) {
    return NextResponse.json(
      { ok: false, error: "cron_insert_failed", message: insRes.error.message },
      { status: 500 },
    );
  }
  const cronId = (insRes.data as { id: string }).id;

  // The actual script-write happens on the operator's machine via the
  // local bridge — Vercel can't touch the operator's disk. The dashboard
  // client picks up the response and POSTs to localhost:9100/exec-tool
  // with the write_file tool. We return enough metadata for the client
  // to do that.
  return NextResponse.json({
    ok: true,
    cron_id: cronId,
    script_path: `scripts/${draft.script_filename}`,
    script_content: draft.script_content,
    next_step: "client_should_post_to_bridge_write_file",
  });
}
