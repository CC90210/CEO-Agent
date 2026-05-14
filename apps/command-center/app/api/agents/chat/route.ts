/**
 * POST /api/agents/chat
 *
 * Streaming chat with any marketplace agent — built-in seed or tenant-
 * custom. The effective system prompt is:
 *
 *   1. Look up the agent in the library (DB-first, seed fallback).
 *   2. Interpolate {{tenant.*}} / {{operator.*}} placeholders from the
 *      tenant's manifest.
 *   3. Append the manifest binding's prompt_overlay (per-tenant customisation).
 *
 * Why this isn't /api/chat: that route hardcodes the agent_key validation
 * (bravo/atlas/maven/aura/hermes) and is tightly bound to persona files +
 * dashboard-context injection. Custom agents from the marketplace need a
 * different shape — no persona file, no dashboard-context block,
 * tenant-specific overlays applied per call. Splitting endpoints keeps
 * both paths simple.
 *
 * Body:
 *   {
 *     tenant_slug: string,
 *     agent_slug:  string,
 *     messages:    ChatMessage[]   // rolling history maintained client-side
 *   }
 *
 * Response: text/event-stream SSE
 *   event: agent       data: { display_name, agent_slug, model }
 *   event: delta       data: { text }
 *   event: usage       data: { input_tokens, output_tokens }
 *   event: done        data: {}
 *   event: error       data: { message }
 */

import { type NextRequest } from "next/server";
import { decryptField } from "@/lib/field-encryption";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { streamChat, type ChatMessage, type Provider } from "@/lib/providers";
import { isOperatorEmail, operatorPlatformFallback } from "@/lib/operator-credentials";
import { redactAll } from "@/lib/secret-redaction";
import { getAgentBySlug } from "@/lib/agents/loader";
import { getManifest, manifestExists } from "@/lib/manifest/loader";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

type Body = {
  tenant_slug?: string;
  agent_slug?: string;
  messages?: ChatMessage[];
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function interpolate(template: string, vars: Record<string, string>): string {
  return template.replace(/\{\{\s*([a-z0-9_.]+)\s*\}\}/gi, (_m, key) => {
    return vars[key] ?? `{{${key}}}`;
  });
}

export async function POST(req: NextRequest) {
  const user = await getSessionUser();
  if (!user) return jsonResponse(401, { ok: false, error: "unauthorized" });

  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return jsonResponse(400, { ok: false, error: "invalid_json" });
  }

  const tenantSlug = (body.tenant_slug || "").trim().toLowerCase();
  const agentSlug = (body.agent_slug || "").trim().toLowerCase();
  if (!tenantSlug || !(await manifestExists(tenantSlug))) {
    return jsonResponse(400, { ok: false, error: "unknown_tenant" });
  }
  if (!agentSlug) {
    return jsonResponse(400, { ok: false, error: "agent_slug_required" });
  }
  const incoming = Array.isArray(body.messages) ? body.messages : [];
  const lastUser = [...incoming].reverse().find((m) => m.role === "user");
  if (!lastUser) return jsonResponse(400, { ok: false, error: "no_user_message" });

  const service = getServiceSupabase();
  const profileRes = await service
    .from("user_profiles")
    .select("tenant_id, display_name, full_name")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const profile = profileRes.data as
    | { tenant_id: string | null; display_name: string | null; full_name: string | null }
    | null;
  if (!profile?.tenant_id) {
    return jsonResponse(403, { ok: false, error: "no_tenant" });
  }

  const agent = await getAgentBySlug(agentSlug, profile.tenant_id);
  if (!agent) return jsonResponse(404, { ok: false, error: "agent_not_found" });

  // Visibility check — public seed OR tenant-owned custom only. RLS on the
  // agents table already enforces this for service-role-bypassed loads, so
  // this is defense-in-depth surface for clear error messaging.
  if (!agent.is_public && agent.tenant_id !== profile.tenant_id) {
    return jsonResponse(403, { ok: false, error: "agent_not_visible" });
  }

  const manifest = await getManifest(tenantSlug);
  const binding = manifest.agents.find((a) => a.slug === agent.slug);
  // If the manifest doesn't have this agent enabled, the operator hasn't
  // subscribed yet. We allow the chat anyway so a "trial" turn before
  // enabling works — but if you want strict enforcement, flip this gate.

  // Provider resolution — read bravo config because chat agent provider
  // selection is global to the tenant for v1. Phase 3.1 can add per-agent
  // provider/model overrides; the schema already supports
  // binding.model_override.
  const cfgRes = await service
    .from("agent_model_config")
    .select("provider, model, encrypted_api_key, enabled")
    .eq("tenant_id", profile.tenant_id)
    .eq("agent_key", "bravo")
    .maybeSingle();
  const cfg = cfgRes.data as
    | { provider: string; model: string; encrypted_api_key: string | null; enabled: boolean }
    | null;

  let provider: Provider;
  let model: string;
  let apiKey = "";
  if (cfg && cfg.enabled && cfg.encrypted_api_key) {
    provider = cfg.provider as Provider;
    model = binding?.model_override || cfg.model;
    try {
      apiKey = decryptField(cfg.encrypted_api_key);
    } catch {
      return jsonResponse(500, { ok: false, error: "key_decrypt_failed" });
    }
  } else {
    const fallback = isOperatorEmail(user.email || "") ? operatorPlatformFallback() : null;
    if (!fallback) {
      return jsonResponse(412, {
        ok: false,
        error: "agent_not_configured",
        hint: "Configure your Bravo provider key in Settings before chatting with marketplace agents.",
      });
    }
    provider = fallback.provider;
    model = binding?.model_override || fallback.model;
    apiKey = fallback.apiKey;
  }

  // Effective system prompt — interpolate placeholders, append overlay.
  const operatorName = profile.display_name || profile.full_name || "Operator";
  const interpolated = interpolate(agent.base_prompt, {
    "tenant.brand.name": manifest.brand.name,
    "tenant.brand.subtitle": manifest.brand.subtitle,
    "tenant.industry": manifest.onboarding_industry || "custom",
    "tenant.slug": tenantSlug,
    "operator.name": operatorName,
    "operator.email": user.email || "",
    "agent.name": binding?.display_name || agent.name,
  });
  const overlay = binding?.prompt_overlay?.trim();
  const system = overlay ? `${interpolated}\n\nTENANT OVERLAY:\n${overlay}` : interpolated;

  const displayName = binding?.display_name || agent.name;
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: string, data: unknown) => {
        controller.enqueue(
          encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
        );
      };
      send("agent", { display_name: displayName, agent_slug: agent.slug, model });

      let streamError: string | null = null;
      const isOllama = provider === "ollama";
      try {
        for await (const ev of streamChat({
          provider,
          model,
          apiKey: isOllama ? "" : apiKey,
          baseUrl: isOllama ? apiKey : undefined,
          system,
          messages: incoming.filter((m) => m.role === "user" || m.role === "assistant"),
          maxTokens: 4096,
        })) {
          if (ev.type === "delta") {
            send("delta", { text: ev.text });
          } else if (ev.type === "done") {
            send("usage", { input_tokens: ev.inputTokens, output_tokens: ev.outputTokens });
          } else if (ev.type === "error") {
            streamError = redactAll(ev.message);
            send("error", { message: streamError });
          }
        }
      } catch (err) {
        streamError = redactAll(err instanceof Error ? err.message : "stream_failed");
        send("error", { message: streamError });
      }
      send("done", {});
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
    },
  });
}
