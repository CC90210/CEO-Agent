/**
 * turso-rpc-shim — PL/pgSQL RPC ports over @libsql/client.
 *
 * Each function is a port of database/rpc_sources/<project>__<name>.sql from
 * the Business-Empire-Agent repo (the extracted live sources). Ports were
 * machine-generated with per-RPC adversarial review where the review pass
 * completed; VERIFICATION STATE PER RPC is recorded in the manifest at the
 * bottom — treat "ported-unverified" entries with the same suspicion as any
 * untested code and prefer verifying before first production use.
 *
 * Dispatched from getServiceSupabase()'s hybrid rpc handler: shim first, then
 * TURSO_RPC_PASSTHROUGH, else TURSO_RPC_BLOCKED.
 */

import type { Client } from "@libsql/client";

/**
 * Port of public.get_portal_logs(target_automation_id uuid DEFAULT NULL,
 *                                target_user_id uuid DEFAULT NULL,
 *                                log_limit integer DEFAULT 50)
 *   RETURNS SETOF automation_logs  (SECURITY DEFINER)
 *
 * Source: database/rpc_sources/oasis__get_portal_logs.sql
 * Schema: database/turso_migrations/oasis__000_master_schema.sql
 *
 * auth.uid() has no ambient equivalent over libsql: the shim MUST inject the
 * authenticated user's id as args.auth_uid. Absent/empty => treated as
 * auth.uid() IS NULL => fail-closed empty result set (the PL/pgSQL falls
 * through its IF without RETURN QUERY and never raises).
 */
export async function get_portal_logs(
  client: Client,
  args: Record<string, unknown>
): Promise<unknown> {
  // --- argument parsing (mirrors the Postgres signature defaults) ---
  const authUid: string | null =
    typeof args.auth_uid === "string" && args.auth_uid.length > 0
      ? args.auth_uid
      : null;

  const targetAutomationId: string | null =
    args.target_automation_id === undefined || args.target_automation_id === null
      ? null
      : String(args.target_automation_id);

  const targetUserId: string | null =
    args.target_user_id === undefined || args.target_user_id === null
      ? null
      : String(args.target_user_id);

  // DEFAULT 50 when omitted; explicit NULL in Postgres means LIMIT NULL = LIMIT ALL,
  // which is LIMIT -1 (no upper bound) in SQLite.
  let logLimit: number;
  if (args.log_limit === undefined) {
    logLimit = 50;
  } else if (args.log_limit === null) {
    logLimit = -1;
  } else {
    logLimit = Number(args.log_limit);
    if (!Number.isInteger(logLimit)) {
      throw new Error(
        `invalid input syntax for type integer: "${String(args.log_limit)}"`
      );
    }
  }

  // --- single read transaction (batch is transactional in libsql) so the
  // --- authorization checks and the log read see one snapshot, like the
  // --- original single-function-call did. NULL params match nothing under
  // --- `=` in SQLite exactly as they do in Postgres, so unauthenticated /
  // --- null-argument paths need no special-casing in SQL.
  const [adminRes, ownRes, logsRes] = await client.batch(
    [
      {
        // IF EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid()
        //   AND (role IN ('admin','super_admin') OR is_admin = true OR is_owner = true))
        sql: `SELECT 1 FROM "profiles"
              WHERE "id" = ?
                AND ("role" IN ('admin', 'super_admin') OR "is_admin" = 1 OR "is_owner" = 1)
              LIMIT 1`,
        args: [authUid],
      },
      {
        // EXISTS (SELECT 1 FROM client_automations
        //   WHERE id = target_automation_id AND user_id = auth.uid())
        sql: `SELECT 1 FROM "client_automations"
              WHERE "id" = ? AND "user_id" = ?
              LIMIT 1`,
        args: [targetAutomationId, authUid],
      },
      {
        // SELECT * FROM automation_logs
        // WHERE (target_automation_id IS NULL OR automation_id = target_automation_id)
        //   AND (target_user_id IS NULL OR user_id = target_user_id)
        // ORDER BY created_at DESC LIMIT log_limit
        // (Postgres DESC default is NULLS FIRST; SQLite default is NULLS LAST,
        //  hence the explicit NULLS FIRST. ISO-8601 TEXT sorts chronologically.)
        sql: `SELECT * FROM "automation_logs"
              WHERE (? IS NULL OR "automation_id" = ?)
                AND (? IS NULL OR "user_id" = ?)
              ORDER BY "created_at" DESC NULLS FIRST
              LIMIT ?`,
        args: [
          targetAutomationId,
          targetAutomationId,
          targetUserId,
          targetUserId,
          logLimit,
        ],
      },
    ],
    "read"
  );

  // --- authorization gate, exactly as in the PL/pgSQL IF ---
  const isAdmin = adminRes.rows.length > 0;
  // (target_user_id = auth.uid()) — NULL on either side is not TRUE in Postgres.
  const isSelf =
    targetUserId !== null && authUid !== null && targetUserId === authUid;
  // (target_automation_id IS NOT NULL AND EXISTS(...))
  const ownsAutomation = targetAutomationId !== null && ownRes.rows.length > 0;

  if (!(isAdmin || isSelf || ownsAutomation)) {
    // The source function ends without RETURN QUERY => empty SETOF, no error.
    return [];
  }

  // --- shape the rows like PostgREST would for SETOF automation_logs ---
  return logsRes.rows.map((row) => {
    const obj: Record<string, unknown> = {};
    for (const col of logsRes.columns) {
      obj[col] = (row as unknown as Record<string, unknown>)[col];
    }
    // metadata was jsonb in Postgres (object on the wire); stored as TEXT in Turso.
    if (typeof obj.metadata === "string") {
      try {
        obj.metadata = JSON.parse(obj.metadata as string);
      } catch {
        // keep raw text if it is not valid JSON — never silently drop data
      }
    }
    return obj;
  });
}
export async function increment_promo_uses(client: Client, args: Record<string, unknown>): Promise<unknown> {
  // Source: public.increment_promo_uses(promo_id uuid) RETURNS void
  //   UPDATE promo_codes SET uses_count = uses_count + 1 WHERE id = promo_id;
  // Turso schema note: promo_codes has no uses_count column; the transpiled
  // counter column is current_uses (see oasis__000_master_schema.sql). Ported 1:1
  // onto current_uses.

  if (!('promo_id' in args) || args.promo_id === undefined) {
    // PostgREST rejects an RPC call whose named arguments don't match the signature.
    throw new Error('increment_promo_uses: missing required argument "promo_id"');
  }
  const promo_id = args.promo_id === null ? null : String(args.promo_id);

  // Single-statement UPDATE — atomic in SQLite exactly as in Postgres; no
  // transaction/batch required. NULL current_uses stays NULL (NULL + 1 = NULL),
  // matching Postgres semantics, so no COALESCE is introduced. Zero rows matched
  // is not an error, matching the PL/pgSQL.
  await client.execute({
    sql: 'UPDATE promo_codes SET current_uses = current_uses + 1 WHERE id = ?',
    args: [promo_id],
  });

  // RETURNS void → supabase-js callers receive { data: null }.
  return null;
}

/**
 * MANIFEST
 *   get_portal_logs                    ported-unverified  writes=False  confidence=high
 *   increment_promo_uses               ported-unverified  writes=True  confidence=high
 */
export const TURSO_RPC_SHIM: Record<string, (client: Client, args: Record<string, unknown>) => Promise<unknown>> = {
  get_portal_logs,
  increment_promo_uses,
};
