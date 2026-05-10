/**
 * Shared rate-limit + audit-log primitives for the pair-related API routes.
 *
 * Backed by public.pair_attempts (migrations 031 + 034). One table holds
 * attempts from both /api/auth/pair (keyed on OASIS_PROFILE_ID) and
 * /api/auth/pair-code/redeem (keyed on `redeem:<client-ip>`). The
 * `profile_id` column accepts both shapes — see migration 034's table
 * comment for the rationale.
 *
 * Why a shared module: both routes have the same threat surface (bearer
 * credential brute-force) and should enforce the same defense uniformly.
 * Inline-duplicating the helpers in each route guarantees they drift —
 * one place is the right shape.
 *
 * USAGE
 *   import { isRateLimited, recordPairAttempt, clientIp } from "@/lib/pair-rate-limit";
 *
 *   // At the top of POST handler:
 *   const ip = clientIp(req);
 *   if (await isRateLimited(rateKey)) {
 *     await recordPairAttempt(rateKey, "rate_limited", ip);
 *     return bad(429, "rate_limited");
 *   }
 *
 *   // After auth check:
 *   if (failed) {
 *     await recordPairAttempt(rateKey, "invalid_hmac", ip);
 *     return bad(401, ...);
 *   }
 *
 *   // After success:
 *   await recordPairAttempt(rateKey, "ok", ip);
 */

import type { NextRequest } from "next/server";
import { getServiceSupabase } from "./supabase-server";

export const PAIR_RATE_WINDOW_SECONDS = 60;
export const PAIR_RATE_MAX_FAILURES = 10;

export type PairOutcome =
  // /api/auth/pair outcomes (migration 031)
  | "ok"
  | "invalid_hmac"
  | "invalid_bearer"
  | "rate_limited"
  | "missing_headers"
  // /api/auth/pair-code/redeem outcomes (migration 034)
  | "code_invalid_shape"
  | "code_not_found"
  | "code_expired"
  | "code_consumed"
  | "code_redeem_failed";

/** Outcomes that count as failures and accumulate toward the rate limit. */
const FAILURE_OUTCOMES: PairOutcome[] = [
  "invalid_hmac",
  "invalid_bearer",
  "missing_headers",
  "code_invalid_shape",
  "code_not_found",
  "code_expired",
  "code_consumed",
  "code_redeem_failed",
];

/**
 * Resolve the originating client IP from common Vercel/proxy headers.
 * Returns null if no header is set (local dev / direct hit).
 */
export function clientIp(req: NextRequest): string | null {
  const xff = req.headers.get("x-forwarded-for");
  if (xff) {
    const first = xff.split(",")[0]?.trim();
    if (first) return first;
  }
  return req.headers.get("x-real-ip") || null;
}

/**
 * Probabilistic GC: on ~1% of writes, prune rows older than 24h. No cron
 * required, table stays bounded over time, write amplification is
 * negligible (1 extra DELETE per 100 INSERTs). Self-sufficient — the
 * table maintains itself. Gating value chosen so a low-traffic deployment
 * still GCs eventually (one event per ~100 attempts; at 10 attempts/day
 * = ~10 days between sweeps, plenty for a 24h retention window).
 */
const GC_PROBABILITY = 0.01;
const GC_RETENTION_HOURS = 24;

async function _maybeRunGc(db: ReturnType<typeof getServiceSupabase>): Promise<void> {
  if (Math.random() >= GC_PROBABILITY) return;
  try {
    const cutoff = new Date(
      Date.now() - GC_RETENTION_HOURS * 3600 * 1000,
    ).toISOString();
    await db.from("pair_attempts").delete().lt("attempted_at", cutoff);
  } catch {
    // Swallow — GC is best-effort. Table growth is the only consequence
    // and it's bounded by traffic volume.
  }
}

/**
 * Insert one row into public.pair_attempts. Best-effort: never throws,
 * never breaks the request flow even if the insert fails. Logging is
 * defense in depth, not gating logic.
 *
 * Side effect: ~1% of calls also prune rows older than 24h via
 * _maybeRunGc, so the table stays bounded without external cron.
 */
export async function recordPairAttempt(
  rateKey: string,
  outcome: PairOutcome,
  ip: string | null,
): Promise<void> {
  try {
    const db = getServiceSupabase();
    await db.from("pair_attempts").insert({
      profile_id: rateKey,  // column name is historical; holds any rate-limit key
      outcome,
      ip,
    });
    // Fire-and-forget GC — never await directly so a slow DELETE doesn't
    // delay the response. Errors are swallowed inside _maybeRunGc.
    void _maybeRunGc(db);
  } catch {
    // intentional swallow — see docstring
  }
}

/**
 * True if `rateKey` has accumulated >= PAIR_RATE_MAX_FAILURES in the
 * last PAIR_RATE_WINDOW_SECONDS, counting only failure outcomes.
 * Successful pairs don't push toward the limit, so a legitimate operator
 * who pairs successfully and then re-pairs immediately doesn't get
 * locked out by their own activity.
 *
 * Fails OPEN (returns false) on DB errors — preferring availability of
 * legitimate auth over a hard lockout from a transient DB issue.
 */
export async function isRateLimited(rateKey: string): Promise<boolean> {
  if (!rateKey) return false;
  try {
    const db = getServiceSupabase();
    const since = new Date(
      Date.now() - PAIR_RATE_WINDOW_SECONDS * 1000,
    ).toISOString();
    const r = await db
      .from("pair_attempts")
      .select("id", { count: "exact", head: true })
      .eq("profile_id", rateKey)
      .in("outcome", FAILURE_OUTCOMES)
      .gte("attempted_at", since);
    if (r.error) return false;
    return (r.count ?? 0) >= PAIR_RATE_MAX_FAILURES;
  } catch {
    return false;
  }
}
