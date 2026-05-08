/**
 * Supabase-backed agent inbox. Replaces filesystem JSON files
 * (tmp/agent_inbox/inbox/*) as the source of truth — multi-machine,
 * tenant-scoped, RLS-protected. The filesystem path stays as a
 * secondary mirror so local agents posting via scripts/agent_inbox.py
 * keep working while we migrate.
 *
 * Read-side: list / count unread / get-by-id.
 * Write-side: post / mark-read.
 *
 * Both server-only (use service Supabase client). The /api/inbox/*
 * route handlers are the only callers.
 */

import { getServiceSupabase } from "./supabase-server";
import { randomBytes } from "node:crypto";

export const VALID_PRIORITIES = ["low", "normal", "high", "urgent"] as const;
export type Priority = (typeof VALID_PRIORITIES)[number];

export const KNOWN_AGENTS = [
  "bravo", "atlas", "maven", "aura", "life-preservation", "codex", "cc", "broadcast",
] as const;

export type DbInboxMessage = {
  id: string;
  message_id: string;
  tenant_id: string;
  from_agent: string;
  to_agent: string;
  subject: string | null;
  body: string;
  priority: Priority;
  requires_response: boolean;
  in_reply_to: string | null;
  thread_id: string | null;
  read_at: string | null;
  created_at: string;
};

const PRIORITY_RANK: Record<Priority, number> = {
  urgent: 0,
  high: 1,
  normal: 2,
  low: 3,
};

export async function listUnreadDb(tenantId: string, toAgent?: string): Promise<DbInboxMessage[]> {
  const db = getServiceSupabase();
  let q = db
    .from("agent_messages")
    .select("*")
    .eq("tenant_id", tenantId)
    .is("read_at", null);
  if (toAgent) q = q.eq("to_agent", toAgent);
  const { data } = await q
    .order("priority", { ascending: true })
    .order("created_at", { ascending: false })
    .limit(200);
  const rows = (data || []) as DbInboxMessage[];
  // Postgres orders alphabetically; we want urgent → low. Re-sort client-side
  // by the rank map so 'urgent' lands above 'high' etc.
  rows.sort((a, b) => {
    const p = PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority];
    if (p !== 0) return p;
    return b.created_at.localeCompare(a.created_at);
  });
  return rows;
}

export async function listReadDb(tenantId: string, toAgent?: string, limit = 50): Promise<DbInboxMessage[]> {
  const db = getServiceSupabase();
  let q = db
    .from("agent_messages")
    .select("*")
    .eq("tenant_id", tenantId)
    .not("read_at", "is", null);
  if (toAgent) q = q.eq("to_agent", toAgent);
  const { data } = await q
    .order("created_at", { ascending: false })
    .limit(limit);
  return (data || []) as DbInboxMessage[];
}

export async function unreadCountDb(tenantId: string, toAgent?: string): Promise<number> {
  const db = getServiceSupabase();
  let q = db
    .from("agent_messages")
    .select("id", { count: "exact", head: true })
    .eq("tenant_id", tenantId)
    .is("read_at", null);
  if (toAgent) q = q.eq("to_agent", toAgent);
  const { count } = await q;
  return count ?? 0;
}

export async function markReadDb(
  tenantId: string,
  id: string
): Promise<{ ok: boolean; error?: string }> {
  if (!id) return { ok: false, error: "missing_id" };
  const db = getServiceSupabase();
  const { error } = await db
    .from("agent_messages")
    .update({ read_at: new Date().toISOString() })
    .eq("tenant_id", tenantId)
    .eq("id", id);
  if (error) return { ok: false, error: error.message };
  return { ok: true };
}

export async function postMessageDb(opts: {
  tenantId: string;
  from: string;
  to: string;
  subject: string;
  body: string;
  priority?: Priority;
  requires_response?: boolean;
  in_reply_to?: string | null;
}): Promise<{ ok: boolean; message?: DbInboxMessage; error?: string }> {
  if (!opts.body || !opts.body.trim()) return { ok: false, error: "body_required" };
  if (!opts.from.trim() || !opts.to.trim()) return { ok: false, error: "agent_required" };
  const priority: Priority = opts.priority || "normal";
  if (!VALID_PRIORITIES.includes(priority)) return { ok: false, error: "invalid_priority" };

  const db = getServiceSupabase();
  const messageId = randomBytes(6).toString("hex");
  const row = {
    message_id: messageId,
    tenant_id: opts.tenantId,
    from_agent: opts.from.trim().toLowerCase(),
    to_agent: opts.to.trim().toLowerCase(),
    subject: opts.subject?.trim() || null,
    body: opts.body.trim(),
    priority,
    requires_response: !!opts.requires_response,
    in_reply_to: opts.in_reply_to || null,
    thread_id: opts.in_reply_to || messageId,
  };
  const { data, error } = await db
    .from("agent_messages")
    .insert(row)
    .select("*")
    .single();
  if (error) return { ok: false, error: error.message };
  return { ok: true, message: data as DbInboxMessage };
}

/**
 * Convert a DB row to the shape the existing UI expects (the InboxMessage
 * type from agent-inbox-fs.ts). Lets us drop in Supabase-backed reads
 * without touching the rendering components.
 */
export function dbToUiShape(row: DbInboxMessage) {
  return {
    message_id: row.message_id,
    from: row.from_agent,
    to: row.to_agent,
    timestamp: row.created_at,
    subject: row.subject || "",
    body: row.body,
    priority: row.priority,
    requires_response: row.requires_response,
    in_reply_to: row.in_reply_to,
    thread_id: row.thread_id || row.message_id,
    _filename: row.id,
    _read: !!row.read_at,
  };
}
