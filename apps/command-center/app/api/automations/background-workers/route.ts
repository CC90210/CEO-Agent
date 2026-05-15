/**
 * GET /api/automations/background-workers — operator's local PM2 daemons
 * + standalone Skool daemon status, sourced from integrations_health rows
 * the bridge daemon writes on each /api/bridge/ping cycle (60s).
 *
 * Why integrations_health (and not a fresh remote probe): the operator's
 * machine is the source of truth — only it can see its own PM2 list. The
 * bridge already pushes that snapshot on every heartbeat (see
 * bravo_cli/local_bridge.py detect_pm2_daemons), so the dashboard just
 * reads back the last-pinged value.
 *
 * Response shape:
 *   {
 *     ok: true,
 *     bridge_online: boolean,        // bridge_pairings.last_seen_at < 120s
 *     last_seen_at: string | null,
 *     workers: Array<{
 *       service: string,             // "pm2.sequence-runner", "skool_engine"
 *       label: string,               // operator-friendly name
 *       status: "healthy" | "degraded" | "down" | "unconfigured",
 *       metadata: Record<string, unknown>,
 *       last_ping_at: string | null,
 *       purpose: string,             // 1-line "what this daemon does"
 *     }>,
 *   }
 *
 * Operator-only: scoped to the session's tenant_id via user_profiles. Empire
 * vs tenant doesn't matter here — each tenant's bridge pushes its own row.
 */

import { NextResponse } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Authoritative list of expected background workers + their purpose copy.
 * Mirrors ecosystem.config.js. Keep these two files in sync — adding a
 * PM2 daemon there without adding the description here just means it
 * shows up as an "unknown background worker" on the dashboard.
 */
const EXPECTED_WORKERS: Array<{
  service: string;
  label: string;
  purpose: string;
}> = [
  {
    service: "pm2.bravo-scheduler",
    label: "Empire scheduler",
    purpose: "Polls cron_jobs every 60s on the operator's machine and executes due jobs.",
  },
  {
    service: "pm2.bravo-telegram",
    label: "Telegram bridge",
    purpose: "Bridges Telegram messages to the chat backbone. Windows-default, Mac cold-standby.",
  },
  {
    service: "pm2.claude-bridge",
    label: "Local chat bridge",
    purpose: "localhost:9100 chat HTTP server — warm-pool Claude Code subprocess + tool proxy.",
  },
  {
    service: "pm2.claude-bridge-ping",
    label: "Bridge heartbeat + tenant cron poller",
    purpose: "Heartbeats to /api/bridge/ping every 60s and polls tenant_cron_jobs for due work.",
  },
  {
    service: "pm2.event-router",
    label: "Event router",
    purpose: "Tails Postgres agent_events into state/event_router.log — feeds /feed page.",
  },
  {
    service: "pm2.override-consumer",
    label: "Override consumer",
    purpose: "Pulls Approve/Deny decisions for exec_guard-blocked actions from Supabase to local state DB.",
  },
  {
    service: "pm2.sequence-runner",
    label: "Sequence runner",
    purpose: "Drip-campaign engine — enrolls leads on stage changes, fires due sequence steps.",
  },
  {
    service: "pm2.lender-response-classifier",
    label: "Lender response classifier",
    purpose: "Polls Gmail threads for shop-out replies, classifies via Claude Haiku 4.5.",
  },
  {
    service: "skool_engine",
    label: "Skool daemon",
    purpose: "Standalone (NOT in PM2 — owns its own lock). Posts/replies in CC's Skool community.",
  },
];

export async function GET() {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const db = getServiceSupabase();
  const profile = await db
    .from("user_profiles")
    .select("id, tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const profileId = (profile.data as { id: string | null } | null)?.id ?? null;
  const tenantId = (profile.data as { tenant_id: string | null } | null)?.tenant_id ?? null;
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });

  // Bridge liveness — the heartbeat tells us when the bridge last pushed
  // anything. Older than 2 minutes means daemon snapshots are stale.
  const pairing = await db
    .from("bridge_pairings")
    .select("last_seen_at")
    .eq("tenant_id", tenantId)
    .is("revoked_at", null)
    .order("last_seen_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  const lastSeenAt = (pairing.data as { last_seen_at: string | null } | null)?.last_seen_at ?? null;
  const bridgeOnline = lastSeenAt
    ? Date.now() - new Date(lastSeenAt).getTime() < 120_000
    : false;

  // integrations_health is keyed (profile_id, service). When the bridge
  // hasn't pushed (no profile_id, or no rows), fall back to "unconfigured".
  const services = EXPECTED_WORKERS.map((w) => w.service);
  let healthMap = new Map<
    string,
    { status: string; metadata: Record<string, unknown>; last_ping_at: string | null }
  >();
  if (profileId) {
    const rows = await db
      .from("integrations_health")
      .select("service, status, metadata, last_ping_at")
      .eq("profile_id", profileId)
      .in("service", services);
    if (!rows.error && Array.isArray(rows.data)) {
      for (const r of rows.data as Array<{
        service: string;
        status: string;
        metadata: Record<string, unknown> | null;
        last_ping_at: string | null;
      }>) {
        healthMap.set(r.service, {
          status: r.status,
          metadata: r.metadata || {},
          last_ping_at: r.last_ping_at,
        });
      }
    }
  }

  const workers = EXPECTED_WORKERS.map((w) => {
    const h = healthMap.get(w.service);
    return {
      service: w.service,
      label: w.label,
      purpose: w.purpose,
      status: (h?.status as "healthy" | "degraded" | "down" | "unconfigured") || "unconfigured",
      metadata: h?.metadata || {},
      last_ping_at: h?.last_ping_at || null,
    };
  });

  return NextResponse.json({
    ok: true,
    bridge_online: bridgeOnline,
    last_seen_at: lastSeenAt,
    workers,
  });
}
