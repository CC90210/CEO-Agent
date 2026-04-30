/**
 * Shared types — what the dashboard reads from Supabase.
 *
 * Clients live in:
 *   - lib/supabase-server.ts  — server-side service-role + authed clients
 *   - lib/supabase-browser.ts — browser anon client (auth flows)
 */

// ============================================================================
// Types
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
  tenant_id?: string | null;
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
  tenant_id?: string | null;
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
  tenant_id: string | null;
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
  preferred_language: string;
  prospect_focus: string[];
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type DailyPlan = {
  id: string;
  profile_id: string;
  tenant_id?: string | null;
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
    intensity?: "intense" | "normal" | "break" | "carryover";
    completed?: boolean;
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
  tenant_id?: string | null;
  service: string;
  status: "healthy" | "degraded" | "down" | "unconfigured";
  last_ping_at: string | null;
  last_error: string | null;
  metadata: Record<string, unknown>;
  updated_at: string;
};

export type Tenant = {
  id: string;
  slug: string;
  name: string;
  plan_tier: string;
  purchase_status: "pending" | "active" | "suspended";
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  primary_brand_color: string | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type PlanTemplate = {
  id: string;
  tenant_id: string;
  profile_id: string;
  kind: "weekday" | "weekend";
  mission: string | null;
  target_calls: number;
  target_emails: number;
  target_bookings: number;
  schedule: Array<{
    time_label: string;
    title: string;
    body: string;
    intensity?: "intense" | "normal" | "break" | "carryover";
  }>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};
