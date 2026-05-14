"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Loader2, Send, Sparkles } from "lucide-react";

type ChatTurn = {
  role: "user" | "assistant";
  content: string;
};

type Props = {
  tenantSlug: string;
  agentSlug: string;
  agentName: string;
  agentSubtitle?: string;
  /** Optional welcome message rendered above the empty-state. */
  greeting?: string;
};

export function AgentChat({
  tenantSlug,
  agentSlug,
  agentName,
  agentSubtitle,
  greeting,
}: Props) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelLabel, setModelLabel] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, streaming]);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || streaming) return;
      setError(null);

      const nextTurns: ChatTurn[] = [
        ...turns,
        { role: "user", content: trimmed },
        { role: "assistant", content: "" }, // placeholder for streaming
      ];
      setTurns(nextTurns);
      setInput("");
      setStreaming(true);

      try {
        const res = await fetch("/api/agents/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            tenant_slug: tenantSlug,
            agent_slug: agentSlug,
            messages: nextTurns
              .slice(0, -1)
              .filter((t) => t.content || t.role === "user"),
          }),
        });

        if (!res.ok || !res.body) {
          const body = await res.json().catch(() => ({}));
          const detail = (body as { error?: string; message?: string }).message ||
            (body as { error?: string }).error ||
            `HTTP ${res.status}`;
          setError(detail);
          setTurns((prev) => prev.slice(0, -1));
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let assistantText = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE frames are separated by blank lines.
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";

          for (const frame of frames) {
            if (!frame.trim()) continue;
            const lines = frame.split("\n");
            let eventName = "message";
            let dataStr = "";
            for (const line of lines) {
              if (line.startsWith("event:")) eventName = line.slice(6).trim();
              else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
            }
            if (!dataStr) continue;
            let payload: unknown;
            try {
              payload = JSON.parse(dataStr);
            } catch {
              continue;
            }
            if (eventName === "agent" && payload && typeof payload === "object") {
              setModelLabel(((payload as { model?: string }).model) || null);
            } else if (eventName === "delta" && payload && typeof payload === "object") {
              const text = (payload as { text?: string }).text || "";
              if (text) {
                assistantText += text;
                setTurns((prev) => {
                  const next = [...prev];
                  next[next.length - 1] = { role: "assistant", content: assistantText };
                  return next;
                });
              }
            } else if (eventName === "error" && payload && typeof payload === "object") {
              setError((payload as { message?: string }).message || "stream_error");
            }
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "network_error");
        setTurns((prev) => prev.slice(0, -1));
      } finally {
        setStreaming(false);
        inputRef.current?.focus();
      }
    },
    [tenantSlug, agentSlug, streaming, turns]
  );

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
    <div className="flex flex-col rounded-2xl border border-bg-border bg-bg-elev/40 backdrop-blur-sm min-h-[640px]">
      <div className="border-b border-bg-border px-5 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 text-accent">
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="leading-tight">
            <div className="font-bold text-sm text-fg">{agentName}</div>
            {agentSubtitle && (
              <div className="text-[10px] uppercase tracking-[0.16em] text-fg-dim">
                {agentSubtitle}
              </div>
            )}
          </div>
        </div>
        {modelLabel && (
          <span className="text-[10px] uppercase tracking-[0.16em] text-fg-dim font-mono">
            {modelLabel}
          </span>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {turns.length === 0 && (
          <div className="rounded-xl border border-bg-border bg-bg-elev/40 px-4 py-3 text-sm text-fg-muted leading-relaxed">
            {greeting || `Start chatting with ${agentName}. Use Cmd/Ctrl+Enter to send.`}
          </div>
        )}
        {turns.map((t, i) => (
          <div
            key={i}
            className={`text-sm leading-relaxed whitespace-pre-wrap break-words ${
              t.role === "user"
                ? "ml-8 rounded-xl bg-accent-soft border border-accent-muted/30 px-4 py-2.5 text-fg"
                : "mr-8 rounded-xl bg-bg-elev/70 border border-bg-border px-4 py-2.5 text-fg-muted"
            }`}
          >
            {t.content || (streaming && i === turns.length - 1 ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-accent inline" />
            ) : null)}
          </div>
        ))}
      </div>

      {error && (
        <div className="mx-5 mb-2 rounded-xl border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-200 inline-flex items-start gap-2">
          <AlertCircle className="h-3.5 w-3.5 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="border-t border-bg-border p-3 space-y-2">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder={`Message ${agentName}... (Cmd/Ctrl+Enter to send)`}
          disabled={streaming}
          rows={2}
          className="w-full resize-none rounded-xl border border-bg-border bg-bg-deep/80 px-4 py-2.5 text-sm text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none disabled:opacity-50"
        />
        <div className="flex items-center justify-end">
          <button
            type="submit"
            disabled={!input.trim() || streaming}
            className="btn-send inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
          >
            {streaming ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
