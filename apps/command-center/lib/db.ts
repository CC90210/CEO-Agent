/**
 * Database backend selector. Routes reads to either Supabase (managed cloud)
 * or Turso (local libSQL) based on the tenant's profile + runtime env override.
 *
 * Wiring:
 *   - profile.dataBackend === "turso" + TURSO_* env present  → "turso"
 *   - env EMPIRE_DATA_BACKEND="supabase_cloud" forces supabase regardless
 *   - anything else  → "supabase"
 *
 * This is a thin selector — actual reads stay in lib/queries.ts. The Turso
 * adapter shape mirrors the Supabase row shape so call sites don't branch.
 */

import { tursoConfigured } from "@/lib/turso";

export type DbBackend = "supabase" | "turso";

let _warnedTursoMissing = false;

export function getDbBackend(profile?: { dataBackend?: "supabase" | "turso" }): DbBackend {
  const envOverride = process.env.EMPIRE_DATA_BACKEND;
  if (envOverride === "supabase_cloud") return "supabase";
  if (envOverride === "turso_local") return tursoConfigured() ? "turso" : "supabase";

  if (profile?.dataBackend === "turso") {
    if (tursoConfigured()) return "turso";
    if (!_warnedTursoMissing) {
      _warnedTursoMissing = true;
      console.warn(
        "[db.getDbBackend] profile.dataBackend=turso but no TURSO_DB_PATH/URL set — falling back to Supabase."
      );
    }
  }
  return "supabase";
}
