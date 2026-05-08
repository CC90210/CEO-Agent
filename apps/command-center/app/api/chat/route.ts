/**
 * POST /api/chat
 *
 * Streaming chat endpoint for the dashboard widget. Streams SSE deltas back
 * to the browser while persisting the full turn to chat_messages on completion.
 *
 * Auth: requires logged-in Supabase user. Resolves their tenant_id, looks up
 * agent_model_config for (tenant_id, agent_key), decrypts the API key, and
 * proxies the call to the chosen provider.
 *
 * Request body:
 *   {
 *     agent_key: "bravo" | "maven" | "atlas" | "aura" | "hermes",
 *     session_id?: uuid,                  // omit to start a new session
 *     messages: [{ role, content }, ...]  // client maintains rolling history
 *   }
 *
 * Response: text/event-stream with frames:
 *   event: session   data: { session_id }
 *   event: delta     data: { text }
 *   event: usage     data: { input_tokens, output_tokens }
 *   event: done      data: {}
 *   event: error     data: { message }
 */

import { NextRequest } from "next/server";
import { getAuthedSupabase, getServiceSupabase, getSessionUser } from "@/lib/supabase-server";
import {
  streamChat,
  type ChatMessage,
  type Provider,
} from "@/lib/providers";
import { getPersona, chatAgentKeys } from "@/lib/agent-personas";
import { decryptField } from "@/lib/field-encryption";
import { composeDashboardContext } from "@/lib/agent-context";
import { rateLimit } from "@/lib/rate-limit";
import { extractActionMarkers, runAction } from "@/lib/agent-actions";
import { logAction } from "@/lib/action-log";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300; // 5 min — enough for long Sonnet/Opus runs

type IncomingPayload = {
  agent_key?: string;
  session_id?: string | null;
  messages?: ChatMessage[];
};

export async function POST(req: NextRequest) {
  const user = await getSessionUser();
  if (!user) return jsonError(401, "unauthorized");

  let payload: IncomingPayload;
  try {
    payload = (await req.json()) as IncomingPayload;
  } catch {
    return jsonError(400, "invalid_json");
  }

  const agentKey = (payload.agent_key || "").toLowerCase();
  if (!chatAgentKeys().includes(agentKey)) {
    return jsonError(400, `invalid_agent:${agentKey}`);
  }
  const messages = Array.isArray(payload.messages) ? payload.messages : [];
  const lastUserMsg = [...messages].reverse().find((m) => m.role === "user");
  if (!lastUserMsg) return jsonError(400, "no_user_message");

  // Resolve tenant_id via service role (faster + RLS-bypass; the auth
  // check at the top of the handler is what gates access). Same trip as
  // the agent_model_config lookup → 1 round-trip for "who are you + what
  // model do you want" instead of 2.
  const service = getServiceSupabase();
  const profileQuery = service
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();

  const profileRes = await profileQuery;
  const profile = profileRes.data as { tenant_id: string | null } | null;
  if (!profile?.tenant_id) return jsonError(403, "no_tenant");
  const tenantId = profile.tenant_id as string;

  // Per-tenant token bucket: 30 turns burst, refill at 1/turn-per-15s
  // (= 4/min steady state). Protects the platform key on operator-fallback;
  // client tenants paying their own provider hit this too but the cap is
  // generous — a real human can't sustain 4 messages/min anyway.
  const limit = rateLimit({
    key: `chat:${tenantId}`,
    capacity: 30,
    refillPerSec: 1 / 15,
  });
  if (!limit.allowed) {
    return new Response(
      JSON.stringify({
        ok: false,
        error: "rate_limited",
        retry_in_sec: limit.resetIn,
      }),
      {
        status: 429,
        headers: {
          "content-type": "application/json",
          "retry-after": String(limit.resetIn),
        },
      }
    );
  }

  // ---- Resolve agent_model_config + decrypt key ---------------------------
  const { data: cfg } = await service
    .from("agent_model_config")
    .select("provider, model, encrypted_api_key, system_prompt_override, enabled")
    .eq("tenant_id", tenantId)
    .eq("agent_key", agentKey)
    .maybeSingle();

  // Admin/operator fallback: when CC (or another admin) chats and has no
  // per-agent config row, fall back to a platform-supplied API key from env.
  // Clients must always BYO key — the fallback is gated by email match.
  const isOperator = isAdminEmail(user.email || "");
  let provider: Provider;
  let model: string;
  let apiKey = "";
  let cfgOverride: string | null = null;

  if (cfg) {
    if (!cfg.enabled) return jsonError(403, "agent_disabled");
    provider = cfg.provider as Provider;
    model = cfg.model as string;
    cfgOverride = cfg.system_prompt_override || null;
    if (!cfg.encrypted_api_key) {
      // Row exists but key wasn't set — try operator fallback before failing
      const fallback = isOperator ? operatorFallback() : null;
      if (!fallback) return jsonError(412, "no_api_key");
      provider = fallback.provider;
      model = fallback.model;
      apiKey = fallback.apiKey;
    } else {
      try {
        apiKey = decryptField(cfg.encrypted_api_key as string);
      } catch (err) {
        return jsonError(500, err instanceof Error ? err.message : "key_decrypt_failed");
      }
    }
  } else {
    // No config row at all
    const fallback = isOperator ? operatorFallback() : null;
    if (!fallback) {
      return jsonError(
        412,
        isOperator ? "admin_no_platform_key" : "agent_not_configured"
      );
    }
    provider = fallback.provider;
    model = fallback.model;
    apiKey = fallback.apiKey;
  }

  // ---- Open or create chat_sessions row -----------------------------------
  let sessionId = payload.session_id || null;
  if (!sessionId) {
    const { data: created, error: createErr } = await service
      .from("chat_sessions")
      .insert({
        tenant_id: tenantId,
        user_id: user.id,
        agent_key: agentKey,
        provider,
        model,
        title: lastUserMsg.content.slice(0, 80),
      })
      .select("id")
      .single();
    if (createErr || !created) return jsonError(500, "session_create_failed");
    sessionId = created.id as string;
  }

  // ---- Persist incoming user message --------------------------------------
  await service.from("chat_messages").insert({
    session_id: sessionId,
    tenant_id: tenantId,
    role: "user",
    content: lastUserMsg.content,
  });

  const personaBase = getPersona(agentKey, cfgOverride);
  // Cloud-mode disclosure — this is the path that runs when the local
  // bridge isn't serving. The agent has DASHBOARD STATE (operator's MRR,
  // pipeline, today's plan, etc) but NO file-system access. Be honest
  // about it; don't infer a repo you can't read.
  const cloudModeNotice = `\n\n---\nRUNTIME: CLOUD MODE\nYou are running through the dashboard's /api/chat path on Vercel, not the operator's local bridge. You have the DASHBOARD STATE block below (real Supabase data — MRR, pipeline, recent inbound, today's plan, integrations health). You do NOT have access to the operator's local file system, brain/* files, skills/* bodies, or any repo content.\n\nIf the operator asks about local files, code structure, or anything that requires reading the repo:\n- Be explicit: say you're in cloud mode without file access.\n- Tell them: "Run \`bravo bridge serve\` on your machine. The chat will then route to localhost with full repo access — you'll see the header turn cyan."\n- Do NOT infer file contents. Do NOT speculate about brain/ structure. Do NOT pretend to have read SOUL.md or any other file.\n\nWhat you CAN do in cloud mode:\n- Answer using the DASHBOARD STATE block.\n- Mutate dashboard data via <dashboard-action> markers (see below).\n- Strategy, drafting, brainstorming, advice — anything that doesn't need file reads.\n---`;
  // Inject live dashboard state — MRR, pipeline, recent inbound, today's
  // plan, integrations health — so the agent answers from real data instead
  // of asking the operator for things it can already see.
  const dashboardCtx = await composeDashboardContext({ tenantId, agentKey }).catch(() => "");
  const persona = `${personaBase}${cloudModeNotice}${dashboardCtx ? `\n\n${dashboardCtx}` : ""}`;
  const startedAt = Date.now();

  // ---- Stream response back as SSE ----------------------------------------
  const encoder = new TextEncoder();
  let assistantText = "";
  let usageIn = 0;
  let usageOut = 0;
  let streamError: string | null = null;

  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: string, data: unknown) => {
        controller.enqueue(
          encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
        );
      };
      send("session", { session_id: sessionId });

      try {
        for await (const ev of streamChat({
          provider,
          model,
          apiKey,
          system: persona,
          messages,
        })) {
          if (ev.type === "delta") {
            assistantText += ev.text;
            send("delta", { text: ev.text });
          } else if (ev.type === "done") {
            usageIn = ev.inputTokens;
            usageOut = ev.outputTokens;
            send("usage", { input_tokens: ev.inputTokens, output_tokens: ev.outputTokens });
          } else if (ev.type === "error") {
            streamError = ev.message;
            send("error", { message: ev.message });
          }
        }
      } catch (err) {
        streamError = err instanceof Error ? err.message : "stream_failed";
        send("error", { message: streamError });
      }

      // ---- Dashboard mutation markers ------------------------------------
      // The model emits <dashboard-action type="..." > JSON </dashboard-action>
      // when the operator asks for a change. Parse, validate, apply, surface.
      try {
        const specs = extractActionMarkers(assistantText);
        for (const spec of specs) {
          const r = await runAction(spec, { tenantId, authUserId: user.id });
          send("action", r);
          // A6: audit log to agent_events. Best-effort; never throws.
          await logAction({
            agent_key: agentKey,
            tenant_id: tenantId,
            user_id: user.id,
            type: r.type,
            ok: r.ok,
            summary: r.ok ? r.summary : undefined,
            error: !r.ok ? r.error : undefined,
          });
        }
      } catch (err) {
        // A failing action handler must not break the stream close
        send("action", {
          ok: false,
          type: "?",
          error: err instanceof Error ? err.message : "actions_failed",
        });
      }

      send("done", {});
      controller.close();

      // ---- Persist assistant turn ----------------------------------------
      const latencyMs = Date.now() - startedAt;
      await service.from("chat_messages").insert({
        session_id: sessionId,
        tenant_id: tenantId,
        role: "assistant",
        content: assistantText,
        input_tokens: usageIn,
        output_tokens: usageOut,
        latency_ms: latencyMs,
        error: streamError,
      });
      const cost = estimateCostUsd(provider, model, usageIn, usageOut);
      await service
        .from("chat_sessions")
        .update({
          total_input_tokens: usageIn,
          total_output_tokens: usageOut,
          estimated_cost_usd: cost,
          updated_at: new Date().toISOString(),
        })
        .eq("id", sessionId);
      await service
        .from("agent_model_config")
        .update({ last_used_at: new Date().toISOString() })
        .eq("tenant_id", tenantId)
        .eq("agent_key", agentKey);
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-store",
      connection: "keep-alive",
      "x-accel-buffering": "no",
    },
  });
}

/* ============================================================================
 * Cost estimation (rough — published per-1M-token pricing as of 2026-05).
 * Wrong is fine; we just want a directional number on the dashboard.
 * ============================================================================ */
function estimateCostUsd(
  provider: Provider,
  model: string,
  inTok: number,
  outTok: number
): number {
  const m = model.toLowerCase();
  let inP = 0;
  let outP = 0;
  if (provider === "anthropic") {
    if (m.includes("opus")) {
      inP = 15;
      outP = 75;
    } else if (m.includes("sonnet")) {
      inP = 3;
      outP = 15;
    } else {
      inP = 1;
      outP = 5;
    }
  } else if (provider === "openai") {
    if (m.includes("mini")) {
      inP = 0.25;
      outP = 2;
    } else if (m.includes("codex")) {
      inP = 3;
      outP = 12;
    } else {
      inP = 2.5;
      outP = 10;
    }
  } else if (provider === "google") {
    if (m.includes("flash")) {
      inP = 0.3;
      outP = 1.2;
    } else {
      inP = 1.25;
      outP = 5;
    }
  }
  return ((inTok * inP) + (outTok * outP)) / 1_000_000;
}

function jsonError(status: number, message: string) {
  return new Response(JSON.stringify({ ok: false, error: message }), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/* ============================================================================
 * Admin/operator helpers — platform-default keys for the operator tenant only.
 * Env vars (set on Vercel for the home tenant only — never for client deploys):
 *   OPERATOR_EMAIL, ADMIN_EMAILS (comma-separated)
 *   PLATFORM_DEFAULT_OPENROUTER_API_KEY (preferred — covers all models)
 *   PLATFORM_DEFAULT_ANTHROPIC_API_KEY
 *   PLATFORM_DEFAULT_OPENAI_API_KEY
 *   PLATFORM_DEFAULT_GOOGLE_API_KEY
 * ============================================================================ */
function isAdminEmail(email: string): boolean {
  const e = email.trim().toLowerCase();
  if (!e) return false;
  const operator = (process.env.OPERATOR_EMAIL || "").trim().toLowerCase();
  if (operator && e === operator) return true;
  const admins = (process.env.ADMIN_EMAILS || "")
    .split(",")
    .map((x) => x.trim().toLowerCase())
    .filter(Boolean);
  return admins.includes(e);
}

function operatorFallback():
  | { provider: Provider; model: string; apiKey: string }
  | null {
  const or = process.env.PLATFORM_DEFAULT_OPENROUTER_API_KEY;
  if (or) return { provider: "openrouter", model: "anthropic/claude-sonnet-4", apiKey: or };
  const ant = process.env.PLATFORM_DEFAULT_ANTHROPIC_API_KEY;
  if (ant) return { provider: "anthropic", model: "claude-sonnet-4-6", apiKey: ant };
  const oai = process.env.PLATFORM_DEFAULT_OPENAI_API_KEY;
  if (oai) return { provider: "openai", model: "gpt-5.4", apiKey: oai };
  const goo = process.env.PLATFORM_DEFAULT_GOOGLE_API_KEY;
  if (goo) return { provider: "google", model: "gemini-2.5-pro", apiKey: goo };
  return null;
}
