/**
 * POST /api/daily-plan/materialize  — manually trigger materialize_today_plan
 *   for the authed user. Useful when CC just edited a template and wants
 *   today's plan to reflect it immediately.
 */
import { NextResponse } from "next/server";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const db = getServiceSupabase();
  const profile = await db
    .from("user_profiles")
    .select("id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  if (!profile.data) return NextResponse.json({ ok: false, error: "no profile" }, { status: 404 });
  const today = new Date().toISOString().slice(0, 10);
  const r = await db.rpc("materialize_today_plan", {
    p_profile_id: profile.data.id,
    p_target_date: today,
  });
  if (r.error) return NextResponse.json({ ok: false, error: r.error.message }, { status: 500 });
  return NextResponse.json({ ok: true, plan_id: r.data });
}
