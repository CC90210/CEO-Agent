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
import { composeDashboardContextV2 } from "@/lib/agent-context";
import { markReadDb } from "@/lib/agent-inbox-db";
import { rateLimit } from "@/lib/rate-limit";
import { extractActionMarkers, runAction } from "@/lib/agent-actions";
import { logAction } from "@/lib/action-log";
import {
  cloudToolsPromptBlock,
  extractCloudToolMarkers,
  runCloudTool,
  stripCloudToolMarkers,
} from "@/lib/cloud-tools";
import {
  cloudToolsPromptBlockV2,
  streamAnthropicWithTools,
} from "@/lib/cloud-tool-runner";
import { resolveChatContext } from "@/lib/chat-auth";
import { getBridgeOnline, getBridgeToolCapabilities } from "@/lib/queries";
import { signResumeState } from "@/lib/resume-hmac";
import { getAgentInfo } from "@/lib/agents";
import { getTenantManifestForUser } from "@/lib/manifest/tenant-scope";
import { redactAll } from "@/lib/secret-redaction";
import { persistAssistantTurn } from "@/lib/chat-persistence";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300; // 5 min — enough for long Sonnet/Opus runs

type IncomingPayload = {
  agent_key?: string;
  session_id?: string | null;
  messages?: ChatMessage[];
  /**
   * Cloud-mode tool surface selector.
   *   "tools"  (default for anthropic provider) — native Anthropic tool_use
   *            loop via lib/cloud-tool-runner. Mid-stream tool calls, results
   *            re-fed to the model, full chain-of-tools. The "API key power"
   *            path that gives the operator Claude-Code-class capability.
   *   "markers" — legacy text-marker pipe (model emits <cloud-tool> markers,
   *            we parse + execute AFTER the stream ends, surface results).
   *            Used by non-Anthropic providers (OpenAI / Google / OpenRouter)
   *            until those adapters get native tool calling.
   *   "off"   — straight text stream, no tool affordances. Operators who
   *            just want chat without dashboard mutation can pin this from
   *            the chat-mode picker.
   */
  cloud_tools?: "tools" | "markers" | "off";
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

  // Resolve tenant + per-agent provider/model/key. Single helper handles
  // user_profiles lookup, agent_model_config decrypt, and the operator
  // platform-key fallback — shared with /api/chat/resume. See lib/chat-auth.ts.
  const ctxResult = await resolveChatContext({ id: user.id, email: user.email }, agentKey);
  if (!ctxResult.ok) {
    return jsonError(ctxResult.status, ctxResult.detail || ctxResult.code);
  }
  const { tenantId, provider, model, apiKey, cfgOverride } = ctxResult;
  const service = getServiceSupabase();

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
  // Bridge-online detection — the persona notice that follows depends on
  // whether the operator's local bridge is reachable. When it IS, Phase 2
  // of giggly-reef gives the cloud-mode chat real local tools (read_file,
  // write_file, bash, send_email, send_sms) via the browser proxy to
  // localhost:9100/exec-tool. Without this check, the OLD notice would
  // gaslight the model into telling the operator "I can't send email —
  // run bravo bridge serve" even when the bridge is right there waiting
  // for the tool call. Caught 2026-05-15 from CC's screenshot.
  // Bridge online check + advertised tool list (Phase F). Single round
  // trip vs the original separate getBridgeOnline call. When the bridge
  // is online AND has advertised a capabilities list, the dashboard
  // intersects TOOL_DEFINITIONS with what the bridge claims it supports.
  // When no advertisement is on record yet (older bridge daemons,
  // freshly-paired bridges before their first heartbeat), bridgeAdvertisedTools
  // is null and the dashboard falls back to advertising every defer:true
  // tool in TOOL_DEFINITIONS (pre-Phase-F behavior).
  const bridgeState = await getBridgeToolCapabilities(tenantId).catch(
    () => ({ online: false, tools: null as string[] | null }),
  );
  const bridgeOnline = bridgeState.online;
  const bridgeAdvertisedTools = bridgeState.tools;

  // Per-agent tool palette from the tenant's manifest (Phase D of
  // giggly-reef). Undefined → no manifest filter (full palette).
  const manifestForChat = await getTenantManifestForUser(tenantId).catch(() => null);
  const agentBinding = manifestForChat?.agents?.find(
    (a) => a.slug.toLowerCase() === agentKey,
  );
  const toolPalette: string[] | undefined = agentBinding?.tool_palette;

  // Two notices — one for "cloud-only" (no local tools available) and
  // one for "cloud + bridge" (operator API key powers the LLM, local
  // bridge owns tool execution). The model gets ONE of them so it
  // doesn't have to guess. Empty when cloud_tools is "off".
  //
  // Phase 0 of harness completeness — these are agent-agnostic. Bravo-
  // specific CLI strings ("bravo bridge serve") removed; the universal
  // "pm2 restart claude-bridge" is correct for every agent on the
  // operator's machine since the bridge is one process shared across
  // agents. The model is addressed by its registry label so Maven
  // says "Maven, your CMO," not "Bravo, your lead architect."
  const agentInfo = getAgentInfo(agentKey);
  const agentLabel = agentInfo.label || agentKey.toUpperCase();
  const agentRole = agentInfo.role || "agent";

  const cloudModeNoticeBridge = `\n\n---\nRUNTIME: CLOUD MODE + LOCAL BRIDGE\nYou are ${agentLabel} (${agentRole}), running through the dashboard's /api/chat path on Vercel — but the operator's local bridge IS online. The browser proxies tool_use calls to localhost:9100/exec-tool, so you have real local capabilities even though the LLM call itself is going through the operator's API key.\n\nWhat you CAN do:\n- Anything in the cloud tool palette below (records, http_get/post, integrations).\n- Read/write files on the operator's machine (read_file, write_file).\n- Run shell commands (bash) — confirm destructive ones first.\n- Discover the operator's scripts (list_scripts) and run them (run_script).\n- Discover the operator's playbooks (list_skills) and load them (load_skill) before executing procedural work — they exist for a reason; don't improvise.\n- Send real emails (send_email) via the operator's Gmail.\n- Send SMS (send_sms) — always include opt-out language on first-touch.\n- Mutate dashboard data via <dashboard-action> markers.\n- Strategy, drafting, brainstorming, advice.\n\nIf a bridge tool fails with "bridge_unreachable" in the result, the operator's bridge just went offline mid-turn. Tell them to check \`pm2 logs claude-bridge\` and \`pm2 restart claude-bridge\` — don't retry the same tool.\n---`;

  const cloudModeNoticeNoBridge = `\n\n---\nRUNTIME: CLOUD ONLY\nYou are ${agentLabel} (${agentRole}), running through the dashboard's /api/chat path on Vercel. The operator's local bridge is NOT online right now. You have the DASHBOARD STATE block below (real Supabase data — MRR, pipeline, recent inbound, today's plan, integrations health) plus the cloud tool palette (records, http_get/post, integrations) but NO local file system access, no shell, no email/SMS sends, no Python scripts.\n\nIf the operator asks for something that needs the local machine (read a file, send an email, run a script, follow a playbook):\n- Be explicit: say the bridge isn't online right now.\n- Tell them: "Open a terminal on your machine and run \`pm2 restart claude-bridge\`. The chat header will turn cyan when it comes back and I'll have read_file / write_file / bash / send_email / send_sms / list_skills / list_scripts available."\n- Do NOT infer file contents. Do NOT pretend to have sent emails you didn't send.\n\nWhat you CAN do right now:\n- Use the cloud tool palette below (records read/write/search, http_get/post, lead lookup, integration status).\n- Mutate dashboard data via <dashboard-action> markers.\n- Strategy, drafting, brainstorming, advice — anything that doesn't need the operator's machine.\n---`;

  const cloudModeNotice = bridgeOnline
    ? cloudModeNoticeBridge
    : cloudModeNoticeNoBridge;
  // Inject live dashboard state — MRR, pipeline, recent inbound, today's
  // plan, integrations health, INBOX FOR YOU — so the agent answers from
  // real data instead of asking the operator for things it can already
  // see. V2 also returns the inbox message IDs we injected so we can
  // mark them read after the stream completes successfully (closes the
  // inbox loop documented on /inbox).
  const dashboardCtxResult = await composeDashboardContextV2({ tenantId, agentKey }).catch(
    () => ({ text: "", injectedInboxIds: [] as string[] })
  );
  const dashboardCtx = dashboardCtxResult.text;
  const injectedInboxIds = dashboardCtxResult.injectedInboxIds;
  // Cloud-mode tool surface selection.
  //
  // - "tools"   → native Anthropic tool_use loop (cloud-tool-runner.ts).
  //               Only valid when provider === "anthropic". The persona
  //               gets cloudToolsPromptBlockV2 (which describes the tools
  //               by name; the API contract teaches the model their schema).
  // - "markers" → legacy <cloud-tool> text-marker pipe (cloud-tools.ts).
  //               Used for non-Anthropic providers and as an explicit
  //               fallback. Tools execute AFTER the stream, surfaced via
  //               the same cloud_tool_result SSE event the UI already
  //               renders.
  // - "off"     → no tool affordances. Operators can pin this from the
  //               chat-mode picker when they want straight chat.
  const requestedCloudTools = payload.cloud_tools;
  const cloudToolsMode: "tools" | "markers" | "off" =
    requestedCloudTools === "off"
      ? "off"
      : requestedCloudTools === "tools"
        ? (provider === "anthropic" ? "tools" : "markers") // fall back if provider can't
        : requestedCloudTools === "markers"
          ? "markers"
          : provider === "anthropic"
            ? "tools" // default: prefer native tools on Anthropic
            : "markers";

  const cloudToolsBlock =
    cloudToolsMode === "off"
      ? ""
      : cloudToolsMode === "tools"
        ? cloudToolsPromptBlockV2({ bridgeOnline })
        : cloudToolsPromptBlock();
  // Phase J — fold per-agent setup answers from the onboarding wizard
  // into a "TENANT SETUP" overlay so the agent sees the operator's
  // specifics (FICO floor, send window, TCPA language, etc.) from turn
  // one. Stable per (tenant, agent) — answers live on the manifest
  // agent binding. Operator can edit later via the manifest editor;
  // changes take effect on the next chat turn.
  const setupAnswers = agentBinding?.setup_answers;
  let setupBlock = "";
  if (setupAnswers && typeof setupAnswers === "object" && Object.keys(setupAnswers).length > 0) {
    const lines: string[] = ["", "---", "TENANT SETUP"];
    lines.push("Operator-provided context from onboarding. Treat these as authoritative facts about how this tenant runs. Apply them in every decision unless the operator explicitly overrides in the conversation.");
    lines.push("");
    for (const [k, v] of Object.entries(setupAnswers)) {
      lines.push(`- ${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`);
    }
    lines.push("---");
    setupBlock = lines.join("\n");
  }
  const persona = `${personaBase}${cloudModeNotice}${cloudToolsBlock}${setupBlock}${dashboardCtx ? `\n\n${dashboardCtx}` : ""}`;
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
        if (cloudToolsMode === "tools" && provider === "anthropic") {
          // Native Anthropic tool_use loop. The runner re-opens /v1/messages
          // each iteration as tools chain — it yields {delta, tool_use,
          // tool_result, done, error} which we forward to the SSE client.
          // The operator sees a "tool call: NAME" chip in the chat while the
          // loop is running.
          const stripped = messages.filter((m) => m.role !== "system") as Array<{
            role: "user" | "assistant";
            content: string;
          }>;
          for await (const ev of streamAnthropicWithTools(
            {
              apiKey,
              model,
              system: persona,
              messages: stripped,
              // Filter deferred (bridge-routed) tools out of the palette
              // when the bridge isn't online. Prevents the model from
              // trying to call send_email / bash etc. and getting
              // bridge_unreachable errors back; the cloud-mode notice
              // upstream tells the operator to start the bridge.
              excludeDeferredTools: !bridgeOnline,
              // Per-agent allowlist from the manifest. Undefined = full
              // palette (current default). Phase D adds operator-side
              // UI in Settings → Agents to populate this per agent.
              toolPalette,
              // Bridge-advertised tool list (Phase F). When set,
              // restricts the bridge-side palette to what the live
              // pairing actually has installed. null = no advertisement
              // on record; runner falls back to the hardcoded bridge set.
              bridgeAdvertisedTools,
            },
            { tenantId, userId: user.id, agentKey, authUserId: user.id }
          )) {
            if (ev.type === "delta") {
              assistantText += ev.text;
              send("delta", { text: ev.text });
            } else if (ev.type === "tool_use") {
              send("cloud_tool_call", { name: ev.name, input: ev.input });
            } else if (ev.type === "tool_result") {
              send("cloud_tool_result", {
                ok: ev.ok,
                name: ev.name,
                summary: ev.summary,
              });
            } else if (ev.type === "tool_use_pending") {
              // Deferred tool — model called something that needs the
              // operator's local bridge. Forward the pending event +
              // resume_state to the browser; the ChatWidget proxies the
              // call to localhost:9100/exec-tool and POSTs the result
              // to /api/chat/resume to continue the iteration.
              //
              // Phase H: sign resume_state with HMAC so /api/chat/resume
              // can verify it was server-issued. Browser is a passthrough;
              // it can't mint valid signatures because BRAVO_RESUME_HMAC_KEY
              // is server-only. In production, signResumeState returns null
              // if the env var is missing — we fail closed by emitting an
              // error event instead of a tool_use_pending.
              const sig = signResumeState(ev.resume_state);
              if (sig === null) {
                streamError = "server_misconfigured:resume_hmac_key_missing";
                send("error", { message: streamError });
              } else {
                send("tool_use_pending", {
                  tool_use_id: ev.tool_use_id,
                  name: ev.name,
                  input: ev.input,
                  resume_state: ev.resume_state,
                  resume_signature: sig,
                });
              }
            } else if (ev.type === "done") {
              usageIn = ev.inputTokens;
              usageOut = ev.outputTokens;
              send("usage", { input_tokens: ev.inputTokens, output_tokens: ev.outputTokens });
            } else if (ev.type === "error") {
              streamError = redactAll(ev.message);
              send("error", { message: streamError });
            }
          }
        } else {
          // Legacy / fallback path: straight text stream via provider
          // adapter. Cloud tools (if mode === "markers") run AFTER the
          // stream completes via the existing marker-extraction block.
          //
          // Ollama / LM Studio: the "API key" field stores the local
          // endpoint URL (operators paste e.g. http://localhost:11434/v1
          // during onboarding because there's no real key). Pass it as
          // baseUrl, leave apiKey blank — streamOllama defaults to the
          // standard Ollama port if baseUrl is empty.
          const isOllama = provider === "ollama";
          for await (const ev of streamChat({
            provider,
            model,
            apiKey: isOllama ? "" : apiKey,
            baseUrl: isOllama ? apiKey : undefined,
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
              // Redact any operator/platform credential values before
              // emitting over SSE or persisting — provider error bodies
              // can echo headers / URLs that contain the API key.
              streamError = redactAll(ev.message);
              send("error", { message: streamError });
            }
          }
        }
      } catch (err) {
        const raw = err instanceof Error ? err.message : "stream_failed";
        streamError = redactAll(raw);
        send("error", { message: streamError });
      }

      // ---- Cloud tool markers (legacy / fallback) -------------------------
      // <cloud-tool name="..."> JSON </cloud-tool> — read-only / safe tools
      // for providers that don't use the native tool_use loop. When mode is
      // "tools" we already executed everything mid-stream above, so skip
      // this block.
      if (cloudToolsMode === "markers") {
        try {
          const toolSpecs = extractCloudToolMarkers(assistantText);
          for (const spec of toolSpecs) {
            const r = await runCloudTool(spec, { tenantId, userId: user.id });
            send("cloud_tool_result", r);
          }
        } catch (err) {
          send("cloud_tool_result", {
            ok: false,
            name: "?",
            error: err instanceof Error ? err.message : "cloud_tool_runner_failed",
          });
        }
      }

      // ---- Dashboard mutation markers ------------------------------------
      // The model emits <dashboard-action type="..." > JSON </dashboard-action>
      // when the operator asks for a change. Parse, validate, apply, surface.
      //
      // In "tools" mode, create_record / update_record / delete_record are
      // exposed as native Anthropic tools — the model called them mid-stream
      // and we already executed. Filter them out of the marker pass here to
      // avoid double-writes if the model emitted BOTH a tool_use AND a
      // text marker for the same intent (rare, but possible because the
      // persona still teaches DASHBOARD_ACTION_SPEC). Operator-side actions
      // like update_profile / toggle_agent_enabled still run via markers
      // because they aren't in the cloud-tool palette.
      const toolNativeMarkerTypes = new Set([
        "create_record",
        "update_record",
        "delete_record",
      ]);
      try {
        const rawSpecs = extractActionMarkers(assistantText);
        const specs =
          cloudToolsMode === "tools"
            ? rawSpecs.filter((s) => !toolNativeMarkerTypes.has(s.type))
            : rawSpecs;
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
      // Shared writer in lib/chat-persistence — same helper /api/chat/resume
      // uses. Centralizes redaction + chat_messages row shape so schema
      // changes only need to land in one place.
      const latencyMs = Date.now() - startedAt;
      await persistAssistantTurn({
        sessionId,
        tenantId,
        content: assistantText,
        inputTokens: usageIn,
        outputTokens: usageOut,
        latencyMs,
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

      // ---- Mark injected inbox messages read ----------------------------
      // The "INBOX FOR YOU" block in the system prompt was assembled by
      // composeDashboardContextV2; it returned the IDs it consumed. We
      // mark them read NOW (after the assistant successfully responded
      // and was persisted) so they don't repeat on the next turn. If
      // the stream errored above, streamError is non-null but we still
      // mark read — the agent saw the message; "delivered" is the right
      // semantic. If the route never got here at all (caller disconnect,
      // crash before persist), the messages stay unread for retry.
      if (injectedInboxIds.length > 0 && !streamError) {
        await Promise.all(
          injectedInboxIds.map((id) =>
            markReadDb(tenantId, id).catch(() => null)
          )
        );
      }
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

// Platform-default operator credentials live in lib/operator-credentials.ts —
// shared with the manifest chat endpoint (api/manifest/chat) so both paths
// agree on "is this the platform operator, and which env key falls back."
