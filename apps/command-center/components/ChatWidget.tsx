"use client";

/**
 * ChatWidget — in-dashboard chat with the agent family.
 *
 * Phase 1: cloud-only. The user picks an agent (Bravo/Maven/Atlas/Aura/Hermes)
 * and the widget streams from /api/chat using whatever provider/model/api_key
 * they've configured for that agent in Settings.
 *
 * Phase 2: paired local bridge unlocks file tree + actual Claude Code spawning.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Send, AlertCircle, Settings as Cog, Loader2 } from "lucide-react";

type Role = "user" | "assistant" | "system";
type Msg = { role: Role; content: string };
type AgentConfig = {
  agent_key: string;
  provider: string;
  model: string;
  enabled: boolean;
  has_key: boolean;
};

type Props = {
  agentKeys: string[];
  defaultAgent?: string;
};

export default function ChatWidget({ agentKeys, defaultAgent }: Props) {
  const [agent, setAgent] = useState<string>(defaultAgent || agentKeys[0] || "bravo");
  const [configs, setConfigs] = useState<AgentConfig[]>([]);
  const [configsLoaded, setConfigsLoaded] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Load agent configs once
  useEffect(() => {
    fetch("/api/agent-config")
      .then((r) => r.json())
      .then((j) => {
        if (j.ok) setConfigs(j.configs as AgentConfig[]);
      })
      .catch(() => null)
      .finally(() => setConfigsLoaded(true));
  }, []);

  // Auto-scroll on new content
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streaming]);

  // Reset thread when agent changes
  useEffect(() => {
    setMessages([]);
    setSessionId(null);
    setError(null);
  }, [agent]);

  const cfg = useMemo(() => configs.find((c) => c.agent_key === agent) || null, [configs, agent]);
  const ready = configsLoaded && cfg?.has_key && cfg?.enabled;

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;
    setError(null);
    const newMessages: Msg[] = [...messages, { role: "user", content: text }];
    setMessages(newMessages);
    setInput("");

    // Optimistic assistant placeholder
    setMessages((m) => [...m, { role: "assistant", content: "" }]);
    setStreaming(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          agent_key: agent,
          session_id: sessionId,
          messages: newMessages,
        }),
      });
      if (!res.ok || !res.body) {
        const errBody = await safeReadJson(res);
        setError(errBody?.error || `http_${res.status}`);
        setStreaming(false);
        // Drop the optimistic placeholder
        setMessages((m) => m.slice(0, -1));
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) !== -1) {
          const block = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          let event = "message";
          let data = "";
          for (const line of block.split("\n")) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            else if (line.startsWith("data:")) data = line.slice(5).trim();
          }
          if (!data) continue;
          let parsed: any;
          try {
            parsed = JSON.parse(data);
          } catch {
            continue;
          }
          if (event === "session" && parsed.session_id) setSessionId(parsed.session_id);
          else if (event === "delta" && typeof parsed.text === "string") {
            setMessages((m) => {
              const next = [...m];
              const last = next[next.length - 1];
              if (last && last.role === "assistant") {
                next[next.length - 1] = { ...last, content: last.content + parsed.text };
              }
              return next;
            });
          } else if (event === "error") {
            setError(parsed.message || "stream_error");
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "request_failed");
      setMessages((m) => m.slice(0, -1));
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="flex flex-col h-[640px]">
      {/* Header — agent picker */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-bg-border">
        <select
          value={agent}
          onChange={(e) => setAgent(e.target.value)}
          className="bg-bg-elev border border-bg-border rounded-md px-3 py-1.5 text-sm text-fg uppercase tracking-[0.12em] font-bold focus:outline-none focus:border-accent"
        >
          {agentKeys.map((k) => (
            <option key={k} value={k}>
              {k.toUpperCase()}
            </option>
          ))}
        </select>
        <div className="flex-1 text-xs text-fg-muted font-mono">
          {cfg
            ? `${cfg.provider} · ${cfg.model}`
            : configsLoaded
              ? "not configured"
              : "loading…"}
        </div>
        <a
          href="/settings#agents"
          className="text-fg-dim hover:text-accent transition-colors"
          title="Configure agent in Settings"
        >
          <Cog className="w-4 h-4" />
        </a>
      </div>

      {/* Transcript */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
        {!messages.length && !error && (
          <div className="text-fg-dim text-sm">
            {ready
              ? `Ready to chat with ${agent.toUpperCase()}.`
              : configsLoaded
                ? `${agent.toUpperCase()} isn't configured yet. Add an API key in Settings → Agents.`
                : "Loading…"}
          </div>
        )}
        {messages.map((m, i) => (
          <Bubble key={i} role={m.role} content={m.content} streaming={streaming && i === messages.length - 1 && m.role === "assistant"} />
        ))}
        {error && (
          <div className="flex items-start gap-2 rounded-md border border-status-warm/40 bg-status-warm/10 p-3 text-sm text-status-warm">
            <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <div className="font-mono break-all">{error}</div>
          </div>
        )}
      </div>

      {/* Composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="border-t border-bg-border px-5 py-3 flex gap-2"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={ready ? `Message ${agent.toUpperCase()}…` : "Configure this agent first"}
          disabled={!ready || streaming}
          className="flex-1 bg-bg-elev border border-bg-border rounded-md px-3 py-2 text-sm text-fg placeholder-fg-dim focus:outline-none focus:border-accent disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!ready || streaming || !input.trim()}
          className="bg-accent text-bg-deep rounded-md px-4 py-2 text-sm font-bold disabled:opacity-40 disabled:cursor-not-allowed hover:bg-accent-bright transition-colors flex items-center gap-1.5"
        >
          {streaming ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Send className="w-4 h-4" />
          )}
          {streaming ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}

function Bubble({ role, content, streaming }: { role: Role; content: string; streaming: boolean }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3.5 py-2.5 text-sm whitespace-pre-wrap leading-relaxed ${
          isUser
            ? "bg-accent/15 border border-accent/30 text-fg"
            : "bg-bg-elev border border-bg-border text-fg"
        }`}
      >
        {content || (streaming ? <span className="text-fg-dim">…</span> : null)}
      </div>
    </div>
  );
}

async function safeReadJson(r: Response): Promise<any> {
  try {
    return await r.json();
  } catch {
    return null;
  }
}
