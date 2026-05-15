/**
 * ProviderAccountsCard — top-level "Connect your AI provider" surface.
 *
 * Lives at the top of /settings so the first thing the operator sees is
 * which provider accounts they've connected. Each provider that powers
 * dashboard chat shows:
 *   - Connection status (any agent has a key for this provider → Connected)
 *   - Tagline + which models it unlocks
 *   - "Get API key" deep-link to the provider's console (opens in a new tab)
 *   - "Manage keys" jump to the per-agent rows below
 *
 * Anthropic gets the "Powers tool_use loop" badge — pasting an Anthropic
 * key flips the cloud-mode chat to the native tool_use protocol (real
 * Claude-Code-class capability), not just the legacy text-marker pipe.
 *
 * Server component — pulls connection status from aiServicesWithKey().
 * The actual paste-key UX still lives in AgentConfigEditor (you paste a
 * key once per agent so different agents can use different providers).
 * This card is the discoverability layer that points operators at it.
 */

import Link from "next/link";
import { ExternalLink, Check, AlertCircle, KeyRound, Cpu, Cloud } from "lucide-react";
import { PROVIDER_REGISTRY, type Provider } from "@/lib/providers";

type Props = {
  /**
   * Set of services-with-key resolved server-side via aiServicesWithKey().
   * Keys: "anthropic", "openai_codex", "google_ai", "openrouter".
   */
  connectedServices: Set<string>;
  bridgeOnline: boolean;
};

// Map providers → aiServicesWithKey service names so we can light up the
// "Connected" pill correctly. Mirrors PROVIDER_TO_SERVICE in queries.ts.
const PROVIDER_TO_SERVICE: Record<Provider, string> = {
  anthropic: "anthropic",
  openai: "openai_codex",
  google: "google_ai",
  openrouter: "openrouter",
  ollama: "ollama", // never returned by aiServicesWithKey (local), shown for parity
};

// Providers that get a card on this surface. Ollama is intentionally hidden
// — it has no "account" to connect; the local-model path is wired through
// the bridge + AgentConfigEditor and shouldn't pretend it's an account.
const CARD_PROVIDERS: Provider[] = ["anthropic", "openrouter", "openai", "google"];

export function ProviderAccountsCard({ connectedServices, bridgeOnline }: Props) {
  const totalConnected = CARD_PROVIDERS.filter((p) =>
    connectedServices.has(PROVIDER_TO_SERVICE[p])
  ).length;
  const anyConnected = totalConnected > 0;

  return (
    <div className="space-y-4">
      {/* Header: what these are, why you'd connect them */}
      <div className="rounded-lg border border-bg-border bg-bg-deep/40 p-4 space-y-2">
        <div className="flex items-start gap-3">
          <KeyRound className="w-4 h-4 text-accent shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-fg">
              Connect an AI provider account
            </div>
            <p className="text-xs text-fg-muted mt-1 leading-relaxed">
              Your agents need a model provider to think. Connect one (or
              several — different agents can use different providers) and
              your dashboard chat works without needing a local Claude Code
              subscription.{" "}
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

      {/* Per-provider cards */}
      <div className="grid sm:grid-cols-2 gap-3">
        {CARD_PROVIDERS.map((p) => {
          const reg = PROVIDER_REGISTRY.find((r) => r.value === p);
          if (!reg) return null;
          const connected = connectedServices.has(PROVIDER_TO_SERVICE[p]);
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
                {connected ? (
                  <Link
                    href="#agents"
                    className="text-[11px] text-accent hover:text-accent-bright inline-flex items-center gap-1 font-bold"
                  >
                    Manage keys ↓
                  </Link>
                ) : (
                  <>
                    <a
                      href={reg.apiKey}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[11px] text-accent hover:text-accent-bright inline-flex items-center gap-1 font-bold"
                    >
                      Get API key <ExternalLink className="w-3 h-3" />
                    </a>
                    <span className="text-fg-dim text-[10px]">·</span>
                    <Link
                      href="#agents"
                      className="text-[11px] text-fg-muted hover:text-fg inline-flex items-center gap-1"
                    >
                      Paste it on an agent ↓
                    </Link>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Bridge install nudge — only if no cloud provider connected AND
          bridge isn't online either. Operator has neither path wired. */}
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
    </div>
  );
}
