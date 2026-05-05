/**
 * GET  /api/agent-config              — list this tenant's per-agent configs
 *                                        (api key NEVER returned, only `has_key: true|false`)
 * POST /api/agent-config              — upsert config + encrypted key
 *
 * POST body:
 *   {
 *     agent_key: "bravo" | ...,
 *     provider: "anthropic" | "openai" | "google",
 *     model: string,
 *     api_key?: string,                 // omit to leave existing key intact
 *     system_prompt_override?: string,
 *     enabled?: boolean
 *   }
 */

import { NextRequest, NextResponse } from "next/server";
import { getAuthedSupabase, getServiceSupabase, getSessionUser } from "@/lib/supabase-server";
import { chatAgentKeys } from "@/lib/agent-personas";
import { PROVIDER_MODELS } from "@/lib/providers";
import { encryptField } from "@/lib/field-encryption";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

async function resolveTenant(): Promise<{ tenantId: string | null; userId: string | null }> {
  const user = await getSessionUser();
  if (!user) return { tenantId: null, userId: null };
  const authed = await getAuthedSupabase();
  const { data: profile } = await authed
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  return { tenantId: profile?.tenant_id || null, userId: user.id };
}

export async function GET() {
  const { tenantId } = await resolveTenant();
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const service = getServiceSupabase();
  const { data, error } = await service
    .from("agent_model_config")
    .select("agent_key, provider, model, enabled, last_used_at, encrypted_api_key, system_prompt_override")
    .eq("tenant_id", tenantId);
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  const configs = (data || []).map((row) => ({
    agent_key: row.agent_key,
    provider: row.provider,
    model: row.model,
    enabled: row.enabled,
    last_used_at: row.last_used_at,
    has_key: !!row.encrypted_api_key,
    has_override: !!row.system_prompt_override,
  }));
  return NextResponse.json({ ok: true, configs });
}

export async function POST(req: NextRequest) {
  const { tenantId } = await resolveTenant();
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });

  let body: any;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const agentKey = String(body?.agent_key || "").toLowerCase();
  if (!chatAgentKeys().includes(agentKey)) {
    return NextResponse.json({ ok: false, error: `invalid_agent:${agentKey}` }, { status: 400 });
  }
  const provider = String(body?.provider || "");
  if (!Object.keys(PROVIDER_MODELS).includes(provider)) {
    return NextResponse.json({ ok: false, error: `invalid_provider:${provider}` }, { status: 400 });
  }
  const model = String(body?.model || "").trim();
  if (!model) return NextResponse.json({ ok: false, error: "missing_model" }, { status: 400 });

  const apiKeyPlain: string | undefined =
    typeof body?.api_key === "string" && body.api_key.trim() ? body.api_key.trim() : undefined;
  const overrideRaw: string | undefined =
    typeof body?.system_prompt_override === "string" ? body.system_prompt_override : undefined;
  const enabled = body?.enabled === false ? false : true;

  const service = getServiceSupabase();

  // Encrypt key Node-side if a new one was supplied
  let encryptedKey: string | undefined;
  if (apiKeyPlain) {
    try {
      encryptedKey = encryptField(apiKeyPlain);
    } catch (err) {
      return NextResponse.json(
        { ok: false, error: err instanceof Error ? err.message : "encrypt_failed" },
        { status: 500 }
      );
    }
  }

  // Upsert
  const { data: existing } = await service
    .from("agent_model_config")
    .select("id")
    .eq("tenant_id", tenantId)
    .eq("agent_key", agentKey)
    .maybeSingle();

  const payload: Record<string, unknown> = {
    tenant_id: tenantId,
    agent_key: agentKey,
    provider,
    model,
    enabled,
  };
  if (encryptedKey !== undefined) payload.encrypted_api_key = encryptedKey;
  if (overrideRaw !== undefined) {
    payload.system_prompt_override = overrideRaw.trim().length ? overrideRaw : null;
  }

  if (existing) {
    const { error } = await service
      .from("agent_model_config")
      .update(payload)
      .eq("id", existing.id);
    if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  } else {
    const { error } = await service.from("agent_model_config").insert(payload);
    if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }

  return NextResponse.json({ ok: true });
}
