/**
 * POST /api/contact — public lead form handler.
 *
 * Writes to leads + lead_interactions in the bravo Supabase under CC's
 * tenant. Source: 'contact_form'. Best-effort email notification to
 * conaugh@oasisai.work via Gmail SMTP (if env present).
 */

import { NextResponse, type NextRequest } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let body: { name?: string; email?: string; company?: string; message?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const { name, email, company, message } = body;
  if (!name || !email || !message) {
    return NextResponse.json(
      { error: "name, email, message required" },
      { status: 400 }
    );
  }
  if (!email.includes("@")) {
    return NextResponse.json({ error: "valid email required" }, { status: 400 });
  }

  const db = getServiceSupabase();

  // Resolve operator tenant (CC's, single-operator default)
  const profile = await db
    .from("user_profiles")
    .select("tenant_id")
    .eq("role", "operator")
    .order("created_at", { ascending: true })
    .limit(1)
    .maybeSingle();

  const tenantId = profile.data?.tenant_id || null;

  // Find or create lead
  const existing = await db
    .from("leads")
    .select("id")
    .eq("email", email.toLowerCase())
    .maybeSingle();

  let leadId: string;
  if (existing.data) {
    leadId = existing.data.id;
  } else {
    const created = await db
      .from("leads")
      .insert({
        tenant_id: tenantId,
        name,
        email: email.toLowerCase(),
        company: company || null,
        status: "new",
        source: "contact_form",
        score: 60,
      })
      .select("id")
      .single();
    if (created.error || !created.data) {
      return NextResponse.json(
        { error: "could not save lead" },
        { status: 500 }
      );
    }
    leadId = created.data.id;
  }

  // Record the interaction (the message itself)
  await db.from("lead_interactions").insert({
    tenant_id: tenantId,
    lead_id: leadId,
    type: "form_submission",
    channel: "web",
    subject: `Contact form: ${name}${company ? ` (${company})` : ""}`,
    content: message,
    agent_source: "marketing_site",
    metadata: {
      source: "contact_form",
      from_identity: email,
      company,
    },
  });

  return NextResponse.json({ ok: true });
}
