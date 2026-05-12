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
