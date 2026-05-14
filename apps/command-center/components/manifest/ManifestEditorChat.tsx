"use client";

import { useCallback, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  RotateCcw,
  Send,
  Sparkles,
} from "lucide-react";
import type { DiffEntry } from "@/lib/manifest/diff";
import type { MutationArgs } from "@/lib/manifest/mutators";
import type { TenantManifest } from "@/lib/manifest/schema";

type ChatTurn =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string };

type Proposal = {
  explanation: string;
  mutations: MutationArgs[];
  diff: DiffEntry[];
  preview_manifest: TenantManifest;
};

type Props = {
  slug: string;
  initialManifest: TenantManifest;
  initialVersion: number;
};

export function ManifestEditorChat({ slug, initialManifest, initialVersion }: Props) {
  const [manifest, setManifest] = useState<TenantManifest>(initialManifest);
  const [version, setVersion] = useState<number>(initialVersion);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<Proposal | null>(null);
  const [thinking, setThinking] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || thinking || applying) return;
      setError(null);
      setFlash(null);
      setTurns((prev) => [...prev, { role: "user", content: trimmed }]);
      setInput("");
      setThinking(true);
      try {
        const res = await fetch("/api/manifest/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            slug,
            message: trimmed,
            history: turns.map((t) => ({ role: t.role, content: t.content })),
          }),
        });
        const data = (await res.json()) as
          | {
              ok: true;
              explanation: string;
              mutations: MutationArgs[];
              diff: DiffEntry[];
              preview_manifest: TenantManifest;
              ai_message: string;
            }
          | {
              ok: false;
              error: string;
              message?: string;
              field?: string;
              reason?: string;
              explanation?: string;
              ai_message?: string;
            };
        if (!data.ok) {
          const detail =
            data.error === "mutation_rejected"
              ? `${data.field}: ${data.reason}`
              : data.message || data.error;
          setTurns((prev) => [
            ...prev,
            {
              role: "assistant",
              content:
                (data.explanation ? `${data.explanation}\n\n` : "") +
                `[error: ${detail}]`,
            },
          ]);
          setError(detail || data.error);
          return;
        }
        setTurns((prev) => [
          ...prev,
          { role: "assistant", content: data.explanation },
        ]);
        if (data.mutations.length > 0) {
          setPending({
            explanation: data.explanation,
            mutations: data.mutations,
            diff: data.diff,
            preview_manifest: data.preview_manifest,
          });
        } else {
          setPending(null);
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "network_error";
        setError(msg);
      } finally {
        setThinking(false);
        inputRef.current?.focus();
      }
    },
    [slug, thinking, applying, turns]
  );

  const apply = useCallback(async () => {
    if (!pending || applying) return;
    setApplying(true);
    setError(null);
    try {
      const res = await fetch(`/api/manifest/${slug}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          mutations: pending.mutations,
          actor: "ai",
          message: pending.explanation,
          if_version: version,
        }),
      });
      const data = (await res.json()) as
        | {
            ok: true;
            manifest: TenantManifest;
            diff: DiffEntry[];
            version: number;
            audit_id: string;
          }
        | { ok: false; error: string; message?: string; field?: string; reason?: string };
      if (!data.ok) {
        const detail =
          data.error === "mutation_rejected"
            ? `${data.field}: ${data.reason}`
            : data.message || data.error;
        setError(detail);
        return;
      }
      setManifest(data.manifest);
      setVersion(data.version);
      setPending(null);
      setFlash(`Applied — ${data.diff.length} change${data.diff.length === 1 ? "" : "s"} saved (v${data.version})`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "network_error");
    } finally {
      setApplying(false);
    }
  }, [pending, applying, slug, version]);

  const discard = useCallback(() => {
    setPending(null);
    setError(null);
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void send(input);
  };
  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void send(input);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1.05fr_0.95fr] gap-6">
      {/* Chat pane */}
      <div className="flex flex-col rounded-2xl border border-bg-border bg-bg-elev/40 backdrop-blur-sm min-h-[600px]">
        <div className="border-b border-bg-border px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-fg">
            <Sparkles className="h-4 w-4 text-accent" />
            <span className="font-bold text-sm">Editor — {manifest.brand.name}</span>
          </div>
          <span className="text-[10px] uppercase tracking-[0.16em] text-fg-dim font-mono">
            v{version}
          </span>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {turns.length === 0 && (
            <div className="text-sm text-fg-muted leading-relaxed">
              Tell the editor what to change. Try:
              <ul className="mt-2 ml-4 list-disc space-y-1 text-fg-dim">
                <li>&ldquo;Add a referral_source field to the lead entity.&rdquo;</li>
                <li>&ldquo;Rename the Bravo agent to &lsquo;Ops Lead&rsquo;.&rdquo;</li>
                <li>&ldquo;Add a Pipeline section to the sidebar with a Deals link.&rdquo;</li>
                <li>&ldquo;Change the brand color to navy.&rdquo;</li>
              </ul>
            </div>
          )}
          {turns.map((t, i) => (
            <div
              key={i}
              className={`text-sm leading-relaxed ${
                t.role === "user"
                  ? "ml-8 rounded-xl bg-accent-soft border border-accent-muted/30 px-4 py-2.5 text-fg"
                  : "mr-8 rounded-xl bg-bg-elev/70 border border-bg-border px-4 py-2.5 text-fg-muted"
              }`}
            >
              {t.content}
            </div>
          ))}
          {thinking && (
            <div className="mr-8 rounded-xl bg-bg-elev/70 border border-bg-border px-4 py-2.5 text-fg-muted text-sm inline-flex items-center gap-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />
              Thinking...
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="border-t border-bg-border p-3 space-y-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Describe a change. Ctrl/Cmd+Enter to send."
            disabled={thinking || applying}
            className="w-full resize-none rounded-xl border border-bg-border bg-bg-deep/80 px-4 py-2.5 text-sm text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none disabled:opacity-50"
            rows={2}
          />
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-fg-faint uppercase tracking-wider">
              Cmd/Ctrl+Enter to send
            </span>
            <button
              type="submit"
              disabled={!input.trim() || thinking || applying}
              className="btn-send inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
            >
              <Send className="h-3 w-3" />
              Send
            </button>
          </div>
        </form>
      </div>

      {/* Preview pane */}
      <div className="flex flex-col rounded-2xl border border-bg-border bg-bg-elev/40 backdrop-blur-sm min-h-[600px]">
        <div className="border-b border-bg-border px-5 py-3 flex items-center justify-between">
          <span className="font-bold text-sm text-fg">Preview</span>
          {pending && (
            <span className="text-[10px] uppercase tracking-[0.16em] text-amber-200 font-mono">
              {pending.diff.length} pending
            </span>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {flash && (
            <div className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-4 py-2.5 text-sm text-emerald-100 inline-flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              {flash}
            </div>
          )}
          {error && (
            <div className="rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-2.5 text-sm text-red-200 inline-flex items-start gap-2">
              <AlertCircle className="h-4 w-4 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {pending ? (
            <>
              <div className="rounded-xl border border-amber-300/25 bg-amber-300/5 px-4 py-3 text-sm text-fg-muted leading-relaxed">
                {pending.explanation}
              </div>
              <div className="space-y-1.5">
                <div className="text-[10px] uppercase tracking-[0.16em] text-fg-dim font-bold">
                  Changes
                </div>
                <ul className="space-y-1.5">
                  {pending.diff.map((d, i) => (
                    <li
                      key={i}
                      className="rounded-lg border border-bg-border bg-bg-elev/60 px-3 py-2 text-xs font-mono text-fg-muted flex items-start gap-2"
                    >
                      <span
                        className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-[10px] font-bold ${
                          d.op === "add"
                            ? "bg-emerald-400/15 text-emerald-200"
                            : d.op === "remove"
                              ? "bg-red-400/15 text-red-200"
                              : "bg-accent-soft text-accent"
                        }`}
                      >
                        {d.op === "add" ? "+" : d.op === "remove" ? "−" : "~"}
                      </span>
                      <span className="leading-snug">{d.summary}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="flex items-center gap-2 pt-2">
                <button
                  type="button"
                  onClick={apply}
                  disabled={applying}
                  className="btn-send inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
                >
                  {applying ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <CheckCircle2 className="h-3 w-3" />
                  )}
                  {applying ? "Applying..." : "Apply changes"}
                </button>
                <button
                  type="button"
                  onClick={discard}
                  disabled={applying}
                  className="btn-secondary inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
                >
                  <RotateCcw className="h-3 w-3" />
                  Discard
                </button>
              </div>
            </>
          ) : (
            <div className="space-y-3 text-sm text-fg-muted">
              <div className="text-[10px] uppercase tracking-[0.16em] text-fg-dim font-bold">
                Manifest snapshot
              </div>
              <div className="grid gap-2">
                <SnapshotRow label="Brand" value={manifest.brand.name} />
                <SnapshotRow label="Subtitle" value={manifest.brand.subtitle} />
                <SnapshotRow
                  label="Agents"
                  value={manifest.agents
                    .filter((a) => a.enabled)
                    .map((a) => `${a.display_name}${a.primary ? " (primary)" : ""}`)
                    .join(", ") || "none"}
                />
                <SnapshotRow
                  label="Nav"
                  value={`${manifest.nav.length} items across ${
                    new Set(manifest.nav.map((n) => n.group)).size
                  } groups`}
                />
                <SnapshotRow
                  label="Data model"
                  value={`${manifest.data_model?.length || 0} entities`}
                />
                <SnapshotRow
                  label="Pages"
                  value={`${manifest.pages?.length || 0} defined`}
                />
                <SnapshotRow
                  label="Industry"
                  value={manifest.onboarding_industry || "custom"}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SnapshotRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-xs">
      <span className="text-fg-dim uppercase tracking-wider font-semibold">{label}</span>
      <span className="text-fg-muted text-right truncate">{value}</span>
    </div>
  );
}
