/**
 * POST /api/inbox/post — Write a new agent inbox message to
 * tmp/agent_inbox/inbox/. Operator-only (session-authed admin).
 *
 * This writes the JSON file directly, mirroring the on-disk shape
 * scripts/agent_inbox.py uses. No subprocess spawn needed for the
 * single-host case (the dashboard and the inbox dir share a filesystem
 * when running locally; on Vercel the inbox is empty by design).
 */

import { NextResponse, type NextRequest } from "next/server";
import { randomBytes } from "node:crypto";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";
import { postMessage, type Priority, KNOWN_AGENTS } from "@/lib/agent-inbox-fs";
import { postMessageDb } from "@/lib/agent-inbox-db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function isAdminEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  const e = email.trim().toLowerCase();
  const operator = (process.env.OPERATOR_EMAIL || "").trim().toLowerCase();
  if (operator && e === operator) return true;
  const admins = (process.env.ADMIN_EMAILS || "")
    .split(",")
    .map((x) => x.trim().toLowerCase())
    .filter(Boolean);
  return admins.includes(e);
}

export async function POST(req: NextRequest) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  if (!isAdminEmail(user.email)) {
    return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  }

  let body: {
    from?: string;
    to?: string;
    subject?: string;
    body?: string;
    priority?: Priority;
    requires_response?: boolean;
    in_reply_to?: string | null;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const to = String(body.to || "").trim().toLowerCase();
  const from = String(body.from || "cc").trim().toLowerCase();
  if (!(KNOWN_AGENTS as readonly string[]).includes(to)) {
    return NextResponse.json({ ok: false, error: `unknown_recipient:${to}` }, { status: 400 });
  }

  // Resolve tenant_id for the Supabase write.
  const service = getServiceSupabase();
  const profileRes = await service
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const tenantId = (profileRes.data as { tenant_id: string | null } | null)?.tenant_id;

  const subject = String(body.subject || "").slice(0, 200);
  const bodyText = String(body.body || "").slice(0, 8000);
  const priority = body.priority;
  const requires = !!body.requires_response;
  const inReply = body.in_reply_to || null;

  // Generate ONE message_id and pass it to both writers so the /inbox
  // page can dedupe rows from the two sources by message_id. Without
  // this, each writer would generate its own random id and the same
  // posted message would render twice on /inbox.
  const sharedMessageId = randomBytes(6).toString("hex");

  // Write to Supabase first (source of truth) and to filesystem in parallel
  // (so local agents that only know how to read tmp/agent_inbox/ keep
  // working). Either path failing logs but does not fail the request.
  const [dbResult, fsResult] = await Promise.all([
    tenantId
      ? postMessageDb({
          tenantId,
          from,
          to,
          subject,
          body: bodyText,
          priority,
          requires_response: requires,
          in_reply_to: inReply,
          messageId: sharedMessageId,
        })
      : Promise.resolve({ ok: false, error: "no_tenant" } as const),
    postMessage({
      from,
      to,
      subject,
      body: bodyText,
      priority,
      requires_response: requires,
      in_reply_to: inReply,
      messageId: sharedMessageId,
    }),
  ]);

  if (!dbResult.ok && !fsResult.ok) {
    return NextResponse.json(
      { ok: false, error: dbResult.error || fsResult.error || "post_failed" },
      { status: 400 }
    );
  }
  // Prefer DB shape when available so the response carries the canonical id.
  return NextResponse.json({
    ok: true,
    db: dbResult.ok ? dbResult.message : null,
    fs: fsResult.ok ? fsResult.message : null,
  });
}
