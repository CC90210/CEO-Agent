"use client";

/**
 * ChatWidget — in-dashboard chat with the agent family.
 *
 * Phase 1: cloud-only. The user picks an agent (Bravo/Maven/Atlas/Aura/Hermes)
 * and the widget streams from /api/chat using whatever provider/model/api_key
 * they've configured for that agent in Settings — OR a platform-default key
 * if the authed user is the operator (CC).
 *
 * Phase 2: paired local bridge unlocks file tree + actual Claude Code spawning.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Send, AlertCircle, Settings as Cog, Loader2, Sparkles, RefreshCw } from "lucide-react";
import Link from "next/link";

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
  /** When true (operator/admin), the widget never blocks on missing config — chat is allowed via platform fallback. */
  isAdmin?: boolean;
};

const AGENT_TAGLINES: Record<string, string> = {
  bravo: "Lead architect · ops · voice",
  maven: "CMO · content · ads · funnels",
  atlas: "CFO · finance · tax · trading",
  aura: "Life · home · habits · voice",
  hermes: "Commerce · POS · EDI",
};

export default function ChatWidget({ agentKeys, defaultAgent, isAdmin }: Props) {
  const [agent, setAgent] = useState<string>(defaultAgent || agentKeys[0] || "bravo");
  const [configs, setConfigs] = useState<AgentConfig[]>([]);
  const [configsLoaded, setConfigsLoaded] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetch("/api/agent-config")
      .then((r) => r.json())
      .then((j) => {
        if (j.ok) setConfigs(j.configs as AgentConfig[]);
      })
      .catch(() => null)
      .finally(() => setConfigsLoaded(true));
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streaming]);

  useEffect(() => {
    setMessages([]);
    setSessionId(null);
    setError(null);
  }, [agent]);

  const cfg = useMemo(() => configs.find((c) => c.agent_key === agent) || null, [configs, agent]);
  const hasOwnKey = cfg?.has_key && cfg?.enabled;
  const ready = configsLoaded && (hasOwnKey || isAdmin);

  function reset() {
    setMessages([]);
    setSessionId(null);
    setError(null);
  }

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;
    setError(null);
    const newMessages: Msg[] = [...messages, { role: "user", content: text }];
    setMessages(newMessages);
    setInput("");
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
      // Auto-focus the input so power-users can keep typing
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="flex flex-col h-[640px] chat-aurora">
      {/* Header — agent picker + model badge */}
      <div className="flex items-center gap-3 px-5 py-4 border-b border-bg-border relative z-10">
        <select
          value={agent}
          onChange={(e) => setAgent(e.target.value)}
          className="bg-bg-elev border border-bg-border rounded-lg px-3 py-2 text-sm text-fg uppercase tracking-[0.14em] font-bold focus:outline-none focus:border-accent transition-colors cursor-pointer"
          aria-label="Choose agent"
        >
          {agentKeys.map((k) => (
            <option key={k} value={k}>
              {k.toUpperCase()}
            </option>
          ))}
        </select>
        <div className="flex-1 min-w-0">
          <div className="text-xs text-fg-muted truncate">
            {AGENT_TAGLINES[agent] || "Custom agent"}
          </div>
          <div className="text-xs text-fg-dim font-mono truncate">
            {cfg
              ? `${cfg.provider} · ${cfg.model}`
              : isAdmin
                ? "platform default (admin)"
                : configsLoaded
                  ? "not configured"
                  : "loading…"}
          </div>
        </div>
        {messages.length > 0 && (
          <button
            type="button"
            onClick={reset}
            className="text-fg-dim hover:text-accent transition-colors p-1"
            title="Start new conversation"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        )}
        <Link
          href="/settings#agents"
          className="text-fg-dim hover:text-accent transition-colors p-1"
          title="Configure agent in Settings"
        >
          <Cog className="w-4 h-4" />
        </Link>
      </div>

      {/* Transcript */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-5 space-y-4 chat-scroll relative z-10">
        {!messages.length && !error && (
          <EmptyTranscript ready={!!ready} agent={agent} configsLoaded={configsLoaded} isAdmin={!!isAdmin} />
        )}
        {messages.map((m, i) => (
          <Bubble
            key={i}
            role={m.role}
            content={m.content}
            streaming={streaming && i === messages.length - 1 && m.role === "assistant"}
          />
        ))}
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-status-warm/40 bg-status-warm/10 p-3 text-sm text-status-warm">
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
        className="border-t border-bg-border px-5 py-4 flex gap-2 relative z-10 bg-bg-panel/40 backdrop-blur"
      >
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={ready ? `Message ${agent.toUpperCase()}…  (Shift+Enter for newline)` : "Configure this agent first"}
          disabled={!ready || streaming}
          rows={1}
          className="flex-1 bg-bg-elev border border-bg-border rounded-lg px-3.5 py-2.5 text-sm text-fg placeholder-fg-dim focus:outline-none focus:border-accent disabled:opacity-50 resize-none max-h-32"
          style={{ minHeight: "2.75rem" }}
        />
        <button
          type="submit"
          disabled={!ready || streaming || !input.trim()}
          className="btn-send"
        >
          {streaming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          {streaming ? "" : "Send"}
        </button>
      </form>
    </div>
  );
}

function EmptyTranscript({
  ready,
  agent,
  configsLoaded,
  isAdmin,
}: {
  ready: boolean;
  agent: string;
  configsLoaded: boolean;
  isAdmin: boolean;
}) {
  if (!configsLoaded) {
    return (
      <div className="flex items-center gap-2 text-fg-dim text-sm">
        <Loader2 className="w-4 h-4 animate-spin" /> loading agent config…
      </div>
    );
  }
  if (!ready) {
    return (
      <div className="rounded-lg border border-accent/20 bg-accent/5 p-5 text-sm space-y-3">
        <div className="flex items-center gap-2 text-accent font-bold uppercase tracking-[0.14em] text-xs">
          <Sparkles className="w-4 h-4" /> Set up {agent.toUpperCase()}
        </div>
        <p className="text-fg">
          {agent.toUpperCase()} needs a model + API key before it can chat. The
          easiest path is OpenRouter — one key gets you Claude, GPT, and
          Gemini.
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          <a
            href="https://openrouter.ai/sign-up"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary text-xs"
          >
            Get OpenRouter key
          </a>
          <Link href="/settings#agents" className="btn-secondary text-xs">
            Open Settings
          </Link>
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-bg-border bg-bg-elev/50 p-5 text-sm space-y-2">
      <div className="text-accent font-bold uppercase tracking-[0.14em] text-xs flex items-center gap-2">
        <span className="agent-pill-dot" />
        Ready
      </div>
      <p className="text-fg-muted">
        {isAdmin
          ? `Talking to ${agent.toUpperCase()} via the platform default key.`
          : `${agent.toUpperCase()} is configured and ready.`} Ask anything — strategy, drafting, debugging, ops.
      </p>
    </div>
  );
}

function Bubble({
  role,
  content,
  streaming,
}: {
  role: Role;
  content: string;
  streaming: boolean;
}) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser ? "bubble-user" : `bubble-assistant ${streaming ? "streaming" : ""}`
        }`}
      >
        {content ? (
          <FormattedContent content={content} />
        ) : streaming ? (
          <div className="typing-dots"><span /><span /><span /></div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Lightweight markdown-ish formatter — handles fenced code blocks and inline
 * code. Anything more advanced is intentionally deferred (no link rewriting,
 * no XSS surface). Plaintext + code + line breaks.
 */
function FormattedContent({ content }: { content: string }) {
  const segments = splitFences(content);
  return (
    <>
      {segments.map((seg, i) =>
        seg.type === "code" ? (
          <pre key={i}>
            <code>{seg.text}</code>
          </pre>
        ) : (
          <span key={i} className="whitespace-pre-wrap">
            {renderInline(seg.text)}
          </span>
        )
      )}
    </>
  );
}

function splitFences(text: string): Array<{ type: "text" | "code"; text: string }> {
  const out: Array<{ type: "text" | "code"; text: string }> = [];
  const re = /```[\w-]*\n?([\s\S]*?)```/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push({ type: "text", text: text.slice(last, m.index) });
    out.push({ type: "code", text: m[1].replace(/\n$/, "") });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ type: "text", text: text.slice(last) });
  return out.length ? out : [{ type: "text", text }];
}

function renderInline(text: string): React.ReactNode {
  // Inline code: `xyz`
  const parts = text.split(/(`[^`\n]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={i}>{part.slice(1, -1)}</code>;
    }
    return <span key={i}>{part}</span>;
  });
}

async function safeReadJson(r: Response): Promise<any> {
  try {
    return await r.json();
  } catch {
    return null;
  }
}
