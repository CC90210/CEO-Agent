/**
 * POST /api/agent-config/bulk-provider
 *
 * Single-click connect: paste an API key once, the route stamps it across
 * every enabled chat agent in the tenant. Powers the "Connect Anthropic"
 * button on the Provider Accounts card in /settings.
 *
 * Behavior:
 *   - Validates the provider + key format (light — server-side string
 *     length sanity check, NOT a live provider ping; ping happens on
 *     first chat turn so we don't leak a key by accident in error
 *     responses here).
 *   - Resolves the agent set: explicit `agent_keys[]` if supplied,
 *     otherwise the tenant's enabled chat-eligible agents.
 *   - Upserts (provider, model, encrypted_api_key) for each agent.
 *     Existing per-agent customizations (system_prompt_override, etc.)
 *     are preserved — only the provider/model/key triple is replaced.
 *   - Defaults model to the provider's first registry entry (the
 *     recommended one) unless the caller passed a specific model.
 *
 * Body shape:
 *   {
 *     provider: "anthropic" | "openai" | "google" | "openrouter",
 *     api_key: string,                    // required, encrypted server-side
 *     model?: string,                     // optional, default = first registry entry
 *     agent_keys?: string[]               // optional, default = enabled agents
 *   }
 *
 * Returns: { ok, applied_to: [agent_key,...], count }
 */

import { NextRequest, NextResponse } from "next/server";
import { getAuthedSupabase, getServiceSupabase } from "@/lib/supabase-server";
import { PROVIDER_MODELS, PROVIDER_REGISTRY, type Provider } from "@/lib/providers";
import { encryptField } from "@/lib/field-encryption";
import { chatAgentKeys } from "@/lib/agent-personas";
import { canManageTeam, getSessionContext } from "@/lib/team";
import { resolveAgentKey } from "@/lib/agents";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

async function resolveTenant(): Promise<{
  tenantId: string | null;
  userId: string | null;
  canManageTenant: boolean;
  profileEnabledAgents: string[];
}> {
  const ctx = await getSessionContext();
  if (!ctx) {
    return { tenantId: null, userId: null, canManageTenant: false, profileEnabledAgents: [] };
  }
  const db = getServiceSupabase();
  const { data } = await db
    .from("user_profiles")
    .select("tenant_id, agents_enabled")
    .eq("auth_user_id", ctx.authUserId)
    .maybeSingle();
  const enabled = Array.isArray(data?.agents_enabled)
    ? (data!.agents_enabled as string[]).filter((s) => typeof s === "string")
    : [];
  return {
    tenantId: data?.tenant_id || ctx.tenantId || null,
    userId: ctx.authUserId,
    canManageTenant: ctx.isOwner || canManageTeam(ctx.teamRole),
    profileEnabledAgents: enabled,
  };
}

export async function POST(req: NextRequest) {
  const { tenantId, userId, canManageTenant, profileEnabledAgents } = await resolveTenant();
  if (!tenantId) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  let body: any;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const provider = String(body?.provider || "");
  if (!Object.keys(PROVIDER_MODELS).includes(provider)) {
    return NextResponse.json({ ok: false, error: `invalid_provider:${provider}` }, { status: 400 });
  }
  const scope = body?.scope === "user" ? "user" : "tenant";
  if (scope === "tenant" && !canManageTenant) {
    return NextResponse.json({ ok: false, error: "admin_required" }, { status: 403 });
  }
  if (scope === "user" && !userId) {
    return NextResponse.json({ ok: false, error: "no_user" }, { status: 401 });
  }
  const effectiveUserId = scope === "user" ? userId : null;

  const apiKeyPlain =
    typeof body?.api_key === "string" && body.api_key.trim() ? body.api_key.trim() : null;
  if (!apiKeyPlain) {
    return NextResponse.json({ ok: false, error: "missing_api_key" }, { status: 400 });
  }
  // Generous length cap — long enough for any real provider key, short enough
  // to refuse obvious paste accidents (entire scripts pasted by mistake).
  if (apiKeyPlain.length < 8 || apiKeyPlain.length > 400) {
    return NextResponse.json({ ok: false, error: "invalid_key_length" }, { status: 400 });
  }

  // Pick a default model — the first registry entry per provider IS the
  // recommended choice (balanced cost/quality), so a single-click flow can
  // safely fall through to it. Caller can override via body.model.
  const requestedModel = typeof body?.model === "string" ? body.model.trim() : "";
  const reg = PROVIDER_REGISTRY.find((p) => p.value === (provider as Provider));
  const defaultModel = reg?.models[0]?.id || "";
  const model = requestedModel || defaultModel;
  if (!model) {
    return NextResponse.json({ ok: false, error: "no_default_model" }, { status: 500 });
  }
  // Light validation: the requested model must be in the provider's known
  // registry. Prevents a typo from silently shipping an invalid model name
  // that the first chat turn will fail on.
  const providerModels = PROVIDER_MODELS[provider as Provider] || [];
  if (requestedModel && !providerModels.includes(requestedModel)) {
    return NextResponse.json(
      { ok: false, error: `unknown_model_for_provider:${provider}:${requestedModel}` },
      { status: 400 }
    );
  }

  // Resolve target agent set. Caller-supplied list takes precedence; otherwise
  // fall back to the profile's enabled agents. If neither is populated, fall
  // back to the full chat-eligible set — operators on a fresh tenant want
  // every agent wired in one shot.
  const requestedAgents = Array.isArray(body?.agent_keys)
    ? (body.agent_keys as unknown[]).filter((s): s is string => typeof s === "string").map((s) => s.toLowerCase())
    : null;
  const fallbackAgents =
    profileEnabledAgents.length > 0 ? profileEnabledAgents : chatAgentKeys();
  const chatAllowed = new Set(chatAgentKeys());
  const targetAgents = Array.from(
    new Set((requestedAgents || fallbackAgents).map((k) => resolveAgentKey(k))),
  ).filter((k) => chatAllowed.has(k));
  if (targetAgents.length === 0) {
    return NextResponse.json({ ok: false, error: "no_target_agents" }, { status: 400 });
  }

  let encryptedKey: string;
  try {
    encryptedKey = encryptField(apiKeyPlain);
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "encrypt_failed" },
      { status: 500 }
    );
  }

  const service = getServiceSupabase();
  const applied: string[] = [];
  const failed: Array<{ agent_key: string; error: string }> = [];
  // Sequential — Supabase upsert with onConflict isn't reliable across the
  // current PostgREST setup for compound keys (we'd need a real unique
  // index on (tenant_id, agent_key)). Doing it as N small writes is fine
  // — N is bounded by chat-eligible agent count (5-ish today).
  //
  // Partial-failure semantics: if any agent fails to save, the response
  // surfaces the failing agents + their error codes so the client can
  // show "saved on 3 of 5, see errors" instead of silently dropping the
  // bad ones. ok is true iff at least one save succeeded — caller is
  // expected to inspect `failed[]` when count < targetAgents.length.
  for (const agentKey of targetAgents) {
    let lookupQ = service
      .from("agent_model_config")
      .select("id")
      .eq("tenant_id", tenantId)
      .eq("agent_key", agentKey);
    lookupQ = effectiveUserId
      ? lookupQ.eq("user_id", effectiveUserId)
      : lookupQ.is("user_id", null);
    const { data: existing, error: lookupErr } = await lookupQ.maybeSingle();
    if (lookupErr) {
      failed.push({ agent_key: agentKey, error: `lookup_failed:${lookupErr.code || lookupErr.message}` });
      continue;
    }
    const payload: Record<string, unknown> = {
      tenant_id: tenantId,
      user_id: effectiveUserId,
      agent_key: agentKey,
      provider,
      model,
      enabled: true,
      encrypted_api_key: encryptedKey,
    };
    if (existing) {
      const { error } = await service
        .from("agent_model_config")
        .update(payload)
        .eq("id", existing.id);
      if (error) failed.push({ agent_key: agentKey, error: error.code || error.message });
      else applied.push(agentKey);
    } else {
      const { error } = await service.from("agent_model_config").insert(payload);
      if (error) failed.push({ agent_key: agentKey, error: error.code || error.message });
      else applied.push(agentKey);
    }
  }

  try {
    const authed = await getAuthedSupabase();
    await authed.rpc("log_tenant_event", {
      p_tenant_id: tenantId,
      p_action_type: scope === "user" ? "agent_config.user_update" : "agent_config.tenant_update",
      p_target_table: "agent_model_config",
      p_target_id: `${tenantId}:${effectiveUserId || "tenant"}:${provider}:bulk`,
      p_after: {
        provider,
        model,
        scope,
        applied_to: applied,
        failed,
        has_key: applied.length > 0,
      },
    });
  } catch {
    // audit-log soft-fail
  }

  return NextResponse.json({
    ok: applied.length > 0,
    scope,
    applied_to: applied,
    failed,
    count: applied.length,
  });
}
