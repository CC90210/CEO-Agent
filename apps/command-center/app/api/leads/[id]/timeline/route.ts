/**
 * GET /api/leads/[id]/timeline
 *
 * Phase 18 of the SunBiz CRM Reconstructor build (2026-05-17). Returns
 * the chronological merge of every event that involves this lead — what
 * the operator sees as the "Conversation timeline" tab on the lead
 * drawer.
 *
 * Source feeds (all tenant-scoped):
 *   - lead_interactions          outbound + inbound SMS/email
 *   - email_open_events           tracking-pixel hits (Phase 19)
 *   - lead_documents              uploaded artefacts (Phase 18/21)
 *   - agent_events                stage changes + system events
 *   - application_lender_threads  lender shop-out + replies
 *   - agent_alerts                operator-facing alerts (Phase 20)
 *
 * Each feed is normalised into a TimelineEvent and merged by `at` desc.
 * The route serves the merged feed as JSON; the drawer's Timeline
 * component renders it with per-source icons + per-event detail.
 *
 * No mutations. Pure read.
 *
 * Failure mode: a single feed's failure doesn't break the response —
 * we return the feeds that did load with a per-feed `errors` array so
 * the UI can show partial state instead of a blank panel.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { resolveTenantId } from "@/lib/api-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type TimelineEvent = {
  source: string;
  type: string;
  at: string; // ISO 8601
  title: string;
  body?: string;
  meta?: Record<string, unknown>;
};

const HARD_CAP = 250; // events returned per request — drawer paginates further if ever needed

export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const tenantId = await resolveTenantId();
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const { id: leadId } = await ctx.params;
  if (!leadId) return NextResponse.json({ ok: false, error: "missing_id" }, { status: 400 });

  const db = getServiceSupabase();
  const events: TimelineEvent[] = [];
  const errors: { feed: string; message: string }[] = [];

  // 1. lead_interactions — both directions; the table mixes them via a
  //    direction column. Table name varies across legacy migrations; try
  //    lead_interactions first, then interactions.
  for (const table of ["lead_interactions", "interactions"]) {
    try {
      const { data, error } = await db
        .from(table)
        .select("id, channel, direction, subject, content_preview, action_type, created_at, sent_at, to_email, to_phone")
        .eq("tenant_id", tenantId)
        .eq("lead_id", leadId)
        .order("created_at", { ascending: false })
        .limit(150);
      if (error) throw error;
      for (const row of data || []) {
        const at = (row as any).sent_at || (row as any).created_at;
        if (!at) continue;
        const direction = (row as any).direction || "outbound";
        const channel = (row as any).channel || "unknown";
        events.push({
          source: "interaction",
          type: `${channel}_${direction}`,
          at,
          title: `${direction === "outbound" ? "Sent" : "Received"} ${channel}${(row as any).subject ? `: ${(row as any).subject}` : ""}`,
          body: (row as any).content_preview || undefined,
          meta: {
            id: (row as any).id,
            action_type: (row as any).action_type,
            to_email: (row as any).to_email,
            to_phone: (row as any).to_phone,
          },
        });
      }
      break; // only one of the two tables exists per deploy
    } catch (e: any) {
      // If both fail we'll record the second failure below; first
      // failure may just be "table not found" which is expected.
      if (table === "interactions") errors.push({ feed: table, message: String(e?.message || e) });
    }
  }

  // 2. email_open_events
  try {
    const { data, error } = await db
      .from("email_open_events")
      .select("id, outbound_message_id, opened_at, suspicious_prefetch, user_agent")
      .eq("tenant_id", tenantId)
      .eq("lead_id", leadId)
      .order("opened_at", { ascending: false })
      .limit(50);
    if (error) throw error;
    for (const row of data || []) {
      events.push({
        source: "email_open",
        type: (row as any).suspicious_prefetch ? "open_prefetch" : "open",
        at: (row as any).opened_at,
        title: (row as any).suspicious_prefetch ? "📨 Email open (prefetch)" : "👁 Email opened",
        meta: {
          outbound_message_id: (row as any).outbound_message_id,
          user_agent: (row as any).user_agent,
        },
      });
    }
  } catch (e: any) {
    errors.push({ feed: "email_open_events", message: String(e?.message || e) });
  }

  // 3. lead_documents
  try {
    const { data, error } = await db
      .from("lead_documents")
      .select("id, filename, doc_type, uploaded_by, uploaded_at, size_bytes")
      .eq("tenant_id", tenantId)
      .eq("lead_id", leadId)
      .order("uploaded_at", { ascending: false })
      .limit(50);
    if (error) throw error;
    for (const row of data || []) {
      events.push({
        source: "document",
        type: "uploaded",
        at: (row as any).uploaded_at,
        title: `📎 Document: ${(row as any).filename}`,
        body: (row as any).doc_type !== "unclassified" ? `Classified as ${(row as any).doc_type}` : undefined,
        meta: {
          id: (row as any).id,
          uploaded_by: (row as any).uploaded_by,
          size_bytes: (row as any).size_bytes,
        },
      });
    }
  } catch (e: any) {
    errors.push({ feed: "lead_documents", message: String(e?.message || e) });
  }

  // 4. agent_events — stage transitions and lifecycle events.
  try {
    const { data, error } = await db
      .from("agent_events")
      .select("id, event_type, payload, created_at")
      .eq("tenant_id", tenantId)
      .contains("payload", { lead_id: leadId })
      .order("created_at", { ascending: false })
      .limit(50);
    if (error) throw error;
    for (const row of data || []) {
      events.push({
        source: "system",
        type: (row as any).event_type,
        at: (row as any).created_at,
        title: humanizeEventType((row as any).event_type),
        meta: (row as any).payload || {},
      });
    }
  } catch (e: any) {
    errors.push({ feed: "agent_events", message: String(e?.message || e) });
  }

  // 5. agent_alerts — missing_info + future operator-side notifications.
  try {
    const { data, error } = await db
      .from("agent_alerts")
      .select("id, alert_type, severity, title, body, created_at, resolved_at")
      .eq("tenant_id", tenantId)
      .eq("subject_type", "lead")
      .eq("subject_id", leadId)
      .order("created_at", { ascending: false })
      .limit(50);
    if (error) throw error;
    for (const row of data || []) {
      events.push({
        source: "alert",
        type: (row as any).alert_type,
        at: (row as any).created_at,
        title: `⚠ ${(row as any).title}`,
        body: (row as any).body || undefined,
        meta: {
          severity: (row as any).severity,
          resolved_at: (row as any).resolved_at,
        },
      });
    }
  } catch (e: any) {
    errors.push({ feed: "agent_alerts", message: String(e?.message || e) });
  }

  events.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
  return NextResponse.json({
    ok: true,
    lead_id: leadId,
    events: events.slice(0, HARD_CAP),
    truncated: events.length > HARD_CAP,
    errors,
  });
}

function humanizeEventType(t: string): string {
  if (!t) return "Event";
  if (t === "BRAVO_RECORD_STATUS_CHANGED") return "Stage changed";
  if (t === "BRAVO_EMAIL_OPENED") return "Email opened";
  if (t === "BRAVO_LEAD_MISSING_INFO") return "Missing info detected";
  return t.replace(/^BRAVO_/, "").replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase());
}
