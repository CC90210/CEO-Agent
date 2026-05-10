import { NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const STATE_API_URL = process.env.STATE_API_URL || "http://state-api:8500";

/**
 * V6 state-health endpoint with a two-tier read path:
 *
 *   1. PREFERRED — proxy `state-api:8500/status` (canonical FastAPI service
 *      that wraps `state_manager.status()` + `memory_retriever.status()` +
 *      live guard-log tails). Available locally and inside the Cloud Compose
 *      stack.
 *
 *   2. FALLBACK — read directly from Supabase tables (`agent_state_snapshot`,
 *      `session_logs`, `agent_events`). Used on Vercel where state-api is
 *      NOT reachable. The dashboard still shows V6 state, just without the
 *      local-only fields (FTS5 index health, guard audit-log tails) which
 *      have no Supabase mirror.
 *
 * The response is shape-compatible with `system-health/page.tsx`'s
 * `StateHealthResponse` type in both paths. A `source` field on the
 * envelope tells the operator which path delivered the data.
 */
export async function GET() {
  // Path 1 — state-api passthrough.
  try {
    const res = await fetch(`${STATE_API_URL}/status`, {
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    if (res.ok) {
      const body = await res.json();
      return NextResponse.json({ available: true, source: "state-api", ...body });
    }
  } catch {
    // fall through to Supabase mirror — state-api unreachable from Vercel
    // is the expected, not exceptional, case in production.
  }

  // Path 2 — Supabase mirror fallback.
  try {
    const data = await fetchFromSupabaseMirror();
    return NextResponse.json(data);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "supabase fallback failed";
    return NextResponse.json(
      {
        available: false,
        error: msg,
        hint:
          "state-api unreachable AND Supabase mirror fetch failed. Check " +
          "BRAVO_SUPABASE_URL + service role env vars on Vercel.",
      },
      { status: 200 },
    );
  }
}

/**
 * Build a `StateHealthResponse`-shaped payload from Supabase tables.
 * Fields the mirror DOESN'T carry (FTS5 stats, guard logs) are omitted —
 * the page renders those sections conditionally.
 */
async function fetchFromSupabaseMirror() {
  const db = getServiceSupabase();

  const [agentSnap, sessionCount, eventCount, lastEvent, lastSession] =
    await Promise.all([
      db
        .from("agent_state_snapshot")
        .select(
          "agent_name, tick_count, last_tick_at, working_memory, health_status",
        )
        .order("last_tick_at", { ascending: false }),
      db.from("session_logs").select("id", { count: "exact", head: true }),
      db.from("agent_events").select("id", { count: "exact", head: true }),
      db
        .from("agent_events")
        .select("published_at, source_agent, event_type")
        .order("published_at", { ascending: false })
        .limit(1)
        .maybeSingle(),
      db
        .from("session_logs")
        .select("session_date, agent_interface, summary, created_at")
        .order("created_at", { ascending: false })
        .limit(1)
        .maybeSingle(),
    ]);

  const agents = (agentSnap.data || []).map((row) => {
    const focus =
      (row.working_memory as { last_focus?: string } | null)?.last_focus ?? "";
    const healthy = row.health_status === "healthy";
    return {
      agent: row.agent_name as string,
      status: healthy ? "working" : "idle",
      current_focus: focus,
      last_heartbeat: row.last_tick_at as string,
      tick_count: row.tick_count as number,
      health: healthy ? "green" : "yellow",
    };
  });

  return {
    available: true,
    source: "supabase-mirror",
    v6_mode: "on",
    deploy_target: "vercel",
    state_db: {
      exists: true,
      agents,
      session_log_count: sessionCount.count ?? 0,
      transaction_count: eventCount.count ?? 0,
      open_tasks_by_bucket: {},
      last_transaction: lastEvent.data
        ? {
            ts: lastEvent.data.published_at as string,
            actor: (lastEvent.data.source_agent as string) ?? "unknown",
            op: lastEvent.data.event_type as string,
            source_script: "agent_events",
          }
        : undefined,
      last_session_log: lastSession.data
        ? {
            ts: lastSession.data.created_at as string,
            agent: (lastSession.data.agent_interface as string) ?? "unknown",
            note: (lastSession.data.summary as string) ?? "",
          }
        : undefined,
    },
    // index_db (FTS5) and guards (jsonl tails) are local-only — omit
    // them so the page renders their sections in a "remote" state.
    index_db: { exists: false },
  };
}
