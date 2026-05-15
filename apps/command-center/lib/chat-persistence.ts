/**
 * Shared chat_messages writer — single home for what was duplicated
 * between /api/chat and /api/chat/resume.
 *
 * Both routes write an assistant row at end-of-stream with the same
 * shape: session_id, tenant_id, role="assistant", redacted content,
 * tokens, latency, error. Without this helper, schema changes
 * (adding a `kind` column for example) needed parallel edits and
 * the two paths drifted easily.
 *
 * Session totals + agent_model_config last_used_at updates are NOT
 * extracted: /api/chat overwrites the running totals from per-turn
 * values (pre-existing behavior — may be a bug, not changing it
 * here); /api/chat/resume fetches + adds (correctly accumulates
 * across the paused/resumed boundary). Different semantics →
 * different code per caller.
 */

import { getServiceSupabase } from "./supabase-server";
import { redactAll } from "./secret-redaction";

export type AssistantTurnPersistArgs = {
  sessionId: string;
  tenantId: string;
  /** Assistant text. Always passed through redactAll before write —
   *  the model might echo a credential it saw in tool output, so the
   *  redaction at persist time is the last line of defense before
   *  chat_messages becomes a long-term secret-leak risk. */
  content: string;
  inputTokens: number;
  outputTokens: number;
  latencyMs: number;
  error?: string | null;
  /** Optional header prepended to content. /api/chat/resume uses this
   *  to mark the row as a resumed turn and list the tool chain. */
  prefix?: string;
};

/**
 * Insert a chat_messages row for an assistant turn. Returns true on
 * success, false on DB error (callers should log but not throw — the
 * SSE stream has already closed).
 */
export async function persistAssistantTurn(
  args: AssistantTurnPersistArgs,
): Promise<boolean> {
  const service = getServiceSupabase();
  const body = redactAll(args.content);
  const fullContent = args.prefix ? `${args.prefix}\n\n${body}` : body;
  const r = await service.from("chat_messages").insert({
    session_id: args.sessionId,
    tenant_id: args.tenantId,
    role: "assistant",
    content: fullContent,
    input_tokens: args.inputTokens,
    output_tokens: args.outputTokens,
    latency_ms: args.latencyMs,
    error: args.error ?? null,
  });
  if (r.error) {
    console.error("[chat-persistence.insert]", r.error.message);
    return false;
  }
  return true;
}
