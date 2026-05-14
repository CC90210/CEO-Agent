"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  PauseCircle,
  PlayCircle,
  Save,
} from "lucide-react";
import type { MutationArgs } from "@/lib/manifest/mutators";

type Binding = {
  display_name: string;
  enabled: boolean;
  primary: boolean;
  prompt_overlay?: string;
};

type Props = {
  tenantSlug: string;
  agentSlug: string;
  defaultDisplayName: string;
  binding: Binding | null;
  manifestVersion: number;
  canEdit: boolean;
  canBuildCustom: boolean;
};

export function AgentSubscriptionPanel({
  tenantSlug,
  agentSlug,
  defaultDisplayName,
  binding,
  manifestVersion,
  canEdit,
  canBuildCustom,
}: Props) {
  const router = useRouter();
  const [displayName, setDisplayName] = useState(binding?.display_name || defaultDisplayName);
  const [promptOverlay, setPromptOverlay] = useState(binding?.prompt_overlay || "");
  const [primary, setPrimary] = useState(!!binding?.primary);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [version, setVersion] = useState(manifestVersion);

  const enabled = !!binding?.enabled;

  async function postMutations(mutations: MutationArgs[], message: string) {
    setBusy(true);
    setError(null);
    setFlash(null);
    try {
      const res = await fetch(`/api/manifest/${tenantSlug}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          mutations,
          actor: "user",
          message,
          if_version: version,
        }),
      });
      const data = (await res.json()) as
        | { ok: true; version: number; diff: { summary: string }[] }
        | { ok: false; error: string; message?: string; field?: string; reason?: string };
      if (!data.ok) {
        const detail =
          data.error === "mutation_rejected"
            ? `${data.field}: ${data.reason}`
            : data.message || data.error;
        setError(detail);
        return false;
      }
      setVersion(data.version);
      setFlash(`Saved (v${data.version}). ${data.diff.length} change${data.diff.length === 1 ? "" : "s"}.`);
      router.refresh();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "network_error");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function enable() {
    await postMutations(
      [{ name: "enable_agent", args: { slug: agentSlug, display_name: displayName, primary } }],
      `Enable ${agentSlug}${primary ? " (primary)" : ""}`
    );
  }

  async function disable() {
    await postMutations(
      [{ name: "disable_agent", args: { slug: agentSlug } }],
      `Disable ${agentSlug}`
    );
  }

  async function savePersonalization() {
    const muts: MutationArgs[] = [];
    if (displayName !== binding?.display_name || promptOverlay !== (binding?.prompt_overlay || "")) {
      muts.push({
        name: "update_agent",
        args: {
          slug: agentSlug,
          changes: {
            display_name: displayName,
            prompt_overlay: promptOverlay || undefined,
          },
        },
      });
    }
    if (primary !== !!binding?.primary) {
      muts.push({
        name: "update_agent",
        args: { slug: agentSlug, changes: { primary } },
      });
    }
    if (muts.length === 0) {
      setFlash("Nothing to save.");
      return;
    }
    await postMutations(muts, `Personalize ${agentSlug}`);
  }

  return (
    <aside className="rounded-2xl border border-bg-border bg-bg-elev/45 p-5 space-y-4">
      <div>
        <div className="text-[10px] uppercase tracking-[0.16em] text-fg-dim font-bold">
          For this tenant
        </div>
        <h3 className="mt-1 text-lg font-bold text-fg">Subscription</h3>
        <p className="text-xs text-fg-muted mt-1 leading-relaxed">
          Enable, rename, and layer your own prompt context onto the base agent.
          Changes are persisted to your manifest with full audit history.
        </p>
      </div>

      {!canEdit && (
        <div className="rounded-xl border border-amber-300/30 bg-amber-300/10 px-3 py-2 text-xs text-amber-100 leading-relaxed">
          You&apos;re viewing read-only. Editing requires an admin or owner role.
        </div>
      )}

      <Field label="Display name" hint="Shown in the sidebar and on chat headers.">
        <input
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          disabled={!canEdit || busy}
          className="w-full rounded-xl border border-bg-border bg-bg-deep/80 px-3 py-2 text-sm text-fg focus:border-accent/50 focus:outline-none disabled:opacity-50"
        />
      </Field>

      <Field
        label="Prompt overlay"
        hint="Optional. Appended to the agent's base prompt for this tenant only."
      >
        <textarea
          value={promptOverlay}
          onChange={(e) => setPromptOverlay(e.target.value)}
          rows={4}
          disabled={!canEdit || busy}
          placeholder="e.g. We're a Toronto-based brokerage. Default to CAD. Be concise — our team reads on mobile."
          className="w-full resize-y rounded-xl border border-bg-border bg-bg-deep/80 px-3 py-2 text-sm text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none disabled:opacity-50"
        />
      </Field>

      <label className="flex items-center gap-2 text-sm text-fg">
        <input
          type="checkbox"
          checked={primary}
          onChange={(e) => setPrimary(e.target.checked)}
          disabled={!canEdit || busy}
          className="rounded"
        />
        Set as primary agent
      </label>

      {flash && (
        <div className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-100 inline-flex items-start gap-2">
          <CheckCircle2 className="h-3.5 w-3.5 mt-0.5" />
          <span>{flash}</span>
        </div>
      )}
      {error && (
        <div className="rounded-xl border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-200 inline-flex items-start gap-2">
          <AlertCircle className="h-3.5 w-3.5 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <div className="space-y-2 pt-2 border-t border-bg-border">
        {enabled ? (
          <>
            <button
              type="button"
              onClick={savePersonalization}
              disabled={!canEdit || busy}
              className="btn-send inline-flex w-full items-center justify-center gap-1.5 !py-2 text-sm"
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              Save personalization
            </button>
            <button
              type="button"
              onClick={disable}
              disabled={!canEdit || busy}
              className="btn-secondary inline-flex w-full items-center justify-center gap-1.5 !py-2 text-sm"
            >
              <PauseCircle className="h-3.5 w-3.5" />
              Disable for this tenant
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={enable}
            disabled={!canEdit || busy}
            className="btn-send inline-flex w-full items-center justify-center gap-1.5 !py-2 text-sm"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlayCircle className="h-3.5 w-3.5" />}
            Enable for this tenant
          </button>
        )}
        {canBuildCustom && (
          <a
            href={`/t/${tenantSlug}/marketplace/new?edit=${agentSlug}`}
            className="block text-center text-xs text-fg-dim hover:text-fg pt-1"
          >
            Edit the underlying agent definition →
          </a>
        )}
      </div>
    </aside>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-semibold text-fg">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-fg-dim">{hint}</span>}
    </label>
  );
}
