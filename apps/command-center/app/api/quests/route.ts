/**
 * GET /api/quests — read-only quest list for the OASIS Town Quest Log.
 *
 * Public path (per the Phase 5 directive). Returns CC's live ACTIVE_TASKS.md
 * state as rows from the Supabase `oasis_quests` table. The OASIS Town
 * Convex backend polls this every 60 seconds; the frontend renders a
 * Quest Log overlay panel.
 *
 * Query params:
 *   status?     'open' | 'completed' | 'archived'   (default: not 'archived')
 *   bucket?     substring filter on bucket name
 *   limit?      default 200, max 500
 *   since_ms?   only quests updated_at > since_ms (cursor-style polling)
 */

import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { bad } from "@/lib/api-helpers";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const status = url.searchParams.get("status");
  const bucket = url.searchParams.get("bucket");
  const sinceMs = url.searchParams.get("since_ms");
  const limit = Math.min(
    Math.max(parseInt(url.searchParams.get("limit") || "200", 10) || 200, 1),
    500,
  );

  try {
    const db = getServiceSupabase();
    let q = db
      .from("oasis_quests")
      .select(
        "id, bucket, title, owner, status, source_file, source_line, " +
          "first_seen_at, completed_at, updated_at",
      )
      .order("updated_at", { ascending: false })
      .limit(limit);
    if (status) q = q.eq("status", status);
    else q = q.neq("status", "archived");
    if (bucket) q = q.ilike("bucket", `%${bucket}%`);
    if (sinceMs) {
      const iso = new Date(parseInt(sinceMs, 10)).toISOString();
      q = q.gt("updated_at", iso);
    }
    const { data, error } = await q;
    if (error) return bad(500, error.message);

    return NextResponse.json({
      ok: true,
      count: (data || []).length,
      rows: data || [],
    });
  } catch (err) {
    return bad(500, err instanceof Error ? err.message : "quests fetch failed");
  }
}
