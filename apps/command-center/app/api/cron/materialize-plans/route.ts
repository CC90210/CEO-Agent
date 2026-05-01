/**
 * Vercel cron handler: materialize tomorrow's daily_plan from the right
 * template (weekday vs weekend) for every profile that has plan_templates.
 *
 * Runs at 03:00 UTC (~11pm Eastern) — see vercel.json crons config.
 *
 * Auth: requires CRON_SECRET in the Authorization header (set in Vercel env).
 */

import { NextResponse, type NextRequest } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { operatorDateKey } from "@/lib/dates";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization") || "";
  const expected = process.env.CRON_SECRET;
  // Fail-closed: refuse if CRON_SECRET isn't configured, OR if header doesn't match.
  // Vercel Cron sends the secret automatically when configured in vercel.json.
  if (!expected || auth !== `Bearer ${expected}`) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const db = getServiceSupabase();
  // For every profile that has at least one enabled template, materialize tomorrow.
  const profiles = await db
    .from("plan_templates")
    .select("profile_id")
    .eq("enabled", true);

  if (profiles.error) {
    return NextResponse.json({ error: profiles.error.message }, { status: 500 });
  }

  const seen = new Set<string>();
  const results: Array<{ profile_id: string; plan_id: string | null; error?: string }> = [];
  const targetDate = operatorDateKey(new Date(), 1);

  for (const row of profiles.data || []) {
    const pid = (row as { profile_id: string }).profile_id;
    if (seen.has(pid)) continue;
    seen.add(pid);
    const r = await db.rpc("materialize_today_plan", {
      p_profile_id: pid,
      p_target_date: targetDate,
    });
    if (r.error) {
      results.push({ profile_id: pid, plan_id: null, error: r.error.message });
    } else {
      results.push({ profile_id: pid, plan_id: r.data as string });
    }
  }

  return NextResponse.json({ ok: true, target_date: targetDate, count: results.length, results });
}

export async function POST(req: NextRequest) {
  return GET(req);
}
