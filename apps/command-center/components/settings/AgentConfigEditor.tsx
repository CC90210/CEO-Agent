"use client";

/**
 * AgentConfigEditor — per-tenant per-agent provider/model/API-key configurator.
 *
 * One row per agent (Bravo/Maven/Atlas/Aura/Hermes). Each row lets the user
 * pick a provider, pick a model from that provider's list, paste an API key,
 * and toggle enabled. Key is sent to /api/agent-config which encrypts it at
 * rest via pgcrypto + the tenant-side passphrase env. Existing keys are
 * never returned to the browser; the row just shows whether one is on file.
 */

import { useEffect, useState } from "react";
import { Save, Eye, EyeOff, Check, AlertCircle } from "lucide-react";

const PROVIDER_OPTIONS: Array<{ value: string; label: string; models: string[] }> = [
  {
    value: "anthropic",
    label: "Anthropic (Claude)",
    models: ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"],
  },
  {
    value: "openai",
    label: "OpenAI",
    models: ["gpt-5.4", "gpt-5.4-mini", "gpt-5.2", "gpt-5.3-codex"],
  },
  {
    value: "google",
    label: "Google (Gemini)",
    models: ["gemini-2.5-pro", "gemini-2.5-flash"],
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
          provider: "anthropic",
          model: "claude-sonnet-4-6",
          apiKey: "",
          enabled: true,
          override: "",
          showKey: false,
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
        const provOpt = PROVIDER_OPTIONS.find((p) => p.value === row.provider);
        return (
          <div
            key={key}
            className="rounded-lg border border-bg-border bg-bg-elev p-4 space-y-3"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-accent font-bold uppercase tracking-[0.14em] text-sm">
                  {key}
                </span>
                {cfg?.has_key ? (
                  <span className="text-xs text-status-engaged font-mono">key on file</span>
                ) : (
                  <span className="text-xs text-fg-dim font-mono">no key</span>
                )}
              </div>
              <label className="flex items-center gap-2 text-xs text-fg-muted cursor-pointer">
                <input
                  type="checkbox"
                  checked={row.enabled}
                  onChange={(e) => patchRow(key, { enabled: e.target.checked })}
                />
                enabled
              </label>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <label className="text-xs text-fg-muted space-y-1">
                <span>Provider</span>
                <select
                  value={row.provider}
                  onChange={(e) => {
                    const next = PROVIDER_OPTIONS.find((p) => p.value === e.target.value);
                    patchRow(key, {
                      provider: e.target.value,
                      model: next?.models[0] || row.model,
                    });
                  }}
                  className="w-full bg-bg-panel border border-bg-border rounded-md px-2 py-1.5 text-sm text-fg focus:outline-none focus:border-accent"
                >
                  {PROVIDER_OPTIONS.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs text-fg-muted space-y-1">
                <span>Model</span>
                <select
                  value={row.model}
                  onChange={(e) => patchRow(key, { model: e.target.value })}
                  className="w-full bg-bg-panel border border-bg-border rounded-md px-2 py-1.5 text-sm text-fg focus:outline-none focus:border-accent"
                >
                  {(provOpt?.models || []).map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="text-xs text-fg-muted space-y-1 block">
              <span>
                API key{" "}
                <span className="text-fg-dim">
                  {cfg?.has_key ? "(leave blank to keep existing)" : "(required)"}
                </span>
              </span>
              <div className="flex gap-2">
                <input
                  type={row.showKey ? "text" : "password"}
                  value={row.apiKey}
                  onChange={(e) => patchRow(key, { apiKey: e.target.value })}
                  placeholder={cfg?.has_key ? "•••••••••••••••" : "sk-… / AIza… / your key"}
                  className="flex-1 bg-bg-panel border border-bg-border rounded-md px-2 py-1.5 text-sm text-fg font-mono focus:outline-none focus:border-accent"
                />
                <button
                  type="button"
                  onClick={() => patchRow(key, { showKey: !row.showKey })}
                  className="text-fg-dim hover:text-fg p-1.5"
                  title={row.showKey ? "Hide" : "Show"}
                >
                  {row.showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </label>

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
                className="bg-accent text-bg-deep rounded-md px-3 py-1.5 text-sm font-bold disabled:opacity-50 hover:bg-accent-bright transition-colors flex items-center gap-1.5"
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
