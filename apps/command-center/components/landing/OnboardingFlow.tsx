"use client";

/**
 * 3-step onboarding wizard:
 *   1. Pick a provider (OpenRouter recommended) and paste a key
 *   2. Pick the primary agent
 *   3. (Optional) pair a local machine for file-system access — Phase 2
 *
 * Final action posts the agent_model_config row for ALL chat-eligible agents
 * with the chosen provider+model+key, then redirects to /agents.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowRight, ExternalLink, Cpu, Cog, Check, Sparkles, Eye, EyeOff,
  Loader2, AlertCircle, ShieldCheck, Monitor, Download,
} from "lucide-react";
import { FAMILY_AGENT_KEYS, getAgentInfo } from "@/lib/agents";
import { PROVIDER_REGISTRY } from "@/lib/providers";
import { InstallBridgeModal } from "@/components/settings/InstallBridgeModal";

// Single source of truth for the provider picker — see lib/providers.ts.
// Add a provider once there, both Onboarding and AgentConfigEditor pick
// it up. Earlier this list was duplicated here AND in AgentConfigEditor;
// the duplicates drifted (one had ollama, one didn't) until consolidation.
const PROVIDERS = PROVIDER_REGISTRY;

// Onboarding shows the C-suite personas (Bravo / Atlas / Maven / Aura / Hermes / Life Preservation).
// Codex is excluded because it is a backend executor, not a standalone persona — see lib/agents.ts.
const AGENTS = FAMILY_AGENT_KEYS.map((k) => {
  const info = getAgentInfo(k);
  return { key: info.key, label: info.label, role: info.tagline, color: info.textClass };
});

type Props = { userEmail: string };

export function OnboardingFlow({ userEmail }: Props) {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [providerKey, setProviderKey] = useState("openrouter");
  const [model, setModel] = useState("anthropic/claude-sonnet-4");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [primaryAgent, setPrimaryAgent] = useState("bravo");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Step 3 install-bridge modal toggle (added 2026-05-10). Wires the
  // same one-click installer flow surfaced in Settings → Devices so
  // first-time operators can pair their machine without leaving the
  // onboarding tab.
  const [installerOpen, setInstallerOpen] = useState(false);

  const provider = PROVIDERS.find((p) => p.value === providerKey)!;

  function pickProvider(value: string) {
    setProviderKey(value);
    const next = PROVIDERS.find((p) => p.value === value)!;
    setModel(next.models[0].id);
  }

  async function finish() {
    setError(null);
    if (!apiKey.trim()) {
      setError("Paste your API key to continue, or skip to the dashboard.");
      return;
    }
    setSubmitting(true);
    try {
      // Configure every chat-eligible agent with the same provider/model/key.
      // Onboarding always seeds all 5; the operator can toggle agents_enabled
      // in Settings to disable any (e.g. Hermes) and they drop out of the
      // chat picker — see app/agents/page.tsx + app/settings/page.tsx.
      const targets = AGENTS.map((a) => a.key);
      const results = await Promise.all(
        targets.map((agent_key) =>
          fetch("/api/agent-config", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              agent_key,
              provider: providerKey,
              model,
              api_key: apiKey.trim(),
              enabled: true,
            }),
          }).then((r) => r.json())
        )
      );
      const failed = results.find((r) => !r.ok);
      if (failed) {
        setError(failed.error || "save_failed");
        setSubmitting(false);
        return;
      }
      // Persist primary agent + mark onboarding complete so the
      // middleware stops force-routing the user back here on every
      // signed-in page load.
      await fetch("/api/profile", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          primary_agent: primaryAgent,
          onboarding_completed_at: new Date().toISOString(),
        }),
      }).catch(() => null);
      router.push("/agents");
    } catch (e) {
      setError(e instanceof Error ? e.message : "request_failed");
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-5">
      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {[1, 2, 3].map((n) => (
          <div key={n} className="flex items-center gap-2">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
              step >= n
                ? "bg-accent text-bg-deep shadow-[0_0_12px_-2px_rgba(0,212,255,0.6)]"
                : "bg-bg-elev text-fg-dim border border-bg-border"
            }`}>
              {step > n ? <Check className="w-3.5 h-3.5" /> : n}
            </div>
            {n < 3 && <div className={`h-px w-12 ${step > n ? "bg-accent" : "bg-bg-border"}`} />}
          </div>
        ))}
      </div>

      {/* Step 1 — Provider + key */}
      {step === 1 && (
        <Card title="Pick how to power your agents" icon={<Cpu className="w-4 h-4" />}>
          <div className="grid sm:grid-cols-2 gap-3">
            {PROVIDERS.map((p) => (
              <button
                key={p.value}
                type="button"
                onClick={() => pickProvider(p.value)}
                className={`text-left rounded-lg border p-3.5 transition-all ${
                  providerKey === p.value
                    ? "border-accent bg-accent/10 shadow-[0_0_16px_-6px_rgba(0,212,255,0.5)]"
                    : "border-bg-border bg-bg-elev hover:border-accent/40"
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="text-sm font-bold text-fg">{p.label}</div>
                  {p.badge && (
                    <span className="provider-chip recommended !py-0.5 !px-1.5 !text-[10px]">
                      <Sparkles className="w-2.5 h-2.5" /> {p.badge.replace("★ ", "")}
                    </span>
                  )}
                </div>
                <div className="text-xs text-fg-muted">{p.tagline}</div>
              </button>
            ))}
          </div>

          <div className="mt-5 grid sm:grid-cols-[1fr_2fr] gap-3">
            <label className="space-y-1.5">
              <span className="label">Model</span>
              <select value={model} onChange={(e) => setModel(e.target.value)} className="select">
                {provider.models.map((m) => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5">
              <span className="label flex items-center justify-between">
                <span>API key</span>
                <span className="flex items-center gap-2 text-fg-dim normal-case tracking-normal text-[11px] font-normal">
                  <a href={provider.signup} target="_blank" rel="noopener noreferrer"
                     className="text-accent hover:text-accent-bright inline-flex items-center gap-1">
                    Sign up <ExternalLink className="w-3 h-3" />
                  </a>
                  <a href={provider.apiKey} target="_blank" rel="noopener noreferrer"
                     className="text-accent hover:text-accent-bright inline-flex items-center gap-1">
                    Get key <ExternalLink className="w-3 h-3" />
                  </a>
                </span>
              </span>
              <div className="flex gap-2">
                <input
                  type={showKey ? "text" : "password"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={provider.placeholder}
                  className="input font-mono"
                />
                <button type="button" onClick={() => setShowKey((s) => !s)} className="btn-secondary !p-2">
                  {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </label>
          </div>

          <div className="mt-5 flex items-center justify-between">
            <div className="text-xs text-fg-dim flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-status-engaged" />
              Encrypted with AES-256-GCM before storage. Never returned to the browser.
            </div>
            <button onClick={() => setStep(2)} className="btn-send">
              Continue <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </Card>
      )}

      {/* Step 2 — Primary agent */}
      {step === 2 && (
        <Card title="Pick your primary agent" icon={<Cog className="w-4 h-4" />}>
          <p className="text-sm text-fg-muted mb-4">
            The primary agent is who you talk to first. You can chat with all of them — switch in the dropdown anytime.
          </p>
          <div className="grid sm:grid-cols-2 gap-3">
            {AGENTS.map((a) => (
              <button
                key={a.key}
                type="button"
                onClick={() => setPrimaryAgent(a.key)}
                className={`text-left rounded-lg border p-3.5 transition-all ${
                  primaryAgent === a.key
                    ? "border-accent bg-accent/10 shadow-[0_0_16px_-6px_rgba(0,212,255,0.5)]"
                    : "border-bg-border bg-bg-elev hover:border-accent/40"
                }`}
              >
                <div className={`text-xs font-bold uppercase tracking-[0.14em] ${a.color} mb-1`}>
                  {a.label}
                </div>
                <div className="text-xs text-fg-muted">{a.role}</div>
              </button>
            ))}
          </div>
          <div className="mt-5 flex items-center justify-between">
            <button onClick={() => setStep(1)} className="btn-secondary text-sm">
              Back
            </button>
            <button onClick={() => setStep(3)} className="btn-send">
              Continue <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </Card>
      )}

      {/* Step 3 — Optional local pairing */}
      {step === 3 && (
        <Card title="Connect your Claude Code CLI — optional" icon={<Monitor className="w-4 h-4" />}>
          <p className="text-sm text-fg-muted mb-4">
            For full file-system access AND to power your chat with your local Claude Code subscription instead of the API key you just pasted, install the OASIS bridge on this machine. <strong className="text-fg">Skip if you'd rather use cloud mode</strong> — chat works fine either way, and you can install later from Settings → Devices.
          </p>
          <div className="rounded-lg border border-bg-border bg-bg-elev p-4 space-y-3">
            <div className="flex items-center gap-2 text-xs text-fg-muted">
              <span className="agent-pill-dot" />
              One-click installer — bridge pairs to your dashboard automatically
            </div>
            <div className="text-xs text-fg-dim">
              Mints a single-use pair-code, hands you a one-liner for your terminal, and watches for the bridge to come online. The bridge runs as a small daemon on this machine; pair-time only, opt-in writes, full audit log.
            </div>
            <button
              type="button"
              onClick={() => setInstallerOpen(true)}
              className="btn-primary inline-flex items-center gap-2 text-sm"
            >
              <Download className="w-4 h-4" />
              Install Claude Code CLI bridge on this machine
            </button>
          </div>
          {installerOpen && <InstallBridgeModal onClose={() => setInstallerOpen(false)} />}

          {error && (
            <div className="mt-4 flex items-start gap-2 rounded-md border border-status-warm/40 bg-status-warm/10 p-3 text-sm text-status-warm">
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <div className="font-mono break-all">{error}</div>
            </div>
          )}

          <div className="mt-5 flex items-center justify-between">
            <button onClick={() => setStep(2)} className="btn-secondary text-sm" disabled={submitting}>
              Back
            </button>
            <div className="flex gap-2">
              <Link href="/" className="btn-secondary text-sm">
                Skip + go to dashboard
              </Link>
              <button onClick={finish} disabled={submitting} className="btn-send">
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                {submitting ? "Saving…" : "Finish setup"}
              </button>
            </div>
          </div>

          <div className="mt-4 text-[11px] text-fg-dim">
            Signed in as <span className="text-fg-muted font-mono">{userEmail}</span>
          </div>
        </Card>
      )}
    </div>
  );
}

function Card({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-bg-border bg-bg-elev/60 backdrop-blur-xl p-6 shadow-[0_8px_40px_-12px_rgba(0,212,255,0.15)]">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-7 h-7 rounded-lg bg-accent/15 border border-accent/30 flex items-center justify-center text-accent">
          {icon}
        </div>
        <h2 className="text-base font-bold text-fg">{title}</h2>
      </div>
      {children}
    </div>
  );
}
