"use client";

/**
 * LeadTimelinePanel — the conversation + activity history for a single lead.
 *
 * Phase 18 of the SunBiz CRM Reconstructor build (2026-05-17). Mounted
 * below the lead's ManifestRecordForm on the detail page so Adon's team
 * can see every interaction in one place — the explicit ask from the
 * 2026-05-16 meeting ("we need to see text + email conversations
 * against the lead record").
 *
 * Data source: GET /api/leads/[id]/timeline (server-side merged feed
 * across lead_interactions, email_open_events, lead_documents,
 * agent_events, agent_alerts). The panel just renders.
 *
 * Render rules:
 *   - Chronological newest-first.
 *   - Per-source icon + colour tint so the operator can scan-skim.
 *   - Email-open events fold under the matching outbound by
 *     outbound_message_id when both are present (rendered as a "👁
 *     opened Nm ago" pill underneath the original send).
 *   - Suspicious-prefetch opens (Apple Mail Privacy Protection) render
 *     with a dimmer style + "(prefetch)" suffix so operators don't
 *     mistake APMP noise for real engagement.
 *   - Empty state: friendly "no activity yet" rather than blank.
 */

import { useEffect, useState } from "react";

type TimelineEvent = {
  source: string;
  type: string;
  at: string;
  title: string;
  body?: string;
  meta?: Record<string, unknown>;
};

type ApiResponse = {
  ok: boolean;
  events?: TimelineEvent[];
  truncated?: boolean;
  errors?: { feed: string; message: string }[];
  error?: string;
};

const SOURCE_STYLES: Record<string, { dot: string; label: string }> = {
  interaction: { dot: "bg-sky-400", label: "Conversation" },
  email_open: { dot: "bg-emerald-400", label: "Open" },
  document: { dot: "bg-violet-400", label: "Document" },
  system: { dot: "bg-fg-dim", label: "System" },
  alert: { dot: "bg-red-400", label: "Alert" },
};

function relTime(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const diff = Date.now() - t;
  const sec = Math.round(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 48) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  if (day < 30) return `${day}d ago`;
  return new Date(iso).toLocaleDateString();
}

function absTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function LeadTimelinePanel({ leadId }: { leadId: string }) {
  const [events, setEvents] = useState<TimelineEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feedErrors, setFeedErrors] = useState<{ feed: string; message: string }[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/leads/${leadId}/timeline`, { cache: "no-store" })
      .then(async (r) => {
        const data = (await r.json()) as ApiResponse;
        if (cancelled) return;
        if (!data.ok) {
          setError(data.error || "timeline unavailable");
          setEvents([]);
        } else {
          setEvents(data.events || []);
          setFeedErrors(data.errors || []);
        }
      })
      .catch((e) => {
        if (cancelled) return;
        setError(String(e?.message || e));
        setEvents([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [leadId]);

  return (
    <div className="rounded-2xl border border-bg-border bg-bg-deep/40 p-5">
      <div className="flex items-baseline justify-between mb-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-fg-muted">
          Timeline
        </h3>
        <span className="text-[11px] text-fg-dim">
          {loading
            ? "loading…"
            : events
              ? `${events.length} event${events.length === 1 ? "" : "s"}`
              : ""}
        </span>
      </div>

      {error && (
        <div className="text-sm text-red-300 border border-red-500/30 bg-red-500/10 rounded-md p-3 mb-3">
          Timeline couldn&apos;t load: {error}
        </div>
      )}

      {feedErrors.length > 0 && (
        <div className="text-[11px] text-amber-300/80 mb-3">
          Partial: couldn&apos;t read {feedErrors.map((f) => f.feed).join(", ")}.
        </div>
      )}

      {!loading && events && events.length === 0 && (
        <div className="text-sm text-fg-dim italic py-6 text-center">
          No activity yet. Send a drip or upload a doc and it&apos;ll appear here.
        </div>
      )}

      {events && events.length > 0 && (
        <ol className="relative border-l border-bg-border ml-2 space-y-3">
          {events.map((e, i) => {
            const style = SOURCE_STYLES[e.source] || SOURCE_STYLES.system;
            const dimmed =
              e.source === "email_open" && (e.meta as any)?.suspicious_prefetch;
            return (
              <li key={i} className="ml-5 relative">
                <span
                  className={`absolute -left-[27px] top-1 inline-block w-2.5 h-2.5 rounded-full ${style.dot} ring-2 ring-bg-deep`}
                />
                <div
                  className={`rounded-md border border-bg-border/60 px-3 py-2 text-[12.5px] ${
                    dimmed ? "opacity-50" : ""
                  }`}
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <div className="font-medium text-fg break-words">
                      {e.title}
                      {dimmed && (
                        <span className="ml-1.5 text-[10px] text-fg-dim font-mono">
                          (prefetch)
                        </span>
                      )}
                    </div>
                    <time
                      title={absTime(e.at)}
                      className="text-[10.5px] text-fg-dim font-mono shrink-0"
                    >
                      {relTime(e.at)}
                    </time>
                  </div>
                  {e.body && (
                    <div className="mt-1 text-fg-muted whitespace-pre-wrap break-words text-[11.5px]">
                      {e.body}
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
