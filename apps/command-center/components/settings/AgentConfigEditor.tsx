"use client";

/**
 * AgentConfigEditor — per-tenant per-agent provider/model/API-key configurator.
 *
 * Recommended path: OpenRouter (one key gets all models). Direct providers
 * (Anthropic / OpenAI / Google) supported for clients with existing keys.
 *
 * One row per agent (Bravo/Maven/Atlas/Aura/Hermes). Each row lets the user
 * pick a provider, pick a model, paste an API key, and toggle enabled.
 * Key is sent to /api/agent-config which encrypts it at rest via AES-256-GCM
 * + the BRAVO_FIELD_ENCRYPTION_KEY env passphrase. Existing keys are never
 * returned to the browser; the row just shows whether one is on file.
 */

import { useEffect, useState } from "react";
import { Save, Eye, EyeOff, Check, AlertCircle, ExternalLink, Sparkles, ChevronDown, ChevronUp } from "lucide-react";
import { getAgentInfo } from "@/lib/agents";

type ProviderOption = {
  value: string;
  label: string;
  models: string[];
  signup: string;
  apiKey: string;
  recommended?: boolean;
  hint: string;
};

const PROVIDER_OPTIONS: ProviderOption[] = [
  {
    value: "openrouter",
    label: "OpenRouter",
    models: [
      "anthropic/claude-opus-4",
      "anthropic/claude-sonnet-4",
      "openai/gpt-5.4",
      "openai/gpt-5.4-mini",
      "google/gemini-2.5-pro",
      "google/gemini-2.5-flash",
      "meta-llama/llama-3.3-70b-instruct",
    ],
    signup: "https://openrouter.ai/sign-up",
    apiKey: "https://openrouter.ai/keys",
    recommended: true,
    hint: "One key, every model. Easiest path — pay-as-you-go, no per-provider setup.",
  },
  {
    value: "anthropic",
    label: "Anthropic (Claude)",
    models: ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"],
    signup: "https://console.anthropic.com/signup",
    apiKey: "https://console.anthropic.com/settings/keys",
    hint: "Direct to Claude. Best for Anthropic-only deployments.",
  },
  {
    value: "openai",
    label: "OpenAI",
    models: ["gpt-5.4", "gpt-5.4-mini", "gpt-5.2", "gpt-5.3-codex"],
    signup: "https://platform.openai.com/signup",
    apiKey: "https://platform.openai.com/api-keys",
    hint: "Direct to OpenAI. Use for GPT-5 + Codex.",
  },
  {
    value: "google",
    label: "Google (Gemini)",
    models: ["gemini-2.5-pro", "gemini-2.5-flash"],
    signup: "https://aistudio.google.com/",
    apiKey: "https://aistudio.google.com/apikey",
    hint: "Direct to Gemini via AI Studio. Free tier available.",
  },
];

type AgentConfig = {
  agent_key: string;
  provider: string;
  model: string;
  enabled: boolean;
  has_key: boolean;
  has_override: boolean;
  last_used_at: string | null;
};

type RowState = {
  provider: string;
  model: string;
  apiKey: string;
  enabled: boolean;
  override: string;
  showKey: boolean;
  showOverride: boolean;
  saving: boolean;
  saved: boolean;
  error: string | null;
};

type Props = {
  agentKeys: string[];
};

export function AgentConfigEditor({ agentKeys }: Props) {
  const [configs, setConfigs] = useState<Record<string, AgentConfig>>({});
  const [rows, setRows] = useState<Record<string, RowState>>(() =>
    Object.fromEntries(
      agentKeys.map((k) => [
        k,
        {
          provider: "openrouter",
          model: "anthropic/claude-sonnet-4",
          apiKey: "",
          enabled: true,
          override: "",
          showKey: false,
          showOverride: false,
          saving: false,
          saved: false,
          error: null,
        },
      ])
    )
  );

  useEffect(() => {
    fetch("/api/agent-config")
      .then((r) => r.json())
      .then((j) => {
        if (!j.ok) return;
        const map: Record<string, AgentConfig> = {};
        for (const c of j.configs as AgentConfig[]) map[c.agent_key] = c;
        setConfigs(map);
        setRows((prev) => {
          const next = { ...prev };
          for (const key of agentKeys) {
            const c = map[key];
            if (c) {
              next[key] = {
                ...next[key],
                provider: c.provider,
                model: c.model,
                enabled: c.enabled,
              };
            }
          }
          return next;
        });
      })
      .catch(() => null);
  }, [agentKeys]);

  function patchRow(key: string, patch: Partial<RowState>) {
    setRows((r) => ({ ...r, [key]: { ...r[key], ...patch } }));
  }

  async function save(agentKey: string) {
    const row = rows[agentKey];
    patchRow(agentKey, { saving: true, error: null, saved: false });
    const body: Record<string, unknown> = {
      agent_key: agentKey,
      provider: row.provider,
      model: row.model,
      enabled: row.enabled,
    };
    if (row.apiKey.trim().length) body.api_key = row.apiKey.trim();
    if (row.override.trim().length) body.system_prompt_override = row.override;
    try {
      const res = await fetch("/api/agent-config", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await res.json();
      if (!j.ok) {
        patchRow(agentKey, { saving: false, error: j.error || `http_${res.status}` });
        return;
      }
      patchRow(agentKey, {
        saving: false,
        saved: true,
        apiKey: "",
        showKey: false,
      });
      setConfigs((c) => ({
        ...c,
        [agentKey]: {
          agent_key: agentKey,
          provider: row.provider,
          model: row.model,
          enabled: row.enabled,
          has_key: row.apiKey.trim().length > 0 || c[agentKey]?.has_key || false,
          has_override:
            row.override.trim().length > 0 || c[agentKey]?.has_override || false,
          last_used_at: c[agentKey]?.last_used_at || null,
        },
      }));
      setTimeout(() => patchRow(agentKey, { saved: false }), 2500);
    } catch (e) {
      patchRow(agentKey, {
        saving: false,
        error: e instanceof Error ? e.message : "save_failed",
      });
    }
  }

  return (
    <div id="agents" className="space-y-4">
      {agentKeys.map((key) => {
        const row = rows[key];
        const cfg = configs[key];
        const provOpt = PROVIDER_OPTIONS.find((p) => p.value === row.provider) || PROVIDER_OPTIONS[0];
        const isOpenRouter = row.provider === "openrouter";
        return (
          <div
            key={key}
            className="rounded-xl border border-bg-border bg-bg-elev p-5 space-y-4 hover:border-accent-muted/40 transition-colors"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className={`agent-pill`}>
                  <span className="agent-pill-dot" />
                  {key}
                </div>
                <div className="text-xs text-fg-muted">
                  {getAgentInfo(key).role}
                </div>
              </div>
              <div className="flex items-center gap-3">
                {cfg?.has_key ? (
                  <span className="text-xs text-status-engaged font-mono flex items-center gap-1">
                    <Check className="w-3 h-3" /> key on file
                  </span>
                ) : (
                  <span className="text-xs text-fg-dim font-mono">no key</span>
                )}
                <label className="flex items-center gap-2 text-xs text-fg-muted cursor-pointer">
                  <input
                    type="checkbox"
                    checked={row.enabled}
                    onChange={(e) => patchRow(key, { enabled: e.target.checked })}
                    className="accent-accent"
                  />
                  enabled
                </label>
              </div>
            </div>

            {/* Provider picker as chips */}
            <div className="flex flex-wrap gap-2">
              {PROVIDER_OPTIONS.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => patchRow(key, { provider: p.value, model: p.models[0] })}
                  className={`provider-chip ${
                    row.provider === p.value
                      ? p.recommended
                        ? "recommended"
                        : "!bg-accent/15 !border-accent/50 !text-fg"
                      : ""
                  } cursor-pointer hover:border-accent/40`}
                >
                  {p.recommended && <Sparkles className="w-3 h-3" />}
                  {p.label}
                </button>
              ))}
            </div>

            {/* Hint + signup links */}
            <div className="text-xs text-fg-muted flex flex-wrap items-center gap-3">
              <span>{provOpt.hint}</span>
              <a
                href={provOpt.signup}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:text-accent-bright inline-flex items-center gap-1 underline-offset-2 hover:underline"
              >
                Sign up <ExternalLink className="w-3 h-3" />
              </a>
              <a
                href={provOpt.apiKey}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:text-accent-bright inline-flex items-center gap-1 underline-offset-2 hover:underline"
              >
                Get API key <ExternalLink className="w-3 h-3" />
              </a>
            </div>

            {/* Model + API key */}
            <div className="grid grid-cols-1 sm:grid-cols-[1fr_2fr] gap-3">
              <label className="text-xs text-fg-muted space-y-1">
                <span className="label">Model</span>
                <select
                  value={row.model}
                  onChange={(e) => patchRow(key, { model: e.target.value })}
                  className="select"
                >
                  {provOpt.models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs text-fg-muted space-y-1">
                <span className="label">
                  API key{" "}
                  <span className="text-fg-dim normal-case tracking-normal font-normal">
                    {cfg?.has_key ? "(leave blank to keep existing)" : "(required)"}
                  </span>
                </span>
                <div className="flex gap-2">
                  <input
                    type={row.showKey ? "text" : "password"}
                    value={row.apiKey}
                    onChange={(e) => patchRow(key, { apiKey: e.target.value })}
                    placeholder={
                      cfg?.has_key
                        ? "•••••••••••••••"
                        : isOpenRouter
                          ? "sk-or-v1-..."
                          : "your provider key"
                    }
                    className="input font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => patchRow(key, { showKey: !row.showKey })}
                    className="btn-secondary !p-2"
                    title={row.showKey ? "Hide" : "Show"}
                  >
                    {row.showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </label>
            </div>

            {/* System prompt override (collapsed by default) */}
            <div>
              <button
                type="button"
                onClick={() => patchRow(key, { showOverride: !row.showOverride })}
                className="text-xs text-fg-muted hover:text-fg inline-flex items-center gap-1"
              >
                {row.showOverride ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                System prompt override {cfg?.has_override && <span className="text-status-engaged">(active)</span>}
              </button>
              {row.showOverride && (
                <textarea
                  value={row.override}
                  onChange={(e) => patchRow(key, { override: e.target.value })}
                  placeholder="Optional — overrides the default agent persona for this tenant. Leave blank to use the OASIS default."
                  className="textarea mt-2"
                  rows={4}
                />
              )}
            </div>

            <div className="flex items-center justify-between pt-1">
              <div className="text-xs">
                {row.error && (
                  <span className="text-status-warm font-mono flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" /> {row.error}
                  </span>
                )}
                {row.saved && (
                  <span className="text-status-engaged font-mono flex items-center gap-1">
                    <Check className="w-3 h-3" /> saved
                  </span>
                )}
              </div>
              <button
                onClick={() => save(key)}
                disabled={row.saving}
                className="btn-primary inline-flex items-center gap-1.5"
              >
                <Save className="w-3.5 h-3.5" /> {row.saving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
