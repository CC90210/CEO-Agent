"use client";

/**
 * ProviderAccountsCard — top-level "Connect your AI provider" surface.
 *
 * Lives at the top of /settings so the first thing the operator sees is
 * which provider accounts they've connected. Each provider that powers
 * dashboard chat shows:
 *   - Connection status (any agent has a key for this provider → Connected)
 *   - Tagline + which models it unlocks
 *   - "Connect" button → inline dialog with single API-key paste
 *   - "Get API key ↗" deep-link to the provider's console (new tab)
 *
 * Single-click connect: paste the key once, the route POSTs to
 * /api/agent-config/bulk-provider which stamps (provider, model, key)
 * across every enabled chat agent in the tenant. No per-agent paste
 * dance, no navigating to /settings#agents to do it five times.
 *
 * Anthropic gets the "Powers tool_use loop" badge — pasting an Anthropic
 * key flips the cloud-mode chat to the native tool_use protocol (real
 * Claude-Code-class capability), not just the legacy text-marker pipe.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ExternalLink,
  Check,
  AlertCircle,
  KeyRound,
  Cpu,
  Cloud,
  Loader2,
  X,
  Eye,
  EyeOff,
} from "lucide-react";
import { PROVIDER_REGISTRY, PROVIDER_TO_SERVICE, type Provider } from "@/lib/providers";

type Props = {
  /** Set of services-with-key resolved server-side via aiServicesWithKey(). */
  connectedServices: Set<string>;
  bridgeOnline: boolean;
};

// Providers that get a card on this surface. Ollama is intentionally hidden
// — it has no "account" to connect; the local-model path is wired through
// the bridge + AgentConfigEditor and shouldn't pretend it's an account.
const CARD_PROVIDERS: Provider[] = ["anthropic", "openrouter", "openai", "google"];

export function ProviderAccountsCard({ connectedServices: initialServices, bridgeOnline }: Props) {
  const router = useRouter();
  // Server-rendered set, but track in state so connecting flips the UI
  // immediately without waiting for the router refresh round-trip.
  const [services, setServices] = useState<Set<string>>(initialServices);
  const [activeProvider, setActiveProvider] = useState<Provider | null>(null);

  function markConnected(p: Provider) {
    const svc = PROVIDER_TO_SERVICE[p];
    if (!svc) return;
    setServices((prev) => {
      if (prev.has(svc)) return prev;
      const next = new Set(prev);
      next.add(svc);
      return next;
    });
    // Cross-component refresh: AgentConfigEditor on this same page caches
    // its config list in client state from a fetch() on mount. Without a
    // poke, the per-agent rows below would still show "no key on file"
    // after a bulk-connect until the user manually reloaded. The custom
    // event lets the editor re-fetch on receipt; router.refresh() re-runs
    // server components so the page's own connectedServices prop is
    // up-to-date next render. Belt + suspenders intentional.
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("oasis:agent-configs-changed"));
    }
    router.refresh();
  }

  const totalConnected = CARD_PROVIDERS.filter((p) =>
    services.has(PROVIDER_TO_SERVICE[p])
  ).length;
  const anyConnected = totalConnected > 0;

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-bg-border bg-bg-deep/40 p-4 space-y-2">
        <div className="flex items-start gap-3">
          <KeyRound className="w-4 h-4 text-accent shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-fg">
              Connect an AI provider account
            </div>
            <p className="text-xs text-fg-muted mt-1 leading-relaxed">
              Paste a key once — it applies to every enabled agent in one
              click. Different agents can use different providers (override
              per-agent under Agents below).{" "}
              <span className="text-accent">
                Connecting Anthropic unlocks the native tool_use loop
              </span>
              {" "}— record reads/writes, http_get/post, integration lookups
              — full Claude-Code-class capability from the cloud.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-[11px] pt-1">
          <span
            className={`inline-flex items-center gap-1 ${
              anyConnected ? "text-status-engaged" : "text-fg-dim"
            }`}
          >
            <Cloud className="w-3 h-3" />
            Cloud:{" "}
            {anyConnected
              ? `${totalConnected} provider${totalConnected === 1 ? "" : "s"} connected`
              : "no provider connected"}
          </span>
          <span className="text-fg-dim">·</span>
          <span
            className={`inline-flex items-center gap-1 ${
              bridgeOnline ? "text-accent" : "text-fg-dim"
            }`}
          >
            <Cpu className="w-3 h-3" />
            Local bridge: {bridgeOnline ? "online" : "offline"}
          </span>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        {CARD_PROVIDERS.map((p) => {
          const reg = PROVIDER_REGISTRY.find((r) => r.value === p);
          if (!reg) return null;
          const connected = services.has(PROVIDER_TO_SERVICE[p]);
          const isAnthropic = p === "anthropic";
          return (
            <div
              key={p}
              className={`rounded-lg border p-4 ${
                connected
                  ? "border-status-engaged/30 bg-status-engaged/5"
                  : "border-bg-border bg-bg-elev/30"
              }`}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="min-w-0">
                  <div className="text-sm font-bold text-fg flex items-center gap-2">
                    {reg.label}
                    {isAnthropic && (
                      <span className="text-[9px] uppercase tracking-wider text-accent border border-accent/40 rounded-full px-1.5 py-0.5">
                        tool_use
                      </span>
                    )}
                    {reg.recommended && (
                      <span className="text-[9px] uppercase tracking-wider text-status-engaged border border-status-engaged/40 rounded-full px-1.5 py-0.5">
                        recommended
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-fg-muted mt-0.5">
                    {reg.tagline}
                  </div>
                </div>
                {connected ? (
                  <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider font-bold text-status-engaged shrink-0">
                    <Check className="w-3 h-3" /> Connected
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider font-bold text-fg-dim shrink-0">
                    <AlertCircle className="w-3 h-3" /> Not connected
                  </span>
                )}
              </div>
              <div className="text-[11px] text-fg-dim leading-relaxed mb-3 line-clamp-3">
                {reg.hint}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => setActiveProvider(p)}
                  className={`text-[11px] font-bold inline-flex items-center gap-1 ${
                    connected
                      ? "text-fg-muted hover:text-fg"
                      : "text-accent hover:text-accent-bright"
                  }`}
                >
                  {connected ? "Replace key" : "Connect"} →
                </button>
                <span className="text-fg-dim text-[10px]">·</span>
                <a
                  href={reg.apiKey}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] text-fg-muted hover:text-fg inline-flex items-center gap-1"
                >
                  Get a key <ExternalLink className="w-3 h-3" />
                </a>
                {connected && (
                  <>
                    <span className="text-fg-dim text-[10px]">·</span>
                    <Link
                      href="#agents"
                      className="text-[11px] text-fg-muted hover:text-fg inline-flex items-center gap-1"
                    >
                      Per-agent ↓
                    </Link>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {!anyConnected && !bridgeOnline && (
        <div className="rounded-lg border border-status-warm/30 bg-status-warm/5 p-3 text-xs text-fg flex items-start gap-2">
          <AlertCircle className="w-4 h-4 text-status-warm shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-bold">No provider wired yet.</span> Your
            agents can't think until you connect at least one — connect a
            cloud provider above (recommended for client tenants) OR{" "}
            <Link
              href="/settings/devices/install"
              className="text-accent hover:text-accent-bright underline"
            >
              install the local bridge
            </Link>{" "}
            to use your own Claude Code subscription.
          </div>
        </div>
      )}

      {activeProvider && (
        <ConnectProviderDialog
          provider={activeProvider}
          onClose={() => setActiveProvider(null)}
          onConnected={(p) => {
            markConnected(p);
            setActiveProvider(null);
          }}
        />
      )}
    </div>
  );
}

// ============================================================================
// Inline connect dialog — single API key input + Save
// ============================================================================

function ConnectProviderDialog({
  provider,
  onClose,
  onConnected,
}: {
  provider: Provider;
  onClose: () => void;
  onConnected: (p: Provider) => void;
}) {
  const reg = PROVIDER_REGISTRY.find((r) => r.value === provider);
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [model, setModel] = useState(reg?.models[0]?.id || "");

  if (!reg) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!apiKey.trim() || saving) return;
    setSaving(true);
    setError(null);
    try {
      const r = await fetch("/api/agent-config/bulk-provider", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ provider, api_key: apiKey, model }),
      });
      const j = await r.json();
      if (!j.ok) {
        setError(j.error || `http_${r.status}`);
        setSaving(false);
        return;
      }
      // Partial-failure case: route returned ok=true (at least one agent
      // saved) but some failed. Surface a non-blocking warning so the
      // operator knows which agents need manual attention, then still
      // flip the card to "connected" since the provider IS connected for
      // the agents that succeeded.
      const failed = Array.isArray(j.failed) ? (j.failed as Array<{ agent_key: string; error: string }>) : [];
      if (failed.length > 0) {
        const list = failed.map((f) => `${f.agent_key} (${f.error})`).join(", ");
        // Use console.warn for the detail; the user sees a summary below.
        console.warn("[bulk-provider] partial failure", failed);
        setError(`Saved on ${j.count} agent${j.count === 1 ? "" : "s"}. Failed: ${list}`);
        setSaving(false);
        // Still call onConnected so the card flips — they ARE connected
        // for the agents that saved. They can retry from #agents.
        onConnected(provider);
        return;
      }
      onConnected(provider);
    } catch (err) {
      setError(err instanceof Error ? err.message : "save_failed");
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-bg-deep/80 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-xl border border-bg-border bg-bg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-5 border-b border-bg-border">
          <div>
            <h2 className="text-base font-bold text-fg">Connect {reg.label}</h2>
            <p className="text-xs text-fg-muted mt-0.5">
              This key will apply to every enabled chat agent in one shot.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-fg-dim hover:text-fg-muted p-1"
            title="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-fg-muted block mb-1.5">
              API key
            </label>
            <div className="relative">
              <input
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={reg.placeholder}
                autoFocus
                className="input w-full font-mono text-sm pr-10"
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShowKey((s) => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-fg-dim hover:text-fg-muted p-1"
                title={showKey ? "Hide" : "Show"}
              >
                {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <a
              href={reg.apiKey}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] text-accent hover:text-accent-bright inline-flex items-center gap-1 mt-2"
            >
              Get an API key at {new URL(reg.apiKey).host}{" "}
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-fg-muted block mb-1.5">
              Default model
            </label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="input w-full text-sm"
            >
              {reg.models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
            <div className="text-[11px] text-fg-dim mt-1.5">
              Applied to every agent. Override per-agent under{" "}
              <span className="font-mono">/settings#agents</span> if a specific
              agent should use a different model on the same provider.
            </div>
          </div>

          {error && (
            <div className="rounded-md border border-status-warm/40 bg-status-warm/10 p-3 text-xs text-status-warm flex items-start gap-2">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>
                {error === "invalid_key_length"
                  ? "That doesn't look like a valid API key. Double-check what you pasted — most keys are 40–80 characters."
                  : error}
              </span>
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary"
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-primary inline-flex items-center gap-2"
              disabled={!apiKey.trim() || saving}
            >
              {saving ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Saving…
                </>
              ) : (
                <>
                  <Check className="w-4 h-4" />
                  Connect {reg.label}
                </>
              )}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
