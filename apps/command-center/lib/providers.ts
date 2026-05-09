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

export type Provider = "openrouter" | "anthropic" | "openai" | "google" | "ollama";

export type ChatRequest = {
  provider: Provider;
  model: string;
  apiKey: string;
  system?: string;
  messages: ChatMessage[];
  maxTokens?: number;
  /** Override base URL — required for `ollama` (where the operator's local
   *  endpoint isn't on the public internet) and useful for self-hosted
   *  OpenAI-compatible endpoints (LM Studio, vLLM, llama.cpp server). */
  baseUrl?: string;
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
  // Local-first via Ollama or LM Studio — `model` is whatever the operator
  // pulled (`ollama pull llama3.3:70b` etc). The picker shows common names;
  // the per-agent config lets the operator type any tag they have locally.
  ollama: [
    "llama3.3:70b",
    "llama3.3",
    "qwen2.5:72b",
    "qwen2.5-coder:32b",
    "mistral",
    "deepseek-r1:70b",
  ],
};

export const PROVIDER_LABEL: Record<Provider, string> = {
  openrouter: "OpenRouter (recommended)",
  anthropic: "Anthropic (Claude)",
  openai: "OpenAI",
  google: "Google (Gemini)",
  ollama: "Local model (Ollama / LM Studio)",
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
  ollama: {
    // No "signup" — the operator runs Ollama on their own machine.
    // The signup link points to the install docs as a stand-in.
    signup: "https://ollama.com/download",
    apiKey: "https://ollama.com/library",
    docs: "https://github.com/ollama/ollama/blob/main/docs/api.md",
  },
};

/* ============================================================================
 * PROVIDER_REGISTRY — single source of truth for provider metadata.
 *
 * Replaces the duplicate PROVIDERS arrays that used to live independently in
 * components/landing/OnboardingFlow.tsx and components/settings/AgentConfigEditor.tsx.
 * Both surfaces now `import { PROVIDER_REGISTRY } from "@/lib/providers"` and
 * derive their pickers from this list. Add a provider once, both surfaces
 * pick it up.
 *
 * Per-surface presentation (pretty model labels, taglines, badges) lives
 * here too — separate fields for each surface so the registry stays the
 * canonical source even when the wording differs slightly.
 * ============================================================================ */
export type ProviderRegistryEntry = {
  value: Provider;
  /** Short label used in pickers (Onboarding's tile, AgentConfigEditor's <select>). */
  label: string;
  /** One-line summary for Onboarding (under the tile). */
  tagline: string;
  /** Longer prose for AgentConfigEditor (under the dropdown). */
  hint: string;
  /** Sign-up + API key URLs (sourced from PROVIDER_LINKS). */
  signup: string;
  apiKey: string;
  /** Optional doc URL — surfaced in the AgentConfigEditor "Get API key" button. */
  docs?: string;
  /** Picker models, with optional pretty labels for OnboardingFlow. */
  models: Array<{ id: string; label: string }>;
  /** Onboarding placeholder for the API-key input. */
  placeholder: string;
  /** Star tile in Onboarding ("★ recommended"). */
  badge?: string;
  /** True for OpenRouter — surfaces the "recommended" flag in AgentConfigEditor. */
  recommended?: boolean;
};

export const PROVIDER_REGISTRY: ProviderRegistryEntry[] = [
  {
    value: "openrouter",
    label: "OpenRouter",
    tagline: "One key, every model — recommended",
    hint: "One key, every model. Easiest path — pay-as-you-go, no per-provider setup.",
    signup: PROVIDER_LINKS.openrouter.signup,
    apiKey: PROVIDER_LINKS.openrouter.apiKey,
    docs: PROVIDER_LINKS.openrouter.docs,
    models: [
      { id: "anthropic/claude-sonnet-4", label: "Claude Sonnet 4 (balanced)" },
      { id: "anthropic/claude-opus-4", label: "Claude Opus 4 (heavy reasoning)" },
      { id: "openai/gpt-5.4", label: "GPT-5.4" },
      { id: "openai/gpt-5.4-mini", label: "GPT-5.4 mini (cheap)" },
      { id: "google/gemini-2.5-pro", label: "Gemini 2.5 Pro" },
      { id: "google/gemini-2.5-flash", label: "Gemini 2.5 Flash (fast)" },
      { id: "meta-llama/llama-3.3-70b-instruct", label: "Llama 3.3 70B" },
    ],
    placeholder: "sk-or-v1-...",
    badge: "★ recommended",
    recommended: true,
  },
  {
    value: "anthropic",
    label: "Anthropic Direct",
    tagline: "Claude only — best if you already have an Anthropic account",
    hint: "Direct to Claude. Best for Anthropic-only deployments.",
    signup: PROVIDER_LINKS.anthropic.signup,
    apiKey: PROVIDER_LINKS.anthropic.apiKey,
    docs: PROVIDER_LINKS.anthropic.docs,
    models: [
      { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6 (balanced)" },
      { id: "claude-opus-4-7", label: "Claude Opus 4.7 (heavy reasoning)" },
      { id: "claude-haiku-4-5", label: "Claude Haiku 4.5 (fast)" },
    ],
    placeholder: "sk-ant-...",
  },
  {
    value: "openai",
    label: "OpenAI Direct",
    tagline: "GPT-5.x + Codex — pay-as-you-go via OpenAI",
    hint: "Direct to OpenAI. Use for GPT-5 + Codex.",
    signup: PROVIDER_LINKS.openai.signup,
    apiKey: PROVIDER_LINKS.openai.apiKey,
    docs: PROVIDER_LINKS.openai.docs,
    models: [
      { id: "gpt-5.4", label: "GPT-5.4" },
      { id: "gpt-5.4-mini", label: "GPT-5.4 mini (cheap)" },
      { id: "gpt-5.2", label: "GPT-5.2" },
      { id: "gpt-5.3-codex", label: "GPT-5.3 Codex" },
    ],
    placeholder: "sk-proj-...",
  },
  {
    value: "google",
    label: "Google Gemini",
    tagline: "Free tier available via AI Studio",
    hint: "Direct to Gemini via AI Studio. Free tier available.",
    signup: PROVIDER_LINKS.google.signup,
    apiKey: PROVIDER_LINKS.google.apiKey,
    docs: PROVIDER_LINKS.google.docs,
    models: [
      { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
      { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash (fast)" },
    ],
    placeholder: "AIza...",
  },
  {
    value: "ollama",
    label: "Local model (Ollama / LM Studio)",
    tagline:
      "Zero per-call cost · full data residency · pair with the local bridge for best results",
    hint:
      "Runs on your machine. Paste your local endpoint URL in the key field (http://localhost:11434/v1 for Ollama, :1234/v1 for LM Studio). Pair with the local bridge for best results.",
    signup: PROVIDER_LINKS.ollama.signup,
    apiKey: PROVIDER_LINKS.ollama.apiKey,
    docs: PROVIDER_LINKS.ollama.docs,
    models: [
      { id: "llama3.3:70b", label: "Llama 3.3 70B (best — needs 48GB+ GPU)" },
      { id: "llama3.3", label: "Llama 3.3 (default tag)" },
      { id: "qwen2.5:72b", label: "Qwen 2.5 72B (strong reasoning)" },
      { id: "qwen2.5-coder:32b", label: "Qwen 2.5 Coder 32B (code-focused)" },
      { id: "mistral", label: "Mistral 7B (light, fast)" },
      { id: "deepseek-r1:70b", label: "DeepSeek R1 70B (reasoning model)" },
    ],
    placeholder: "http://localhost:11434/v1  (or LM Studio: http://localhost:1234/v1)",
  },
];

/* ============================================================================
 * Public entry point — async generator that yields StreamEvents.
 * ============================================================================ */
export async function* streamChat(req: ChatRequest): AsyncGenerator<StreamEvent> {
  // Ollama / LM Studio run locally without auth — empty key is fine.
  // Every other provider needs a key.
  if (!req.apiKey && req.provider !== "ollama") {
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
    case "ollama":
      yield* streamOllama(req);
      return;
    default:
      yield { type: "error", message: `unknown_provider:${req.provider}` };
  }
}

/* ============================================================================
 * Ollama / LM Studio / any OpenAI-compatible local endpoint.
 *
 * baseUrl points at the operator's local model server. Defaults to the
 * standard Ollama address (http://localhost:11434/v1). LM Studio's default
 * (http://localhost:1234/v1) and any other OpenAI-compatible local server
 * works by passing `baseUrl` in the agent_model_config row.
 *
 * This path runs in the dashboard server. For client-installed local
 * models, the dashboard cannot reach the operator's machine directly —
 * the bridge proxies the call (or, for cloud-only clients, this provider
 * isn't usable). Documented in the playbook + onboarding.
 *
 * Wire format is OpenAI-compatible (Ollama and LM Studio both expose
 * /v1/chat/completions). Same code path as streamOpenAI minus the bearer
 * auth (Ollama doesn't require one for local installs).
 * ============================================================================ */
async function* streamOllama(req: ChatRequest): AsyncGenerator<StreamEvent> {
  const base = (req.baseUrl || "http://localhost:11434/v1").replace(/\/+$/, "");
  const messages: Array<{ role: ChatRole; content: string }> = [];
  if (req.system) messages.push({ role: "system", content: req.system });
  messages.push(...req.messages);

  const body = {
    model: req.model,
    messages,
    stream: true,
    stream_options: { include_usage: true },
    max_tokens: req.maxTokens ?? 4096,
  };
  const headers: Record<string, string> = { "content-type": "application/json" };
  // LM Studio honors a Bearer key when configured; Ollama ignores it.
  // Pass through whatever the operator stored (often "ollama" or
  // a user-set token) for compatibility.
  if (req.apiKey && req.apiKey !== "ollama") {
    headers.authorization = `Bearer ${req.apiKey}`;
  }

  const res = await fetchWithRetry(`${base}/chat/completions`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    const detail = await safeText(res);
    yield {
      type: "error",
      message:
        res.status >= 500 || res.status === 429
          ? `local_model_temporarily_unavailable:${res.status}`
          : `ollama_${res.status}:${detail}`,
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
