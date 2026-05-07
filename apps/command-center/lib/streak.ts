/**
 * Rolling 7-day streak + missed-day computer for the Today page.
 *
 * "Streak" = consecutive days (back to today) where ≥1 schedule item was
 * marked completed. "Missed" = days in the window where the plan exists
 * but zero items got checked off. Days with no plan at all are NOT
 * counted as misses (operator wasn't running the dashboard yet).
 *
 * Reads daily_plans rows for the operator's profile, looks at each row's
 * schedule[] JSONB, counts completed entries.
 */

import { getServiceSupabase } from "./supabase-server";

export type StreakResult = {
  streak: number; // consecutive completed days back from today
  missed: number; // days in window with plan but no completion
  daysWithPlan: number;
  byDay: Array<{ date: string; completed: number; total: number }>;
};

const FALLBACK: StreakResult = {
  streak: 0,
  missed: 0,
  daysWithPlan: 0,
  byDay: [],
};

function _ymd(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export async function computeStreak(
  profileId: string,
  daysBack = 7
): Promise<StreakResult> {
  if (!profileId) return FALLBACK;
  const db = getServiceSupabase();

  const today = new Date();
  const window: string[] = [];
  for (let i = 0; i < daysBack; i++) {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i);
    window.push(_ymd(d));
  }
  const oldest = window[window.length - 1];

  const { data, error } = await db
    .from("daily_plans")
    .select("plan_date, schedule")
    .eq("profile_id", profileId)
    .gte("plan_date", oldest)
    .order("plan_date", { ascending: false });
  if (error || !data) return FALLBACK;

  type Row = { plan_date: string; schedule: unknown };
  const byDate = new Map<string, Row>();
  for (const row of data as Row[]) {
    byDate.set(row.plan_date, row);
  }

  const byDay: StreakResult["byDay"] = [];
  let streak = 0;
  let streakBroken = false;
  let missed = 0;
  let daysWithPlan = 0;

  for (const day of window) {
    const row = byDate.get(day);
    if (!row) {
      // No plan for this day — neither contributes to streak nor missed
      byDay.push({ date: day, completed: 0, total: 0 });
      streakBroken = true;
      continue;
    }
    daysWithPlan += 1;
    const items = Array.isArray(row.schedule) ? (row.schedule as Array<Record<string, unknown>>) : [];
    const completed = items.filter((s) => Boolean(s.completed)).length;
    byDay.push({ date: day, completed, total: items.length });
    if (completed > 0) {
      if (!streakBroken) streak += 1;
    } else {
      streakBroken = true;
      missed += 1;
    }
  }

  return { streak, missed, daysWithPlan, byDay };
}
