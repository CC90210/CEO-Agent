/**
 * GET /api/usage?agent=<key>
 *
 * Proxies to OpenRouter's /api/v1/auth/key with the operator's encrypted
 * key. Returns { usage, limit, is_free_tier, currency } so the chat header
 * can show "$3.42 / $10 used today" instead of guessing.
 *
 * Anthropic doesn't expose a comparable endpoint per-key, so the header
 * hides the pill when the active provider isn't OpenRouter.
 *
 * Auth: same path as /api/chat — authed user, agent_model_config row,
 * operator fallback for admins. Read-only; no mutations possible here.
 */

import { NextResponse, type NextRequest } from "next/server";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";
import { decryptField } from "@/lib/field-encryption";
import { getAgentModelForUser } from "@/lib/agent-resolver";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function bad(status: number, error: string) {
  return NextResponse.json({ ok: false, error }, { status });
}

export async function GET(req: NextRequest) {
  const user = await getSessionUser();
  if (!user) return bad(401, "unauthorized");

  const agentKey = (new URL(req.url).searchParams.get("agent") || "").toLowerCase();
  if (!agentKey) return bad(400, "agent param required");

  const db = getServiceSupabase();
  const profileR = await db
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const tenantId = (profileR.data?.tenant_id as string | null) || null;
  if (!tenantId) return bad(403, "no_tenant");

  const cfg = await getAgentModelForUser({ tenantId, userId: user.id, agentKey });

  let provider = cfg?.provider || "openrouter";
  let apiKey: string | null = null;

  if (cfg?.encrypted_api_key) {
    try {
      apiKey = decryptField(cfg.encrypted_api_key as string);
    } catch {
      return bad(500, "key_decrypt_failed");
    }
  } else if (process.env.PLATFORM_DEFAULT_OPENROUTER_API_KEY) {
    apiKey = process.env.PLATFORM_DEFAULT_OPENROUTER_API_KEY || null;
    provider = "openrouter";
  }
  if (!apiKey) return bad(412, "no_api_key");

  if (provider !== "openrouter") {
    // Anthropic / OpenAI / Google don't expose a clean per-key usage endpoint.
    return NextResponse.json({ ok: true, supported: false, provider });
  }

  try {
    const r = await fetch("https://openrouter.ai/api/v1/auth/key", {
      headers: { authorization: `Bearer ${apiKey}` },
      cache: "no-store",
    });
    if (!r.ok) return bad(r.status, `openrouter_${r.status}`);
    const j = (await r.json()) as { data?: { usage?: number; limit?: number; is_free_tier?: boolean } };
    return NextResponse.json({
      ok: true,
      supported: true,
      provider: "openrouter",
      usage: j.data?.usage ?? 0,
      limit: j.data?.limit ?? null,
      is_free_tier: j.data?.is_free_tier ?? false,
    });
  } catch (e) {
    return bad(500, e instanceof Error ? e.message : "fetch_failed");
  }
}
