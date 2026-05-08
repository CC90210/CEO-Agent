/**
 * Rolling 7-day streak + missed-day computer for the Today page.
 *
 * "Streak" = consecutive finalized days (back from today) where ≥1 schedule
 * item was marked completed. "Missed" = past days in the window where the
 * plan exists, was finalized, but zero items got checked off. Days with no
 * plan at all are NOT counted as misses (operator wasn't running the
 * dashboard yet).
 *
 * Today is treated specially: if today's plan exists but isn't finalized
 * yet, today is in-progress — checking and unchecking blocks does NOT
 * retroactively mark today as missed and does NOT break a prior streak.
 * Today only contributes to the streak (or to missed) once the operator
 * clicks "Finalize day", which sets daily_plans.finalized_at.
 *
 * This was the source of the "I unchecked one block and my 1-day streak
 * flipped to 3-days-behind" bug — the old logic counted any 0-completion
 * day as missed, even if it was today and still in progress.
 */

import { getServiceSupabase } from "./supabase-server";

export type StreakResult = {
  streak: number; // consecutive completed days back from today
  missed: number; // days in window with plan but no completion
  daysWithPlan: number;
  byDay: Array<{ date: string; completed: number; total: number; finalized: boolean }>;
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
  const todayYmd = _ymd(today);
  const window: string[] = [];
  for (let i = 0; i < daysBack; i++) {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i);
    window.push(_ymd(d));
  }
  const oldest = window[window.length - 1];

  const { data, error } = await db
    .from("daily_plans")
    .select("plan_date, schedule, finalized_at")
    .eq("profile_id", profileId)
    .gte("plan_date", oldest)
    .order("plan_date", { ascending: false });
  if (error || !data) return FALLBACK;

  type Row = { plan_date: string; schedule: unknown; finalized_at: string | null };
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
    const isToday = day === todayYmd;
    if (!row) {
      // No plan for this day — neither contributes to streak nor missed.
      // Today with no plan yet shouldn't break the streak either; the
      // operator may not have materialized today's plan yet.
      byDay.push({ date: day, completed: 0, total: 0, finalized: false });
      if (!isToday) streakBroken = true;
      continue;
    }
    daysWithPlan += 1;
    const items = Array.isArray(row.schedule)
      ? (row.schedule as Array<Record<string, unknown>>)
      : [];
    const completed = items.filter((s) => Boolean(s.completed)).length;
    const finalized = Boolean(row.finalized_at);
    byDay.push({ date: day, completed, total: items.length, finalized });

    if (isToday && !finalized) {
      // Today is still in-progress. Count completions toward the streak
      // (so the operator sees "🔥 1-day streak" the moment they check
      // their first block) but do NOT mark today as missed if 0 — the
      // day isn't over yet. Crucially, don't set streakBroken either:
      // unchecking the only completed block must not retroactively
      // break a streak that prior finalized days earned.
      if (completed > 0 && !streakBroken) streak += 1;
      continue;
    }

    if (completed > 0) {
      if (!streakBroken) streak += 1;
    } else {
      streakBroken = true;
      missed += 1;
    }
  }

  return { streak, missed, daysWithPlan, byDay };
}
