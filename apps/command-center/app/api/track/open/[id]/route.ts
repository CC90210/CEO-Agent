/**
 * GET /api/track/open/[id] — email open tracking pixel endpoint.
 *
 * Phase 19 of the SunBiz CRM Reconstructor build (2026-05-17). Every
 * outbound email rendered by scripts/send_gateway.py embeds:
 *
 *   <img src=".../api/track/open/<reservation_id>" width=1 height=1 ...>
 *
 * When the recipient's mail client renders the message, the GET hit
 * lands here. We:
 *
 *   1. Look up the interaction row (the reservation_id from
 *      send_gateway) so we can resolve tenant_id + lead_id WITHOUT
 *      trusting the URL parameter.
 *   2. Insert one row into public.email_open_events. Multiple opens
 *      from the same recipient (re-opens, forwards, multi-device) are
 *      expected and not deduplicated at the DB level — the timeline
 *      renders them as engagement-over-time.
 *   3. Flag `suspicious_prefetch=true` when the open arrives < 60s
 *      after the send. Apple Mail Privacy Protection pre-fetches
 *      images so opens look instant — down-weighted by
 *      sequence_runner's on-open-followup logic instead of dropped
 *      entirely.
 *   4. Emit a BRAVO_EMAIL_OPENED event to agent_events so
 *      sequence_runner.py can fast-forward an on-open follow-up step.
 *   5. Return a 1x1 transparent GIF with cache-control:no-store so
 *      every render hits us (no aggressive caching by mail clients).
 *
 * Failure mode: this route is best-effort — a DB write failure must
 * never break the pixel response (the mail client would log a broken
 * image and that's a worse signal than a silently-missed open). Any
 * error is logged server-side and the GIF is still returned.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// 1x1 transparent GIF, base64 — 43 bytes when decoded.
const TRANSPARENT_GIF_B64 = "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";

function gifResponse(): NextResponse {
  const buf = Buffer.from(TRANSPARENT_GIF_B64, "base64");
  return new NextResponse(buf, {
    status: 200,
    headers: {
      "Content-Type": "image/gif",
      "Content-Length": String(buf.length),
      "Cache-Control": "no-store, no-cache, must-revalidate, private",
      "Pragma": "no-cache",
      "Expires": "0",
    },
  });
}

function hashIp(ip: string | null): string | null {
  if (!ip) return null;
  // Tiny non-cryptographic hash so we record a stable identifier
  // without storing the raw IP. djb2 — fine for this use case.
  let h = 5381;
  for (let i = 0; i < ip.length; i++) {
    h = ((h << 5) + h + ip.charCodeAt(i)) & 0xffffffff;
  }
  return "h" + (h >>> 0).toString(16);
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id: rawId } = await params;
  const id = (rawId || "").trim();

  // Always return the pixel; never let body lookup failures leak as
  // a broken image to the recipient.
  if (!id || id.length < 8) return gifResponse();

  try {
    const sb = getServiceSupabase();

    // 1. Resolve tenant_id + lead_id + sent_at from the interaction
    //    row. send_gateway writes interactions/lead_interactions with
    //    id=reservation_id; the exact table name varies across legacy
    //    migrations so we probe lead_interactions first (the canonical
    //    table in current production), falling back to interactions.
    let tenantId: string | null = null;
    let leadId: string | null = null;
    let sentAtMs: number | null = null;

    const lookupTables = ["lead_interactions", "interactions"];
    for (const table of lookupTables) {
      const { data, error } = await sb
        .from(table)
        .select("id, tenant_id, lead_id, created_at, sent_at")
        .eq("id", id)
        .maybeSingle();
      if (!error && data) {
        tenantId = (data as any).tenant_id || null;
        leadId = (data as any).lead_id || null;
        const ts = (data as any).sent_at || (data as any).created_at;
        if (ts) sentAtMs = new Date(ts).getTime();
        break;
      }
    }

    if (!tenantId) return gifResponse(); // unknown id — silently drop, return pixel

    const ua = req.headers.get("user-agent") || null;
    const fwd = req.headers.get("x-forwarded-for") || null;
    const ip = fwd ? fwd.split(",")[0].trim() : null;
    const ipHash = hashIp(ip);
    const nowMs = Date.now();
    const suspicious =
      sentAtMs !== null && nowMs - sentAtMs < 60_000; // <60s = APMP-likely prefetch

    // Insert with ON CONFLICT DO NOTHING semantics via upsert + the
    // partial unique index (outbound_message_id, ip_hash) added in
    // migration 050. Re-opens from the same recipient don't add new
    // rows; the operator timeline cares "did they open" not the
    // exact re-open count. Anonymous opens (ip_hash null) skip the
    // index and always insert — over-counting anon is the right side
    // of the trade-off.
    await sb
      .from("email_open_events")
      .upsert(
        {
          tenant_id: tenantId,
          outbound_message_id: id,
          lead_id: leadId,
          user_agent: ua,
          ip_hash: ipHash,
          suspicious_prefetch: suspicious,
        },
        { onConflict: "outbound_message_id,ip_hash", ignoreDuplicates: true },
      );

    // Emit on the event bus so sequence_runner can react to opens
    // without polling email_open_events on every tick. Soft-fail if
    // agent_events isn't reachable in this deploy.
    //
    // Payload follows the canonical agent_event shape (tenant_id +
    // entity + record_id) so the existing drip enrollment path in
    // sequence_runner.enrollment_tick picks it up for free if a drip
    // is configured with trigger_event='BRAVO_EMAIL_OPENED' — no new
    // handler needed in the daemon. Suspicious prefetches are flagged
    // in payload so drip authors can filter them out via
    // trigger_filter if desired.
    try {
      await sb.from("agent_events").insert({
        tenant_id: tenantId,
        event_type: "BRAVO_EMAIL_OPENED",
        payload: {
          tenant_id: tenantId,
          entity: "lead",
          record_id: leadId,
          lead_id: leadId,
          outbound_message_id: id,
          suspicious_prefetch: suspicious,
        },
      });
    } catch {
      // event-bus optional
    }
  } catch (err) {
    // Best-effort — log + serve pixel.
    console.error("[track/open] insert failed", err);
  }

  return gifResponse();
}
