/**
 * POST /api/inbound/n8n
 *
 * The n8n inbound bridge. The "OASIS Inbound Qualifier" workflow POSTs every
 * classified email here; we authenticate via shared-secret header, then call
 * the record_inbound_from_n8n_v2 RPC which:
 *   1. Validates the secret hash
 *   2. Finds-or-creates a lead for the from email
 *   3. Records the interaction with classification metadata
 *   4. Bumps integrations_health for the green dot in Settings
 *
 * Headers required:
 *   x-oasis-profile-id  — the profile the webhook is owned by (uuid)
 *   x-oasis-secret      — the raw secret (we sha256 it server-side)
 *
 * Body schema:
 *   {
 *     from_email: string,
 *     subject: string,
 *     body: string,
 *     classification: { intent, sentiment, priority, ... },  // from n8n classifier
 *     received_at?: ISO timestamp                             // optional, defaults now()
 *   }
 *
 * Returns: { ok: true, interaction_id } on success, { ok: false, error } on auth/validation fail
 */

import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { bad, sha256 } from "@/lib/api-helpers";

export const dynamic = "force-dynamic";
export const runtime = "nodejs"; // service role + sha256 → Node, not edge

type IncomingPayload = {
  from_email?: string;
  subject?: string;
  body?: string;
  classification?: Record<string, unknown>;
  received_at?: string;
};

// sha256 + bad imported from @/lib/api-helpers (consolidated 2026-05-09).

export async function POST(req: NextRequest) {
  // 1. Auth headers
  const profileId = req.headers.get("x-oasis-profile-id");
  const rawSecret = req.headers.get("x-oasis-secret");
  if (!profileId || !rawSecret) {
    return bad(401, "missing x-oasis-profile-id or x-oasis-secret header");
  }
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(profileId)
  ) {
    return bad(400, "x-oasis-profile-id is not a valid UUID");
  }

  // 2. Body parse
  let body: IncomingPayload;
  try {
    body = (await req.json()) as IncomingPayload;
  } catch {
    return bad(400, "body must be JSON");
  }
  if (!body.from_email || !body.subject) {
    return bad(400, "from_email and subject are required");
  }

  // 2.5. Junk-sender filter — reject the obvious non-leads BEFORE the RPC
  // creates a lead row. Transactional senders (noreply@kraken, billing@stripe,
  // notifications@github, etc.) and test/example domains were polluting the
  // pipeline. The filter is conservative — anything ambiguous still gets
  // through and creates a lead.
  const junk = isJunkSender(body.from_email, body.subject);
  if (junk) {
    return NextResponse.json({
      ok: true,
      filtered: true,
      reason: junk,
      interaction_id: null,
    });
  }

  // 3. Hash secret + call RPC (the RPC re-validates the hash against the table)
  const secretHash = sha256(rawSecret);
  const db = getServiceSupabase();
  const r = await db.rpc("record_inbound_from_n8n_v2", {
    p_profile_id: profileId,
    p_secret_hash: secretHash,
    p_from_email: body.from_email,
    p_subject: body.subject,
    p_body: body.body || "",
    p_classification: body.classification || {},
    p_received_at: body.received_at || new Date().toISOString(),
  });

  if (r.error) {
    // The RPC raises 42501 on invalid_n8n_secret — translate to 401
    const code = (r.error as { code?: string }).code;
    if (code === "42501" || /invalid_n8n_secret/i.test(r.error.message || "")) {
      return bad(401, "invalid secret");
    }
    return bad(500, r.error.message || "rpc failed");
  }

  return NextResponse.json({
    ok: true,
    interaction_id: r.data,
  });
}

// Reject other methods
export async function GET() {
  return bad(405, "POST only");
}

/**
 * Identify obvious non-leads so we don't pollute the pipeline. Returns a
 * short reason string when the email should be filtered, or null when it
 * should pass through to lead creation.
 *
 * Conservative on purpose — only blocks the patterns that are clearly NOT
 * humans pitching us. Anything ambiguous (real-looking address, real
 * subject) still becomes a lead so we don't lose real outreach.
 */
function isJunkSender(fromEmail: string, subject: string): string | null {
  const e = (fromEmail || "").toLowerCase().trim();
  const s = (subject || "").toLowerCase().trim();
  if (!e || !e.includes("@")) return "invalid_email";

  const local = e.split("@")[0];
  const domain = e.split("@")[1] || "";

  // 1. No-reply / transactional local-parts. These are NEVER leads.
  const NOREPLY_LOCALPARTS = [
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "notifications", "notification", "alerts", "alert",
    "billing", "receipts", "receipt", "invoices", "invoice",
    "support", "help", "hello", "info", "contact", "mailer",
    "mailer-daemon", "postmaster", "bounces", "bounce",
    "newsletter", "news", "updates", "team", "system",
    "auto", "automated", "bot", "noreply-",
  ];
  for (const p of NOREPLY_LOCALPARTS) {
    if (local === p || local.startsWith(`${p}-`) || local.startsWith(`${p}_`) || local.startsWith(`${p}@`)) {
      return `noreply_localpart:${p}`;
    }
  }

  // 2. Test / example domains. Never real leads.
  const TEST_DOMAINS = ["example.com", "example.org", "test.com", "test.test", "localhost", "invalid"];
  if (TEST_DOMAINS.includes(domain)) return `test_domain:${domain}`;
  if (local === "test" || local === "example" || local.startsWith("test+")) return "test_localpart";

  // 3. Known transactional senders. These send INVOICE / RECEIPT / etc., not
  // sales inquiries. Add to this list as new false positives appear.
  const TRANSACTIONAL_DOMAINS = [
    "kraken.com", "stripe.com", "github.com", "vercel.com", "cloudflare.com",
    "supabase.io", "supabase.com", "openrouter.ai", "anthropic.com", "openai.com",
    "google.com", "googlemail.com", "amazon.com", "aws.amazon.com",
    "linear.app", "notion.so", "slack.com", "discord.com", "intercom.com",
    "mailchimp.com", "sendgrid.net", "postmark.com",
  ];
  if (TRANSACTIONAL_DOMAINS.includes(domain)) return `transactional_domain:${domain}`;

  // 4. Subject patterns that mark it as transactional rather than a lead.
  const TRANSACTIONAL_SUBJECTS = [
    /^(your )?receipt/i,
    /^invoice (#|ref|number)/i,
    /^withdrawal /i,
    /^payment /i,
    /^you added/i,
    /^security alert/i,
    /^login from a new/i,
    /^verify your /i,
    /^confirm your /i,
    /^your order /i,
    /^shipped:/i,
    /unsubscribe/i,
  ];
  for (const re of TRANSACTIONAL_SUBJECTS) {
    if (re.test(s)) return `transactional_subject`;
  }

  return null;
}
