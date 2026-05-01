/**
 * POST /api/daily-plan/materialize   — re-run the materialize_today_plan RPC for the authed user
 * PATCH /api/daily-plan              — update today's plan (mission, primary lead play, schedule completion)
 */
import { NextResponse, type NextRequest } from "next/server";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function bad(status: number, error: string) {
  return NextResponse.json({ ok: false, error }, { status });
}

async function profileForUser() {
  const user = await getSessionUser();
  if (!user) return null;
  const db = getServiceSupabase();
  const r = await db
    .from("user_profiles")
    .select("id, tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  return r.data || null;
}

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
  };
  try { body = await req.json(); } catch { return bad(400, "invalid JSON"); }

  const update: Record<string, unknown> = {};
  if (body.mission !== undefined) update.mission = body.mission;
  if (body.primary_lead_play !== undefined) update.primary_lead_play = body.primary_lead_play;
  if (body.schedule !== undefined) update.schedule = body.schedule;
  if (body.actual_calls !== undefined) update.actual_calls = body.actual_calls;
  if (body.actual_bookings !== undefined) update.actual_bookings = body.actual_bookings;
  if (body.retro_notes !== undefined) update.retro_notes = body.retro_notes;

  if (Object.keys(update).length === 0) return bad(400, "no editable fields");

  const today = new Date().toISOString().slice(0, 10);
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
