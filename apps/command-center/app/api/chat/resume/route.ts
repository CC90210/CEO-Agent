/**
 * POST /api/chat/resume
 *
 * Resumes a paused Anthropic tool_use loop after the browser has executed
 * a deferred tool via the local bridge. Phase 2 of giggly-reef.
 *
 * Flow:
 *   1. /api/chat streams a turn. Model emits tool_use for a tool marked
 *      defer:true (e.g., send_email). cloud-tool-runner yields
 *      `tool_use_pending` with the ResumeState; route forwards as SSE
 *      and closes the stream.
 *   2. ChatWidget POSTs to localhost:9100/exec-tool with the tool name
 *      + input. The bridge runs it locally (bridge_tools.execute_tool),
 *      returns { output, is_error }.
 *   3. ChatWidget POSTs to this route with the original ResumeState +
 *      the tool_result. We re-open the Anthropic stream picking up
 *      where the pause happened.
 *
 * Body:
 *   {
 *     agent_key: string,
 *     session_id?: string,
 *     resume_state: ResumeState,        // opaque to the client, originally
 *                                        // issued by cloud-tool-runner
 *     tool_use_id: string,              // matches the paused tool_use block
 *     tool_result: {
 *       content: string,
 *       is_error: boolean,
 *     }
 *   }
 *
 * Response: text/event-stream with the same shape /api/chat uses
 *   (session/delta/cloud_tool_call/cloud_tool_result/tool_use_pending/usage/done/error).
 *
 * Auth: same as /api/chat. Resume state passes through the browser; this
 * route trusts the user's session cookie. v1 does NOT HMAC-sign the
 * resume state — replay attacks only let an operator mess with their
 * own chat. Document this when /api/chat/resume goes multi-tenant.
 */

import { NextRequest } from "next/server";
import { getSessionUser } from "@/lib/supabase-server";
import { chatAgentKeys } from "@/lib/agent-personas";
import { rateLimit } from "@/lib/rate-limit";
import { resolveChatContext } from "@/lib/chat-auth";
import {
  resumeAnthropicTurn,
  type ResumeState,
} from "@/lib/cloud-tool-runner";
import { redactAll } from "@/lib/secret-redaction";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

type IncomingPayload = {
  agent_key?: string;
  session_id?: string | null;
  resume_state?: ResumeState;
  tool_use_id?: string;
  tool_result?: { content?: string; is_error?: boolean };
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

  const resumeState = payload.resume_state;
  if (!resumeState || typeof resumeState !== "object" || !Array.isArray(resumeState.history)) {
    return jsonError(400, "missing_or_invalid_resume_state");
  }

  const toolUseId = String(payload.tool_use_id || "").trim();
  if (!toolUseId) return jsonError(400, "missing_tool_use_id");

  const toolResult = payload.tool_result;
  if (!toolResult || typeof toolResult.content !== "string") {
    return jsonError(400, "missing_tool_result");
  }
  const normalizedResult = {
    content: toolResult.content,
    is_error: Boolean(toolResult.is_error),
  };

  // Resolve tenant + per-agent provider/key. Single source of truth for the
  // auth+tenant+key plumbing — same helper /api/chat uses.
  const ctxResult = await resolveChatContext({ id: user.id, email: user.email }, agentKey);
  if (!ctxResult.ok) {
    return jsonError(ctxResult.status, ctxResult.detail || ctxResult.code);
  }
  const { tenantId, provider, apiKey } = ctxResult;

  // Per-tenant token bucket — sized smaller than /api/chat (resumes are
  // continuations of a paused turn; burst caps don't add value here).
  const limit = rateLimit({
    key: `chat-resume:${tenantId}`,
    capacity: 30,
    refillPerSec: 1 / 15,
  });
  if (!limit.allowed) {
    return new Response(
      JSON.stringify({ ok: false, error: "rate_limited", retry_in_sec: limit.resetIn }),
      { status: 429, headers: { "content-type": "application/json" } }
    );
  }

  // Resume is only supported on the Anthropic tool_use loop. Markers
  // path (non-Anthropic providers) doesn't pause — the tool_use_pending
  // event never fires there.
  if (provider !== "anthropic") {
    return jsonError(400, `resume_not_supported_for_provider:${provider}`);
  }

  // Stream the resumed iteration back to the browser as SSE.
  const encoder = new TextEncoder();
  const sessionId = payload.session_id || null;

  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: string, data: unknown) => {
        controller.enqueue(
          encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
        );
      };
      if (sessionId) send("session", { session_id: sessionId });

      try {
        for await (const ev of resumeAnthropicTurn(
          resumeState,
          toolUseId,
          normalizedResult,
          { tenantId, userId: user.id, agentKey, authUserId: user.id },
          apiKey,
        )) {
          if (ev.type === "delta") {
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
            // Another deferred tool on the resumed turn — perfectly
            // valid. Forward it; ChatWidget will loop through another
            // bridge execution + resume.
            send("tool_use_pending", {
              tool_use_id: ev.tool_use_id,
              name: ev.name,
              input: ev.input,
              resume_state: ev.resume_state,
            });
          } else if (ev.type === "done") {
            send("usage", {
              input_tokens: ev.inputTokens,
              output_tokens: ev.outputTokens,
            });
          } else if (ev.type === "error") {
            send("error", { message: redactAll(ev.message) });
          }
        }
      } catch (err) {
        const raw = err instanceof Error ? err.message : "resume_failed";
        send("error", { message: redactAll(raw) });
      }

      send("done", {});
      controller.close();
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

function jsonError(status: number, message: string) {
  return new Response(JSON.stringify({ ok: false, error: message }), {
    status,
    headers: { "content-type": "application/json" },
  });
}
