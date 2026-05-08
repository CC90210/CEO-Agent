/**
 * A6: Persist a dashboard-action result to agent_events so /runs can
 * show CC every mutation the chat agent has made. Best-effort — never
 * throws; the chat stream must not break if the audit write fails.
 */

import { getServiceSupabase } from "./supabase-server";

export type LoggedAction = {
  agent_key: string;
  tenant_id: string;
  user_id: string;
  type: string;
  ok: boolean;
  summary?: string;
  error?: string;
  before?: unknown;
  after?: unknown;
};

export async function logAction(input: LoggedAction): Promise<void> {
  try {
    const db = getServiceSupabase();
    await db.from("agent_events").insert({
      event_type: "dashboard_action",
      publisher_agent: input.agent_key,
      severity: input.ok ? "info" : "warn",
      payload: {
        type: input.type,
        ok: input.ok,
        summary: input.summary || null,
        error: input.error || null,
        before: input.before ?? null,
        after: input.after ?? null,
        tenant_id: input.tenant_id,
        user_id: input.user_id,
      },
      correlation_id: input.tenant_id,
    });
  } catch {
    // best-effort
  }
}
