/**
 * Per-user agent-config resolver.
 *
 * Phase B of the master multi-tenant infra plan (2026-05-17). Replaces the
 * single per-tenant lookup with a two-tier fallback chain:
 *
 *   1. (tenant_id, user_id, agent_key) — the operator's personal override
 *   2. (tenant_id, agent_key, user_id=NULL) — the tenant default
 *   3. null — caller should fall back to bridge mode / cloud default
 *
 * Migration 052 added the `user_id` column + partial unique indexes that
 * make both rows coexist. RLS lets every authenticated tenant member
 * read both rows (necessary for the fallback to work) but only WRITE
 * their own user-scoped rows; tenant defaults are admin-only.
 *
 * Callers:
 *   - bravo_cli/bridge_chat_server.py — resolves the model + key per
 *     incoming chat request (passes auth user_id when present).
 *   - apps/command-center/components/settings/MyAgentsCard.tsx — reads
 *     to render the operator's current personal override.
 *   - apps/command-center/components/settings/AgentConfigEditor.tsx —
 *     reads to render the tenant default.
 */

import { getServiceSupabase } from "@/lib/supabase-server";

export type AgentScope = "user" | "tenant" | null;

export type ResolvedAgentModel = {
  scope: AgentScope;
  tenant_id: string;
  user_id: string | null;
  agent_key: string;
  provider: string;
  model: string;
  encrypted_api_key: string | null;
  system_prompt_override: string | null;
  enabled: boolean;
} | null;

/**
 * Look up the effective agent model + key for a given (tenant, user, agent).
 * Returns the user-scoped row if it exists and is enabled; otherwise the
 * tenant-default row; null when neither exists.
 *
 * Uses the service-role client to bypass RLS — the caller is trusted (it's
 * server-side code resolving config for an already-authenticated request).
 */
export async function getAgentModelForUser(args: {
  tenantId: string;
  userId: string | null;
  agentKey: string;
}): Promise<ResolvedAgentModel> {
  const { tenantId, userId, agentKey } = args;
  if (!tenantId || !agentKey) return null;

  const db = getServiceSupabase();

  // 1. User override — only if userId provided
  if (userId) {
    const { data, error } = await db
      .from("agent_model_config")
      .select(
        "tenant_id, user_id, agent_key, provider, model, encrypted_api_key, system_prompt_override, enabled",
      )
      .eq("tenant_id", tenantId)
      .eq("user_id", userId)
      .eq("agent_key", agentKey)
      .maybeSingle();
    if (!error && data && data.enabled !== false) {
      return { scope: "user", ...data };
    }
  }

  // 2. Tenant default
  const { data: defaultRow, error: defaultErr } = await db
    .from("agent_model_config")
    .select(
      "tenant_id, user_id, agent_key, provider, model, encrypted_api_key, system_prompt_override, enabled",
    )
    .eq("tenant_id", tenantId)
    .is("user_id", null)
    .eq("agent_key", agentKey)
    .maybeSingle();
  if (!defaultErr && defaultRow && defaultRow.enabled !== false) {
    return { scope: "tenant", ...defaultRow };
  }

  return null;
}

/**
 * Upsert a user-scoped agent config row. Writes encrypted_api_key as-is
 * (callers must encrypt via lib/field-encryption.ts before passing in).
 * Returns the new row's id.
 */
export async function upsertUserAgentConfig(args: {
  tenantId: string;
  userId: string;
  agentKey: string;
  provider: string;
  model: string;
  encrypted_api_key?: string | null;
  system_prompt_override?: string | null;
}): Promise<string> {
  const db = getServiceSupabase();
  const payload = {
    tenant_id: args.tenantId,
    user_id: args.userId,
    agent_key: args.agentKey,
    provider: args.provider,
    model: args.model,
    encrypted_api_key: args.encrypted_api_key ?? null,
    system_prompt_override: args.system_prompt_override ?? null,
    enabled: true,
  };

  const existing = await db
    .from("agent_model_config")
    .select("id")
    .eq("tenant_id", args.tenantId)
    .eq("user_id", args.userId)
    .eq("agent_key", args.agentKey)
    .maybeSingle();
  if (existing.error) throw existing.error;

  const { data, error } = existing.data
    ? await db
        .from("agent_model_config")
        .update(payload)
        .eq("id", existing.data.id)
        .select("id")
        .single()
    : await db
        .from("agent_model_config")
        .insert(payload)
        .select("id")
        .single();
  if (error || !data) throw error ?? new Error("upsert_user_agent_failed");
  return data.id as string;
}

/**
 * Delete a user-scoped override. The operator falls back to the tenant
 * default on the next chat after deletion.
 */
export async function deleteUserAgentConfig(args: {
  tenantId: string;
  userId: string;
  agentKey: string;
}): Promise<void> {
  const db = getServiceSupabase();
  await db
    .from("agent_model_config")
    .delete()
    .eq("tenant_id", args.tenantId)
    .eq("user_id", args.userId)
    .eq("agent_key", args.agentKey);
}

/**
 * List every personal agent override the authenticated user has set in
 * their current tenant. Powers the "My agents" settings card.
 */
export async function listUserAgentOverrides(args: {
  tenantId: string;
  userId: string;
}): Promise<
  Array<{
    agent_key: string;
    provider: string;
    model: string;
    has_personal_key: boolean;
    enabled: boolean;
    updated_at: string | null;
  }>
> {
  const db = getServiceSupabase();
  const { data, error } = await db
    .from("agent_model_config")
    .select("agent_key, provider, model, encrypted_api_key, enabled, updated_at")
    .eq("tenant_id", args.tenantId)
    .eq("user_id", args.userId);
  if (error) throw error;
  return (data || []).map((r) => ({
    agent_key: r.agent_key as string,
    provider: r.provider as string,
    model: r.model as string,
    has_personal_key: !!r.encrypted_api_key,
    enabled: r.enabled !== false,
    updated_at: (r.updated_at as string | null) ?? null,
  }));
}
