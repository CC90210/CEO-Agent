/**
 * Supabase client factory for the command center.
 *
 * Uses the SERVICE-ROLE key because every page renders on the server
 * (React Server Components) — the key never reaches the browser.
 *
 * Env vars (set in Vercel dashboard / .env.local):
 *   BRAVO_SUPABASE_URL                — the Bravo project URL
 *   BRAVO_SUPABASE_SERVICE_ROLE_KEY   — server-side only; never expose to client
 *
 * If you ever add client-side interactivity, create a separate factory that
 * uses the ANON key and enforces RLS policies.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let _cached: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient {
  if (_cached) return _cached;
  const url = process.env.BRAVO_SUPABASE_URL;
  const key = process.env.BRAVO_SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error(
      "Command center is misconfigured: BRAVO_SUPABASE_URL and " +
        "BRAVO_SUPABASE_SERVICE_ROLE_KEY must be set in the environment. " +
        "See apps/command-center/README.md.",
    );
  }
  _cached = createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return _cached;
}

/**
 * Basic shape helpers so pages don't have to carry around raw Supabase types.
 * These are lightweight — just what the dashboard actually reads.
 */
export type LeadInteraction = {
  id: string;
  lead_id: string | null;
  type: string;
  channel: string;
  subject: string | null;
  content: string | null;
  agent_source: string | null;
  cooldown_until: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

export type AgentDecision = {
  id: string;
  tick_id: string;
  agent_name: string;
  phase: string;
  decision_type: string;
  target_lead_id: string | null;
  target_description: string | null;
  reasoning: string | null;
  confidence: number | null;
  chosen_action: string | null;
  alternatives_considered: unknown;
  executed: boolean | null;
  execution_result: Record<string, unknown> | null;
  outcome_status: string | null;
  created_at: string;
};

export type Lead = {
  id: string;
  name: string | null;
  email: string | null;
  company: string | null;
  status: string | null;
  score: number | null;
  source: string | null;
  last_contacted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentEvent = {
  id: string;
  event_type: string;
  publisher_agent: string;
  severity: string;
  payload: Record<string, unknown>;
  correlation_id: string | null;
  published_at: string;
};

export type AgentStateSnapshot = {
  agent_name: string;
  tick_count: number;
  last_tick_at: string | null;
  last_tick_id: string | null;
  working_memory: Record<string, unknown>;
  pending_actions: unknown;
  health_status: string;
  updated_at: string;
};
