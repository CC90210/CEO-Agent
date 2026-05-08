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
import { getSessionUser } from "@/lib/supabase-server";
import { postMessage, type Priority, KNOWN_AGENTS } from "@/lib/agent-inbox-fs";

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

  const result = await postMessage({
    from,
    to,
    subject: String(body.subject || "").slice(0, 200),
    body: String(body.body || "").slice(0, 8000),
    priority: body.priority,
    requires_response: !!body.requires_response,
    in_reply_to: body.in_reply_to || null,
  });
  if (!result.ok) {
    return NextResponse.json(result, { status: 400 });
  }
  return NextResponse.json(result);
}
