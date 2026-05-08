/**
 * A1: Filesystem-backed agent inbox reader. Mirrors the on-disk shape
 * written by scripts/agent_inbox.py — JSON files in
 * tmp/agent_inbox/inbox/ (unread) and tmp/agent_inbox/read/ (acknowledged).
 *
 * Server-only. Returns the parsed message list sorted urgent → normal,
 * newest first within priority.
 */

import { promises as fs } from "node:fs";
import path from "node:path";
import { randomBytes } from "node:crypto";
import { homedir } from "node:os";
import { VALID_PRIORITIES, KNOWN_AGENTS, type Priority } from "./agent-inbox-types";

// Re-export shared types so existing call sites that import from this
// file keep compiling without churn.
export { VALID_PRIORITIES, KNOWN_AGENTS };
export type { Priority };

const REPO_ROOT = process.env.BRAVO_REPO_ROOT || path.resolve(process.cwd(), "..", "..");

export const INBOX_ROOT = path.join(REPO_ROOT, "tmp", "agent_inbox");
export const INBOX_DIR = path.join(INBOX_ROOT, "inbox");
export const READ_DIR = path.join(INBOX_ROOT, "read");

// Cross-repo routing — mirror scripts/sibling_repos.py so messages posted
// to a sibling land in their repo's inbox dir, not Bravo's. Anything not
// listed (cc, codex, broadcast, unknown) stays local.
const HOME = homedir();
const SIBLING_REPOS: Record<string, string> = {
  bravo: process.env.BRAVO_REPO || path.join(HOME, "Business-Empire-Agent"),
  maven: process.env.MAVEN_REPO || path.join(HOME, "CMO-Agent"),
  atlas: process.env.ATLAS_REPO || path.join(HOME, "APPS", "CFO-Agent"),
  aura: process.env.AURA_REPO || path.join(HOME, "AURA"),
  "life-preservation":
    process.env.LIFE_PRESERVATION_REPO || path.join(HOME, "life-preservation"),
};

async function _inboxPathForRecipient(recipient: string): Promise<string> {
  const repo = SIBLING_REPOS[recipient.toLowerCase()];
  if (!repo) return INBOX_DIR;
  try {
    await fs.access(repo);
  } catch {
    return INBOX_DIR; // sibling not installed on this machine — keep local
  }
  const target = path.join(repo, "tmp", "agent_inbox", "inbox");
  await fs.mkdir(target, { recursive: true });
  return target;
}

// VALID_PRIORITIES, KNOWN_AGENTS, and Priority moved to
// lib/agent-inbox-types.ts and re-exported above. See that file
// for the canonical source.

export type InboxMessage = {
  message_id: string;
  from: string;
  to: string;
  timestamp: string;
  subject: string;
  body: string;
  priority: Priority;
  requires_response: boolean;
  in_reply_to: string | null;
  thread_id: string;
  // Synthetic — added at read time
  _filename: string;
  _read: boolean;
};

const PRIORITY_RANK: Record<Priority, number> = {
  urgent: 0,
  high: 1,
  normal: 2,
  low: 3,
};

async function _readDir(dir: string, isRead: boolean): Promise<InboxMessage[]> {
  let entries: string[];
  try {
    entries = (await fs.readdir(dir, { withFileTypes: true }))
      .filter((e) => e.isFile() && e.name.endsWith(".json"))
      .map((e) => e.name);
  } catch {
    return [];
  }
  const out: InboxMessage[] = [];
  for (const name of entries) {
    try {
      const raw = await fs.readFile(path.join(dir, name), "utf-8");
      const j = JSON.parse(raw) as Partial<InboxMessage>;
      out.push({
        message_id: String(j.message_id || ""),
        from: String(j.from || ""),
        to: String(j.to || ""),
        timestamp: String(j.timestamp || ""),
        subject: String(j.subject || ""),
        body: String(j.body || ""),
        priority: (VALID_PRIORITIES as readonly string[]).includes(String(j.priority))
          ? (j.priority as Priority)
          : "normal",
        requires_response: !!j.requires_response,
        in_reply_to: j.in_reply_to ? String(j.in_reply_to) : null,
        thread_id: String(j.thread_id || j.message_id || ""),
        _filename: name,
        _read: isRead,
      });
    } catch {
      // skip malformed
    }
  }
  return out;
}

export async function listUnread(): Promise<InboxMessage[]> {
  const rows = await _readDir(INBOX_DIR, false);
  rows.sort((a, b) => {
    const p = PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority];
    if (p !== 0) return p;
    return b.timestamp.localeCompare(a.timestamp);
  });
  return rows;
}

export async function listRead(limit = 50): Promise<InboxMessage[]> {
  const rows = await _readDir(READ_DIR, true);
  rows.sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  return rows.slice(0, limit);
}

export async function markRead(filename: string): Promise<{ ok: boolean; error?: string }> {
  // Validate filename — no slashes, must end in .json. Prevents path
  // traversal even though the route is session-gated.
  if (!filename || filename.includes("/") || filename.includes("\\") || !filename.endsWith(".json")) {
    return { ok: false, error: "invalid_filename" };
  }
  const src = path.join(INBOX_DIR, filename);
  const dst = path.join(READ_DIR, filename);
  try {
    await fs.mkdir(READ_DIR, { recursive: true });
    await fs.rename(src, dst);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "rename_failed" };
  }
}

export async function postMessage(opts: {
  from: string;
  to: string;
  subject: string;
  body: string;
  priority?: Priority;
  requires_response?: boolean;
  in_reply_to?: string | null;
  /**
   * Optional pre-generated message_id so the route can pass the SAME id
   * to the Supabase writer and this filesystem writer in dual-write mode.
   * Lets the /inbox page dedupe rows from both sources by message_id.
   */
  messageId?: string;
}): Promise<{ ok: boolean; message?: InboxMessage; error?: string }> {
  if (!opts.body || !opts.body.trim()) return { ok: false, error: "body_required" };
  if (!opts.subject || !opts.subject.trim()) return { ok: false, error: "subject_required" };
  if (!opts.from.trim() || !opts.to.trim()) return { ok: false, error: "agent_required" };
  const priority: Priority = opts.priority || "normal";
  if (!VALID_PRIORITIES.includes(priority)) return { ok: false, error: "invalid_priority" };

  const msgId = opts.messageId || randomBytes(6).toString("hex");
  const now = new Date().toISOString();
  const msg: InboxMessage = {
    message_id: msgId,
    from: opts.from.trim().toLowerCase(),
    to: opts.to.trim().toLowerCase(),
    timestamp: now,
    subject: opts.subject.trim(),
    body: opts.body.trim(),
    priority,
    requires_response: !!opts.requires_response,
    in_reply_to: opts.in_reply_to || null,
    thread_id: opts.in_reply_to || msgId,
    _filename: "",
    _read: false,
  };
  const priorityPrefix = { urgent: "0", high: "1", normal: "2", low: "3" }[priority];
  const tsSlug = now.replace(/:/g, "-").replace(/\./g, "-");
  const fname = `${priorityPrefix}_${tsSlug}_${msg.to}_${msgId}.json`;
  msg._filename = fname;

  try {
    const targetDir = await _inboxPathForRecipient(msg.to);
    const persistShape = { ...msg } as Record<string, unknown>;
    delete persistShape._filename;
    delete persistShape._read;
    await fs.writeFile(path.join(targetDir, fname), JSON.stringify(persistShape, null, 2), "utf-8");
    return { ok: true, message: msg };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "write_failed" };
  }
}
