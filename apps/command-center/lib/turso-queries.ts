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
import type { DailyPlan, Lead } from "@/lib/supabase";
import { operatorDateKey } from "@/lib/dates";

function _rowToObject(columns: string[], row: unknown[]): Record<string, unknown> {
  const obj: Record<string, unknown> = {};
  columns.forEach((c, i) => {
    obj[c] = row[i];
  });
  return obj;
}

const _warned = new Set<string>();
function _warnOnce(scope: string, err: unknown) {
  if (_warned.has(scope)) return;
  _warned.add(scope);
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
    const obj = _rowToObject(r.columns, row as unknown as unknown[]);
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

/**
 * Tenant-scoped recent leads (SunBiz "Leads" page + the lead-discovery surface).
 * Mirrors recentLeads() options: include_archived, include_no_email, include_lost.
 *
 * Returns null on Turso failure so the caller falls back to Supabase. Returns
 * [] on empty result (not a fallback — genuine empty state).
 */
export async function recentLeadsTurso(
  tenantId: string,
  limit = 30,
  opts?: { include_archived?: boolean; include_no_email?: boolean; include_lost?: boolean }
): Promise<Lead[] | null> {
  try {
    const client = getTursoClient();
    const filters = ["tenant_id = ?"];
    const args: (string | number)[] = [tenantId];
    if (!opts?.include_archived) filters.push("status != 'archived'");
    if (!opts?.include_lost) filters.push("status != 'lost'");
    if (!opts?.include_no_email) filters.push("email IS NOT NULL");
    const sql = `SELECT * FROM leads WHERE ${filters.join(" AND ")} ORDER BY updated_at DESC LIMIT ?`;
    args.push(limit);
    const r = await client.execute({ sql, args });
    return (r.rows || []).map((row) => _rowToObject(r.columns, row as unknown as unknown[]) as unknown as Lead);
  } catch (err) {
    _warnOnce("recentLeadsTurso", err);
    return null;
  }
}

export type PipelineBreakdown = {
  stages: Record<string, number>;
  total: number;
  sources: Record<string, number>;
};

/**
 * Aggregate lead counts by status + source — powers the dashboard's pipeline
 * stat band. Same shape as pipelineBreakdown() in queries.ts.
 *
 * Returns null on Turso failure (caller falls back to Supabase). Returns an
 * empty breakdown on empty result.
 */
export async function pipelineBreakdownTurso(
  tenantId: string,
  includeArchived = false
): Promise<PipelineBreakdown | null> {
  try {
    const client = getTursoClient();
    const sql = includeArchived
      ? "SELECT status, source FROM leads WHERE tenant_id = ?"
      : "SELECT status, source FROM leads WHERE tenant_id = ? AND status != 'archived'";
    const r = await client.execute({ sql, args: [tenantId] });
    const stages: Record<string, number> = {
      new: 0, contacted: 0, qualified: 0, proposal: 0, won: 0, lost: 0,
    };
    const sources: Record<string, number> = {};
    let total = 0;
    for (const row of r.rows || []) {
      const obj = _rowToObject(r.columns, row as unknown as unknown[]);
      const s = (obj.status as string) || "new";
      stages[s] = (stages[s] || 0) + 1;
      const src = (obj.source as string) || "unknown";
      sources[src] = (sources[src] || 0) + 1;
      total += 1;
    }
    return { stages, total, sources };
  } catch (err) {
    _warnOnce("pipelineBreakdownTurso", err);
    return null;
  }
}

/**
 * Date-windowed daily_plans for the streak computation. Returns the raw rows
 * (plan_date + schedule + finalized_at); streak math lives in lib/streak.ts
 * so the same logic powers both backends.
 *
 * Returns null on Turso failure (caller falls back to Supabase).
 */
export async function streakWindowTurso(
  profileId: string,
  oldestYmd: string
): Promise<Array<{ plan_date: string; schedule: unknown; finalized_at: string | null }> | null> {
  try {
    const client = getTursoClient();
    const r = await client.execute({
      sql: "SELECT plan_date, schedule, finalized_at FROM daily_plans WHERE profile_id = ? AND plan_date >= ? ORDER BY plan_date DESC",
      args: [profileId, oldestYmd],
    });
    return (r.rows || []).map((row) => {
      const obj = _rowToObject(r.columns, row as unknown as unknown[]);
      // schedule is TEXT(JSON) in SQLite — deserialize so callers iterate arrays.
      if (typeof obj.schedule === "string") {
        try {
          obj.schedule = JSON.parse(obj.schedule);
        } catch {
          obj.schedule = [];
        }
      }
      return {
        plan_date: obj.plan_date as string,
        schedule: obj.schedule,
        finalized_at: (obj.finalized_at as string | null) ?? null,
      };
    });
  } catch (err) {
    _warnOnce("streakWindowTurso", err);
    return null;
  }
}
