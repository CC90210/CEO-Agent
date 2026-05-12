/**
 * Turso / libSQL client factory for tenants whose data sovereignty choice is
 * "Local libSQL" (see ClientCommandCenterProfile.dataBackend === "turso").
 *
 * Two source modes:
 *   - file: TURSO_DB_PATH=/Users/.../tenant.db  → local libSQL file
 *   - http: TURSO_DB_URL=libsql://... + TURSO_AUTH_TOKEN  → hosted Turso
 *
 * The factory is process-cached and idempotent. Callers that get an error
 * should swallow + fall back to Supabase via lib/db.ts — see getDbBackend().
 */

import { createClient, type Client } from "@libsql/client";

let _cached: Client | null = null;

export function getTursoClient(): Client {
  if (_cached) return _cached;
  const path = process.env.TURSO_DB_PATH;
  const remote = process.env.TURSO_DB_URL;
  const token = process.env.TURSO_AUTH_TOKEN;

  if (path) {
    _cached = createClient({ url: `file:${path}` });
    return _cached;
  }
  if (remote) {
    _cached = createClient({ url: remote, authToken: token });
    return _cached;
  }
  throw new Error(
    "Turso misconfigured: set TURSO_DB_PATH (local file) or TURSO_DB_URL (+ TURSO_AUTH_TOKEN)."
  );
}

export function tursoConfigured(): boolean {
  return !!(process.env.TURSO_DB_PATH || process.env.TURSO_DB_URL);
}
