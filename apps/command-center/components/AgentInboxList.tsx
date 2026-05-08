"use client";

import { useState, useTransition } from "react";
import { Check, ChevronRight, Reply } from "lucide-react";
import { useRouter } from "next/navigation";
import { Tag } from "./Card";
import type { InboxMessage, Priority } from "@/lib/agent-inbox-fs";

const TONE_BY_PRIORITY: Record<Priority, "warm" | "hot" | "neutral" | "info"> = {
  urgent: "hot",
  high: "warm",
  normal: "info",
  low: "neutral",
};

function _relTime(iso: string): string {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "—";
  const d = (Date.now() - t) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86_400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86_400)}d ago`;
}

export function AgentInboxList({
  unread,
  read,
}: {
  unread: InboxMessage[];
  read: InboxMessage[];
}) {
  const router = useRouter();
  const [openId, setOpenId] = useState<string | null>(null);
  const [showRead, setShowRead] = useState(false);
  const [pending, startTransition] = useTransition();
  const [marking, setMarking] = useState<string | null>(null);

  function toggle(id: string) {
    setOpenId((cur) => (cur === id ? null : id));
  }

  async function onMarkRead(filename: string) {
    setMarking(filename);
    try {
      const res = await fetch("/api/inbox/mark-read", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ filename }),
      });
      const j = await res.json().catch(() => ({}));
      if (!j.ok) {
        alert(`mark-read failed: ${j.error || "unknown"}`);
        return;
      }
      startTransition(() => router.refresh());
    } finally {
      setMarking(null);
    }
  }

  if (unread.length === 0 && read.length === 0) {
    return (
      <div className="text-sm text-fg-muted py-6 text-center">
        Inbox is empty. Messages from sibling agents will appear here.
      </div>
    );
  }

  const list = showRead ? read : unread;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs">
        <button
          type="button"
          className={`px-2 py-1 rounded border ${
            !showRead
              ? "bg-accent-soft text-accent border-accent/30"
              : "border-bg-border text-fg-muted hover:text-fg"
          }`}
          onClick={() => setShowRead(false)}
        >
          Unread {unread.length > 0 && <span className="font-mono">({unread.length})</span>}
        </button>
        <button
          type="button"
          className={`px-2 py-1 rounded border ${
            showRead
              ? "bg-accent-soft text-accent border-accent/30"
              : "border-bg-border text-fg-muted hover:text-fg"
          }`}
          onClick={() => setShowRead(true)}
        >
          Read {read.length > 0 && <span className="font-mono">({read.length})</span>}
        </button>
      </div>

      {list.length === 0 ? (
        <div className="text-sm text-fg-muted py-4 text-center">
          {showRead ? "No archived messages." : "No unread messages."}
        </div>
      ) : (
        <ul className="divide-y divide-bg-border rounded-lg border border-bg-border overflow-hidden bg-bg">
          {list.map((m) => {
            const isOpen = openId === m.message_id;
            return (
              <li key={m.message_id || m._filename} className="text-sm">
                <button
                  type="button"
                  onClick={() => toggle(m.message_id || m._filename)}
                  className="w-full flex items-start gap-3 px-4 py-3 hover:bg-bg-elev transition-colors text-left"
                >
                  <ChevronRight
                    className={`w-4 h-4 mt-0.5 flex-shrink-0 transition-transform text-fg-dim ${
                      isOpen ? "rotate-90" : ""
                    }`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <span className="font-mono text-[10px] uppercase tracking-wider text-fg-muted">
                        {m.from} → {m.to}
                      </span>
                      <Tag tone={TONE_BY_PRIORITY[m.priority]}>{m.priority}</Tag>
                      {m.requires_response && (
                        <Tag tone="accent">needs reply</Tag>
                      )}
                    </div>
                    <div className="text-fg font-medium mt-1 truncate">
                      {m.subject || "(no subject)"}
                    </div>
                  </div>
                  <span className="text-xs text-fg-dim font-mono flex-shrink-0">
                    {_relTime(m.timestamp)}
                  </span>
                </button>
                {isOpen && (
                  <div className="px-4 pb-4 pt-1 ml-7 space-y-3">
                    <pre className="whitespace-pre-wrap font-sans text-fg-muted text-sm">
                      {m.body}
                    </pre>
                    {!m._read && (
                      <div className="flex items-center gap-2 pt-2 border-t border-bg-border">
                        <button
                          type="button"
                          disabled={marking === m._filename || pending}
                          onClick={() => onMarkRead(m._filename)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-bg-border text-xs text-fg hover:border-accent-muted hover:text-accent transition-colors disabled:opacity-50"
                        >
                          <Check className="w-3.5 h-3.5" />
                          {marking === m._filename ? "marking…" : "mark read"}
                        </button>
                        <span className="text-[11px] text-fg-dim">
                          message_id: <span className="font-mono">{m.message_id}</span>
                        </span>
                      </div>
                    )}
                    {m._read && (
                      <div className="flex items-center gap-2 pt-2 border-t border-bg-border text-[11px] text-fg-dim">
                        <Reply className="w-3.5 h-3.5" />
                        Reply via the post form below — set in_reply_to to{" "}
                        <span className="font-mono">{m.message_id}</span>.
                      </div>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export function AgentInboxComposer({ defaultFrom = "cc" }: { defaultFrom?: string }) {
  const router = useRouter();
  const [to, setTo] = useState("bravo");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [priority, setPriority] = useState<Priority>("normal");
  const [requiresResponse, setRequiresResponse] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!subject.trim() || !body.trim()) {
      setError("subject + body required");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/inbox/post", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          from: defaultFrom,
          to,
          subject,
          body,
          priority,
          requires_response: requiresResponse,
        }),
      });
      const j = await res.json().catch(() => ({}));
      if (!j.ok) {
        setError(j.error || "post_failed");
        return;
      }
      setSubject("");
      setBody("");
      setRequiresResponse(false);
      startTransition(() => router.refresh());
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3 text-sm">
      <div className="flex flex-wrap gap-3">
        <label className="flex flex-col gap-1 flex-1 min-w-[140px]">
          <span className="text-[10px] uppercase tracking-wider text-fg-muted">to</span>
          <select
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="bg-bg-elev border border-bg-border rounded px-2 py-1.5 text-fg"
          >
            {["bravo", "atlas", "maven", "aura", "life-preservation", "codex", "broadcast"].map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-fg-muted">priority</span>
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value as Priority)}
            className="bg-bg-elev border border-bg-border rounded px-2 py-1.5 text-fg"
          >
            <option value="urgent">urgent</option>
            <option value="high">high</option>
            <option value="normal">normal</option>
            <option value="low">low</option>
          </select>
        </label>
        <label className="flex items-end gap-2 pb-1.5">
          <input
            type="checkbox"
            checked={requiresResponse}
            onChange={(e) => setRequiresResponse(e.target.checked)}
            className="accent-accent"
          />
          <span className="text-xs text-fg-muted">needs reply</span>
        </label>
      </div>
      <label className="flex flex-col gap-1">
        <span className="text-[10px] uppercase tracking-wider text-fg-muted">subject</span>
        <input
          type="text"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          maxLength={200}
          className="bg-bg-elev border border-bg-border rounded px-2 py-1.5 text-fg"
          placeholder="Brief subject"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-[10px] uppercase tracking-wider text-fg-muted">body</span>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={4}
          maxLength={8000}
          className="bg-bg-elev border border-bg-border rounded px-2 py-1.5 text-fg font-mono text-xs resize-y min-h-[100px]"
          placeholder="Body — markdown OK."
        />
      </label>
      {error && <div className="text-status-warm text-xs">{error}</div>}
      <button
        type="submit"
        disabled={submitting || pending}
        className="px-3 py-1.5 rounded bg-accent-soft border border-accent/30 text-accent text-xs font-bold uppercase tracking-wider hover:bg-accent/20 transition-colors disabled:opacity-50"
      >
        {submitting ? "posting…" : "post message"}
      </button>
    </form>
  );
}
