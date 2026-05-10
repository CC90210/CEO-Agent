/**
 * /api/event-feed
 *
 * GET — returns the most recent agent_events rows for the dashboard feed.
 *       Service-role read with simple time-window + limit. Used by both the
 *       /feed page (server-side initial render) and any client-side poller
 *       that wants a typed snapshot of recent activity.
 *
 * Query params:
 *   since_minutes — default 60, max 1440 (24h)
 *   limit         — default 100, max 500
 *   source        — optional filter on source_agent
 *   event_type    — optional exact-match filter
 */

import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { bad } from "@/lib/api-helpers";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const sinceMinutes = Math.min(
    Math.max(parseInt(url.searchParams.get("since_minutes") || "60", 10) || 60, 1),
    1440,
  );
  const limit = Math.min(
    Math.max(parseInt(url.searchParams.get("limit") || "100", 10) || 100, 1),
    500,
  );
  const source = url.searchParams.get("source");
  const eventType = url.searchParams.get("event_type");

  try {
    const db = getServiceSupabase();
    const cutoff = new Date(Date.now() - sinceMinutes * 60 * 1000).toISOString();

    let q = db
      .from("agent_events")
      .select(
        "id, event_type, source_agent, target_agent, severity, payload, " +
          "published_at, created_at, status",
      )
      .gte("created_at", cutoff)
      .order("created_at", { ascending: false })
      .limit(limit);

    if (source) q = q.eq("source_agent", source);
    if (eventType) q = q.eq("event_type", eventType);

    const { data, error } = await q;
    if (error) return bad(500, error.message);

    return NextResponse.json({
      ok: true,
      window_minutes: sinceMinutes,
      count: (data || []).length,
      rows: data || [],
    });
  } catch (err) {
    return bad(500, err instanceof Error ? err.message : "feed fetch failed");
  }
}
