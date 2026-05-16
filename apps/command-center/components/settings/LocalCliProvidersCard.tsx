"use client";

/**
 * LocalCliProvidersCard — second SETTINGS section: "Connect via local
 * CLI subscription".
 *
 * Phase 8.2 of the OASIS HQ redesign. CC wants a parallel UX path to
 * the API-key cards: instead of pasting an Anthropic / OpenAI key, the
 * operator can run their EXISTING Claude Code, Codex CLI, or Gemini CLI
 * subscription. The bridge already spawns `claude -p` for the chat
 * surface — this card just makes the same capability visible + adds
 * Codex / Gemini parity.
 *
 * Detection flow:
 *   1. Component mounts → POST to localhost:9100/exec-tool with
 *      {name: "cli_status", input: {}}
 *   2. Bridge runs `claude --version`, scripts/codex_health.py --json,
 *      `gemini --version` + auth checks in parallel
 *   3. Returns {claude, codex, gemini: {installed, authenticated,
 *      version, install_hint_url}}
 *   4. Each card renders one of: Ready / Needs auth / Not installed /
 *      Bridge offline.
 *
 * Bridge-offline state is its own banner (not a per-card error) since
 * none of the cards can self-detect without it.
 */

import { useEffect, useState } from "react";
import { Loader2, CheckCircle2, AlertCircle, Terminal, ExternalLink, RefreshCw } from "lucide-react";
import { Card, Tag } from "@/components/Card";
import { BRIDGE_CHAT_BASE } from "@/lib/agent-roots";

type CliInfo = {
  installed: boolean;
  authenticated: boolean;
  version: string | null;
  install_hint_url: string;
};

type CliStatusResponse = {
  claude: CliInfo;
  codex: CliInfo;
  gemini: CliInfo;
};

type ProbeState =
  | { kind: "loading" }
  | { kind: "bridge_offline" }
  | { kind: "error"; message: string }
  | { kind: "ok"; data: CliStatusResponse };

const CARDS: Array<{
  key: keyof CliStatusResponse;
  label: string;
  blurb: string;
  install_url: string;
  install_command: string;
}> = [
  {
    key: "claude",
    label: "Claude Code",
    blurb: "Uses your Claude Max / Pro subscription. Spawns the local `claude` CLI.",
    install_url: "https://docs.anthropic.com/en/docs/claude-code/quickstart",
    install_command: "npm install -g @anthropic-ai/claude-code",
  },
  {
    key: "codex",
    label: "Codex CLI",
    blurb: "Uses your OpenAI subscription via the Codex CLI / plugin.",
    install_url: "https://github.com/openai/codex",
    install_command: "npm install -g @openai/codex",
  },
  {
    key: "gemini",
    label: "Gemini CLI",
    blurb: "Uses your Google AI Studio account via the Gemini CLI.",
    install_url: "https://github.com/google-gemini/gemini-cli",
    install_command: "npm install -g @google/gemini-cli",
  },
];

async function probeCliStatus(signal: AbortSignal): Promise<ProbeState> {
  let healthOk = false;
  try {
    const h = await fetch(`${BRIDGE_CHAT_BASE}/health`, { signal });
    healthOk = h.ok;
  } catch {
    return { kind: "bridge_offline" };
  }
  if (!healthOk) return { kind: "bridge_offline" };

  try {
    const r = await fetch(`${BRIDGE_CHAT_BASE}/exec-tool`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ tool_name: "cli_status", input: {} }),
      signal,
    });
    if (!r.ok) {
      return { kind: "error", message: `bridge returned ${r.status}` };
    }
    const body = (await r.json()) as { output?: string; is_error?: boolean };
    if (body.is_error || !body.output) {
      return { kind: "error", message: "bridge cli_status returned no output" };
    }
    const data = JSON.parse(body.output) as CliStatusResponse;
    return { kind: "ok", data };
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      return { kind: "loading" };
    }
    return { kind: "error", message: (err as Error).message };
  }
}

function statusFor(info: CliInfo): { label: string; tone: "engaged" | "warm" | "neutral"; icon: React.ReactNode } {
  if (info.installed && info.authenticated) {
    return { label: "Ready", tone: "engaged", icon: <CheckCircle2 className="w-3.5 h-3.5" /> };
  }
  if (info.installed && !info.authenticated) {
    return { label: "Needs auth", tone: "warm", icon: <AlertCircle className="w-3.5 h-3.5" /> };
  }
  return { label: "Not installed", tone: "neutral", icon: <Terminal className="w-3.5 h-3.5" /> };
}

export function LocalCliProvidersCard() {
  const [state, setState] = useState<ProbeState>({ kind: "loading" });

  async function refresh() {
    setState({ kind: "loading" });
    const ctl = new AbortController();
    // 10s ceiling — the codex_health probe is the slowest, ~3-5s.
    const timer = setTimeout(() => ctl.abort(), 10_000);
    const next = await probeCliStatus(ctl.signal);
    clearTimeout(timer);
    setState(next);
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Card
      title="Connect via local CLI subscription"
      subtitle="Use Claude Code, Codex, or Gemini installed on this machine — no API key needed. Each card detects install + auth state via the local bridge."
      action={
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={state.kind === "loading"}
          className="text-xs text-fg-dim hover:text-accent inline-flex items-center gap-1 disabled:opacity-50"
        >
          <RefreshCw className={`w-3 h-3 ${state.kind === "loading" ? "animate-spin" : ""}`} />
          Refresh
        </button>
      }
    >
      {state.kind === "loading" && (
        <div className="flex items-center gap-2 text-sm text-fg-muted">
          <Loader2 className="w-4 h-4 animate-spin" />
          Probing local CLIs...
        </div>
      )}

      {state.kind === "bridge_offline" && (
        <div className="flex items-start gap-2 text-sm text-status-warm bg-status-warm/5 border border-status-warm/30 rounded-lg p-3">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <div className="font-bold">Local bridge offline</div>
            <p className="mt-1 text-xs text-fg-muted leading-relaxed">
              The CLI cards need the local bridge running on this machine to probe installed
              CLIs. Run <code className="font-mono text-fg">bravo bridge start</code> and refresh.
              Until then the dashboard can't tell which CLIs are installed.
            </p>
          </div>
        </div>
      )}

      {state.kind === "error" && (
        <div className="flex items-start gap-2 text-sm text-status-hot bg-status-hot/5 border border-status-hot/30 rounded-lg p-3">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <div className="font-bold">CLI probe failed</div>
            <p className="mt-1 text-xs text-fg-muted">{state.message}</p>
          </div>
        </div>
      )}

      {state.kind === "ok" && (
        <div className="grid sm:grid-cols-3 gap-3">
          {CARDS.map((card) => {
            const info = state.data[card.key];
            const s = statusFor(info);
            return (
              <div
                key={card.key}
                className={`rounded-lg border p-3 space-y-2 ${
                  info.installed && info.authenticated
                    ? "border-status-engaged/30 bg-status-engaged/5"
                    : info.installed
                      ? "border-status-warm/30 bg-status-warm/5"
                      : "border-bg-border bg-bg-elev/30"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold text-sm text-fg">{card.label}</span>
                  <Tag tone={s.tone}>
                    <span className="inline-flex items-center gap-1">
                      {s.icon}
                      {s.label}
                    </span>
                  </Tag>
                </div>
                <p className="text-xs text-fg-muted leading-snug">{card.blurb}</p>
                {info.version && (
                  <div className="text-[10px] font-mono text-fg-dim truncate" title={info.version}>
                    {info.version}
                  </div>
                )}
                {!info.installed && (
                  <div className="space-y-1.5">
                    <div className="text-[10px] font-mono text-fg-dim bg-bg-deep px-2 py-1 rounded break-all">
                      {card.install_command}
                    </div>
                    <a
                      href={card.install_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline"
                    >
                      Install guide
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                )}
                {info.installed && !info.authenticated && (
                  <div className="text-[11px] text-status-warm">
                    Run the CLI&apos;s login command on this machine, then refresh.
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
