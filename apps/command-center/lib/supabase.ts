/**
 * Supabase client factory for the OASIS AI Agent Command Center.
 *
 * Server-side service role for v1 (every page is a React Server Component).
 * When client interactions land, switch to per-request anon-key with RLS.
 *
 * Env vars (set in Vercel → Settings → Environment Variables):
 *   BRAVO_SUPABASE_URL                — the Bravo project URL
 *   BRAVO_SUPABASE_SERVICE_ROLE_KEY   — server-side only, never expose
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let _cached: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient {
  if (_cached) return _cached;
  const url = process.env.BRAVO_SUPABASE_URL;
  const key = process.env.BRAVO_SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error(
      "OASIS Command Center misconfigured: BRAVO_SUPABASE_URL and " +
        "BRAVO_SUPABASE_SERVICE_ROLE_KEY must be set. See apps/command-center/README.md."
    );
  }
  _cached = createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return _cached;
}

// ============================================================================
// Shared types — what the dashboard reads from Supabase
// ============================================================================

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
  phone: string | null;
  company: string | null;
  status: string | null;
  score: number | null;
  source: string | null;
  notes: string | null;
  tags: string[] | null;
  last_contacted_at: string | null;
  next_followup_at: string | null;
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

export type UserProfile = {
  id: string;
  auth_user_id: string | null;
  email: string;
  full_name: string;
  display_name: string | null;
  brand: string;
  role: string;
  mrr_target_usd: number;
  mrr_current_usd: number;
  mrr_target_date: string | null;
  agents_enabled: string[];
  primary_agent: string;
  manifesto: string | null;
  primary_script_version: string;
  deal_architecture_version: string;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type DailyPlan = {
  id: string;
  profile_id: string;
  plan_date: string;
  mission: string | null;
  primary_lead_id: string | null;
  primary_lead_play: string | null;
  target_calls: number;
  target_emails: number;
  target_bookings: number;
  schedule: Array<{
    time_label: string;
    title: string;
    body: string;
    intensity?: "intense" | "normal" | "break";
  }>;
  actual_calls: number | null;
  actual_bookings: number | null;
  retro_notes: string | null;
  created_at: string;
  updated_at: string;
};

export type IntegrationHealth = {
  id: string;
  profile_id: string | null;
  service: string;
  status: "healthy" | "degraded" | "down" | "unconfigured";
  last_ping_at: string | null;
  last_error: string | null;
  metadata: Record<string, unknown>;
  updated_at: string;
};
