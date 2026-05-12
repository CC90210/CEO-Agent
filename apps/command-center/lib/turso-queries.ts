/**
 * Turso/libSQL adapter for the hot reads in queries.ts.
 *
 * Same return shapes as the Supabase paths so call sites don't branch.
 *
 * Schema assumption: the libSQL file has the same DDL as Supabase (migrations
 * 001-037 replayed against the local file). When `bravo db init --backend=turso`
 * lands, it will do this automatically; until then, operators bootstrap the
 * schema manually.
 *
 * Failure mode: every adapter catches its own errors, logs once, and returns
 * a sentinel (`null` / `[]`) so queries.ts can decide whether to fall back to
 * Supabase or surface an empty state to the UI.
 */

import { getTursoClient } from "@/lib/turso";
import type { DailyPlan } from "@/lib/supabase";
import { operatorDateKey } from "@/lib/dates";

let _warnedTurso = false;
function _warnOnce(scope: string, err: unknown) {
  if (_warnedTurso) return;
  _warnedTurso = true;
  console.warn(`[turso-queries:${scope}] Turso read failed — check libSQL bootstrap:`, err);
}

export async function getTodayPlanTurso(profileId: string): Promise<DailyPlan | null> {
  try {
    const client = getTursoClient();
    const r = await client.execute({
      sql: "SELECT * FROM daily_plans WHERE profile_id = ? AND plan_date = ? LIMIT 1",
      args: [profileId, operatorDateKey()],
    });
    const row = r.rows?.[0];
    if (!row) return null;
    // libSQL rows are array-shaped; column metadata lives on r.columns.
    const cols = r.columns;
    const obj: Record<string, unknown> = {};
    cols.forEach((c, i) => {
      obj[c] = row[i];
    });
    // Schedule is stored as TEXT (JSON) in SQLite/libSQL; parse it.
    if (typeof obj.schedule === "string") {
      try {
        obj.schedule = JSON.parse(obj.schedule);
      } catch {
        obj.schedule = [];
      }
    }
    return obj as unknown as DailyPlan;
  } catch (err) {
    _warnOnce("getTodayPlanTurso", err);
    return null;
  }
}
