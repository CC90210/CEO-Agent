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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ToolTimelineList } from "@/components/chat/ToolTimelineList";
import { useSynthCalls } from "@/lib/use-synth-calls";
import {
  Send,
  AlertCircle,
  Settings as Cog,
  Loader2,
  Sparkles,
  RefreshCw,
  Cpu,
  ArrowDown,
  Check,
  ChevronRight,
  Clipboard,
  // FileText / Pencil / Terminal / Search / Globe / X / Brain moved to
  // components/chat/ToolTimelineList.tsx along with the timeline that
  // used them. Database stays — used by the cloud-tool result pill below.
  Database,
  Maximize2,
  Minimize2,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { getAgentInfo } from "@/lib/agents";
import { BRIDGE_CHAT_BASE } from "@/lib/agent-roots";

type Role = "user" | "assistant" | "system";
type Msg = { role: Role; content: string; at: number };

const AGENT_SUGGESTIONS: Record<string, string[]> = {
  bravo: [
    "Show me my MRR + this week's revenue movement",
    "Which leads are qualified and ready to close?",
    "Send a check-in to Jonathan",
    "Run the daily briefing",
  ],
  atlas: [
    "Summarize this week's net worth + cash position",
    "Show me what's owing on tax this quarter",
    "Run a FIRE projection with current inputs",
    "Any red-flag transactions in the last 7 days?",
  ],
  maven: [
    "Draft 3 hooks for tomorrow's content drop",
    "What's working in our latest ads?",
    "Build a funnel audit on the booking page",
    "Plan this week's content calendar",
  ],
  aura: [
    "Run the morning briefing",
    "Summarize last night's sleep + recovery",
    "Draft this week's habit audit",
    "What's on the calendar today?",
  ],
  hermes: [
    "Status of open POs + chargebacks",
    "Draft the EDI 856 for the latest shipment",
    "Show me yesterday's A2000 sync log",
    "Any commerce alerts I need to handle?",
  ],
  "life-preservation": [
    "Help me plan an interview session with Grandma",
    "What questions surface the small details, not the obvious ones?",
    "Show me what we've captured so far",
    "What's missing from her story?",
  ],
};

function _suggestionsFor(agent: string): string[] {
  return AGENT_SUGGESTIONS[agent] || [
    "What can you do?",
    "Run the daily briefing",
    "Show me what changed in the last 24 hours",
    "Read brain/STATE.md",
  ];
}

/**
 * Map a tool SSE event to a display label + detail. Handles every Claude
 * Code tool kind plus the legacy bridge tools. Keep this small — the pill
 * UI just needs a 1-2 word verb + a one-line detail.
 */
function _toolLabel(parsed: Record<string, unknown>): string {
  const n = String(parsed.name || "tool");
  switch (n) {
    case "read_file": return "read";
    case "edit_file": return "edit";
    case "write_file": return "write";
    case "run_script": return "bash";
    case "glob": return "glob";
    case "grep": return "grep";
    case "web_fetch": return "fetch";
    case "mcp_call":
      return `${parsed.server ?? "mcp"}`;
    default:
      return String(parsed.raw_name ?? n);
  }
}

function _toolDetail(parsed: Record<string, unknown>): string {
  const n = String(parsed.name || "tool");
  switch (n) {
    case "read_file":
    case "edit_file":
    case "write_file":
      return String(parsed.path || "");
    case "run_script": {
      const args = Array.isArray(parsed.args) ? (parsed.args as unknown[]).join(" ") : "";
      return String(parsed.script || "") + (args ? ` ${args}` : "");
    }
    case "glob": return String(parsed.pattern || "");
    case "grep": return String(parsed.pattern || "");
    case "web_fetch": return String(parsed.url || "");
    case "mcp_call":
      return String(parsed.tool || parsed.summary || "");
    default:
      return String(parsed.summary || "");
  }
}
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
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  // URL params let /reasoning Quick Actions deep-link a prompt + agent
  // straight into the composer. Read once on mount, then strip from URL
  // so a refresh doesn't re-fire the prompt.
  const urlAgent = searchParams?.get("agent");
  const urlPrompt = searchParams?.get("prompt");
  const urlAutosend = searchParams?.get("autosend") === "1";

  const initialAgent = urlAgent && agentKeys.includes(urlAgent)
    ? urlAgent
    : (defaultAgent || agentKeys[0] || "bravo");
  const [agent, setAgent] = useState<string>(initialAgent);
  const [configs, setConfigs] = useState<AgentConfig[]>([]);
  const [configsLoaded, setConfigsLoaded] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actions, setActions] = useState<
    Array<{
      ok: boolean;
      type: string;
      summary?: string;
      error?: string;
      // A4: verification UI — uid for dismiss target, dismissed flips to
      // true once CC clicks "got it" so the pill collapses.
      uid: string;
      dismissed?: boolean;
    }>
  >([]);
  const [bridgeOnline, setBridgeOnline] = useState<boolean | null>(null);
  const [usage, setUsage] = useState<{ usage: number; limit: number | null } | null>(null);
  // Cloud-tool results — only fire on the cloud /api/chat path. Each
  // entry is one execution of a <cloud-tool> marker the agent emitted
  // (e.g., lookup_lead_by_name → matched leads). Rendered as inline
  // pills so the operator sees what the cloud agent looked up.
  const [cloudResults, setCloudResults] = useState<
    Array<{ uid: string; ok: boolean; name: string; summary?: string; error?: string; data?: unknown }>
  >([]);
  // Generic tool-call pills — covers every Claude Code tool (Read, Edit,
  // Write, Bash, Glob, Grep, WebFetch, MCP servers) plus the legacy
  // bridge tools (read_file, run_script). Correlated by tool_use_id.
  const [toolCalls, setToolCalls] = useState<
    Array<{
      id: string;
      kind: string;
      label: string;
      detail?: string;
      output?: string;
      error?: boolean;
      elapsed_s?: number;
      createdAt: number;
      completedAt?: number;
    }>
  >([]);
  // [DEPRECATED — REMOVE AFTER 2026-05-14] toolReads + toolRuns + their
  // ToolReadList / ToolRunList renderers below are only used when the
  // bridge runs in OASIS_CHAT_LEGACY=1 mode (raw_name absent on tool
  // events). Default Claude Code subprocess path uses the unified
  // toolCalls list above. Cut both pieces of state + their renderers
  // after the new path proves stable for one week.
  const [toolReads, setToolReads] = useState<Array<{ path: string; body?: string }>>([]);
  const [toolRuns, setToolRuns] = useState<
    Array<{
      script: string;
      args: string[];
      confirm: boolean;
      output?: string;
      elapsed_s?: number;
    }>
  >([]);
  const [awayFromBottom, setAwayFromBottom] = useState(false);
  const [expandedReads, setExpandedReads] = useState<Set<number>>(new Set());
  const [expandedRuns, setExpandedRuns] = useState<Set<number>>(new Set());
  const [thinking, setThinking] = useState(false);
  // Fullscreen mode — uses the browser Fullscreen API on the chat
  // element itself (same pattern as Claude / ChatGPT). The chat fills
  // the screen, Esc exits, no portal magic, no parent stacking-context
  // wrestling. We only track an `isFullscreen` flag so the maximize/
  // minimize icon swaps correctly.
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  function toggleFullscreen() {
    if (typeof document === "undefined") return;
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => null);
    } else if (chatContainerRef.current?.requestFullscreen) {
      chatContainerRef.current.requestFullscreen().catch(() => null);
    }
  }

  // Track the browser's fullscreen state so our icon stays in sync
  // when the user hits Esc (the browser exits fullscreen on its own).
  useEffect(() => {
    if (typeof document === "undefined") return;
    const onFsChange = () => {
      setIsFullscreen(document.fullscreenElement === chatContainerRef.current);
    };
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);
  // A0c: status phase + elapsed-time counter so CC sees "starting Atlas in
  // CFO-Agent…" → "thinking… (0:12)" instead of a static "thinking…" during
  // the first 30s of a Claude Code subprocess cold start.
  const [statusPhase, setStatusPhase] = useState<"spawning" | "thinking" | "tool" | null>(null);
  const [statusDetail, setStatusDetail] = useState<string>("");
  const [streamStartedAt, setStreamStartedAt] = useState<number | null>(null);
  const [elapsedTick, setElapsedTick] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Tick elapsed time every second while a request is mid-flight.
  useEffect(() => {
    if (!streamStartedAt) return;
    const id = setInterval(() => setElapsedTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [streamStartedAt]);

  // Synthetic activity feed via the extracted useSynthCalls hook. Shows
  // motion (terminal opening, cd, claude spawn, file scans) during the
  // 0-30s cold-start window when no real tool events fire yet. Real
  // tool events always win — the hook bails the moment toolCalls is
  // non-empty. See lib/use-synth-calls.ts.
  const synthCalls = useSynthCalls({
    streaming,
    streamStartedAt,
    hasRealTools: toolCalls.length > 0,
    agent,
  });

  const elapsedLabel = useMemo(() => {
    if (!streamStartedAt) return "";
    // elapsedTick is referenced so this memo recomputes every second.
    void elapsedTick;
    const s = Math.max(0, Math.floor((Date.now() - streamStartedAt) / 1000));
    const mm = Math.floor(s / 60);
    const ss = String(s % 60).padStart(2, "0");
    return `${mm}:${ss}`;
  }, [streamStartedAt, elapsedTick]);

  useEffect(() => {
    fetch("/api/agent-config")
      .then((r) => r.json())
      .then((j) => {
        if (j.ok) setConfigs(j.configs as AgentConfig[]);
      })
      .catch(() => null)
      .finally(() => setConfigsLoaded(true));
  }, []);

  // Hydrate composer from /reasoning Quick Action deep-links. Once.
  // Then strip params so a refresh doesn't re-trigger.
  const [hydratedFromUrl, setHydratedFromUrl] = useState(false);
  useEffect(() => {
    if (hydratedFromUrl || !urlPrompt) return;
    setInput(urlPrompt);
    setHydratedFromUrl(true);
    // Remove the params from the URL without a full nav so the composer
    // text remains visible to the operator.
    if (pathname) {
      const fresh = new URLSearchParams(searchParams?.toString() || "");
      fresh.delete("prompt");
      fresh.delete("agent");
      fresh.delete("autosend");
      const qs = fresh.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    }
    // Auto-send only if explicitly requested — default is to let the
    // operator review + edit before firing.
    if (urlAutosend) {
      setTimeout(() => {
        // send() is defined later — trigger via the form submit affordance
        const f = document.querySelector("form[data-chat-composer]") as HTMLFormElement | null;
        f?.requestSubmit();
      }, 200);
    } else {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [hydratedFromUrl, urlPrompt, urlAutosend, pathname, searchParams, router]);

  // OpenRouter usage pill — only fetches when the agent's provider is
  // openrouter (or unknown but admin-fallback is openrouter). Anthropic /
  // OpenAI / Google don't expose this cleanly, so the pill stays hidden.
  useEffect(() => {
    if (!configsLoaded) return;
    const cfg = configs.find((c) => c.agent_key === agent);
    const isOpenRouter = !cfg || cfg.provider === "openrouter";
    if (!isOpenRouter) {
      setUsage(null);
      return;
    }
    fetch(`/api/usage?agent=${encodeURIComponent(agent)}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!j || !j.ok || !j.supported) {
          setUsage(null);
          return;
        }
        setUsage({ usage: Number(j.usage) || 0, limit: j.limit === null ? null : Number(j.limit) });
      })
      .catch(() => setUsage(null));
  }, [agent, configs, configsLoaded]);

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
    if (awayFromBottom) return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streaming, awayFromBottom]);

  useEffect(() => {
    setMessages([]);
    setSessionId(null);
    setError(null);
    setActions([]);
    setCloudResults([]);
    setToolReads([]);
    setToolRuns([]);
    setToolCalls([]);
    setExpandedReads(new Set());
    setExpandedRuns(new Set());
    setThinking(false);
    setAwayFromBottom(false);
  }, [agent]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setAwayFromBottom(distanceFromBottom > 80);
  }, []);

  function jumpToLatest() {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    setAwayFromBottom(false);
  }

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
    setCloudResults([]);
    setToolReads([]);
    setToolRuns([]);
    setToolCalls([]);
    setExpandedReads(new Set());
    setExpandedRuns(new Set());
    setThinking(false);
    setAwayFromBottom(false);
  }

  function applySuggestion(text: string) {
    setInput(text);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;
    setError(null);
    const now = Date.now();
    const newMessages: Msg[] = [...messages, { role: "user", content: text, at: now }];
    setMessages(newMessages);
    setInput("");
    setMessages((m) => [...m, { role: "assistant", content: "", at: Date.now() }]);
    setStreaming(true);
    setThinking(true);
    setStreamStartedAt(Date.now());
    setStatusPhase(bridgeOnline === true ? "spawning" : "thinking");
    setStatusDetail("");

    try {
      // Routing decision:
      //   bridge online → POST localhost:9100/chat (full repo + read_file
      //                   tool, operator's API key, never leaves machine)
      //   bridge offline → POST /api/chat (Vercel relay, BYO encrypted key)
      const useBridge = bridgeOnline === true;
      const url = useBridge ? `${BRIDGE_CHAT_BASE}/chat` : "/api/chat";
      const body = useBridge
        ? {
            agent,
            messages: newMessages,
            // Pass the Claude Code session id so the bridge can use
            // --resume on subsequent turns. First turn omits it; bridge
            // mints a fresh session and emits its id back via the
            // 'session' SSE event.
            session_id: sessionId,
          }
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
          else if (event === "agent_status") {
            // A0c: bridge synthesizes "spawning" before claude is up, then
            // "thinking" once the subprocess is alive. Pure UX signal.
            const phase = String(parsed.phase || "");
            if (phase === "spawning" || phase === "thinking" || phase === "tool") {
              setStatusPhase(phase as "spawning" | "thinking" | "tool");
              if (phase === "spawning" && parsed.cwd) {
                const cwd = String(parsed.cwd);
                const last = cwd.split(/[\\/]/).filter(Boolean).pop() || cwd;
                setStatusDetail(last);
              } else {
                setStatusDetail("");
              }
            }
          }
          else if (event === "delta" && typeof parsed.text === "string") {
            setThinking(false);
            setStatusPhase(null);
            setMessages((m) => {
              const next = [...m];
              const last = next[next.length - 1];
              if (last && last.role === "assistant") {
                next[next.length - 1] = { ...last, content: last.content + parsed.text };
              }
              return next;
            });
          } else if (event === "cloud_tool_result") {
            // Cloud-only path — agent emitted a <cloud-tool> marker that
            // the route executed against the tenant's data. Surface result
            // inline so the operator sees what the agent looked up.
            setCloudResults((prev) => [
              ...prev,
              {
                uid: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                ok: !!parsed.ok,
                name: String(parsed.name || "?"),
                summary: parsed.summary,
                error: parsed.error,
                data: parsed.data,
              },
            ]);
          } else if (event === "action") {
            setActions((prev) => [
              ...prev,
              {
                ok: !!parsed.ok,
                type: String(parsed.type || "?"),
                summary: parsed.summary,
                error: parsed.error,
                uid: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
              },
            ]);
          } else if (event === "tool") {
            setThinking(true);
            setStatusPhase("tool");
            setStatusDetail(_toolLabel(parsed));
            const toolName = String(parsed.name || "tool");
            const toolUseId = String(parsed.tool_use_id || "");
            const isClaudePath = !!parsed.raw_name;
            if (isClaudePath) {
              // Claude Code subprocess path — unified pill list.
              const entryId = toolUseId || `${toolName}-${Date.now()}-${Math.random()}`;
              setToolCalls((prev) => [
                ...prev,
                {
                  id: entryId,
                  kind: toolName,
                  label: _toolLabel(parsed),
                  detail: _toolDetail(parsed),
                  createdAt: Date.now(),
                },
              ]);
            } else {
              // Legacy bridge path — split read/run lists (kept for
              // OASIS_CHAT_LEGACY=1 rollback support).
              if (toolName === "read_file") {
                setToolReads((prev) => [
                  ...prev,
                  {
                    path: String(parsed.path || ""),
                    body: typeof parsed.body === "string" ? parsed.body : undefined,
                  },
                ]);
              } else if (toolName === "run_script") {
                setToolRuns((prev) => [
                  ...prev,
                  {
                    script: String(parsed.script || ""),
                    args: Array.isArray(parsed.args) ? parsed.args.map(String) : [],
                    confirm: !!parsed.confirm,
                    output: typeof parsed.output === "string" ? parsed.output : undefined,
                  },
                ]);
              }
            }
          } else if (event === "tool_result") {
            const toolUseId = String(parsed.tool_use_id || "");
            const body =
              typeof parsed.body === "string"
                ? parsed.body
                : typeof parsed.output === "string"
                  ? parsed.output
                  : undefined;
            // Match by tool_use_id first (Claude Code), then by name+ordinal
            // for legacy path.
            if (toolUseId) {
              setToolCalls((prev) => {
                const next = [...prev];
                for (let i = next.length - 1; i >= 0; i--) {
                  if (next[i].id === toolUseId) {
                    next[i] = {
                      ...next[i],
                      output: body,
                      error: !!parsed.error,
                      elapsed_s: undefined,
                      completedAt: Date.now(),
                    };
                    break;
                  }
                }
                return next;
              });
            }
            if (parsed.name === "read_file") {
              setToolReads((prev) => {
                const next = [...prev];
                for (let i = next.length - 1; i >= 0; i--) {
                  if (next[i].path === String(parsed.path || "") && next[i].body === undefined) {
                    next[i] = { ...next[i], body };
                    break;
                  }
                }
                return next;
              });
            } else if (parsed.name === "run_script") {
              setToolRuns((prev) => {
                const next = [...prev];
                for (let i = next.length - 1; i >= 0; i--) {
                  if (next[i].script === String(parsed.script || "") && next[i].output === undefined) {
                    next[i] = { ...next[i], output: body, elapsed_s: undefined };
                    break;
                  }
                }
                return next;
              });
            }
          } else if (event === "tool_progress" && parsed.name === "run_script") {
            // Bridge ticks every 10s while a long script runs. Surface the
            // elapsed time on the matching pill so the operator knows it's
            // still working (a 90s ceo_dashboard otherwise feels broken).
            setToolRuns((prev) => {
              const next = [...prev];
              for (let i = next.length - 1; i >= 0; i--) {
                if (next[i].script === String(parsed.script || "") && next[i].output === undefined) {
                  next[i] = {
                    ...next[i],
                    elapsed_s: Number(parsed.elapsed_s) || 0,
                  };
                  break;
                }
              }
              return next;
            });
          } else if (event === "error") {
            // Surface the stderr detail when the bridge supplies one
            // (e.g., claude_exit_1 with the actual claude error message)
            // so the operator can see WHY the subprocess crashed instead
            // of just a cryptic exit code.
            const msg = String(parsed.message || "stream_error");
            const rawDetail = parsed.detail ? String(parsed.detail) : "";
            const detail = rawDetail.slice(0, 1500);
            setError(detail ? `${msg}\n\n${detail}` : msg);
            // Auto-clear sessionId on subprocess crashes so the next
            // Send doesn't pass --resume <stale-id> to claude. The user
            // gets a clean retry without having to click refresh.
            // claude_exit_*, claude_spawn_failed, and claude_stream_failed
            // all qualify.
            if (msg.startsWith("claude_") || msg.includes("session not found")) {
              setSessionId(null);
            }
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "request_failed");
      setMessages((m) => m.slice(0, -1));
    } finally {
      setStreaming(false);
      setThinking(false);
      setStatusPhase(null);
      setStatusDetail("");
      setStreamStartedAt(null);
      setElapsedTick(0);
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
    <div
      ref={chatContainerRef}
      className={`chat-container agent-${agent} flex flex-col h-[640px]`}
    >
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
              <span
                className="text-accent"
                title="Local bridge spawns the Claude Code CLI on your machine using your Claude subscription — your saved provider keys are not used in this mode."
              >
                <Cpu className="w-3 h-3 inline-block mr-1 -mt-0.5" />
                local bridge · Claude Code CLI · full repo access
              </span>
            ) : cfg ? (
              <span title={`Cloud mode — using your saved ${cfg.provider} key for ${cfg.model}.`}>
                {`${cfg.provider} · ${cfg.model} · your key`}
              </span>
            ) : isAdmin ? (
              <span title="Cloud mode, no per-agent key saved — falling back to the platform-default key (admin only).">
                admin · platform-default key
              </span>
            ) : configsLoaded ? (
              "not configured"
            ) : (
              "loading…"
            )}
          </div>
        </div>
        {usage && (
          <span
            className="text-[10px] font-mono text-fg-dim border border-bg-border bg-bg-elev rounded-full px-2 py-0.5 hidden sm:inline-flex items-center gap-1"
            title={`OpenRouter usage this period${usage.limit ? ` (limit $${usage.limit.toFixed(2)})` : ""}`}
          >
            ${usage.usage.toFixed(2)}
            {usage.limit !== null ? ` / $${usage.limit.toFixed(2)}` : ""}
          </span>
        )}
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
        <button
          type="button"
          onClick={toggleFullscreen}
          className="text-fg-dim hover:text-accent transition-colors p-1"
          title={isFullscreen ? "Exit fullscreen (Esc)" : "Open chat fullscreen"}
        >
          {isFullscreen ? (
            <Minimize2 className="w-4 h-4" />
          ) : (
            <Maximize2 className="w-4 h-4" />
          )}
        </button>
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
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-5 py-5 space-y-4 chat-scroll relative z-10"
      >
        {!messages.length && !error && (
          <EmptyTranscript
            ready={!!ready}
            agent={agent}
            configsLoaded={configsLoaded}
            isAdmin={!!isAdmin}
            onSuggestion={applySuggestion}
          />
        )}
        {messages.map((m, i) => {
          const isLastAssistant = i === messages.length - 1 && m.role === "assistant";
          // Show the tool timeline ABOVE the in-progress assistant bubble
          // so CC sees the agent working (read → bash → grep → …) BEFORE
          // the final text answer lands. Matches Claude Code's CLI rhythm.
          // Real toolCalls win; synthCalls fill the silence when the model
          // is just thinking (40-60s of cold-start latency before any real
          // tool fires).
          const showRealTools = isLastAssistant && toolCalls.length > 0;
          const showSynthTools = isLastAssistant && toolCalls.length === 0 && synthCalls.length > 0;
          return (
            <div key={i} className="contents">
              {showRealTools && (
                process.env.NEXT_PUBLIC_TOOL_TIMELINE === "false"
                  ? <ToolCallList entries={toolCalls} />
                  : <ToolTimelineList entries={toolCalls} />
              )}
              {showSynthTools && (
                <ToolTimelineList entries={synthCalls} />
              )}
              {(showRealTools || showSynthTools) && thinking && streaming && (
                <ThinkingIndicator
                  phase={statusPhase}
                  detail={statusDetail}
                  agent={agent}
                  elapsed={elapsedLabel}
                />
              )}
              <Bubble
                role={m.role}
                agent={agent}
                content={stripActionMarkers(m.content)}
                at={m.at}
                streaming={streaming && isLastAssistant}
              />
            </div>
          );
        })}
        {thinking && streaming && toolCalls.length === 0 && synthCalls.length === 0 && (
          <ThinkingIndicator
            phase={statusPhase}
            detail={statusDetail}
            agent={agent}
            elapsed={elapsedLabel}
          />
        )}
        {toolReads.length > 0 && (
          <ToolReadList
            entries={toolReads}
            expanded={expandedReads}
            onToggle={(i) => {
              setExpandedReads((prev) => {
                const next = new Set(prev);
                if (next.has(i)) next.delete(i);
                else next.add(i);
                return next;
              });
            }}
          />
        )}
        {toolRuns.length > 0 && (
          <ToolRunList
            entries={toolRuns}
            expanded={expandedRuns}
            onToggle={(i) => {
              setExpandedRuns((prev) => {
                const next = new Set(prev);
                if (next.has(i)) next.delete(i);
                else next.add(i);
                return next;
              });
            }}
          />
        )}
        {cloudResults.length > 0 && (
          <div className="ml-9 space-y-1.5 border-l border-bg-border pl-3 mt-1">
            {cloudResults.map((r) => (
              <div
                key={r.uid}
                className={`flex items-start gap-2 rounded-md border px-3 py-2 text-xs font-mono ${
                  r.ok
                    ? "border-accent/40 bg-accent/5 text-accent"
                    : "border-status-warm/40 bg-status-warm/10 text-status-warm"
                }`}
                title={r.ok ? "cloud tool ran successfully" : "cloud tool failed"}
              >
                <Database className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span className="font-bold uppercase tracking-wider text-[10px]">
                      {r.ok ? "looked up" : "lookup failed"}
                    </span>
                    <span className="text-fg-muted">{r.name}</span>
                  </div>
                  <div className="font-sans mt-0.5 text-fg break-words">
                    {r.summary || r.error || "(no summary)"}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
        {actions.length > 0 && (
          <div className="space-y-1.5">
            {actions.filter((a) => !a.dismissed).map((a) => {
              const verifyOn = process.env.NEXT_PUBLIC_VERIFY_ACTIONS !== "false";
              const needsAck = verifyOn && a.ok; // mutating + applied -> needs ack
              return (
                <div
                  key={a.uid}
                  className={`flex items-start gap-2 rounded-md border px-3 py-2 text-xs font-mono ${
                    a.ok
                      ? needsAck
                        ? "border-accent/40 bg-accent/10 text-accent"
                        : "border-status-engaged/40 bg-status-engaged/10 text-status-engaged"
                      : "border-status-warm/40 bg-status-warm/10 text-status-warm"
                  }`}
                >
                  <Check className={`w-3.5 h-3.5 mt-0.5 flex-shrink-0 ${a.ok ? "" : "hidden"}`} />
                  <AlertCircle className={`w-3.5 h-3.5 mt-0.5 flex-shrink-0 ${a.ok ? "hidden" : ""}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <span className="font-bold uppercase tracking-wider text-[10px]">
                        {a.ok ? (needsAck ? "applied — verify" : "applied") : "rejected"}
                      </span>
                      <span className="text-fg-muted">{a.type}</span>
                    </div>
                    <div className="font-sans mt-0.5 text-fg break-words">
                      {a.summary || a.error || "(no detail)"}
                    </div>
                  </div>
                  {needsAck && (
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <Link
                        href="/runs"
                        className="text-[10px] uppercase tracking-wider underline decoration-accent/40 hover:decoration-accent"
                        title="See full mutation history"
                      >
                        history
                      </Link>
                      <button
                        type="button"
                        onClick={() =>
                          setActions((prev) =>
                            prev.map((x) =>
                              x.uid === a.uid ? { ...x, dismissed: true } : x
                            )
                          )
                        }
                        className="px-2 py-0.5 rounded border border-accent/40 hover:bg-accent/20 text-[10px] uppercase tracking-wider"
                        title="Acknowledge — dismiss this verification pill"
                      >
                        got it
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-status-warm/40 bg-status-warm/10 p-3 text-sm text-status-warm">
            <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <div className="space-y-1 min-w-0 flex-1">
              {error.startsWith("provider_temporarily_unavailable") ? (
                <>
                  <div className="font-bold">Provider had a hiccup.</div>
                  <div className="text-xs text-fg-muted font-sans">
                    The chat retried 3 times and the upstream LLM is still unhappy. Usually clears in a minute. Try again, or switch model in <Link href="/settings#agents" className="text-accent underline">Settings</Link>.
                  </div>
                </>
              ) : (
                <div className="font-mono break-words whitespace-pre-wrap text-[11px] leading-relaxed">{error}</div>
              )}
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

      {awayFromBottom && (
        <button
          type="button"
          onClick={jumpToLatest}
          className="absolute right-6 bottom-24 z-20 rounded-full border border-accent/40 bg-bg-panel/90 backdrop-blur px-3 py-1.5 text-[11px] font-mono text-accent hover:bg-accent/10 transition-colors flex items-center gap-1 shadow-[0_4px_16px_-4px_rgba(0,212,255,0.4)]"
        >
          <ArrowDown className="w-3 h-3" /> jump to latest
        </button>
      )}

      {/* Composer */}
      <form
        data-chat-composer
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
  onSuggestion,
}: {
  ready: boolean;
  agent: string;
  configsLoaded: boolean;
  isAdmin: boolean;
  onSuggestion: (text: string) => void;
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
  const suggestions = _suggestionsFor(agent);
  return (
    <div className="space-y-4">
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
      <div>
        <div className="text-[10px] uppercase tracking-wider font-bold text-fg-muted mb-2">
          Try one of these
        </div>
        <div className="grid sm:grid-cols-2 gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onSuggestion(s)}
              className="text-left rounded-lg border border-bg-border bg-bg-elev/40 hover:border-accent/40 hover:bg-accent/5 transition-all px-3 py-2.5 text-xs text-fg leading-snug"
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Bubble({
  role,
  agent,
  content,
  at,
  streaming,
}: {
  role: Role;
  agent: string;
  content: string;
  at: number;
  streaming: boolean;
}) {
  const isUser = role === "user";
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    if (typeof navigator === "undefined" || !navigator.clipboard) return;
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className={`group flex items-start gap-2 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && <AgentAvatar agent={agent} />}
      <div className={`max-w-[88%] flex flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser ? "bubble-user" : `bubble-assistant ${streaming ? "streaming" : ""}`
          }`}
        >
          {content ? (
            <FormattedContent content={content} />
          ) : streaming ? (
            <div className="typing-dots"><span /><span /><span /></div>
          ) : null}
        </div>
        <div className="flex items-center gap-2 px-1 opacity-0 group-hover:opacity-100 transition-opacity text-[10px] text-fg-dim">
          <span className="font-mono">{_relTime(at)}</span>
          {!isUser && content && (
            <button
              type="button"
              onClick={handleCopy}
              className="hover:text-accent transition-colors inline-flex items-center gap-0.5"
              title="Copy reply"
            >
              {copied ? <Check className="w-3 h-3 text-status-engaged" /> : <Clipboard className="w-3 h-3" />}
              {copied ? "copied" : "copy"}
            </button>
          )}
        </div>
      </div>
      {isUser && <UserAvatar />}
    </div>
  );
}

function AgentAvatar({ agent }: { agent: string }) {
  const initial = agent.slice(0, 1).toUpperCase();
  const info = getAgentInfo(agent);
  return (
    <div
      className={`w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-black tracking-tight border bg-bg-elev/80 ${info.textClass}`}
      style={{ borderColor: "currentColor" }}
      title={agent.toUpperCase()}
    >
      {initial}
    </div>
  );
}

function UserAvatar() {
  return (
    <div className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-black tracking-tight border border-bg-border bg-bg-elev/80 text-fg-muted">
      You
    </div>
  );
}

function ToolReadList({
  entries,
  expanded,
  onToggle,
}: {
  entries: Array<{ path: string; body?: string }>;
  expanded: Set<number>;
  onToggle: (i: number) => void;
}) {
  return (
    <div className="space-y-1.5">
      {entries.map((p, i) => {
        const isOpen = expanded.has(i);
        const canExpand = !!p.body;
        return (
          <div key={i} className="text-[11px]">
            <button
              type="button"
              disabled={!canExpand}
              onClick={() => canExpand && onToggle(i)}
              className={`inline-flex items-center gap-1 font-mono px-2 py-0.5 rounded-full bg-accent/10 border border-accent/20 text-accent ${
                canExpand ? "hover:bg-accent/20 cursor-pointer" : "cursor-default"
              }`}
              title={canExpand ? "Click to expand file body" : "Agent read this file"}
            >
              {canExpand && <ChevronRight className={`w-3 h-3 transition-transform ${isOpen ? "rotate-90" : ""}`} />}
              read · {p.path}
            </button>
            {isOpen && p.body && (
              <pre className="mt-1.5 max-h-64 overflow-auto rounded-md border border-accent/20 bg-bg-deep/60 p-2 text-[10px] font-mono text-fg-muted whitespace-pre-wrap">
                <code>{p.body}</code>
              </pre>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ToolRunList({
  entries,
  expanded,
  onToggle,
}: {
  entries: Array<{
    script: string;
    args: string[];
    confirm: boolean;
    output?: string;
    elapsed_s?: number;
  }>;
  expanded: Set<number>;
  onToggle: (i: number) => void;
}) {
  return (
    <div className="space-y-1.5">
      {entries.map((r, i) => {
        const isOpen = expanded.has(i);
        const canExpand = !!r.output;
        const isRunning = !r.output && (r.elapsed_s ?? 0) > 0;
        const tone = isRunning
          ? "bg-accent/10 border-accent/30 text-accent animate-pulse-slow"
          : r.confirm
            ? "bg-status-engaged/15 border-status-engaged/30 text-status-engaged"
            : "bg-status-warm/10 border-status-warm/30 text-status-warm";
        return (
          <div key={i} className="text-[11px]">
            <button
              type="button"
              disabled={!canExpand}
              onClick={() => canExpand && onToggle(i)}
              className={`inline-flex items-center gap-1 font-mono px-2 py-0.5 rounded-full border ${tone} ${
                canExpand ? "hover:opacity-90 cursor-pointer" : "cursor-default"
              }`}
              title={
                isRunning
                  ? `Script still running… (${r.elapsed_s}s elapsed)`
                  : r.confirm
                    ? "Agent ran this allowlisted script"
                    : "Agent attempted a mutating script without confirm — bounced for safety"
              }
            >
              {canExpand && <ChevronRight className={`w-3 h-3 transition-transform ${isOpen ? "rotate-90" : ""}`} />}
              {isRunning ? "running" : r.confirm ? "ran" : "blocked"} · {r.script}
              {r.args.length > 0 ? ` ${r.args.slice(0, 4).join(" ")}${r.args.length > 4 ? "…" : ""}` : ""}
              {isRunning ? ` · ${r.elapsed_s}s` : ""}
            </button>
            {isOpen && r.output && (
              <pre className="mt-1.5 max-h-64 overflow-auto rounded-md border border-bg-border bg-bg-deep/60 p-2 text-[10px] font-mono text-fg-muted whitespace-pre-wrap">
                <code>{r.output}</code>
              </pre>
            )}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Unified pill list for the Claude Code subprocess path. Each entry is
 * one tool invocation (Read, Edit, Write, Bash, Glob, Grep, WebFetch,
 * MCP server call, etc). Output streams in via tool_result correlated
 * by tool_use_id. Click to expand the body inline.
 */
function ToolCallList({
  entries,
}: {
  entries: Array<{
    id: string;
    kind: string;
    label: string;
    detail?: string;
    output?: string;
    error?: boolean;
  }>;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  const tone = (e: { error?: boolean; output?: string }) =>
    e.error
      ? "bg-status-warm/10 border-status-warm/30 text-status-warm"
      : e.output
        ? "bg-accent/10 border-accent/30 text-accent"
        : "bg-bg-elev/40 border-bg-border text-fg-muted animate-pulse-slow";
  return (
    <div className="space-y-1.5">
      {entries.map((e) => {
        const isOpen = expanded.has(e.id);
        const canExpand = !!e.output;
        return (
          <div key={e.id} className="text-[11px]">
            <button
              type="button"
              disabled={!canExpand}
              onClick={() => canExpand && toggle(e.id)}
              className={`inline-flex items-center gap-1 font-mono px-2 py-0.5 rounded-full border ${tone(e)} ${
                canExpand ? "hover:opacity-90 cursor-pointer" : "cursor-default"
              }`}
              title={e.error ? "tool returned an error" : canExpand ? "click to expand output" : "running…"}
            >
              {canExpand && (
                <ChevronRight
                  className={`w-3 h-3 transition-transform ${isOpen ? "rotate-90" : ""}`}
                />
              )}
              <span className="font-bold">{e.label}</span>
              {e.detail && (
                <span className="text-fg-dim truncate max-w-[28ch]">· {e.detail}</span>
              )}
            </button>
            {isOpen && e.output && (
              <pre className="mt-1.5 max-h-64 overflow-auto rounded-md border border-bg-border bg-bg-deep/60 p-2 text-[10px] font-mono text-fg-muted whitespace-pre-wrap">
                <code>{e.output}</code>
              </pre>
            )}
          </div>
        );
      })}
    </div>
  );
}


/**
 * Pulsing dots + status copy with elapsed time. Used both above the in-
 * progress assistant bubble (when tools are streaming) and below the user
 * message (before the first tool fires). Single component to keep the
 * status copy in one place.
 */
/**
 * Narration ticker — when no real tool events are firing (e.g., the
 * cloud /api/chat path is just thinking, or the bridge is between
 * tool calls), the UI used to go silent for 30+ seconds. This cycles
 * through plausible activity descriptions based on elapsed seconds so
 * CC sees motion and isn't left wondering if the chat hung.
 *
 * The phases are intentionally generic — they describe what an LLM is
 * actually doing under the hood (loading context, reasoning, drafting)
 * rather than promising specific tool calls that may not happen.
 */
const NARRATION_PHASES: Array<{ at: number; label: string }> = [
  { at: 0, label: "thinking" },
  { at: 6, label: "loading context" },
  { at: 12, label: "considering tools" },
  { at: 20, label: "reasoning through this" },
  { at: 30, label: "drafting response" },
  { at: 45, label: "almost there" },
  { at: 60, label: "still working — long task" },
];

function _narrationFor(elapsedSec: number): string {
  let label = NARRATION_PHASES[0].label;
  for (const p of NARRATION_PHASES) {
    if (elapsedSec >= p.at) label = p.label;
  }
  return label;
}

function ThinkingIndicator({
  phase,
  detail,
  agent,
  elapsed,
}: {
  phase: "spawning" | "thinking" | "tool" | null;
  detail: string;
  agent: string;
  elapsed: string;
}) {
  // Convert "M:SS" elapsed back to seconds for narration phase lookup.
  const elapsedSec = (() => {
    const m = elapsed.match(/^(\d+):(\d+)$/);
    if (!m) return 0;
    return Number(m[1]) * 60 + Number(m[2]);
  })();
  const narration = _narrationFor(elapsedSec);
  const label =
    phase === "spawning"
      ? `starting ${agent.toLowerCase()}${detail ? ` in ${detail}` : ""}…`
      : phase === "tool"
        ? `running ${detail || "tool"}…`
        : `${narration}…`;
  return (
    <div className="flex items-center gap-2 text-fg-dim text-xs ml-9">
      <span className="typing-dots"><span /><span /><span /></span>
      <span>
        {label}
        {elapsed && (
          <span className="ml-1.5 font-mono text-fg-dim/70">({elapsed})</span>
        )}
      </span>
    </div>
  );
}

function _relTime(at: number): string {
  if (!at) return "";
  const diff = Date.now() - at;
  if (diff < 10_000) return "just now";
  if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  return `${Math.floor(diff / 3_600_000)}h ago`;
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
    // Cloud-tool markers are also stripped from display — results render
    // as separate inline pills (cloud_tool_result SSE events).
    .replace(/<cloud-tool\s+name=["'][a-z0-9_]+["']\s*>[\s\S]*?<\/cloud-tool>/gi, "")
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
