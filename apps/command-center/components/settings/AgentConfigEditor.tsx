"use client";

/**
 * AgentConfigEditor — per-tenant per-agent provider/model/API-key configurator.
 *
 * Recommended path: OpenRouter (one key gets all models). Direct providers
 * (Anthropic / OpenAI / Google) supported for clients with existing keys.
 *
 * One row per agent (Bravo/Maven/Atlas/Aura/Hermes). Each row lets the user
 * pick a provider, pick a model, paste an API key, and toggle enabled.
 * Key is sent to /api/agent-config which encrypts it at rest via AES-256-GCM
 * + the BRAVO_FIELD_ENCRYPTION_KEY env passphrase. Existing keys are never
 * returned to the browser; the row just shows whether one is on file.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { Save, Eye, EyeOff, Check, AlertCircle, ExternalLink, Sparkles, ChevronDown, ChevronUp, Cpu, Cloud, KeyRound } from "lucide-react";
import { getAgentInfo } from "@/lib/agents";
import { PROVIDER_REGISTRY } from "@/lib/providers";

// Settings/Agents picker derives from the same single-source registry as
// Onboarding. Each entry already carries `models`, `hint`, `recommended`,
// signup/apiKey/docs links — same shape this component consumes. See
// lib/providers.ts for the canonical definition.
const PROVIDER_OPTIONS = PROVIDER_REGISTRY;

type AgentConfig = {
  agent_key: string;
  provider: string;
  model: string;
  enabled: boolean;
  has_key: boolean;
  has_override: boolean;
  last_used_at: string | null;
};

type RowState = {
  provider: string;
  model: string;
  apiKey: string;
  enabled: boolean;
  override: string;
  showKey: boolean;
  showOverride: boolean;
  saving: boolean;
  saved: boolean;
  error: string | null;
  // Phase E — per-agent tool palette editor state. The expandable panel
  // shows checkboxes for every tool in toolCatalog (Cloud + Bridge
  // groups). null `palette` means "use full palette" (no filter); a
  // string[] is the explicit allowlist. paletteDirty tracks whether the
  // operator has made unsaved changes so the Save button activates.
  showPalette: boolean;
  palette: string[] | null;
  paletteDirty: boolean;
  paletteSaving: boolean;
  paletteSaved: boolean;
  paletteError: string | null;
};

export type ToolCatalogEntry = {
  name: string;
  description: string;
  defer: boolean;
};

type Props = {
  agentKeys: string[];
  /**
   * Tenant-level bridge-pairing state — single source of truth resolved
   * server-side via getBridgeOnline(). The per-agent Tool Access strip
   * below reads this to show whether the agent has full local-tool
   * access (bridge paired, Python/file/script tools wired) or runs
   * cloud-only (chat + dashboard actions via the saved API key).
   */
  bridgeOnline?: boolean;
  /**
   * Per-agent tool palette from the tenant's manifest (Phase D of
   * giggly-reef). Map of agent slug → string[] (allowlist) | undefined
   * (no filter — full palette). Used to render a read-only indicator
   * below the Tool Access strip so the operator sees the current
   * state at a glance. Editing happens via the AI manifest editor (the
   * /api/manifest/<slug> mutator handles update_agent with tool_palette).
   */
  agentPalettes?: Record<string, string[] | undefined>;
  /** Manifest slug for the deep-link to the AI editor when present. */
  manifestSlug?: string | null;
  /**
   * Slim catalog of every tool the model could be allowed to call.
   * Server-rendered from TOOL_DEFINITIONS in lib/cloud-tool-runner.ts
   * (which can't be imported client-side because it transitively pulls
   * server-only Supabase code). Used by the per-agent palette editor
   * to render checkboxes grouped by Cloud vs Bridge.
   */
  toolCatalog?: ToolCatalogEntry[];
};

export function AgentConfigEditor({
  agentKeys,
  bridgeOnline = false,
  agentPalettes = {},
  manifestSlug = null,
  toolCatalog = [],
}: Props) {
  const [configs, setConfigs] = useState<Record<string, AgentConfig>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  // Bumped from the cross-component event below (oasis:agent-configs-changed)
  // when bulk-provider-connect from /settings#providers writes new rows
  // for every agent. Triggers the fetch effect to re-run so the per-agent
  // rows reflect the freshly-saved provider+model+key without a reload.
  const [refreshTick, setRefreshTick] = useState(0);
  const [rows, setRows] = useState<Record<string, RowState>>(() =>
    Object.fromEntries(
      agentKeys.map((k) => {
        // Initial palette: convert undefined → null (UI semantic for
        // "use full palette") so the checkbox group renders all-checked.
        // An empty array stays as [] (chat-only). A populated list
        // stays as-is.
        const initialPalette = agentPalettes[k];
        return [
          k,
          {
            provider: "openrouter",
            model: "anthropic/claude-sonnet-4",
            apiKey: "",
            enabled: true,
            override: "",
            showKey: false,
            showOverride: false,
            saving: false,
            saved: false,
            error: null,
            showPalette: false,
            palette: initialPalette === undefined ? null : initialPalette,
            paletteDirty: false,
            paletteSaving: false,
            paletteSaved: false,
            paletteError: null,
          },
        ];
      })
    )
  );

  useEffect(() => {
    fetch("/api/agent-config")
      .then(async (r) => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok || !j.ok) {
          // Surface the failure to the operator — otherwise the rows stay at
          // their hardcoded defaults (openrouter / claude-sonnet-4) and the
          // operator may "save" over their actual stored config.
          const msg = j.error || `status ${r.status}`;
          console.error("[agent_config_editor.load]", msg);
          setLoadError(msg);
          return;
        }
        const map: Record<string, AgentConfig> = {};
        for (const c of j.configs as AgentConfig[]) map[c.agent_key] = c;
        setConfigs(map);
        setRows((prev) => {
          const next = { ...prev };
          for (const key of agentKeys) {
            const c = map[key];
            if (c) {
              next[key] = {
                ...next[key],
                provider: c.provider,
                model: c.model,
                enabled: c.enabled,
              };
            }
          }
          return next;
        });
      })
      .catch((err) => {
        console.error("[agent_config_editor.load]", err);
        setLoadError(err instanceof Error ? err.message : "network error");
      });
  }, [agentKeys, refreshTick]);

  // Listen for cross-component "configs changed" pokes — emitted by the
  // ProviderAccountsCard's single-click connect flow upstream on /settings.
  // Bumps refreshTick which re-runs the fetch effect above. Cleaned up on
  // unmount so a navigated-away editor isn't holding an orphan listener.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onChange = () => setRefreshTick((n) => n + 1);
    window.addEventListener("oasis:agent-configs-changed", onChange);
    return () => window.removeEventListener("oasis:agent-configs-changed", onChange);
  }, []);

  function patchRow(key: string, patch: Partial<RowState>) {
    setRows((r) => ({ ...r, [key]: { ...r[key], ...patch } }));
  }

  async function save(agentKey: string) {
    const row = rows[agentKey];
    patchRow(agentKey, { saving: true, error: null, saved: false });
    const body: Record<string, unknown> = {
      agent_key: agentKey,
      provider: row.provider,
      model: row.model,
      enabled: row.enabled,
    };
    if (row.apiKey.trim().length) body.api_key = row.apiKey.trim();
    if (row.override.trim().length) body.system_prompt_override = row.override;
    try {
      const res = await fetch("/api/agent-config", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await res.json();
      if (!j.ok) {
        patchRow(agentKey, { saving: false, error: j.error || `http_${res.status}` });
        return;
      }
      patchRow(agentKey, {
        saving: false,
        saved: true,
        apiKey: "",
        showKey: false,
      });
      setConfigs((c) => ({
        ...c,
        [agentKey]: {
          agent_key: agentKey,
          provider: row.provider,
          model: row.model,
          enabled: row.enabled,
          has_key: row.apiKey.trim().length > 0 || c[agentKey]?.has_key || false,
          has_override:
            row.override.trim().length > 0 || c[agentKey]?.has_override || false,
          last_used_at: c[agentKey]?.last_used_at || null,
        },
      }));
      setTimeout(() => patchRow(agentKey, { saved: false }), 2500);
    } catch (e) {
      patchRow(agentKey, {
        saving: false,
        error: e instanceof Error ? e.message : "save_failed",
      });
    }
  }

  /**
   * Phase E — save the per-agent tool palette to the manifest via the
   * existing /api/manifest/<slug> mutation endpoint. Different write
   * path than save(): tool_palette lives on the manifest, not on
   * agent_model_config.
   *
   * Empty array means "chat-only, no tools". A null palette (toggled by
   * the "Use full palette" link) becomes the absent field on the agent
   * binding, which the /api/chat filter treats as "no filter, full
   * palette" — preserves pre-Phase-D behavior.
   */
  async function savePalette(agentKey: string) {
    if (!manifestSlug) {
      patchRow(agentKey, {
        paletteError:
          "No manifest slug available — palette editing requires a manifest-managed tenant. Operator account / dev mode falls through to the full palette automatically.",
      });
      return;
    }
    const row = rows[agentKey];
    patchRow(agentKey, { paletteSaving: true, paletteError: null, paletteSaved: false });
    const change: Record<string, unknown> = { tool_palette: row.palette };
    try {
      const res = await fetch(`/api/manifest/${manifestSlug}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          mutations: [
            {
              name: "update_agent",
              args: { slug: agentKey, changes: change },
            },
          ],
          actor: "user",
          message: `Palette update for ${agentKey} via Settings → Agents`,
        }),
      });
      const j = await res.json();
      if (!j.ok) {
        patchRow(agentKey, {
          paletteSaving: false,
          paletteError: j.error || `http_${res.status}`,
        });
        return;
      }
      patchRow(agentKey, {
        paletteSaving: false,
        paletteSaved: true,
        paletteDirty: false,
      });
      setTimeout(() => patchRow(agentKey, { paletteSaved: false }), 2500);
      // Cross-component refresh so the parent server component re-reads
      // the manifest on next render and the indicator stays in sync.
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("oasis:agent-configs-changed"));
      }
    } catch (e) {
      patchRow(agentKey, {
        paletteSaving: false,
        paletteError: e instanceof Error ? e.message : "save_failed",
      });
    }
  }

  return (
    <div id="agents" className="space-y-4">
      {loadError && (
        <div className="rounded-xl border border-status-hot/40 bg-status-hot/10 p-4 flex items-start gap-3">
          <AlertCircle size={18} className="text-status-hot shrink-0 mt-0.5" />
          <div className="text-sm">
            <div className="font-bold text-fg">Could not load your saved agent config</div>
            <p className="text-fg-muted mt-1">
              Showing default values. <span className="font-mono text-xs">{loadError}</span>
            </p>
            <p className="text-fg-muted mt-1">
              Refresh the page before saving — otherwise you may overwrite stored
              providers/models with defaults.
            </p>
          </div>
        </div>
      )}
      {agentKeys.map((key) => {
        const row = rows[key];
        const cfg = configs[key];
        const provOpt = PROVIDER_OPTIONS.find((p) => p.value === row.provider) || PROVIDER_OPTIONS[0];
        const isOpenRouter = row.provider === "openrouter";
        return (
          <div
            key={key}
            className="rounded-xl border border-bg-border bg-bg-elev p-5 space-y-4 hover:border-accent-muted/40 transition-colors"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className={`agent-pill`}>
                  <span className="agent-pill-dot" />
                  {key}
                </div>
                <div className="text-xs text-fg-muted">
                  {getAgentInfo(key).role}
                </div>
              </div>
              <div className="flex items-center gap-3">
                {cfg?.has_key ? (
                  <span className="text-xs text-status-engaged font-mono flex items-center gap-1">
                    <Check className="w-3 h-3" /> key on file
                  </span>
                ) : (
                  <span className="text-xs text-fg-dim font-mono">no key</span>
                )}
                <label className="flex items-center gap-2 text-xs text-fg-muted cursor-pointer">
                  <input
                    type="checkbox"
                    checked={row.enabled}
                    onChange={(e) => patchRow(key, { enabled: e.target.checked })}
                    className="accent-accent"
                  />
                  enabled
                </label>
              </div>
            </div>

            {/* Provider picker as chips */}
            <div className="flex flex-wrap gap-2">
              {PROVIDER_OPTIONS.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => patchRow(key, { provider: p.value, model: p.models[0]?.id || "" })}
                  className={`provider-chip ${
                    row.provider === p.value
                      ? p.recommended
                        ? "recommended"
                        : "!bg-accent/15 !border-accent/50 !text-fg"
                      : ""
                  } cursor-pointer hover:border-accent/40`}
                >
                  {p.recommended && <Sparkles className="w-3 h-3" />}
                  {p.label}
                </button>
              ))}
            </div>

            {/* Hint + signup links */}
            <div className="text-xs text-fg-muted flex flex-wrap items-center gap-3">
              <span>{provOpt.hint}</span>
              <a
                href={provOpt.signup}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:text-accent-bright inline-flex items-center gap-1 underline-offset-2 hover:underline"
              >
                Sign up <ExternalLink className="w-3 h-3" />
              </a>
              <a
                href={provOpt.apiKey}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:text-accent-bright inline-flex items-center gap-1 underline-offset-2 hover:underline"
              >
                Get API key <ExternalLink className="w-3 h-3" />
              </a>
            </div>

            {/* Model + API key */}
            <div className="grid grid-cols-1 sm:grid-cols-[1fr_2fr] gap-3">
              <label className="text-xs text-fg-muted space-y-1">
                <span className="label">Model</span>
                <select
                  value={row.model}
                  onChange={(e) => patchRow(key, { model: e.target.value })}
                  className="select"
                >
                  {provOpt.models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs text-fg-muted space-y-1">
                <span className="label">
                  {row.provider === "ollama" ? "Endpoint URL" : "API key"}{" "}
                  <span className="text-fg-dim normal-case tracking-normal font-normal">
                    {cfg?.has_key ? "(leave blank to keep existing)" : "(required)"}
                  </span>
                </span>
                <div className="flex gap-2">
                  <input
                    type={row.showKey || row.provider === "ollama" ? "text" : "password"}
                    value={row.apiKey}
                    onChange={(e) => patchRow(key, { apiKey: e.target.value })}
                    placeholder={
                      cfg?.has_key
                        ? "•••••••••••••••"
                        : row.provider === "ollama"
                          ? "http://localhost:11434/v1"
                          : isOpenRouter
                            ? "sk-or-v1-..."
                            : "your provider key"
                    }
                    className="input font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => patchRow(key, { showKey: !row.showKey })}
                    className="btn-secondary !p-2"
                    title={row.showKey ? "Hide" : "Show"}
                  >
                    {row.showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </label>
            </div>

            {/* Tool Access — two-channel summary. Channel A (Cloud tools)
                is always available once a key is on file; on Anthropic
                provider it's a native tool_use loop (cloud-tool-runner.ts).
                Channel B (Local bridge tools) requires bridge_pairings to
                be fresh (<5 min heartbeat) and unlocks Python scripts /
                file reads / cron / real SMS via the operator's machine.
                Both channels coexist — the chat-mode picker chooses which
                one a given turn routes to. */}
            <div className="grid sm:grid-cols-2 gap-2.5">
              {/* Cloud tools — always available with an API key. */}
              <div
                className={`rounded-lg border p-3 flex items-start gap-2.5 ${
                  cfg?.has_key
                    ? "border-accent/40 bg-accent/5"
                    : "border-bg-border bg-bg-deep/40"
                }`}
              >
                <Cloud
                  className={`w-4 h-4 shrink-0 mt-0.5 ${
                    cfg?.has_key ? "text-accent" : "text-fg-dim"
                  }`}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-bold uppercase tracking-wider text-fg-muted">
                    Cloud tools · API key
                  </div>
                  <div className="text-xs text-fg mt-0.5 leading-relaxed">
                    {cfg?.has_key ? (
                      <>
                        <span className="text-accent">Active.</span> Real
                        tool_use loop on Anthropic: records read/write/search,
                        http_get/post, integration status, lead lookup. No
                        local file access.
                      </>
                    ) : (
                      <>
                        <span className="text-fg-muted">Inactive.</span> Paste
                        an API key above to unlock the cloud tool palette
                        (records, http, integrations).
                      </>
                    )}
                  </div>
                </div>
              </div>
              {/* Local bridge tools — needs `bravo bridge serve` running. */}
              <div
                className={`rounded-lg border p-3 flex items-start gap-2.5 ${
                  bridgeOnline
                    ? "border-status-engaged/30 bg-status-engaged/5"
                    : "border-bg-border bg-bg-deep/40"
                }`}
              >
                <Cpu
                  className={`w-4 h-4 shrink-0 mt-0.5 ${
                    bridgeOnline ? "text-status-engaged" : "text-fg-dim"
                  }`}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-bold uppercase tracking-wider text-fg-muted">
                    Local bridge · CLI
                  </div>
                  <div className="text-xs text-fg mt-0.5 leading-relaxed">
                    {bridgeOnline ? (
                      <>
                        <span className="text-status-engaged">Online.</span>{" "}
                        Python scripts, file reads, scheduled jobs, real
                        sends — all via the desktop bridge.
                      </>
                    ) : (
                      <>
                        <span className="text-fg-muted">Offline.</span> Install
                        the bridge for full Claude Code parity (file system,
                        bash, all MCPs).
                      </>
                    )}
                  </div>
                  {!bridgeOnline && (
                    <Link
                      href="/settings/devices/install"
                      className="text-[11px] text-accent hover:text-accent-bright inline-flex items-center gap-1 mt-1.5"
                    >
                      Install the bridge →{" "}
                      <ExternalLink className="w-3 h-3" />
                    </Link>
                  )}
                </div>
              </div>
            </div>

            {/* Phase E — per-agent tool palette editor.
                Collapsed: one-line summary of current allowlist state.
                Expanded: grouped checkboxes (Cloud / Bridge) + Save.
                Writes through /api/manifest/<slug> via update_agent
                mutation; that's the canonical path for manifest changes. */}
            {(() => {
              const palette = row.palette;
              const isFull = palette === null;
              const cloudTools = toolCatalog.filter((t) => !t.defer);
              const bridgeTools = toolCatalog.filter((t) => t.defer);
              const totalCount = palette === null ? toolCatalog.length : palette.length;
              const summary = isFull
                ? "Full palette (no manifest filter)"
                : palette!.length === 0
                  ? "Chat-only (zero tools allowed)"
                  : `${palette!.length} tool${palette!.length === 1 ? "" : "s"} allowed`;
              const setPalette = (next: string[] | null) =>
                patchRow(key, { palette: next, paletteDirty: true });
              const toggle = (toolName: string, checked: boolean) => {
                const base = palette === null ? toolCatalog.map((t) => t.name) : palette;
                if (checked && !base.includes(toolName)) {
                  setPalette([...base, toolName]);
                } else if (!checked && base.includes(toolName)) {
                  setPalette(base.filter((n) => n !== toolName));
                }
              };
              const groupCheckboxes = (group: ToolCatalogEntry[]) => (
                <div className="grid sm:grid-cols-2 gap-x-3 gap-y-1.5">
                  {group.map((t) => {
                    const checked = palette === null || palette.includes(t.name);
                    return (
                      <label
                        key={t.name}
                        className="flex items-start gap-2 text-xs cursor-pointer hover:text-fg"
                        title={t.description}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => toggle(t.name, e.target.checked)}
                          className="mt-0.5 shrink-0 accent-accent"
                        />
                        <span className="font-mono text-fg-muted leading-relaxed">{t.name}</span>
                      </label>
                    );
                  })}
                </div>
              );
              return (
                <div className="rounded-lg border border-bg-border bg-bg-deep/30">
                  <button
                    type="button"
                    onClick={() => patchRow(key, { showPalette: !row.showPalette })}
                    className="w-full px-3 py-2 text-xs flex items-start gap-2 hover:bg-bg-elev/40 transition-colors text-left"
                  >
                    <KeyRound className="w-3.5 h-3.5 text-fg-muted shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <div className="text-fg-muted">
                        <span className="font-bold uppercase tracking-wider text-[10px] text-fg-dim">Tool palette · </span>
                        <span className={isFull ? "text-fg" : palette!.length === 0 ? "text-status-warm" : "text-fg"}>
                          {summary}
                        </span>
                        {row.paletteDirty && (
                          <span className="ml-2 text-[10px] text-status-warm">(unsaved)</span>
                        )}
                      </div>
                    </div>
                    {row.showPalette ? (
                      <ChevronUp className="w-3.5 h-3.5 text-fg-dim shrink-0 mt-0.5" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5 text-fg-dim shrink-0 mt-0.5" />
                    )}
                  </button>
                  {row.showPalette && (
                    <div className="border-t border-bg-border px-3 py-3 space-y-3">
                      <p className="text-[11px] text-fg-dim leading-relaxed">
                        Choose which tools this agent can call. Uncheck what
                        it shouldn&apos;t touch (e.g. give Helios{" "}
                        <span className="font-mono">send_sms</span> but not{" "}
                        <span className="font-mono">bash</span>). The bridge
                        tools (right column) require the local bridge to be
                        online — when offline they get auto-filtered out
                        regardless of palette state.
                      </p>
                      <div className="flex items-center gap-3 text-[11px]">
                        <button
                          type="button"
                          onClick={() => setPalette(null)}
                          className="text-accent hover:text-accent-bright"
                          disabled={isFull}
                        >
                          Use full palette
                        </button>
                        <span className="text-fg-dim">·</span>
                        <button
                          type="button"
                          onClick={() => setPalette(toolCatalog.map((t) => t.name))}
                          className="text-fg-muted hover:text-fg"
                        >
                          Check all
                        </button>
                        <span className="text-fg-dim">·</span>
                        <button
                          type="button"
                          onClick={() => setPalette([])}
                          className="text-fg-muted hover:text-fg"
                        >
                          Uncheck all
                        </button>
                        <span className="text-fg-dim ml-auto">
                          {totalCount} / {toolCatalog.length} selected
                        </span>
                      </div>
                      <div className="space-y-3">
                        <div>
                          <div className="text-[10px] font-bold uppercase tracking-wider text-fg-dim mb-1.5">
                            Cloud tools ({cloudTools.length})
                          </div>
                          {groupCheckboxes(cloudTools)}
                        </div>
                        <div>
                          <div className="text-[10px] font-bold uppercase tracking-wider text-fg-dim mb-1.5">
                            Bridge tools ({bridgeTools.length})
                          </div>
                          {groupCheckboxes(bridgeTools)}
                        </div>
                      </div>
                      {row.paletteError && (
                        <div className="text-[11px] text-status-warm flex items-start gap-1">
                          <AlertCircle className="w-3 h-3 mt-0.5" />
                          <span>{row.paletteError}</span>
                        </div>
                      )}
                      <div className="flex items-center justify-end gap-2 pt-1">
                        <button
                          type="button"
                          onClick={() => {
                            // Revert to whatever the server-rendered manifest
                            // says — clears the dirty flag without saving.
                            const orig = agentPalettes[key];
                            patchRow(key, {
                              palette: orig === undefined ? null : orig,
                              paletteDirty: false,
                              paletteError: null,
                            });
                          }}
                          className="btn-secondary !px-3 !py-1.5 text-[11px]"
                          disabled={!row.paletteDirty || row.paletteSaving}
                        >
                          Revert
                        </button>
                        <button
                          type="button"
                          onClick={() => savePalette(key)}
                          className="btn-primary !px-3 !py-1.5 text-[11px] inline-flex items-center gap-1"
                          disabled={!row.paletteDirty || row.paletteSaving}
                        >
                          {row.paletteSaving ? (
                            <Sparkles className="w-3 h-3 animate-spin" />
                          ) : row.paletteSaved ? (
                            <Check className="w-3 h-3" />
                          ) : (
                            <Save className="w-3 h-3" />
                          )}
                          {row.paletteSaving ? "Saving" : row.paletteSaved ? "Saved" : "Save palette"}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })()}

            {/* System prompt override (collapsed by default) */}
            <div>
              <button
                type="button"
                onClick={() => patchRow(key, { showOverride: !row.showOverride })}
                className="text-xs text-fg-muted hover:text-fg inline-flex items-center gap-1"
              >
                {row.showOverride ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                System prompt override {cfg?.has_override && <span className="text-status-engaged">(active)</span>}
              </button>
              {row.showOverride && (
                <textarea
                  value={row.override}
                  onChange={(e) => patchRow(key, { override: e.target.value })}
                  placeholder="Optional — overrides the default agent persona for this tenant. Leave blank to use the OASIS default."
                  className="textarea mt-2"
                  rows={4}
                />
              )}
            </div>

            <div className="flex items-center justify-between pt-1">
              <div className="text-xs">
                {row.error && (
                  <span className="text-status-warm font-mono flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" /> {row.error}
                  </span>
                )}
                {row.saved && (
                  <span className="text-status-engaged font-mono flex items-center gap-1">
                    <Check className="w-3 h-3" /> saved
                  </span>
                )}
              </div>
              <button
                onClick={() => save(key)}
                disabled={row.saving}
                className="btn-primary inline-flex items-center gap-1.5"
              >
                <Save className="w-3.5 h-3.5" /> {row.saving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
