/**
 * PATCH /api/daily-plan — update today's plan (mission, primary lead play,
 * schedule completion flags, retro fields).
 */
import { NextResponse, type NextRequest } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { bad, profileForUser } from "@/lib/api-helpers";
import { operatorDateKey } from "@/lib/dates";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function PATCH(req: NextRequest) {
  const profile = await profileForUser();
  if (!profile) return bad(401, "unauthorized");

  let body: {
    mission?: string;
    primary_lead_play?: string;
    schedule?: unknown[];
    actual_calls?: number;
    actual_bookings?: number;
    retro_notes?: string;
    finalized_at?: string | null;
  };
  try { body = await req.json(); } catch { return bad(400, "invalid JSON"); }

  const update: Record<string, unknown> = {};
  if (body.mission !== undefined) update.mission = body.mission;
  if (body.primary_lead_play !== undefined) update.primary_lead_play = body.primary_lead_play;
  if (body.schedule !== undefined) update.schedule = body.schedule;
  if (body.actual_calls !== undefined) update.actual_calls = body.actual_calls;
  if (body.actual_bookings !== undefined) update.actual_bookings = body.actual_bookings;
  if (body.retro_notes !== undefined) update.retro_notes = body.retro_notes;
  if (body.finalized_at !== undefined) update.finalized_at = body.finalized_at;

  if (Object.keys(update).length === 0) return bad(400, "no editable fields");

  const today = operatorDateKey();
  const db = getServiceSupabase();
  const r = await db
    .from("daily_plans")
    .update(update)
    .eq("profile_id", profile.id)
    .eq("plan_date", today)
    .select("*")
    .maybeSingle();
  if (r.error) return bad(500, r.error.message);
  return NextResponse.json({ ok: true, plan: r.data });
}
