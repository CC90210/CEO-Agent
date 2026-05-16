/**
 * POST /api/leads/[id]/score
 *
 * Run AI scoring on one OASIS lead. Phase 5a of the OASIS HQ redesign.
 *
 * Pipeline:
 *   1. Resolve operator tenant via session cookie
 *   2. Fetch the lead row from tenant_records
 *   3. Hand the lead data to lib/ai-lead-scoring.ts (Claude Sonnet)
 *   4. Merge {ai_score, ai_reasoning, ai_scored_at} into lead.data
 *   5. Update the row + return the new score for the client to render
 *
 * Body: {} (no params — pulls everything from the lead row)
 * Response 200: { ok: true, score, reasoning, scored_at }
 * Response 4xx: { ok: false, error, message? }
 */

import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { resolveTenantId } from "@/lib/api-auth";
import { scoreLead } from "@/lib/ai-lead-scoring";

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
  const { id: leadId } = await ctx.params;
  if (!leadId) {
    return NextResponse.json({ ok: false, error: "missing_id" }, { status: 400 });
  }

  const db = getServiceSupabase();
  const r = await db
    .from("tenant_records")
    .select("id, data")
    .eq("tenant_id", tenantId)
    .eq("entity_type", "lead")
    .eq("id", leadId)
    .maybeSingle();
  if (r.error || !r.data) {
    return NextResponse.json({ ok: false, error: "lead_not_found" }, { status: 404 });
  }
  const leadData = ((r.data as { data: Record<string, unknown> }).data) || {};

  let result;
  try {
    result = await scoreLead(leadData);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    // Specific status codes for diagnostics that surface clearly in the UI.
    if (message === "anthropic_key_missing") {
      return NextResponse.json(
        { ok: false, error: "ai_unavailable", message: "BRAVO_ANTHROPIC_API_KEY not set on the dashboard" },
        { status: 503 },
      );
    }
    if (message.startsWith("score_parse_failed")) {
      return NextResponse.json(
        { ok: false, error: "score_parse_failed", message },
        { status: 502 },
      );
    }
    return NextResponse.json(
      { ok: false, error: "ai_failed", message },
      { status: 500 },
    );
  }

  const merged = {
    ...leadData,
    ai_score: result.score,
    ai_reasoning: result.reasoning,
    ai_scored_at: result.scored_at,
  };

  const upd = await db
    .from("tenant_records")
    .update({ data: merged })
    .eq("tenant_id", tenantId)
    .eq("entity_type", "lead")
    .eq("id", leadId);
  if (upd.error) {
    return NextResponse.json(
      { ok: false, error: "write_failed", message: upd.error.message },
      { status: 500 },
    );
  }

  return NextResponse.json({
    ok: true,
    score: result.score,
    reasoning: result.reasoning,
    scored_at: result.scored_at,
  });
}
