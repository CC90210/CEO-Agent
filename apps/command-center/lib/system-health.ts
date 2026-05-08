/**
 * A2: System health aggregator. Returns counts of stale agents, offline
 * bridges, down integrations, stale memory files, and unread inbox items
 * so the banner on / can show "3 issues" without making CC navigate
 * across pages.
 *
 * Server-only. Never throws — every signal degrades to 0 on error.
 */

import { getServiceSupabase } from "./supabase-server";
import { getMemoryFreshness, staleCount } from "./memory-freshness";
import { promises as fs } from "node:fs";
import path from "node:path";

const REPO_ROOT = process.env.BRAVO_REPO_ROOT || path.resolve(process.cwd(), "..", "..");
const FRESH_AGENT_MS = 15 * 60 * 1000;
const FRESH_BRIDGE_MS = 5 * 60 * 1000;

export type SystemHealth = {
  staleAgents: number;
  staleAgentNames: string[];
  bridgeOffline: boolean;
  bridgeLastSeenMs: number | null;
  integrationsDown: number;
  memoryStale: number;
  inboxUnread: number;
  totalIssues: number;
};

async function _staleAgents(enabled: string[]): Promise<{ count: number; names: string[] }> {
  try {
    const db = getServiceSupabase();
    const { data } = await db
      .from("agent_state_snapshot")
      .select("agent_name, last_tick_at");
    const rows = (data || []) as Array<{ agent_name: string; last_tick_at: string | null }>;
    const byName = new Map<string, number>();
    for (const r of rows) {
      const ms = r.last_tick_at ? new Date(r.last_tick_at).getTime() : 0;
      byName.set(r.agent_name, ms);
    }
    const names: string[] = [];
    for (const a of enabled) {
      const ms = byName.get(a) || 0;
      if (ms === 0 || Date.now() - ms > FRESH_AGENT_MS) names.push(a);
    }
    return { count: names.length, names };
  } catch {
    return { count: 0, names: [] };
  }
}

async function _bridgeStatus(tenantId: string | null): Promise<{ offline: boolean; lastSeenMs: number | null }> {
  if (!tenantId) return { offline: false, lastSeenMs: null };
  try {
    const db = getServiceSupabase();
    const { data } = await db
      .from("bridge_pairings")
      .select("last_seen_at")
      .eq("tenant_id", tenantId)
      .is("revoked_at", null)
      .order("last_seen_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    const row = data as { last_seen_at: string | null } | null;
    if (!row?.last_seen_at) return { offline: false, lastSeenMs: null };
    const ms = new Date(row.last_seen_at).getTime();
    return { offline: Date.now() - ms > FRESH_BRIDGE_MS, lastSeenMs: ms };
  } catch {
    return { offline: false, lastSeenMs: null };
  }
}

async function _integrationsDown(tenantId: string | null): Promise<number> {
  if (!tenantId) return 0;
  try {
    const db = getServiceSupabase();
    const { data } = await db
      .from("integrations_health")
      .select("status")
      .eq("tenant_id", tenantId);
    return (data || []).filter((r) => {
      const s = String((r as { status?: string }).status || "").toLowerCase();
      return s === "down" || s === "degraded" || s === "error";
    }).length;
  } catch {
    return 0;
  }
}

async function _inboxUnread(): Promise<number> {
  // Filesystem inbox at tmp/agent_inbox/inbox/. A1 wires this into a UI;
  // for now the banner just counts unread .json files.
  try {
    const dir = path.join(REPO_ROOT, "tmp", "agent_inbox", "inbox");
    const entries = await fs.readdir(dir, { withFileTypes: true });
    return entries.filter((e) => e.isFile() && e.name.endsWith(".json")).length;
  } catch {
    return 0;
  }
}

export async function getSystemHealth(opts: {
  tenantId: string | null;
  enabledAgents: string[];
}): Promise<SystemHealth> {
  const [agentInfo, bridge, integrationsDown, memoryRows, inboxUnread] = await Promise.all([
    _staleAgents(opts.enabledAgents),
    _bridgeStatus(opts.tenantId),
    _integrationsDown(opts.tenantId),
    getMemoryFreshness(),
    _inboxUnread(),
  ]);
  const memoryStale = staleCount(memoryRows);
  const totalIssues =
    agentInfo.count +
    (bridge.offline ? 1 : 0) +
    integrationsDown +
    memoryStale +
    (inboxUnread > 0 ? 1 : 0);
  return {
    staleAgents: agentInfo.count,
    staleAgentNames: agentInfo.names,
    bridgeOffline: bridge.offline,
    bridgeLastSeenMs: bridge.lastSeenMs,
    integrationsDown,
    memoryStale,
    inboxUnread,
    totalIssues,
  };
}
