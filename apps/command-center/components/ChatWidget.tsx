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
import { MessageDownloadMenu } from "@/components/chat/MessageDownloadMenu";
import { mdToHtml } from "@/lib/markdown";
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

// Legacy localStorage keys from the FIRST Auto/Cloud/Desktop picker (removed
// 2026-05-13). The one-shot cleanup effect below clears them. Nothing else
// reads them.
const ACCESS_MODE_STORAGE_KEY = "oasis.chat.accessMode";
const LEGACY_RUNTIME_MODE_STORAGE_KEY = "oasis.chat.runtimeMode";

/**
 * Chat-mode picker — Phase 3 of giggly-reef, 2026-05-15.
 *
 * Four real combinations of (who-owns-the-LLM, who-owns-the-tools):
 *
 *   "auto"               — bridge if reachable, else cloud_bridge_tools.
 *                          The fall-through default.
 *   "cli"                — pin to the local Claude Code bridge. Operator's
 *                          Claude.ai Pro subscription owns the LLM AND the
 *                          tools. Cheapest path; errors loud if the bridge
 *                          isn't running.
 *   "cloud_only"         — /api/chat with the operator's API key. ONLY the
 *                          11 cloud tools (records, http, integrations). No
 *                          bridge tools even when the bridge is online —
 *                          some operators prefer this when they don't
 *                          trust an LLM with bash/edit_file on real prod
 *                          machines.
 *   "cloud_bridge_tools" — /api/chat with the operator's API key for the
 *                          LLM, AND the bridge for tool execution. Browser
 *                          proxies tool_use to localhost:9100/exec-tool,
 *                          posts the result to /api/chat/resume. The best
 *                          of both worlds — paid LLM, free local tools —
 *                          and what auto upgrades to when the bridge is
 *                          paired.
 *
 * The mode survives reloads via localStorage so the operator's choice sticks.
 * The previous union ("auto" | "bridge" | "cloud") used the v2 key and has
 * no notion of "cloud only without bridge tools"; the migration below
 * translates v2 → v3 once, transparently. CC's framing on 2026-05-15:
 * "It's literally the same as the Telegram bridge. The API key should be
 * connected to my running server just like the Telegram bridge is."
 */
type ChatMode = "auto" | "cli" | "cloud_only" | "cloud_bridge_tools";
const CHAT_MODE_STORAGE_KEY = "oasis.chat.mode.v3";
const LEGACY_CHAT_MODE_STORAGE_KEY = "oasis.chat.mode.v2";
const isChatMode = (s: unknown): s is ChatMode =>
  s === "auto" || s === "cli" || s === "cloud_only" || s === "cloud_bridge_tools";

/**
 * One-shot migration from the v2 vocabulary to the v3 vocabulary.
 *
 *   bridge → cli                 (bridge owned LLM + tools — that's CLI mode)
 *   cloud  → cloud_bridge_tools  (the prior "cloud" path automatically used
 *                                 bridge tools when the bridge was online;
 *                                 the new name makes that opt-in explicit
 *                                 and adds the cloud_only escape hatch
 *                                 alongside it)
 *   auto   → auto                (semantics unchanged)
 *
 * Returns the migrated ChatMode if a v2 value was present and translated,
 * or null otherwise. Caller writes it to v3 and deletes v2 on success.
 */
function migrateLegacyChatMode(): ChatMode | null {
  try {
    const legacy = localStorage.getItem(LEGACY_CHAT_MODE_STORAGE_KEY);
    if (!legacy) return null;
    let mapped: ChatMode;
    if (legacy === "bridge") mapped = "cli";
    else if (legacy === "cloud") mapped = "cloud_bridge_tools";
    else if (legacy === "auto") mapped = "auto";
    else return null;
    localStorage.setItem(CHAT_MODE_STORAGE_KEY, mapped);
    localStorage.removeItem(LEGACY_CHAT_MODE_STORAGE_KEY);
    return mapped;
  } catch {
    return null;
  }
}

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
  solara: [
    "What funding leads need action today?",
    "Which renewals should we chase first?",
    "Pipeline this week — who's stuck?",
    "Which deals need lender assignment?",
  ],
  helios: [
    "Draft a first-touch SMS for a freshly qualified lead",
    "Revival sequence for leads that ghosted after the application step",
    "Close-the-loop SMS for an offer that just expired",
    "What's the best follow-up cadence for this stage?",
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

/**
 * Pretty-prints a tool's input object as a single-line detail string. Used by
 * the cloud_tool_call event handler (the runner gives us the model's input
 * blob; we want to show "list_records: entity=lead, limit=10" not the full
 * JSON in the chip). Falls back to a JSON.stringify slice if no meaningful
 * keys are present.
 */
function truncateJson(obj: Record<string, unknown>, maxLen = 80): string {
  try {
    const parts: string[] = [];
    for (const [k, v] of Object.entries(obj)) {
      if (v === null || v === undefined) continue;
      if (typeof v === "string") {
        parts.push(`${k}="${v.length > 24 ? v.slice(0, 24) + "…" : v}"`);
      } else if (typeof v === "number" || typeof v === "boolean") {
        parts.push(`${k}=${v}`);
      } else {
        // object/array — just signal its shape so the chip stays one line
        parts.push(`${k}=${Array.isArray(v) ? "[…]" : "{…}"}`);
      }
      if (parts.join(", ").length > maxLen) break;
    }
    const out = parts.join(", ");
    return out.length > maxLen ? out.slice(0, maxLen - 1) + "…" : out;
  } catch {
    return "";
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
  welcomeMessages?: Partial<Record<string, string>>;
};

function seedMessagesForAgent(
  agent: string,
  welcomeMessages?: Partial<Record<string, string>>
): Msg[] {
  const content = welcomeMessages?.[agent]?.trim();
  if (!content) return [];
  return [{ role: "assistant", content, at: Date.now() }];
}

export default function ChatWidget({ agentKeys, defaultAgent, isAdmin, welcomeMessages }: Props) {
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
  const [messages, setMessages] = useState<Msg[]>(() => seedMessagesForAgent(initialAgent, welcomeMessages));
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  // Tab-stable identifier for the warm-process pool. Minted ONCE per
  // ChatWidget mount; persists across agent switches and turns. The
  // bridge keys its warm pool by `agent:tab_id` so even turn 1 (before
  // claude has minted a session_id) lands in the pool. See
  // bravo_cli/warm_claude_pool.py for the architecture.
  const [tabId] = useState(() =>
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `tab-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  );
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
  // Chat-mode picker — see the type docs at the top of this file. SSR-safe
  // initializer (always returns "auto" on the server, then localStorage
  // hydration runs in the mount effect below).
  const [chatMode, setChatModeState] = useState<ChatMode>("auto");
  // Tracks which routing mode the most recent FAILED message used. Powers
  // the "Retry on the other mode" affordance on the error banner. Null
  // while everything is healthy or after a successful turn.
  // Tracks which transport bucket failed on the previous turn so the
  // Retry button can pick the most-likely-working alternate. Collapsed
  // to two buckets — cli-vs-cloud — because the API surface for the
  // retry is the same regardless of which cloud variant failed.
  const [lastFailedMode, setLastFailedMode] = useState<"cli" | "cloud" | null>(null);
  function setChatMode(next: ChatMode) {
    setChatModeState(next);
    if (typeof window !== "undefined") {
      try {
        window.localStorage.setItem(CHAT_MODE_STORAGE_KEY, next);
      } catch {
        // localStorage quota / privacy mode — fine, mode is in-memory.
      }
    }
  }
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
  const [statusPhase, setStatusPhase] = useState<"spawning" | "thinking" | "tool" | "warm_resume" | null>(null);
  const [statusDetail, setStatusDetail] = useState<string>("");
  const [streamStartedAt, setStreamStartedAt] = useState<number | null>(null);
  const [elapsedTick, setElapsedTick] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const activeWelcomeMessage = welcomeMessages?.[agent]?.trim() || "";

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
      .then(async (r) => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok || !j.ok) {
          // Log so a stuck "not configured" state in the chat composer is
          // searchable in Vercel logs / browser console. The composer still
          // renders — just with whatever configs were last hydrated (none on
          // first mount) — so the operator can retry the page.
          console.error("[chat_widget.agent_config]", j?.error || `status ${r.status}`);
          return;
        }
        setConfigs(j.configs as AgentConfig[]);
      })
      .catch((err) => {
        console.error("[chat_widget.agent_config]", err);
      })
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

  // Clean up legacy localStorage keys from the removed Auto/Cloud/Desktop
  // picker. One-shot on mount — the keys are no longer written to or read.
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(ACCESS_MODE_STORAGE_KEY);
    window.localStorage.removeItem(LEGACY_RUNTIME_MODE_STORAGE_KEY);
  }, []);

  // Hydrate chat-mode picker from localStorage on mount. Initial render is
  // always "auto" (matches SSR); this effect upgrades to the persisted value.
  // Phase 3 migration: if the operator's machine still has the v2 vocabulary
  // ("bridge" / "cloud"), translate it into v3 once and drop the legacy
  // entry. Subsequent reads always come from v3.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const stored = window.localStorage.getItem(CHAT_MODE_STORAGE_KEY);
      if (isChatMode(stored)) {
        setChatModeState(stored);
        return;
      }
      const migrated = migrateLegacyChatMode();
      if (migrated) setChatModeState(migrated);
    } catch {
      // Privacy mode / disabled storage — leave default "auto".
    }
  }, []);

  // Probe the local bridge on mount + every 30s. When the operator runs
  // `pm2 restart claude-bridge`, this flips true and desktop-enabled runtimes can
  // target their machine instead of /api/chat.
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

  // Pre-warm the bridge's claude process for the active agent as soon
  // as we know the bridge is online. The operator's first turn skips
  // cold-start (5-30s) entirely — claude is already booted, MCP servers
  // already loaded, brain files already parsed by the time they hit
  // Send. Re-fires on:
  //   - agent switch — each agent gets its own warm process
  //   - reset (🔄)   — bumping `prewarmEpoch` re-triggers the effect
  // Fire-and-forget; if the bridge is offline or pre-warm fails the
  // chat falls back to cold-spawn naturally.
  const [prewarmEpoch, setPrewarmEpoch] = useState(0);
  useEffect(() => {
    if (bridgeOnline !== true) return;
    void fetch(`${BRIDGE_CHAT_BASE}/prewarm`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ agent, tab_id: tabId }),
    }).catch(() => null);
  }, [bridgeOnline, agent, tabId, prewarmEpoch]);

  useEffect(() => {
    if (awayFromBottom) return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streaming, awayFromBottom]);

  useEffect(() => {
    setMessages(seedMessagesForAgent(agent, welcomeMessages));
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
    // Conversation-boundary reset — drop the "last failed mode" tracker
    // so the Retry button doesn't carry over from a previous chat or a
    // previous agent. The button hides anyway when error=null, but
    // leaving the state populated is a foot-gun for any future code
    // path that surfaces the value.
    setLastFailedMode(null);
  }, [agent, activeWelcomeMessage, welcomeMessages]);

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
  const cloudProviderReachable = cfg?.provider !== "ollama";
  const cloudReady = configsLoaded && (hasOwnKey || isAdmin) && cloudProviderReachable;
  const bridgeReady = bridgeOnline === true;
  // Routing self-selects now: desktop bridge when paired + online, else the
  // per-agent API key. The Auto/Cloud/Desktop picker is gone — see the
  // header render block + commit 150a124.
  const desktopBridgeActive = bridgeReady;
  const ready = bridgeReady || cloudReady;
  const providerStatus = (() => {
    if (desktopBridgeActive && cfg?.provider === "ollama") {
      return `Provider: ${cfg.provider} · ${cfg.model} · local desktop`;
    }
    if (desktopBridgeActive) return "Provider: Claude Code subscription (desktop bridge)";
    if (cfg?.provider === "ollama") return "Provider: local model (Desktop required)";
    if (cfg) return `Provider: ${cfg.provider} · ${cfg.model} · saved key`;
    if (isAdmin) return "Provider: OASIS platform default";
    return configsLoaded ? "Provider: not connected" : "Provider: loading...";
  })();
  // Resolve the actual route the next /send will take, given the picker.
  // The 4-mode union collapses into 3 "where does the work happen" buckets:
  //   - cli                : bridge owns LLM + tools (subscription billing)
  //   - cloud_only         : cloud LLM, ONLY the 11 cloud tools, no bridge
  //   - cloud_bridge_tools : cloud LLM (API key), bridge for tool execution
  // "auto" picks cli when the bridge is ready, otherwise cloud_bridge_tools
  // (which degrades gracefully to cloud-only when the bridge isn't there).
  const effectiveMode: "cli" | "cloud_only" | "cloud_bridge_tools" =
    chatMode === "cli"
      ? "cli"
      : chatMode === "cloud_only"
        ? "cloud_only"
        : chatMode === "cloud_bridge_tools"
          ? "cloud_bridge_tools"
          : bridgeReady
            ? "cli"
            : "cloud_bridge_tools";
  const accessStatus =
    effectiveMode === "cli"
      ? "Access: this desktop · local tools + files"
      : effectiveMode === "cloud_only"
        ? "Access: cloud workspace · cloud tools only"
        : bridgeReady
          ? "Access: cloud workspace (Anthropic API) · local tool execution (bridge)"
          : "Access: cloud workspace · tool_use loop";
  const accessTitle =
    chatMode === "auto"
      ? "Auto: bridge if paired + online, otherwise API key with bridge tools when available."
      : chatMode === "cli"
        ? "CLI: pinned to the local Claude Code bridge. Uses your Claude subscription, full repo + every Claude Code tool. Errors loud if the bridge isn't running."
        : chatMode === "cloud_only"
          ? "Cloud-only: pinned to /api/chat with your API key. ONLY the 11 cloud tools (records, http, integrations) — no bridge tools even if it's online. Pick this when you don't want the LLM running bash / edit_file on your machine."
          : "API + local tools: LLM on your Anthropic API key, tools executed by the bridge (read_file, write_file, bash, send_email, send_sms). Best of both worlds — paid LLM, free local tools.";
  const activeStatus = `${providerStatus} · ${accessStatus}`;
  const composerPlaceholder = !ready
    ? cfg?.provider === "ollama"
      ? "Install the desktop bridge to use local Ollama models"
      : "Configure this agent's provider + API key in Settings → Agents"
    : `Message ${getAgentInfo(agent).label.toUpperCase()}…  (Shift+Enter for newline)`;

  function reset() {
    // Best-effort: tell the bridge to kill the warm claude subprocess
    // for the session we're abandoning. Without this, the orphaned
    // process pins ~50-200MB of RAM until the 15-min idle reaper
    // catches up. Fire-and-forget; bridge offline / 404 is fine since
    // the reaper is the safety net.
    if (bridgeOnline === true) {
      void fetch(`${BRIDGE_CHAT_BASE}/chat-reset`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        // tab_id is the canonical pool key; session_id sent for legacy
        // fallback path on older bridge builds.
        body: JSON.stringify({ agent, tab_id: tabId, session_id: sessionId }),
      }).catch(() => null);
      // Bump the prewarm epoch so the prewarm effect re-fires and
      // spawns a fresh warm process for the next chat. Without this,
      // the first message after reset would cold-spawn (~5-30s).
      setPrewarmEpoch((e) => e + 1);
    }
    setMessages(seedMessagesForAgent(agent, welcomeMessages));
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
    // Conversation-boundary reset — drop the "last failed mode" tracker
    // so the Retry button doesn't carry over from a previous chat or a
    // previous agent. The button hides anyway when error=null, but
    // leaving the state populated is a foot-gun for any future code
    // path that surfaces the value.
    setLastFailedMode(null);
  }

  function applySuggestion(text: string) {
    setInput(text);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    return submitText(text);
  }

  /**
   * Internal: send a user message with full routing logic. send() is the
   * thin entry point from the composer; submitText also powers the
   * "Retry on the other mode" button below the error banner — that retry
   * passes a modeOverride so we route to the alternate path WITHOUT
   * having to wait for setChatMode to flush before reading state.
   */
  async function submitText(text: string, modeOverride?: ChatMode) {
    if (!text || streaming) return;
    setError(null);
    const now = Date.now();
    const newMessages: Msg[] = [...messages, { role: "user", content: text, at: now }];
    setMessages(newMessages);
    setMessages((m) => [...m, { role: "assistant", content: "", at: Date.now() }]);
    setStreaming(true);
    setThinking(true);
    setStreamStartedAt(Date.now());
    // Resolve routing intent — honors the chat-mode picker, with an explicit
    // modeOverride taking precedence (used by the "Retry on the other mode"
    // button below the error banner so the retry routes to the OTHER path
    // without waiting for a setChatMode flush to land in React state).
    const activeMode: ChatMode = modeOverride ?? chatMode;
    // Phase 3 routing — the 4-mode union collapses into "bridge-pinned" vs
    // "cloud path." Both cloud_only and cloud_bridge_tools go through
    // /api/chat; they differ only in whether bridge tools join the palette
    // (resolved server-side via tool_routing below).
    const wantsBridge =
      activeMode === "cli" ||
      (activeMode === "auto" && bridgeOnline === true);
    if (activeMode === "cli" && bridgeOnline !== true) {
      // Pinned to bridge but bridge isn't online — fail loud rather than
      // silently falling through to the API-key path. The operator chose
      // CLI mode for a reason.
      setError(
        "Pinned to CLI (local bridge), but the bridge isn't reachable. Run `pm2 restart claude-bridge` on this machine, or switch the mode to API key."
      );
      setStreaming(false);
      setMessages((m) => m.slice(0, -1));
      return;
    }
    setStatusPhase(wantsBridge ? "spawning" : "thinking");
    setStatusDetail("");

    try {
      // Routing now respects the chat-mode picker (chatMode):
      //   - "bridge" or ("auto" + bridgeOnline)
      //         → bridge endpoints (Claude Code subprocess or local Ollama)
      //   - "cloud" or ("auto" + bridge offline)
      //         → /api/chat (cloud relay with operator's API key + native
      //           tool_use loop on Anthropic provider)
      const isOllama = cfg?.provider === "ollama";
      const useBridge = wantsBridge;
      const useLocalChat = useBridge && isOllama;
      const url = useLocalChat
        ? `${BRIDGE_CHAT_BASE}/local-chat`
        : useBridge
          ? `${BRIDGE_CHAT_BASE}/chat`
          : "/api/chat";
      const body = useLocalChat
        ? {
            // Bridge `/local-chat` payload: model + messages. The bridge
            // resolves base_url from its own .env.agents (OLLAMA_BASE_URL
            // / LM_STUDIO_BASE_URL) since the operator's saved URL is
            // encrypted in Supabase and the dashboard never has it
            // unencrypted on the client side. System prompt is built
            // by the bridge from agent_roots like the Claude Code path.
            model: cfg?.model || "llama3.3",
            messages: newMessages,
          }
        : useBridge
          ? {
              agent,
              messages: newMessages,
              session_id: sessionId,
              tab_id: tabId,  // warm pool key — stable across the widget's lifetime
            }
          : {
              agent_key: agent,
              session_id: sessionId,
              messages: newMessages,
              // Hint to /api/chat which cloud-tool surface to use. "tools"
              // gives the native Anthropic tool_use loop; route will fall
              // back to "markers" automatically for non-Anthropic providers.
              cloud_tools: "tools" as const,
              // Phase 3 tool_routing — "cloud_only" force-disables bridge
              // tools even when the bridge is online (operator opt-out for
              // the "I don't want this LLM running bash on my machine"
              // case). "bridge_proxy" is the default and what auto +
              // cloud_bridge_tools both want; server falls back to
              // cloud-only automatically when the bridge isn't reachable.
              tool_routing:
                activeMode === "cloud_only"
                  ? ("cloud_only" as const)
                  : ("bridge_proxy" as const),
            };
      const res = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok || !res.body) {
        const errBody = await safeReadJson(res);
        setError(errBody?.error || `http_${res.status}`);
        setLastFailedMode(useBridge ? "cli" : "cloud");
        setStreaming(false);
        setMessages((m) => m.slice(0, -1));
        return;
      }
      // Flipped to true the first time we get any assistant text. Used after
      // the loop to detect silent-stream failures without having to read
      // React state from inside another setter.
      let receivedAnyContent = false;
      // Populated when the cloud tool_use loop pauses on a deferred tool
      // (defer:true on a tool definition — see lib/cloud-tool-runner.ts).
      // After the SSE stream closes, we proxy this to localhost:9100 via
      // the bridge's /exec-tool, then POST the result to /api/chat/resume
      // and consume the resumed SSE stream. Repeat for any further
      // deferred tools until the iteration finishes or hits its cap.
      type PendingTool = {
        tool_use_id: string;
        name: string;
        input: Record<string, unknown>;
        resume_state: unknown;
        /** HMAC signature minted by /api/chat (Phase H). The browser must
         *  forward it verbatim on the resume POST so the route can
         *  verify the resume_state hasn't been tampered with. */
        resume_signature: string;
      };
      let pendingToolUse: PendingTool | null = null;

      /**
       * Consume an SSE Response body. Side-effects React state (messages,
       * tool calls, status) through the surrounding closures. Returns when
       * the stream closes — either because the turn completed cleanly OR
       * because tool_use_pending fired (the model wants a deferred tool
       * executed locally). The caller checks pendingToolUse to decide
       * whether to resume.
       */
      const consumeStream = async (stream: Response): Promise<void> => {
        if (!stream.body) return;
        const reader = stream.body.getReader();
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
            // Phases the bridge emits:
            //   "spawning"    — before claude subprocess is up (cold path)
            //   "thinking"    — subprocess alive, model reasoning
            //   "tool"        — currently running a tool
            //   "warm_resume" — warm-pool path: persistent process took
            //                   the turn; cold-start was skipped entirely
            const phase = String(parsed.phase || "");
            if (phase === "spawning" || phase === "thinking" || phase === "tool" || phase === "warm_resume") {
              setStatusPhase(phase as "spawning" | "thinking" | "tool" | "warm_resume");
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
            if (parsed.text.length > 0) receivedAnyContent = true;
            setMessages((m) => {
              const next = [...m];
              const last = next[next.length - 1];
              if (last && last.role === "assistant") {
                next[next.length - 1] = { ...last, content: last.content + parsed.text };
              }
              return next;
            });
          } else if (event === "cloud_tool_call") {
            // Native tool_use loop — model called a tool MID-stream, runner
            // is executing now. Push onto the unified toolCalls list (same
            // surface the CLI/bridge path uses) so CLI mode and API mode
            // render tool activity identically. The matching cloud_tool_result
            // event arrives a moment later and patches `output`.
            const toolName = String(parsed.name || "tool");
            const entryId = `cloud-${toolName}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
            setThinking(true);
            setStatusPhase("tool");
            setStatusDetail(toolName);
            // Stash the id on the inputs object so the matching result can
            // find this entry via the most-recent-pending-by-name lookup
            // below (since the SSE protocol doesn't echo our generated id
            // back from the route).
            setToolCalls((prev) => [
              ...prev,
              {
                id: entryId,
                kind: toolName,
                label: toolName,
                detail:
                  parsed.input && typeof parsed.input === "object"
                    ? truncateJson(parsed.input)
                    : undefined,
                createdAt: Date.now(),
              },
            ]);
          } else if (event === "cloud_tool_result") {
            // Cloud-mode tool result — either from the native tool_use loop
            // (cloud-tool-runner.ts, mid-stream) or the legacy text marker
            // path (cloud-tools.ts, post-stream). Two surfaces:
            //   1. Update the matching toolCalls entry so chrome matches CLI
            //   2. (Legacy compat) also push a cloudResults pill — the
            //      below-transcript renderer still consumes them for the
            //      markers path. Harmless duplication; cloudResults is the
            //      summary line, toolCalls is the expandable detail row.
            const toolName = String(parsed.name || "?");
            setToolCalls((prev) => {
              const next = [...prev];
              // Find the most recent matching pending entry from this kind.
              for (let i = next.length - 1; i >= 0; i--) {
                if (next[i].kind === toolName && next[i].output === undefined && !next[i].completedAt) {
                  next[i] = {
                    ...next[i],
                    output: parsed.summary || undefined,
                    error: !parsed.ok,
                    completedAt: Date.now(),
                  };
                  break;
                }
              }
              return next;
            });
            setCloudResults((prev) => [
              ...prev,
              {
                uid: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                ok: !!parsed.ok,
                name: toolName,
                summary: parsed.summary,
                error: parsed.error,
                data: parsed.data,
              },
            ]);
          } else if (event === "tool_use_pending") {
            // Phase 2: deferred tool. The cloud runner paused because the
            // model called a tool that needs the operator's local bridge
            // (send_email, read_file, bash, etc.). Stash the pending data
            // and exit the read loop — the outer resume loop below will
            // POST the call to localhost:9100/exec-tool and then POST the
            // result to /api/chat/resume to continue the model's iteration.
            pendingToolUse = {
              tool_use_id: String(parsed.tool_use_id || ""),
              name: String(parsed.name || "tool"),
              input: (parsed.input && typeof parsed.input === "object") ? parsed.input : {},
              resume_state: parsed.resume_state,
              // Phase H signature — opaque to the browser, must echo
              // verbatim on the resume POST so the server can verify
              // the resume_state hasn't been tampered with.
              resume_signature: String(parsed.resume_signature || ""),
            };
            // Show "calling NAME..." chip in the toolCalls strip so the
            // operator sees activity while the bridge runs the tool.
            const entryId = `bridge-${pendingToolUse.name}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
            setThinking(true);
            setStatusPhase("tool");
            setStatusDetail(pendingToolUse.name);
            setToolCalls((prev) => [
              ...prev,
              {
                id: entryId,
                kind: pendingToolUse!.name,
                label: pendingToolUse!.name,
                detail: truncateJson(pendingToolUse!.input),
                createdAt: Date.now(),
              },
            ]);
            // No early return — let the SSE stream finish naturally.
            // The outer resume loop checks pendingToolUse after the
            // stream closes.
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
      };
      // ─── End of consumeStream definition ──────────────────────────────

      // Drive the initial SSE stream.
      await consumeStream(res);

      // Phase 2 resume loop: if the cloud runner paused on a deferred
      // tool, proxy it to the local bridge and POST the result back to
      // /api/chat/resume. The resumed stream may pause AGAIN on another
      // deferred tool; loop until the model finishes or the resume cap
      // is hit (mirrors MAX_TOOL_ITERATIONS server-side).
      let resumeCount = 0;
      while (pendingToolUse && resumeCount < 8) {
        // Explicit cast — TS can't narrow a closure-captured `let` via the
        // while condition (the consumeStream arrow function mutates it,
        // so flow analysis treats every read as potentially the original
        // null). Asserting against the explicit type alias is cleaner
        // than NonNullable<typeof ...> for the same reason.
        const pending: PendingTool = pendingToolUse as PendingTool;
        pendingToolUse = null;
        resumeCount += 1;

        // 1) Hit the local bridge to execute the tool. Bridge must be
        //    online for this to work — if it's not, fall through with
        //    is_error so the model sees the failure and can adapt.
        let toolOutput = "";
        let toolIsError = false;
        try {
          const bridgeRes = await fetch(`${BRIDGE_CHAT_BASE}/exec-tool`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              tool_name: pending.name,
              input: pending.input,
            }),
          });
          const bridgePayload = await bridgeRes.json().catch(() => null);
          if (!bridgeRes.ok || !bridgePayload?.ok) {
            toolOutput = `bridge_exec_failed:${bridgeRes.status}:${bridgePayload?.error || "unknown"}`;
            toolIsError = true;
          } else {
            toolOutput = String(bridgePayload.output ?? "");
            toolIsError = Boolean(bridgePayload.is_error);
          }
        } catch (bridgeErr) {
          toolOutput = `bridge_unreachable:${bridgeErr instanceof Error ? bridgeErr.message : "fetch_failed"}`;
          toolIsError = true;
        }

        // Patch the matching toolCalls pill with the result (mirrors the
        // cloud_tool_result event handler above).
        setToolCalls((prev) => {
          const next = [...prev];
          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].kind === pending.name && next[i].output === undefined && !next[i].completedAt) {
              next[i] = {
                ...next[i],
                output: toolOutput.slice(0, 2000),
                error: toolIsError,
                completedAt: Date.now(),
              };
              break;
            }
          }
          return next;
        });

        // 2) POST the result to /api/chat/resume. New SSE response —
        //    feed it through the same consumeStream. The resume_signature
        //    (Phase H) MUST be passed verbatim — the server signs on
        //    tool_use_pending emit and verifies here. Without it the
        //    route returns resume_signature_missing_signature.
        const resumeRes = await fetch("/api/chat/resume", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            agent_key: agent,
            session_id: sessionId,
            resume_state: pending.resume_state,
            resume_signature: pending.resume_signature,
            tool_use_id: pending.tool_use_id,
            tool_result: { content: toolOutput, is_error: toolIsError },
          }),
        });
        if (!resumeRes.ok || !resumeRes.body) {
          const e = await safeReadJson(resumeRes);
          setError(e?.error || `resume_http_${resumeRes.status}`);
          break;
        }
        await consumeStream(resumeRes);
      }
      if (resumeCount >= 8 && pendingToolUse) {
        setError(
          "Tool loop exceeded the safety cap (8 deferred tools per turn). The model kept asking for tools without finishing — try splitting the request into smaller steps."
        );
      }

      // Stream closed. If no delta ever fired, the bridge (or cloud route)
      // ended the stream without emitting any content — silent failure.
      // Surface it instead of leaving the operator staring at an empty
      // bubble (CC's reported "glitches out after 2s, no response" symptom).
      // Tracked via local boolean so we don't have to read React state
      // from inside another setter's updater (strict-mode double-invoke
      // hazard).
      if (!receivedAnyContent) {
        setError(
          "The agent returned no response. The bridge or upstream model closed the stream without sending any text. Check the bridge logs (pm2 logs claude-bridge) or your API-key quota."
        );
        // Stash which route just failed so the error banner can offer a
        // one-click retry on the OTHER route (CLI bridge ↔ cloud API key).
        setLastFailedMode(useBridge ? "cli" : "cloud");
        // Stale session_id can keep tripping the same failure if the
        // server-side process crashed — clear it for a clean retry.
        setSessionId(null);
        // Drop the empty placeholder bubble.
        setMessages((m) => {
          const last = m[m.length - 1];
          if (last && last.role === "assistant" && last.content.trim().length === 0) {
            return m.slice(0, -1);
          }
          return m;
        });
      } else {
        // Successful turn — clear any stale "last failed mode" tracking so
        // the retry button doesn't linger past the next happy message.
        setLastFailedMode(null);
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

      {/* Header — agent picker only. Routing (cloud-API-key vs local-bridge)
          is decided automatically: use the desktop bridge when it's paired
          and online, otherwise the per-agent API key from Settings → Agents.
          The previous Auto/Cloud/Desktop dropdown over-exposed a one-time
          configuration decision as a per-message choice — gone 2026-05-14
          per CC. accessMode state stays internally as "auto" so the
          downstream routing logic + status labels keep working. */}
      <div className="flex items-center gap-3 px-5 py-4 relative z-10">
        {/* Defensive fallback — if the page passed an empty agentKeys array (legacy
            profile.agents_enabled out of sync with chat-eligible agents), always
            include the current `agent` selection so the dropdown isn't a void
            rectangle that breaks the chat. */}
        <select
          value={agent}
          onChange={(e) => setAgent(e.target.value)}
          className="bg-bg-elev border border-bg-border rounded-lg px-3 py-2 text-sm text-fg uppercase tracking-[0.14em] font-bold focus:outline-none focus:border-accent transition-colors cursor-pointer min-w-[120px]"
          aria-label="Choose agent"
        >
          {(agentKeys.length > 0 ? agentKeys : [agent]).map((k) => (
            <option key={k} value={k}>
              {getAgentInfo(k).label || k.toUpperCase()}
            </option>
          ))}
        </select>
        <div className="flex-1 min-w-0">
          <div className="text-xs text-fg-muted truncate">
            {getAgentInfo(agent).tagline}
          </div>
          <div className="text-xs text-fg-dim font-mono truncate">
            <span title={accessTitle} className={bridgeReady ? "text-accent" : undefined}>
              {bridgeReady && (
                <Cpu className="w-3 h-3 inline-block mr-1 -mt-0.5" />
              )}
              {activeStatus}
            </span>
          </div>
        </div>
        {/*
          Chat-mode picker — Phase 3 of giggly-reef (2026-05-15). Four real
          combinations of (who-owns-the-LLM, who-owns-the-tools):
            - Auto:                bridge if paired+online, else cloud
            - CLI:                 bridge owns LLM + tools (subscription)
            - API · cloud tools:   API key LLM, ONLY the 11 cloud tools
            - API + local tools:   API key LLM, bridge owns tool execution
          The last option is disabled while the bridge is offline — the
          model would emit tool_use for read_file/bash/send_email and the
          browser-proxy would have nothing to forward to. The picker
          tooltip explains why it's grey.
          See type ChatMode docs at the top of this file.
        */}
        <select
          value={chatMode}
          onChange={(e) => {
            const v = e.target.value;
            if (isChatMode(v)) setChatMode(v);
          }}
          className="bg-bg-elev border border-bg-border rounded-lg px-2 py-2 text-[11px] text-fg-muted focus:outline-none focus:border-accent transition-colors cursor-pointer"
          aria-label="Chat routing mode"
          title={accessTitle}
        >
          <option value="auto">Mode: Auto</option>
          <option value="cli">Mode: CLI (local bridge)</option>
          <option value="cloud_only">Mode: API · cloud tools only</option>
          <option
            value="cloud_bridge_tools"
            disabled={bridgeOnline !== true}
            title={
              bridgeOnline !== true
                ? "Disabled: the local bridge isn't reachable. Run `pm2 restart claude-bridge` on this machine to enable API + local tools."
                : undefined
            }
          >
            {bridgeOnline === true
              ? "Mode: API + local tools"
              : "Mode: API + local tools (bridge offline)"}
          </option>
        </select>
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

      {/* The previous "Desktop offline" banner gated on accessMode === "desktop"
          and bridgeOnline === false. Both are gone with the picker — the
          accessMode forced-cloud path doesn't exist anymore, so a missing
          bridge just means the chat falls through to the cloud API key
          silently. Bridge-onboarding nudges, if needed later, belong in
          Settings → Devices, not as a chat-blocking banner. */}

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
            currentProvider={cfg?.provider ?? null}
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
                  No provider key on file. Open{" "}
                  <Link href="/settings#providers" className="text-accent underline">
                    Settings → AI provider accounts
                  </Link>{" "}
                  and click Connect — it applies to every agent in one shot.
                </div>
              )}
              {error === "no_api_key" && (
                <div className="text-xs text-fg-muted font-sans">
                  This agent's provider row exists but has no key. Open{" "}
                  <Link href="/settings#providers" className="text-accent underline">
                    Settings → AI provider accounts
                  </Link>{" "}
                  and Connect (or Replace key) for the matching provider.
                </div>
              )}
              {error === "agent_disabled" && (
                <div className="text-xs text-fg-muted font-sans">
                  This agent is disabled. Open{" "}
                  <Link href="/settings#agents" className="text-accent underline">
                    Settings → Agents
                  </Link>{" "}
                  and flip its enabled toggle.
                </div>
              )}
              {error === "rate_limited" && (
                <div className="text-xs text-fg-muted font-sans">
                  Too many messages too fast. Wait ~15 seconds and try again.
                </div>
              )}
              {/* One-click recovery: if a route failed (CLI or cloud), offer
                  to re-send the same message on the OTHER route. The retry
                  pops the trailing user message from history before calling
                  submitText so the chat doesn't double-print "yo wsp" once
                  the assistant replies.

                  Phase 3 — the picker now has 4 modes (auto / cli /
                  cloud_only / cloud_bridge_tools). The retry button picks
                  the most-likely-working alternate within the OTHER bucket:
                    - cli failed   → cloud_bridge_tools (if bridge online),
                                      else cloud_only
                    - cloud failed → cli (if bridge ready) */}
              {(() => {
                if (!lastFailedMode || streaming) return null;
                // Map the collapsed bucket to a concrete ChatMode the
                // retry will route through. cloud_bridge_tools is the
                // preferred "other cloud" because it has the broadest
                // tool surface; fall back to cloud_only when the bridge
                // isn't reachable.
                const otherMode: ChatMode =
                  lastFailedMode === "cli"
                    ? (bridgeOnline === true ? "cloud_bridge_tools" : "cloud_only")
                    : "cli";
                const otherReady =
                  otherMode === "cli"
                    ? bridgeReady
                    : (cloudReady || isAdmin);
                if (!otherReady) return null;
                // Last user message — what we'll re-send. If history has no
                // user message somehow, the button shouldn't appear.
                const lastUser = [...messages].reverse().find((m) => m.role === "user");
                if (!lastUser) return null;
                const otherLabel =
                  otherMode === "cli"
                    ? "CLI (local bridge)"
                    : otherMode === "cloud_only"
                      ? "API key · cloud tools only"
                      : "API key + local tools";
                return (
                  <button
                    type="button"
                    onClick={() => {
                      const text = lastUser.content;
                      setLastFailedMode(null);
                      setError(null);
                      // Pop the trailing user message so submitText doesn't
                      // print it twice when it re-pushes its own copy.
                      setMessages((m) => {
                        const last = m[m.length - 1];
                        if (last && last.role === "user" && last.content === text) {
                          return m.slice(0, -1);
                        }
                        return m;
                      });
                      // Update the persisted picker too so subsequent turns
                      // default to the working path.
                      setChatMode(otherMode);
                      void submitText(text, otherMode);
                    }}
                    className="mt-2 inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-accent/40 bg-accent/10 hover:bg-accent/20 text-accent text-xs font-bold transition-colors"
                  >
                    Retry on {otherLabel} →
                  </button>
                );
              })()}
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
          placeholder={composerPlaceholder}
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
  currentProvider,
  onSuggestion,
}: {
  ready: boolean;
  agent: string;
  configsLoaded: boolean;
  isAdmin: boolean;
  currentProvider: string | null;
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
    // Ollama models need the desktop bridge running (they're local-only,
    // not reachable from Vercel). All other providers work in pure cloud
    // mode once a key is saved.
    const needsDesktop = currentProvider === "ollama";
    const agentLabel = getAgentInfo(agent).label.toUpperCase();
    return (
      <div className="rounded-lg border border-accent/20 bg-accent/5 p-5 text-sm space-y-3">
        <div className="flex items-center gap-2 text-accent font-bold uppercase tracking-[0.14em] text-xs">
          <Sparkles className="w-4 h-4" /> Set up {agentLabel}
        </div>
        <p className="text-fg">
          {needsDesktop
            ? `${agentLabel} needs OASIS Desktop running before it can use local files, tools, or local models.`
            : `${agentLabel} needs a model + API key before it can chat. The easiest path is OpenRouter - one key gets you Claude, GPT, and Gemini.`}
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          {!needsDesktop && (
            <a
              href="https://openrouter.ai/sign-up"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary text-xs"
            >
              Get OpenRouter key
            </a>
          )}
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
            ? `Talking to ${getAgentInfo(agent).label.toUpperCase()} via the platform default key.`
            : `${getAgentInfo(agent).label.toUpperCase()} is configured and ready.`} Ask anything — strategy, drafting, debugging, ops.
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

  // Show export controls only on completed assistant messages — mid-stream
  // partial markdown would download as a half-doc, which is just confusing.
  const showExports = !isUser && !streaming && content.trim().length > 0;

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
          {showExports && <MessageDownloadMenu content={content} agent={agent} />}
        </div>
      </div>
      {isUser && <UserAvatar />}
    </div>
  );
}

function AgentAvatar({ agent }: { agent: string }) {
  const info = getAgentInfo(agent);
  const initial = info.label.slice(0, 1).toUpperCase();
  return (
    <div
      className={`w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-black tracking-tight border bg-bg-elev/80 ${info.textClass}`}
      style={{ borderColor: "currentColor" }}
      title={info.label}
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
  phase: "spawning" | "thinking" | "tool" | "warm_resume" | null;
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
      : phase === "warm_resume"
        ? `${agent.toLowerCase()} resuming (warm)…`
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
/**
 * FormattedContent — renders the assistant's markdown using the SAME
 * renderer as the export pipeline (lib/markdown.ts). What you see in
 * the chat bubble is what you get when you click Download → MD/HTML/PDF.
 *
 * Security: lib/markdown.mdToHtml escapes the entire input before
 * applying any markdown patterns, then filters link hrefs against
 * dangerous URL schemes. The output is safe to render via
 * dangerouslySetInnerHTML — no path lets raw HTML through. See the
 * security comment in lib/markdown.ts before changing.
 *
 * Previously the chat bubble only handled fenced code blocks + inline
 * code, displaying `**bold**` / `# heading` as literal text. CC's
 * download was richer than the chat — confusing UX. They now match.
 */
function FormattedContent({ content }: { content: string }) {
  const html = mdToHtml(content);
  return (
    <div
      className="markdown-bubble whitespace-normal"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
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
