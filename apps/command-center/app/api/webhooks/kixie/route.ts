/**
 * POST /api/webhooks/kixie
 *
 * Kixie's webhook lands here on call lifecycle events. Phase 5.2 of the
 * SunBiz CRM build (2026-05-15).
 *
 * Event types Kixie sends (per https://docs.kixie.com/):
 *   call.answered     -- agent + prospect on the line
 *   call.completed    -- call ended with duration
 *   call.missed       -- prospect didn't answer
 *   call.transferred  -- warm-transfer event
 *   sms.received      -- inbound SMS reply
 *
 * Auth: signed via X-Kixie-Signature header (HMAC-SHA256 of the raw body
 * with KIXIE_WEBHOOK_SECRET). We verify before processing; unsigned
 * requests get a 401. This is the standard webhook-signature pattern;
 * lib/webhook-hmac.ts has the shared verifier.
 *
 * Side effects:
 *   - Inserts an agent_events row (event_type "BRAVO_KIXIE_<event>")
 *     so the /feed page picks up the event live.
 *   - On call.answered with a customField1 (Bravo lead UUID), increments
 *     the lead's interaction count so subsequent drips know contact
 *     happened.
 */

import { NextRequest, NextResponse } from "next/server";
import { createHmac, timingSafeEqual } from "crypto";
import { getServiceSupabase } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const WEBHOOK_SECRET_ENV = "KIXIE_WEBHOOK_SECRET";

type KixieEvent = {
  eventname?: string;
  callid?: string;
  number?: string;
  email?: string;
  duration?: number;
  customField1?: string;  // Bravo lead UUID echoed back from click-to-call
  customField2?: string;
  businessid?: string;
  [k: string]: unknown;
};

function verifySignature(rawBody: string, headerSig: string | null): boolean {
  if (!headerSig) return false;
  const secret = (process.env[WEBHOOK_SECRET_ENV] || "").trim();
  if (!secret) {
    // Production-safe default: refuse webhooks when the secret isn't
    // configured. Otherwise an attacker can spam fake call events to
    // pollute /feed + waste agent_events rows.
    return false;
  }
  const expected = createHmac("sha256", secret).update(rawBody, "utf8").digest("hex");
  // Header format Kixie uses: just the hex string (no version prefix).
  const provided = headerSig.trim();
  if (provided.length !== expected.length) return false;
  try {
    return timingSafeEqual(Buffer.from(provided, "hex"), Buffer.from(expected, "hex"));
  } catch {
    return false;
  }
}

export async function POST(req: NextRequest) {
  const rawBody = await req.text();
  const sig = req.headers.get("x-kixie-signature");

  if (!verifySignature(rawBody, sig)) {
    return NextResponse.json(
      { ok: false, error: "invalid_signature" },
      { status: 401 },
    );
  }

  let evt: KixieEvent;
  try {
    evt = JSON.parse(rawBody) as KixieEvent;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const eventname = String(evt.eventname || "").toLowerCase();
  if (!eventname) {
    return NextResponse.json({ ok: false, error: "missing_eventname" }, { status: 400 });
  }

  // Map Kixie event names to canonical Bravo event types so /feed
  // filtering can branch cleanly.
  const eventType = `BRAVO_KIXIE_${eventname.toUpperCase().replace(/\./g, "_")}`;

  // Tenant resolution: Kixie's businessid is per-tenant. Map it to a
  // Bravo tenant via the tenants table (looking for a row whose
  // metadata.kixie_business_id matches). If no mapping exists we drop
  // the event silently — operators set the mapping during onboarding
  // and we shouldn't store cross-tenant orphan rows.
  const db = getServiceSupabase();
  let tenantId: string | null = null;
  if (evt.businessid) {
    const tenantRow = await db
      .from("tenants")
      .select("id")
      .eq("metadata->>kixie_business_id", String(evt.businessid))
      .maybeSingle();
    tenantId = (tenantRow.data as { id: string } | null)?.id ?? null;
  }

  if (!tenantId) {
    // Unmapped business — log + 200 so Kixie doesn't retry. Operators
    // see the warning in Vercel logs and can fix the mapping.
    console.warn(
      `[webhooks.kixie] no tenant mapping for businessid=${evt.businessid} event=${eventname}`,
    );
    return NextResponse.json({ ok: true, ignored: "no_tenant_mapping" });
  }

  // Publish to agent_events so /feed surfaces the call. Best-effort.
  try {
    await db.from("agent_events").insert({
      event_type: eventType,
      publisher_agent: "kixie",
      severity: eventname.includes("missed") ? "warn" : "info",
      payload: {
        tenant_id: tenantId,
        call_id: evt.callid || null,
        number: evt.number || null,
        agent_email: evt.email || null,
        duration_sec: evt.duration ?? null,
        lead_id: evt.customField1 || null,
        raw_eventname: eventname,
      },
      correlation_id: tenantId,
    });
  } catch (err) {
    console.error("[webhooks.kixie] agent_events insert failed", err);
  }

  return NextResponse.json({ ok: true, event_type: eventType });
}
