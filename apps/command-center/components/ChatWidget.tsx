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
import { Send, AlertCircle, Settings as Cog, Loader2, Sparkles, RefreshCw, Cpu } from "lucide-react";
import Link from "next/link";
import { getAgentInfo } from "@/lib/agents";
import { BRIDGE_CHAT_BASE } from "@/lib/agent-roots";

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

export default function ChatWidget({ agentKeys, defaultAgent, isAdmin }: Props) {
  const [agent, setAgent] = useState<string>(defaultAgent || agentKeys[0] || "bravo");
  const [configs, setConfigs] = useState<AgentConfig[]>([]);
  const [configsLoaded, setConfigsLoaded] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actions, setActions] = useState<
    Array<{ ok: boolean; type: string; summary?: string; error?: string }>
  >([]);
  const [bridgeOnline, setBridgeOnline] = useState<boolean | null>(null);
  const [toolReads, setToolReads] = useState<string[]>([]);
  const [toolRuns, setToolRuns] = useState<
    Array<{ script: string; args: string[]; confirm: boolean }>
  >([]);
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

  // Probe the local bridge on mount + every 30s. When the operator runs
  // `bravo bridge serve`, this flips true and chat starts targeting their
  // machine instead of /api/chat (full repo access, operator's API key).
  useEffect(() => {
    let alive = true;
    const probe = async () => {
      try {
        const ctl = new AbortController();
        const t = setTimeout(() => ctl.abort(), 1500);
        const r = await fetch(`${BRIDGE_CHAT_BASE}/health`, { signal: ctl.signal });
        clearTimeout(t);
        if (alive) setBridgeOnline(r.ok);
      } catch {
        if (alive) setBridgeOnline(false);
      }
    };
    probe();
    const id = setInterval(probe, 30_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streaming]);

  useEffect(() => {
    setMessages([]);
    setSessionId(null);
    setError(null);
    setActions([]);
    setToolReads([]);
    setToolRuns([]);
  }, [agent]);

  const cfg = useMemo(() => configs.find((c) => c.agent_key === agent) || null, [configs, agent]);
  const hasOwnKey = cfg?.has_key && cfg?.enabled;
  // Bridge online → chat works regardless of cloud config (operator's local
  // ANTHROPIC_API_KEY drives it). Otherwise the cloud config / admin
  // fallback decides.
  const ready = bridgeOnline === true || (configsLoaded && (hasOwnKey || isAdmin));

  function reset() {
    setMessages([]);
    setSessionId(null);
    setError(null);
    setActions([]);
    setToolReads([]);
    setToolRuns([]);
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
      // Routing decision:
      //   bridge online → POST localhost:9100/chat (full repo + read_file
      //                   tool, operator's API key, never leaves machine)
      //   bridge offline → POST /api/chat (Vercel relay, BYO encrypted key)
      const useBridge = bridgeOnline === true;
      const url = useBridge ? `${BRIDGE_CHAT_BASE}/chat` : "/api/chat";
      const body = useBridge
        ? { agent, messages: newMessages }
        : { agent_key: agent, session_id: sessionId, messages: newMessages };
      const res = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
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
          } else if (event === "action") {
            setActions((prev) => [
              ...prev,
              {
                ok: !!parsed.ok,
                type: String(parsed.type || "?"),
                summary: parsed.summary,
                error: parsed.error,
              },
            ]);
          } else if (event === "tool" && parsed.name === "read_file") {
            setToolReads((prev) => [...prev, String(parsed.path || "")]);
          } else if (event === "tool" && parsed.name === "run_script") {
            setToolRuns((prev) => [
              ...prev,
              {
                script: String(parsed.script || ""),
                args: Array.isArray(parsed.args) ? parsed.args.map(String) : [],
                confirm: !!parsed.confirm,
              },
            ]);
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
    <div className={`chat-container agent-${agent} flex flex-col h-[640px]`}>
      {/* Aurora wash inside the bordered container */}
      <div className="chat-aurora absolute inset-0 pointer-events-none" />

      {/* Header — agent picker + model badge */}
      <div className="flex items-center gap-3 px-5 py-4 relative z-10">
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
            {getAgentInfo(agent).tagline}
          </div>
          <div className="text-xs text-fg-dim font-mono truncate">
            {bridgeOnline === true ? (
              <span className="text-accent">
                <Cpu className="w-3 h-3 inline-block mr-1 -mt-0.5" />
                local bridge · full repo access
              </span>
            ) : cfg ? (
              `${cfg.provider} · ${cfg.model}`
            ) : isAdmin ? (
              "admin · platform key"
            ) : configsLoaded ? (
              "not configured"
            ) : (
              "loading…"
            )}
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

      {/* Animated rail beneath the header */}
      <div className="chat-rail" />

      {/* Bridge-state banner — only when chat is in cloud mode and missing
          the local repo context. Mirrors the path CC asked for: he should
          never wonder "why doesn't this agent know my files." */}
      {bridgeOnline === false && (
        <div className="px-5 py-2.5 bg-status-warm/10 border-b border-status-warm/30 text-xs text-status-warm flex items-start gap-2 relative z-10">
          <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
          <div className="flex-1 leading-relaxed space-y-1.5">
            <div>
              <span className="font-bold">Cloud mode.</span> Agent doesn&apos;t have access to your local file structure right now. For full repo context (read brain/, skills/, memory/, propose code edits), open a terminal in your install dir and run:
            </div>
            <code className="block px-2 py-1 bg-bg-deep rounded text-accent font-mono">bravo bridge serve</code>
            <div className="text-fg-dim text-[11px]">
              Refresh this page once it&apos;s running. Header turns cyan.
              {" "}If your browser asks <em>&quot;Allow this site to access local network?&quot;</em> click <strong>Allow</strong> — that&apos;s Chrome&apos;s Private Network Access check, not a privacy issue. The dashboard never reads anything outside the agent&apos;s repo (path-allowlisted in the bridge).
            </div>
            <div className="text-fg-dim text-[11px]">
              Auto-start the bridge on every login: <code className="text-accent">bravo bridge install</code> (Windows scheduled task / macOS launchd / Linux systemd).
            </div>
          </div>
        </div>
      )}

      {/* Transcript */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-5 space-y-4 chat-scroll relative z-10">
        {!messages.length && !error && (
          <EmptyTranscript ready={!!ready} agent={agent} configsLoaded={configsLoaded} isAdmin={!!isAdmin} />
        )}
        {messages.map((m, i) => (
          <Bubble
            key={i}
            role={m.role}
            content={stripActionMarkers(m.content)}
            streaming={streaming && i === messages.length - 1 && m.role === "assistant"}
          />
        ))}
        {toolReads.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {toolReads.map((p, i) => (
              <span
                key={i}
                className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-accent/10 border border-accent/20 text-accent"
                title="Agent read this file from its repo"
              >
                read · {p}
              </span>
            ))}
          </div>
        )}
        {toolRuns.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {toolRuns.map((r, i) => (
              <span
                key={i}
                className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${
                  r.confirm
                    ? "bg-status-engaged/15 border border-status-engaged/30 text-status-engaged"
                    : "bg-status-warm/10 border border-status-warm/30 text-status-warm"
                }`}
                title={
                  r.confirm
                    ? "Agent ran this allowlisted script"
                    : "Agent attempted a mutating script without confirm — bounced for safety"
                }
              >
                {r.confirm ? "ran" : "blocked"} · {r.script}
                {r.args.length > 0 ? ` ${r.args.slice(0, 4).join(" ")}${r.args.length > 4 ? "…" : ""}` : ""}
              </span>
            ))}
          </div>
        )}
        {actions.length > 0 && (
          <div className="space-y-1.5">
            {actions.map((a, i) => (
              <div
                key={i}
                className={`flex items-start gap-2 rounded-md border px-3 py-2 text-xs font-mono ${
                  a.ok
                    ? "border-status-engaged/40 bg-status-engaged/10 text-status-engaged"
                    : "border-status-warm/40 bg-status-warm/10 text-status-warm"
                }`}
              >
                <span className="font-bold uppercase tracking-wider text-[10px] mt-0.5">
                  {a.ok ? "applied" : "rejected"}
                </span>
                <span className="text-fg-muted">{a.type}</span>
                <span className="font-sans">{a.summary || a.error || "(no detail)"}</span>
              </div>
            ))}
          </div>
        )}
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-status-warm/40 bg-status-warm/10 p-3 text-sm text-status-warm">
            <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <div className="space-y-1 min-w-0">
              <div className="font-mono break-all">{error}</div>
              {error === "admin_no_platform_key" && (
                <div className="text-xs text-fg-muted font-sans">
                  Admin chat needs a platform key. Two ways: (1) run{" "}
                  <code className="bg-bg-elev px-1 py-0.5 rounded text-accent">bravo bridge seed-keys</code>{" "}
                  on your machine to push your local Anthropic / OpenAI / OpenRouter key into the dashboard, or (2) add{" "}
                  <code className="bg-bg-elev px-1 py-0.5 rounded text-accent">PLATFORM_DEFAULT_OPENROUTER_API_KEY</code>{" "}
                  in Vercel env vars.
                </div>
              )}
              {error === "agent_not_configured" && (
                <div className="text-xs text-fg-muted font-sans">
                  This agent needs a provider + key. Open{" "}
                  <Link href="/settings#agents" className="text-accent underline">
                    Settings → Agents
                  </Link>{" "}
                  to configure it.
                </div>
              )}
              {error === "rate_limited" && (
                <div className="text-xs text-fg-muted font-sans">
                  Too many messages too fast. Wait ~15 seconds and try again.
                </div>
              )}
            </div>
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

/**
 * Strip <dashboard-action ...> markers from the displayed text. The agent
 * emits these so the server can apply mutations; users don't want to see
 * the raw JSON tags in the bubble. The applied/rejected pills below the
 * transcript are the human-facing surface for these.
 */
function stripActionMarkers(text: string): string {
  return text
    .replace(/<dashboard-action\s+type=["'][a-z_]+["']\s*>[\s\S]*?<\/dashboard-action>/gi, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

async function safeReadJson(r: Response): Promise<any> {
  try {
    return await r.json();
  } catch {
    return null;
  }
}
