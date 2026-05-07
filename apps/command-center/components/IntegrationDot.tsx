"use client";

import { useState } from "react";
import { timeAgo } from "@/lib/fmt";
import type { IntegrationHealth } from "@/lib/supabase";
import { categorize, CONNECTION_KIND_LABEL, type ConnectionKind } from "@/lib/integrations-registry";
import { ExternalLink, KeyRound, Sparkles, Download, Plug, Package, UserCircle, Check } from "lucide-react";
import { KeyPasteModal } from "@/components/integrations/KeyPasteModal";

const COMPLEXITY_LABEL: Record<string, { label: string; tone: string }> = {
  trivial: { label: "easy setup", tone: "text-status-engaged" },
  simple: { label: "minutes", tone: "text-accent" },
  moderate: { label: "moderate", tone: "text-status-warm" },
  advanced: { label: "advanced", tone: "text-status-hot" },
};

const KIND_ICON: Record<ConnectionKind, React.ReactNode> = {
  api_key: <KeyRound className="w-3 h-3" />,
  oauth: <Plug className="w-3 h-3" />,
  local_install: <Download className="w-3 h-3" />,
  built_in: <Package className="w-3 h-3" />,
  account_only: <UserCircle className="w-3 h-3" />,
};

/**
 * Optional connection signal supplied by the page rendering this card.
 * `hasCredentials` means: for api_key / oauth, a key/token is on file;
 * for local_install / built_in / account_only, the side-channel says it's
 * present (FFmpeg installed, repo cloned with bundled skill, account linked).
 */
export type IntegrationConnection = {
  hasCredentials?: boolean;
};

export function IntegrationDot({
  health,
  connection,
  bridgeToken,
}: {
  health: IntegrationHealth;
  connection?: IntegrationConnection;
  bridgeToken?: string | null;
}) {
  const [modalOpen, setModalOpen] = useState(false);
  const def = categorize(health);
  const label = def?.label || health.service;
  const description = def?.description;
  const signupUrl = def?.signup_url;
  const apiKeyUrl = def?.api_key_url;
  const docUrl = def?.setup_doc_url;
  const complexity = def?.setup_complexity;
  const isRecommended = def?.service === "openrouter";
  const kind: ConnectionKind = def?.connection_kind || "api_key";
  const usedBy = def?.used_by || [];

  // Compute display state — what should the badge actually say?
  // Built-in and bundled skills are always "ready" (they ship with the repo).
  // Everything else looks at: is there a recent ping AND/OR credentials on file?
  const recentPing =
    health.last_ping_at &&
    Date.now() - new Date(health.last_ping_at).getTime() < 24 * 60 * 60 * 1000;
  const hasCreds = !!connection?.hasCredentials;

  let stateLabel: string;
  let stateTone: string;
  let stateIcon: React.ReactNode = null;
  let dotColor: string;
  if (kind === "built_in") {
    stateLabel = "Built-in · ready";
    stateTone = "text-status-engaged";
    dotColor = "bg-status-engaged shadow-[0_0_10px_rgba(16,185,129,0.6)]";
    stateIcon = <Check className="w-3 h-3" />;
  } else if (health.status === "healthy" || (recentPing && hasCreds)) {
    stateLabel = "Connected";
    stateTone = "text-status-engaged";
    dotColor = "bg-status-engaged shadow-[0_0_10px_rgba(16,185,129,0.65)]";
    stateIcon = <Check className="w-3 h-3" />;
  } else if (health.status === "degraded") {
    stateLabel = "Degraded";
    stateTone = "text-status-warm";
    dotColor = "bg-status-warm shadow-[0_0_10px_rgba(245,158,11,0.5)]";
  } else if (health.status === "down") {
    stateLabel = "Down";
    stateTone = "text-status-hot";
    dotColor = "bg-status-hot shadow-[0_0_10px_rgba(239,68,68,0.5)]";
  } else if (hasCreds) {
    stateLabel = "Configured · awaiting first ping";
    stateTone = "text-accent";
    dotColor = "bg-accent shadow-[0_0_10px_rgba(0,212,255,0.5)]";
  } else {
    stateLabel = "Not connected";
    stateTone = "text-fg-dim";
    dotColor = "bg-fg-faint";
  }

  // Per-kind primary CTA
  const primaryCta = (() => {
    if (kind === "built_in") return null;
    if (kind === "local_install") {
      return signupUrl ? (
        <a
          href={signupUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-accent hover:text-accent-bright inline-flex items-center gap-1 transition-colors"
        >
          <Download className="w-3 h-3" /> Install
        </a>
      ) : null;
    }
    if (kind === "oauth") {
      return signupUrl ? (
        <a
          href={signupUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-accent hover:text-accent-bright inline-flex items-center gap-1 transition-colors"
        >
          <Plug className="w-3 h-3" /> Connect
        </a>
      ) : null;
    }
    if (kind === "account_only") {
      return signupUrl ? (
        <a
          href={signupUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-accent hover:text-accent-bright inline-flex items-center gap-1 transition-colors"
        >
          <UserCircle className="w-3 h-3" /> Open account
        </a>
      ) : null;
    }
    // api_key — show in-place modal connect when env_key is mapped
    return (
      <>
        {def?.env_key && (
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="text-xs text-accent hover:text-accent-bright inline-flex items-center gap-1 transition-colors font-bold"
          >
            <KeyRound className="w-3 h-3" /> {hasCreds ? "Update key" : "Connect"}
          </button>
        )}
        {signupUrl && (
          <a
            href={signupUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-fg-muted hover:text-accent inline-flex items-center gap-1 transition-colors"
          >
            <ExternalLink className="w-3 h-3" /> Sign up
          </a>
        )}
        {!def?.env_key && apiKeyUrl && apiKeyUrl !== signupUrl && (
          <a
            href={apiKeyUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-accent hover:text-accent-bright inline-flex items-center gap-1 transition-colors"
          >
            <KeyRound className="w-3 h-3" /> Get API key
          </a>
        )}
      </>
    );
  })();

  return (
    <div
      className={`group rounded-xl border bg-bg-elev px-4 py-3.5 transition-all ${
        isRecommended
          ? "border-accent/40 hover:border-accent/70 hover:shadow-[0_0_24px_-8px_rgba(0,212,255,0.4)]"
          : "border-bg-border hover:border-accent/40"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <div className={`w-2.5 h-2.5 rounded-full shrink-0 mt-1.5 ${dotColor} ${health.status === "healthy" || stateLabel === "Built-in · ready" ? "animate-pulse-slow" : ""}`} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <div className="text-sm font-semibold text-fg truncate">{label}</div>
              {isRecommended && (
                <span className="provider-chip recommended !py-0.5 !px-1.5 !text-[10px]">
                  <Sparkles className="w-2.5 h-2.5" /> recommended
                </span>
              )}
              <span className="text-[10px] uppercase tracking-wider font-bold text-fg-muted inline-flex items-center gap-1">
                {KIND_ICON[kind]} {CONNECTION_KIND_LABEL[kind]}
              </span>
              {complexity && COMPLEXITY_LABEL[complexity] && (
                <span className={`text-[10px] uppercase tracking-wider font-bold ${COMPLEXITY_LABEL[complexity].tone}`}>
                  {COMPLEXITY_LABEL[complexity].label}
                </span>
              )}
            </div>
            <div className="text-xs text-fg-dim mt-1 truncate">{description || "—"}</div>
            <div className={`text-[10px] mt-1.5 font-mono inline-flex items-center gap-1 ${stateTone}`}>
              {stateIcon}
              {stateLabel}
              {health.last_ping_at && health.status !== "unconfigured" && kind !== "built_in" && (
                <span className="text-fg-muted"> · last ping {timeAgo(health.last_ping_at)}</span>
              )}
            </div>
            {usedBy.length > 0 && (
              <div className="text-[10px] text-fg-faint mt-1 uppercase tracking-wider">
                used by {usedBy.join(" · ")}
              </div>
            )}
          </div>
        </div>
      </div>

      {primaryCta && (
        <div className="flex items-center gap-3 mt-3 pt-3 border-t border-bg-border opacity-80 group-hover:opacity-100 transition-opacity">
          {primaryCta}
          {docUrl && (
            <a
              href={docUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-fg-muted hover:text-accent inline-flex items-center gap-1 ml-auto transition-colors"
            >
              docs <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
      )}
      {def?.env_key && (
        <KeyPasteModal
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          service={health.service}
          serviceLabel={label}
          envKey={def.env_key}
          apiKeyUrl={apiKeyUrl}
          bridgeToken={bridgeToken}
        />
      )}
    </div>
  );
}
