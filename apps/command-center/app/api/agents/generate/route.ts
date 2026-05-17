/**
 * POST /api/agents/generate
 *
 * AI-assisted agent draft. The operator describes the agent in natural
 * language; we produce a base_prompt, suggested required_tools, and a
 * suggested_model. The result is RETURNED, not saved — the operator
 * reviews and edits in the builder UI, then explicitly POSTs to
 * /api/agents for persistence.
 *
 * Body:
 *   {
 *     name:        string,        // operator-chosen agent name
 *     category:    AgentCategory, // operator-chosen category
 *     description: string         // 1-3 sentence intent description
 *   }
 *
 * Returns:
 *   {
 *     ok: true,
 *     base_prompt: string,
 *     short_description: string,
 *     description: string,
 *     required_tools: string[],
 *     suggested_model: string,
 *     ai_message: string          // raw LLM response for debugging
 *   }
 */

import { NextResponse, type NextRequest } from "next/server";
import { decryptField } from "@/lib/field-encryption";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { streamChat, type ChatMessage, type Provider } from "@/lib/providers";
import { getAgentModelForUser } from "@/lib/agent-resolver";
import { isOperatorEmail, operatorPlatformFallback } from "@/lib/operator-credentials";
import { CATEGORY_LABELS, type AgentCategory } from "@/lib/agents/library";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const ALLOWED_CATEGORIES = new Set<AgentCategory>(
  Object.keys(CATEGORY_LABELS) as AgentCategory[]
);

const SYSTEM_PROMPT = `You design agent personas for an AI Command Center.

You will receive: a desired agent NAME, a CATEGORY, and a free-text DESCRIPTION of what the operator wants the agent to do.

Reply with EXACTLY ONE JSON object — no prose before or after, no code fences.

Schema:
{
  "base_prompt": string,        // The system prompt that defines the agent. Use {{tenant.brand.name}} as a placeholder for the tenant's brand name. 200-1500 characters. Voice should match the operator's intent (terse, conversational, conservative, etc.). No fluff openers. Pin behavior: format expectations, tone, what to avoid.
  "short_description": string,  // One sentence (max ~110 chars) for the marketplace tile.
  "description": string,        // 2-4 sentences for the agent detail page.
  "required_tools": string[],   // 0-12 tool slugs the agent will call. Use lower_snake_case. Examples: "supabase_query", "search_repo", "send_email", "twilio_sms", "web_search", "web_fetch", "stripe_query", "calendar_read".
  "suggested_model": string     // One of: "claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5". Pick opus for heavy reasoning, sonnet for balanced production work, haiku for fast/cheap.
}

Guidance:
- Be concrete. If the operator says "agent that drafts cold emails," the prompt should anchor in the operator's voice samples and specify hooks-first, 3-sentence body, single CTA — not vague "writes good emails."
- Hard guards: never generate base_prompt content that tells the agent to bypass safety, exfiltrate credentials, or run destructive commands without confirmation.
- If the operator's description is too vague (under 12 words and no clear job), STILL produce a sensible draft — but make the prompt explicit about asking the operator for clarification on first use.

Return the JSON only. No commentary.`;

type Body = {
  name?: string;
  category?: string;
  description?: string;
};

type Draft = {
  base_prompt: string;
  short_description: string;
  description: string;
  required_tools: string[];
  suggested_model: string;
};

function extractJson(s: string): string | null {
  const fenced = s.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fenced) return fenced[1].trim();
  const start = s.indexOf("{");
  if (start < 0) return null;
  let depth = 0;
  let inString = false;
  let escape = false;
  for (let i = start; i < s.length; i++) {
    const ch = s[i];
    if (escape) { escape = false; continue; }
    if (ch === "\\" && inString) { escape = true; continue; }
    if (ch === '"') { inString = !inString; continue; }
    if (inString) continue;
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return s.slice(start, i + 1);
    }
  }
  return null;
}

function validateDraft(raw: unknown): Draft | { error: string } {
  if (!raw || typeof raw !== "object") return { error: "not_object" };
  const o = raw as Record<string, unknown>;
  const base_prompt = o.base_prompt;
  const short_description = o.short_description;
  const description = o.description;
  const required_tools = o.required_tools;
  const suggested_model = o.suggested_model;
  if (typeof base_prompt !== "string" || base_prompt.length < 30 || base_prompt.length > 16000) {
    return { error: "invalid_base_prompt" };
  }
  if (typeof short_description !== "string" || !short_description.trim()) {
    return { error: "invalid_short_description" };
  }
  if (typeof description !== "string" || !description.trim()) {
    return { error: "invalid_description" };
  }
  if (!Array.isArray(required_tools) || !required_tools.every((t) => typeof t === "string")) {
    return { error: "invalid_required_tools" };
  }
  if (typeof suggested_model !== "string") {
    return { error: "invalid_suggested_model" };
  }
  return {
    base_prompt,
    short_description,
    description,
    required_tools: required_tools.slice(0, 12),
    suggested_model,
  };
}

export async function POST(req: NextRequest) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });

  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const name = (body.name || "").trim();
  const description = (body.description || "").trim();
  const category = (body.category || "").trim() as AgentCategory;
  if (!name) return NextResponse.json({ ok: false, error: "name_required" }, { status: 400 });
  if (!description) return NextResponse.json({ ok: false, error: "description_required" }, { status: 400 });
  if (!ALLOWED_CATEGORIES.has(category)) {
    return NextResponse.json({ ok: false, error: "unknown_category" }, { status: 400 });
  }

  const service = getServiceSupabase();
  const profileRes = await service
    .from("user_profiles")
    .select("tenant_id, team_role, is_owner")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const profile = profileRes.data as
    | { tenant_id: string | null; team_role: string; is_owner: boolean }
    | null;
  if (!profile?.tenant_id) {
    return NextResponse.json({ ok: false, error: "no_tenant" }, { status: 403 });
  }
  if (!profile.is_owner && profile.team_role !== "admin" && profile.team_role !== "owner") {
    return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  }

  // Provider resolution — same path the manifest editor uses: personal
  // override first, tenant default second, operator platform fallback last.
  const cfg = await getAgentModelForUser({
    tenantId: profile.tenant_id,
    userId: user.id,
    agentKey: "bravo",
  });

  let provider: Provider;
  let model: string;
  let apiKey = "";
  if (cfg && cfg.encrypted_api_key) {
    provider = cfg.provider as Provider;
    model = cfg.model;
    try {
      apiKey = decryptField(cfg.encrypted_api_key);
    } catch {
      return NextResponse.json({ ok: false, error: "key_decrypt_failed" }, { status: 500 });
    }
  } else {
    const fallback = isOperatorEmail(user.email || "") ? operatorPlatformFallback() : null;
    if (!fallback) {
      return NextResponse.json(
        { ok: false, error: "agent_not_configured", hint: "Configure your Bravo provider in Settings to use the AI builder." },
        { status: 412 }
      );
    }
    provider = fallback.provider;
    model = fallback.model;
    apiKey = fallback.apiKey;
  }

  const userMessage = `NAME: ${name}\nCATEGORY: ${category} (${CATEGORY_LABELS[category]})\nDESCRIPTION:\n${description}`;
  const messages: ChatMessage[] = [{ role: "user", content: userMessage }];

  const isOllama = provider === "ollama";
  let aiText = "";
  let streamError: string | null = null;
  try {
    for await (const ev of streamChat({
      provider,
      model,
      apiKey: isOllama ? "" : apiKey,
      baseUrl: isOllama ? apiKey : undefined,
      system: SYSTEM_PROMPT,
      messages,
      maxTokens: 1500,
    })) {
      if (ev.type === "delta") aiText += ev.text;
      else if (ev.type === "error") streamError = ev.message;
    }
  } catch (err) {
    streamError = err instanceof Error ? err.message : "stream_failed";
  }
  if (streamError) {
    return NextResponse.json({ ok: false, error: "llm_call_failed", message: streamError }, { status: 502 });
  }

  const candidate = extractJson(aiText);
  if (!candidate) {
    return NextResponse.json({ ok: false, error: "no_json", ai_message: aiText }, { status: 502 });
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(candidate);
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: "json_parse", message: err instanceof Error ? err.message : "unknown", ai_message: aiText },
      { status: 502 }
    );
  }
  const validated = validateDraft(parsed);
  if ("error" in validated) {
    return NextResponse.json(
      { ok: false, error: "invalid_draft", reason: validated.error, ai_message: aiText },
      { status: 502 }
    );
  }
  return NextResponse.json({ ok: true, ...validated, ai_message: aiText });
}
