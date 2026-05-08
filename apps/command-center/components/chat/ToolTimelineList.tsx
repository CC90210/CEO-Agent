"use client";

/**
 * Claude-Code-style tool-call timeline. Each tool call is a row with
 * status icon, kind glyph, label, full args, and (when complete)
 * duration + output preview. Rendered above the in-progress assistant
 * bubble so CC sees the agent's work as it happens.
 *
 * Three states per row:
 *   - running (Loader2 spin, accent tone)
 *   - done    (green check, muted tone)
 *   - error   (X icon, warm tone) — auto-demoted to "retried" if a
 *               same-key success arrives later in time.
 *
 * Synthetic entries (predicted activity during pure model thinking)
 * dim further with an italic detail and a "predicted" tag so users
 * never mistake them for real file reads.
 *
 * Extracted from ChatWidget.tsx 2026-05-08 to keep that file under
 * 1500 lines.
 */

import { useState } from "react";
import {
  Loader2,
  Check,
  ChevronRight,
  X as XIcon,
  RefreshCw,
  FileText,
  Pencil,
  Terminal,
  Search,
  Globe,
  Brain,
  Database,
  Cpu,
} from "lucide-react";

export type TimelineEntry = {
  id: string;
  kind: string;
  label: string;
  detail?: string;
  output?: string;
  error?: boolean;
  createdAt: number;
  completedAt?: number;
  /** True for predicted/fake activity rendered while the agent is in
   *  pure model-thinking time. Renders dimmer with a clarifying tooltip
   *  so users don't mistake it for a real file read. */
  synthetic?: boolean;
};

function _toolIcon(kind: string): React.ReactNode {
  const sz = "w-3.5 h-3.5";
  switch (kind) {
    case "read_file":
    case "Read":
      return <FileText className={sz} />;
    case "edit_file":
    case "write_file":
    case "Edit":
    case "Write":
    case "MultiEdit":
      return <Pencil className={sz} />;
    case "run_script":
    case "Bash":
      return <Terminal className={sz} />;
    case "glob":
    case "Glob":
    case "grep":
    case "Grep":
      return <Search className={sz} />;
    case "web_fetch":
    case "WebFetch":
    case "WebSearch":
      return <Globe className={sz} />;
    case "mcp_call":
      return <Database className={sz} />;
    default:
      if (kind.startsWith("mcp__")) {
        if (kind.includes("sequential-thinking") || kind.includes("memory")) return <Brain className={sz} />;
        return <Database className={sz} />;
      }
      return <Cpu className={sz} />;
  }
}

function _formatDuration(createdAt: number, completedAt?: number): string {
  if (!completedAt) return "";
  const ms = completedAt - createdAt;
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}m${s % 60}s`;
}

export function ToolTimelineList({ entries }: { entries: TimelineEntry[] }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  // Detect supersedes — when Claude retries the SAME kind+detail and the
  // retry succeeds AFTER the failure, the earlier failed entry is recovery
  // noise, not a real failure. Require the success to come strictly later
  // in time so a successful read followed by a real failed read is NOT
  // mis-flagged as recovered.
  const successesByKey = new Map<string, number[]>();
  for (const e of entries) {
    if (!e.error && e.completedAt) {
      const key = `${e.kind}::${e.detail || ""}`;
      const list = successesByKey.get(key) ?? [];
      list.push(e.createdAt);
      successesByKey.set(key, list);
    }
  }
  return (
    <div className="ml-9 space-y-1 border-l border-bg-border pl-3 mt-1">
      {entries.map((e) => {
        const isOpen = expanded.has(e.id);
        const isRunning = !e.completedAt && !e.error;
        const canExpand = !!e.output || !!e.detail;
        const successTimes = successesByKey.get(`${e.kind}::${e.detail || ""}`) ?? [];
        const wasRetried = !!e.error && successTimes.some((t) => t > e.createdAt);
        const status = e.error
          ? wasRetried
            ? "retried"
            : "error"
          : e.completedAt
            ? "done"
            : "running";
        const statusIcon =
          status === "running" ? (
            <Loader2 className="w-3 h-3 animate-spin text-accent" />
          ) : status === "error" ? (
            <XIcon className="w-3 h-3 text-status-warm" />
          ) : status === "retried" ? (
            <RefreshCw className="w-3 h-3 text-fg-dim" />
          ) : (
            <Check className="w-3 h-3 text-status-engaged" />
          );
        const tone =
          status === "error"
            ? "text-status-warm"
            : status === "running"
              ? "text-accent"
              : status === "retried"
                ? "text-fg-dim opacity-60"
                : "text-fg-muted";
        const dur = _formatDuration(e.createdAt, e.completedAt);
        const synthClass = e.synthetic ? "opacity-50 italic" : "";
        const titleText = e.synthetic
          ? `Predicted activity (the agent is thinking — this is what it would typically look at). ${e.detail || e.label}`
          : e.detail || e.label;
        return (
          <div key={e.id} className={`text-[11px] ${synthClass}`}>
            <button
              type="button"
              disabled={!canExpand}
              onClick={() => canExpand && toggle(e.id)}
              className={`w-full flex items-start gap-2 px-1.5 py-1 rounded ${
                canExpand ? "hover:bg-bg-elev/40 cursor-pointer" : "cursor-default"
              } ${tone}`}
              title={titleText}
            >
              <span className="flex items-center gap-1.5 mt-0.5 flex-shrink-0">
                {statusIcon}
                <span className="text-fg-dim">{_toolIcon(e.kind)}</span>
              </span>
              <span className="flex-1 min-w-0 flex items-baseline gap-1.5 text-left">
                <span className="font-mono font-bold uppercase tracking-wider text-[10px]">
                  {e.label}
                </span>
                {e.detail && (
                  <span className="text-fg-dim font-mono truncate">{e.detail}</span>
                )}
                {e.synthetic && (
                  <span className="text-[9px] uppercase tracking-wider text-fg-dim/60 flex-shrink-0">
                    · predicted
                  </span>
                )}
              </span>
              {dur && (
                <span className="text-fg-dim font-mono text-[10px] flex-shrink-0 ml-1">
                  {dur}
                </span>
              )}
              {canExpand && (
                <ChevronRight
                  className={`w-3 h-3 transition-transform mt-0.5 flex-shrink-0 ${
                    isOpen ? "rotate-90" : ""
                  } text-fg-dim`}
                />
              )}
              {isRunning && !canExpand && (
                <span className="text-fg-dim font-mono text-[10px] flex-shrink-0 ml-1">
                  …
                </span>
              )}
            </button>
            {isOpen && (
              <div className="ml-7 mt-1 mb-1 space-y-1.5">
                {e.detail && (
                  <div className="text-[10px] font-mono text-fg-muted break-all px-2 py-1 rounded border border-bg-border bg-bg-deep/40">
                    {e.detail}
                  </div>
                )}
                {e.output && (
                  <pre className="max-h-64 overflow-auto rounded-md border border-bg-border bg-bg-deep/60 p-2 text-[10px] font-mono text-fg-muted whitespace-pre-wrap">
                    <code>{e.output}</code>
                  </pre>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
