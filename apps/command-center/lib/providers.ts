/**
 * Multi-provider chat client.
 *
 * Three providers, one streaming interface. Each adapter takes a normalized
 * request (messages, model, system, api_key) and yields token deltas as
 * { type: "delta", text } or { type: "done", input_tokens, output_tokens }.
 *
 * No SDK deps — straight fetch against each vendor's REST API. Keeps the
 * Vercel bundle small and avoids version drift.
 *
 * Provider 5xx / 429 errors auto-retry via fetchWithRetry (3 attempts,
 * 2s/4s/8s with jitter) so a single Anthropic/OpenRouter blip doesn't
 * kill the chat. Once we have an open stream we don't retry mid-stream.
 */

import { fetchWithRetry } from "./retry";

export type ChatRole = "system" | "user" | "assistant";
export type ChatMessage = { role: ChatRole; content: string };

export type Provider = "openrouter" | "anthropic" | "openai" | "google";

export type ChatRequest = {
  provider: Provider;
  model: string;
  apiKey: string;
  system?: string;
  messages: ChatMessage[];
  maxTokens?: number;
};

export type StreamEvent =
  | { type: "delta"; text: string }
  | { type: "done"; inputTokens: number; outputTokens: number }
  | { type: "error"; message: string };

/** Default models per provider — what the picker offers. */
export const PROVIDER_MODELS: Record<Provider, string[]> = {
  openrouter: [
    "anthropic/claude-opus-4",
    "anthropic/claude-sonnet-4",
    "openai/gpt-5.4",
    "openai/gpt-5.4-mini",
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    "meta-llama/llama-3.3-70b-instruct",
  ],
  anthropic: [
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
  ],
  openai: ["gpt-5.4", "gpt-5.4-mini", "gpt-5.2", "gpt-5.3-codex"],
  google: ["gemini-2.5-pro", "gemini-2.5-flash"],
};

export const PROVIDER_LABEL: Record<Provider, string> = {
  openrouter: "OpenRouter (recommended)",
  anthropic: "Anthropic (Claude)",
  openai: "OpenAI",
  google: "Google (Gemini)",
};

/** Where each provider's signup + API key page lives. */
export const PROVIDER_LINKS: Record<Provider, { signup: string; apiKey: string; docs?: string }> = {
  openrouter: {
    signup: "https://openrouter.ai/sign-up",
    apiKey: "https://openrouter.ai/keys",
    docs: "https://openrouter.ai/docs/quick-start",
  },
  anthropic: {
    signup: "https://console.anthropic.com/signup",
    apiKey: "https://console.anthropic.com/settings/keys",
    docs: "https://docs.anthropic.com/en/api/getting-started",
  },
  openai: {
    signup: "https://platform.openai.com/signup",
    apiKey: "https://platform.openai.com/api-keys",
    docs: "https://platform.openai.com/docs/quickstart",
  },
  google: {
    signup: "https://aistudio.google.com/",
    apiKey: "https://aistudio.google.com/apikey",
    docs: "https://ai.google.dev/gemini-api/docs",
  },
};

/* ============================================================================
 * Public entry point — async generator that yields StreamEvents.
 * ============================================================================ */
export async function* streamChat(req: ChatRequest): AsyncGenerator<StreamEvent> {
  if (!req.apiKey) {
    yield { type: "error", message: "missing_api_key" };
    return;
  }
  if (!req.messages.length) {
    yield { type: "error", message: "empty_messages" };
    return;
  }
  switch (req.provider) {
    case "openrouter":
      yield* streamOpenRouter(req);
      return;
    case "anthropic":
      yield* streamAnthropic(req);
      return;
    case "openai":
      yield* streamOpenAI(req);
      return;
    case "google":
      yield* streamGoogle(req);
      return;
    default:
      yield { type: "error", message: `unknown_provider:${req.provider}` };
  }
}

/* ============================================================================
 * OpenRouter — OpenAI-compatible /api/v1/chat/completions
 * One key, hundreds of models. Recommended onboarding path.
 * ============================================================================ */
async function* streamOpenRouter(req: ChatRequest): AsyncGenerator<StreamEvent> {
  const messages: Array<{ role: ChatRole; content: string }> = [];
  if (req.system) messages.push({ role: "system", content: req.system });
  messages.push(...req.messages);

  const body = {
    model: req.model,
    messages,
    stream: true,
    max_tokens: req.maxTokens ?? 4096,
  };
  const res = await fetchWithRetry("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${req.apiKey}`,
      "HTTP-Referer": "https://oasisai.work",
      "X-Title": "OASIS Agent Command Center",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    const detail = await safeText(res);
    yield {
      type: "error",
      message:
        res.status >= 500 || res.status === 429
          ? `provider_temporarily_unavailable:openrouter_${res.status}`
          : `openrouter_${res.status}:${detail}`,
    };
    return;
  }
  let inputTokens = 0;
  let outputTokens = 0;
  for await (const event of parseSSE(res.body)) {
    const data = event.data;
    if (!data || data === "[DONE]") continue;
    if (typeof data === "string") continue;
    const choice = data.choices?.[0];
    const delta = choice?.delta?.content;
    if (typeof delta === "string" && delta.length) yield { type: "delta", text: delta };
    if (data.usage) {
      inputTokens = data.usage.prompt_tokens ?? inputTokens;
      outputTokens = data.usage.completion_tokens ?? outputTokens;
    }
  }
  yield { type: "done", inputTokens, outputTokens };
}

/* ============================================================================
 * Anthropic — /v1/messages with stream:true SSE
 * ============================================================================ */
async function* streamAnthropic(req: ChatRequest): AsyncGenerator<StreamEvent> {
  const body = {
    model: req.model,
    max_tokens: req.maxTokens ?? 4096,
    stream: true,
    system: req.system,
    messages: req.messages
      .filter((m) => m.role !== "system")
      .map((m) => ({ role: m.role, content: m.content })),
  };
  const res = await fetchWithRetry("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": req.apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    const detail = await safeText(res);
    yield {
      type: "error",
      message:
        res.status >= 500 || res.status === 429
          ? `provider_temporarily_unavailable:anthropic_${res.status}`
          : `anthropic_${res.status}:${detail}`,
    };
    return;
  }
  let inputTokens = 0;
  let outputTokens = 0;
  for await (const event of parseSSE(res.body)) {
    if (event.event === "message_start") {
      const usage = event.data?.message?.usage;
      if (usage) inputTokens = usage.input_tokens ?? 0;
    } else if (event.event === "content_block_delta") {
      const text = event.data?.delta?.text;
      if (typeof text === "string") yield { type: "delta", text };
    } else if (event.event === "message_delta") {
      const usage = event.data?.usage;
      if (usage?.output_tokens) outputTokens = usage.output_tokens;
    } else if (event.event === "message_stop") {
      break;
    }
  }
  yield { type: "done", inputTokens, outputTokens };
}

/* ============================================================================
 * OpenAI — /v1/chat/completions stream:true (works for gpt-5.x)
 * ============================================================================ */
async function* streamOpenAI(req: ChatRequest): AsyncGenerator<StreamEvent> {
  const messages: Array<{ role: ChatRole; content: string }> = [];
  if (req.system) messages.push({ role: "system", content: req.system });
  messages.push(...req.messages);

  const body = {
    model: req.model,
    messages,
    stream: true,
    stream_options: { include_usage: true },
    max_completion_tokens: req.maxTokens ?? 4096,
  };
  const res = await fetchWithRetry("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${req.apiKey}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    const detail = await safeText(res);
    yield {
      type: "error",
      message:
        res.status >= 500 || res.status === 429
          ? `provider_temporarily_unavailable:openai_${res.status}`
          : `openai_${res.status}:${detail}`,
    };
    return;
  }
  let inputTokens = 0;
  let outputTokens = 0;
  for await (const event of parseSSE(res.body)) {
    const data = event.data;
    if (!data || data === "[DONE]") continue;
    const choice = data.choices?.[0];
    const delta = choice?.delta?.content;
    if (typeof delta === "string" && delta.length) yield { type: "delta", text: delta };
    if (data.usage) {
      inputTokens = data.usage.prompt_tokens ?? inputTokens;
      outputTokens = data.usage.completion_tokens ?? outputTokens;
    }
  }
  yield { type: "done", inputTokens, outputTokens };
}

/* ============================================================================
 * Google Gemini — :streamGenerateContent SSE
 * ============================================================================ */
async function* streamGoogle(req: ChatRequest): AsyncGenerator<StreamEvent> {
  // Pass the API key in the `x-goog-api-key` header instead of the URL
  // query string. Google supports both, but URL params can leak via
  // server logs, error response bodies that echo the request URL, and
  // any error stack trace that quotes the URL. Header-based auth keeps
  // the credential out of those surfaces.
  const url =
    `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(
      req.model
    )}:streamGenerateContent?alt=sse`;

  const contents = req.messages.map((m) => ({
    role: m.role === "assistant" ? "model" : "user",
    parts: [{ text: m.content }],
  }));
  const body: Record<string, unknown> = {
    contents,
    generationConfig: { maxOutputTokens: req.maxTokens ?? 4096 },
  };
  if (req.system) {
    body.systemInstruction = { role: "user", parts: [{ text: req.system }] };
  }
  const res = await fetchWithRetry(url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-goog-api-key": req.apiKey,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    const detail = await safeText(res);
    yield {
      type: "error",
      message:
        res.status >= 500 || res.status === 429
          ? `provider_temporarily_unavailable:google_${res.status}`
          : `google_${res.status}:${detail}`,
    };
    return;
  }
  let inputTokens = 0;
  let outputTokens = 0;
  for await (const event of parseSSE(res.body)) {
    const data = event.data;
    if (!data) continue;
    const parts = data.candidates?.[0]?.content?.parts;
    if (Array.isArray(parts)) {
      for (const p of parts) {
        if (typeof p?.text === "string" && p.text.length) {
          yield { type: "delta", text: p.text };
        }
      }
    }
    if (data.usageMetadata) {
      inputTokens = data.usageMetadata.promptTokenCount ?? inputTokens;
      outputTokens = data.usageMetadata.candidatesTokenCount ?? outputTokens;
    }
  }
  yield { type: "done", inputTokens, outputTokens };
}

/* ============================================================================
 * SSE parser — yields { event, data } from a ReadableStream of bytes.
 * ============================================================================ */
type SSEFrame = { event: string; data: any };
async function* parseSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<SSEFrame> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      const dataLines: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) continue;
      const raw = dataLines.join("\n");
      if (raw === "[DONE]") {
        yield { event, data: "[DONE]" };
        continue;
      }
      try {
        yield { event, data: JSON.parse(raw) };
      } catch {
        yield { event, data: raw };
      }
    }
  }
}

async function safeText(r: Response): Promise<string> {
  try {
    const t = await r.text();
    return t.slice(0, 500);
  } catch {
    return "";
  }
}
