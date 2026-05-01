/**
 * POST /api/daily-plan/materialize — manually trigger materialize_today_plan
 * for the authed user. Useful when CC just edited a template and wants
 * today's plan to reflect it immediately.
 */
import { NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { bad, profileForUser } from "@/lib/api-helpers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  const profile = await profileForUser();
  if (!profile) return bad(401, "unauthorized");
  const today = new Date().toISOString().slice(0, 10);
  const db = getServiceSupabase();
  const r = await db.rpc("materialize_today_plan", {
    p_profile_id: profile.id,
    p_target_date: today,
  });
  if (r.error) return bad(500, r.error.message);
  return NextResponse.json({ ok: true, plan_id: r.data });
}
