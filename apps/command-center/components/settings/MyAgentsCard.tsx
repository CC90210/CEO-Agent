"use client";

/**
 * MyAgentsCard — operator's personal per-agent overrides.
 *
 * Phase B of the master multi-tenant infra plan (2026-05-17). Sits in
 * Settings alongside the tenant-level AgentConfigEditor. Lets each
 * employee paste their own API key + pick their own model per agent;
 * those settings only affect THEIR chat. Anyone else on the tenant
 * keeps using the tenant default.
 *
 * Backend contract:
 *   - GET  /api/agent-config?scope=user → list of personal overrides
 *   - POST /api/agent-config { scope: "user", agent_key, provider,
 *           model, api_key? } → upsert
 *   - The chat path (lib/chat-auth.ts) looks up (tenant, user, agent)
 *     first, falls back to tenant default. Migration 052 backs the
 *     uniqueness; migration 053's audit log records every save.
 *
 * UX:
 *   - One row per agent enabled on the tenant.
 *   - "Using tenant default" badge when no personal override exists.
 *   - "Override saved" badge when one does.
 *   - Each row is collapsible; click to edit provider/model/key inline.
 *   - "Clear my override" link removes the row → falls back to tenant.
 */

import { useEffect, useState } from "react";
import { Loader2, Sparkles, Check, AlertCircle, Eye, EyeOff, Trash2 } from "lucide-react";
import { PROVIDER_MODELS } from "@/lib/providers";

type Override = {
  agent_key: string;
  provider: string;
  model: string;
  enabled: boolean;
  has_key: boolean;
  last_used_at: string | null;
};

type Props = {
  enabledAgentKeys: string[];
  agentLabels: Record<string, string>;
};

const PROVIDERS = Object.keys(PROVIDER_MODELS) as Array<keyof typeof PROVIDER_MODELS>;

export function MyAgentsCard({ enabledAgentKeys, agentLabels }: Props) {
  const [overrides, setOverrides] = useState<Override[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      const r = await fetch("/api/agent-config?scope=user", { cache: "no-store" });
      const body = (await r.json()) as { ok: boolean; configs?: Override[]; error?: string };
      if (!body.ok) {
        setError(body.error || "Failed to load");
        setOverrides([]);
      } else {
        setOverrides(body.configs || []);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
      setOverrides([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const byKey: Record<string, Override | null> = {};
  for (const a of enabledAgentKeys) byKey[a] = null;
  for (const o of overrides || []) byKey[o.agent_key] = o;

  return (
    <div className="rounded-2xl border border-bg-border bg-bg-elev/40 p-5 space-y-4">
      <header>
        <h3 className="text-sm font-bold text-fg uppercase tracking-wider flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-accent" />
          My Agents — personal AI overrides
        </h3>
        <p className="text-[12px] text-fg-muted leading-relaxed mt-1">
          Connect your own AI account to override the workspace defaults. Only your chat is affected
          — your teammates keep using whatever the admin set. Leave a row alone to use the tenant
          default.
        </p>
      </header>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-fg-muted">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading overrides…
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 text-[12px] text-red-300 bg-red-500/10 border border-red-500/30 rounded-md p-2">
          <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      {!loading && (
        <ul className="space-y-2">
          {enabledAgentKeys.map((agentKey) => (
            <AgentRow
              key={agentKey}
              agentKey={agentKey}
              label={agentLabels[agentKey] || agentKey}
              override={byKey[agentKey]}
              onSaved={refresh}
            />
          ))}
          {enabledAgentKeys.length === 0 && (
            <li className="text-[12px] text-fg-dim italic py-2 text-center">
              No agents enabled on this workspace yet. Ask your admin to enable one in Settings → Agents.
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

function AgentRow({
  agentKey,
  label,
  override,
  onSaved,
}: {
  agentKey: string;
  label: string;
  override: Override | null;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState<string>(override?.provider || "openrouter");
  const [model, setModel] = useState<string>(override?.model || "");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);

  const providerModels = PROVIDER_MODELS[provider as keyof typeof PROVIDER_MODELS] || [];

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/agent-config", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          scope: "user",
          agent_key: agentKey,
          provider,
          model: model || providerModels[0],
          api_key: apiKey || undefined,
        }),
      });
      const body = (await r.json()) as { ok: boolean; error?: string };
      if (!r.ok || !body.ok) {
        setErr(body.error || `save_failed:${r.status}`);
        setBusy(false);
        return;
      }
      setApiKey("");
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 1500);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "save failed");
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    if (!confirm(`Remove your personal override for ${label}? You'll fall back to the workspace default on the next chat.`)) return;
    setBusy(true);
    try {
      const r = await fetch(`/api/agent-config?scope=user&agent_key=${encodeURIComponent(agentKey)}`, {
        method: "DELETE",
      });
      if (!r.ok) {
        const body = (await r.json().catch(() => ({}))) as { error?: string };
        setErr(body.error || `clear_failed:${r.status}`);
      } else {
        onSaved();
        setOpen(false);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rounded-lg border border-bg-border bg-bg-deep/40">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left hover:bg-bg-elev/40 transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-semibold text-sm text-fg">{label}</span>
          {override ? (
            <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
              <Check className="w-3 h-3" />
              Personal override
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium bg-bg-elev/60 text-fg-dim border border-bg-border">
              Tenant default
            </span>
          )}
          {override && (
            <span className="text-[11px] text-fg-dim font-mono truncate">
              {override.provider} · {override.model}
              {override.has_key ? " · key set" : ""}
            </span>
          )}
        </div>
        <span className="text-fg-dim text-xs shrink-0">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-bg-border px-3 py-3 space-y-3">
          <label className="block">
            <span className="text-[10.5px] uppercase tracking-wider font-bold text-fg-dim">
              Provider
            </span>
            <select
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value);
                const next = PROVIDER_MODELS[e.target.value as keyof typeof PROVIDER_MODELS] || [];
                if (next.length > 0) setModel(next[0]);
              }}
              className="mt-1 w-full bg-bg-deep border border-bg-border rounded-md px-2 py-1.5 text-sm text-fg focus:border-accent focus:outline-none"
            >
              {PROVIDERS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-[10.5px] uppercase tracking-wider font-bold text-fg-dim">Model</span>
            <select
              value={model || providerModels[0] || ""}
              onChange={(e) => setModel(e.target.value)}
              className="mt-1 w-full bg-bg-deep border border-bg-border rounded-md px-2 py-1.5 text-sm text-fg focus:border-accent focus:outline-none"
            >
              {providerModels.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-[10.5px] uppercase tracking-wider font-bold text-fg-dim">
              Your API key
              {override?.has_key && (
                <span className="ml-2 text-emerald-400 normal-case font-normal">
                  (key already saved — leave blank to keep)
                </span>
              )}
            </span>
            <div className="mt-1 relative">
              <input
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={override?.has_key ? "•••••••• (saved)" : "sk-…"}
                className="w-full bg-bg-deep border border-bg-border rounded-md px-2 py-1.5 pr-8 text-sm text-fg placeholder:text-fg-dim focus:border-accent focus:outline-none font-mono"
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShowKey((s) => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-fg-dim hover:text-fg"
                aria-label={showKey ? "Hide key" : "Show key"}
              >
                {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
              </button>
            </div>
            <span className="text-[11px] text-fg-dim mt-1 block leading-relaxed">
              Encrypted at rest with AES-256-GCM. Never returned by the API after save.
            </span>
          </label>

          {err && (
            <div className="flex items-start gap-2 text-[12px] text-red-300 bg-red-500/10 border border-red-500/30 rounded-md p-2">
              <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              {err}
            </div>
          )}

          <div className="flex items-center justify-between gap-2 pt-1">
            {override ? (
              <button
                type="button"
                onClick={clear}
                disabled={busy}
                className="text-[11.5px] text-fg-dim hover:text-red-300 inline-flex items-center gap-1 underline underline-offset-2 disabled:opacity-50"
              >
                <Trash2 className="w-3 h-3" />
                Clear my override
              </button>
            ) : (
              <span className="text-[11px] text-fg-dim">
                No personal override yet — using tenant default.
              </span>
            )}
            <button
              type="button"
              onClick={save}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-md bg-accent text-bg-deep px-3 py-1.5 text-[12.5px] font-bold hover:bg-accent/90 disabled:opacity-60 transition-colors"
            >
              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : savedFlash ? <Check className="w-3.5 h-3.5" /> : null}
              {savedFlash ? "Saved" : busy ? "Saving…" : "Save override"}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
