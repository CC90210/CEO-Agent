"use client";

/**
 * 3-step pre-signup configurator:
 *  1. Pick the agent role (Bravo / Atlas / Maven / Aura / Hermes / Custom)
 *  2. Personalize (name, brand, north-star MRR / focus area)
 *  3. Generate a one-line install command + show the buy/oasisai link
 *
 * Output is intentionally a copy-pasteable install one-liner — the visitor
 * is not yet signed up, so we can't auto-execute on their machine. The
 * one-liner runs `bravo setup` with their answers pre-baked.
 */

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Check,
  Copy,
  Sparkles,
  Cpu,
  ExternalLink,
  ChevronDown,
} from "lucide-react";

type OS = "windows" | "macos" | "linux" | "unknown";

function _detectOS(): OS {
  if (typeof navigator === "undefined") return "unknown";
  const ua = navigator.userAgent.toLowerCase();
  if (ua.includes("win")) return "windows";
  if (ua.includes("mac")) return "macos";
  if (ua.includes("linux") || ua.includes("x11")) return "linux";
  return "unknown";
}

const AGENTS = [
  {
    key: "bravo",
    label: "Bravo",
    role: "CEO / Lead architect — business ops, sales, content voice",
    repo: "Business-Empire-Agent",
    color: "text-accent",
  },
  {
    key: "atlas",
    label: "Atlas",
    role: "CFO — capital allocation, tax, trades, FIRE planning",
    repo: "CFO-Agent",
    color: "text-emerald-400",
  },
  {
    key: "maven",
    label: "Maven",
    role: "CMO — content, paid ads, brand voice, funnels",
    repo: "CMO-Agent",
    color: "text-pink-400",
  },
  {
    key: "aura",
    label: "Aura",
    role: "Life agent — habits, sleep, gym, smart home, voice",
    repo: "Aura-Home-Agent",
    color: "text-purple-400",
  },
  {
    key: "hermes",
    label: "Hermes",
    role: "Commerce ops — PO/POS, EDI, chargebacks, A2000 ERP",
    repo: "hermes",
    color: "text-amber-400",
  },
  {
    key: "custom",
    label: "Custom",
    role: "Build your own from a Bravo fork — wizard scaffolds the new role",
    repo: "Business-Empire-Agent",
    color: "text-fg",
  },
];

type Personalization = {
  full_name: string;
  brand: string;
  north_star: string;
};

export function ConfigureFlow() {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [agentKey, setAgentKey] = useState<string>("bravo");
  const [p, setP] = useState<Personalization>({
    full_name: "",
    brand: "",
    north_star: "",
  });
  const [copied, setCopied] = useState(false);
  const [os, setOs] = useState<OS>("unknown");
  const [showAllPlatforms, setShowAllPlatforms] = useState(false);

  useEffect(() => {
    setOs(_detectOS());
  }, []);

  const agent = AGENTS.find((a) => a.key === agentKey)!;

  const psInstall = `# Windows (PowerShell, run as your user — no admin needed)
$env:OASIS_PROFILE="${agentKey}"
$env:OASIS_OPERATOR_NAME="${p.full_name || 'Your Name'}"
$env:OASIS_BRAND="${p.brand || 'Your Brand'}"
$env:OASIS_NORTH_STAR="${p.north_star || 'Your goal'}"
irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.ps1 | iex`;
  const bashInstall = `# macOS / Linux / WSL
export OASIS_PROFILE="${agentKey}"
export OASIS_OPERATOR_NAME="${p.full_name || 'Your Name'}"
export OASIS_BRAND="${p.brand || 'Your Brand'}"
export OASIS_NORTH_STAR="${p.north_star || 'Your goal'}"
curl -fsSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.sh | bash`;

  function copy(text: string) {
    if (typeof navigator === "undefined" || !navigator.clipboard) return;
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="space-y-5">
      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {[1, 2, 3].map((n) => (
          <div key={n} className="flex items-center gap-2">
            <div
              className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                step >= n
                  ? "bg-accent text-bg-deep shadow-[0_0_12px_-2px_rgba(0,212,255,0.6)]"
                  : "bg-bg-elev text-fg-dim border border-bg-border"
              }`}
            >
              {step > n ? <Check className="w-3.5 h-3.5" /> : n}
            </div>
            {n < 3 && <div className={`h-px w-12 ${step > n ? "bg-accent" : "bg-bg-border"}`} />}
          </div>
        ))}
      </div>

      {/* Step 1 — pick agent */}
      {step === 1 && (
        <Card title="Pick the agent" icon={<Cpu className="w-4 h-4" />}>
          <div className="grid sm:grid-cols-2 gap-3">
            {AGENTS.map((a) => (
              <button
                key={a.key}
                type="button"
                onClick={() => setAgentKey(a.key)}
                className={`text-left rounded-lg border p-3.5 transition-all ${
                  agentKey === a.key
                    ? "border-accent bg-accent/10 shadow-[0_0_16px_-6px_rgba(0,212,255,0.5)]"
                    : "border-bg-border bg-bg-elev hover:border-accent/40"
                }`}
              >
                <div className={`text-xs font-bold uppercase tracking-[0.14em] ${a.color} mb-1`}>
                  {a.label}
                </div>
                <div className="text-xs text-fg-muted">{a.role}</div>
                <div className="text-[10px] text-fg-dim mt-1.5 font-mono">{a.repo}</div>
              </button>
            ))}
          </div>
          <div className="mt-5 flex items-center justify-end">
            <button onClick={() => setStep(2)} className="btn-send">
              Continue <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </Card>
      )}

      {/* Step 2 — personalize */}
      {step === 2 && (
        <Card title="Personalize" icon={<Sparkles className="w-4 h-4" />}>
          <p className="text-sm text-fg-muted mb-4">
            These get baked into the install command and pre-fill the setup wizard. You can edit any of them later in your dashboard.
          </p>
          <div className="space-y-3">
            <label className="block">
              <span className="label">Your name</span>
              <input
                className="input"
                value={p.full_name}
                onChange={(e) => setP({ ...p, full_name: e.target.value })}
                placeholder="Jane Doe"
              />
            </label>
            <label className="block">
              <span className="label">Brand or company</span>
              <input
                className="input"
                value={p.brand}
                onChange={(e) => setP({ ...p, brand: e.target.value })}
                placeholder="Acme AI"
              />
            </label>
            <label className="block">
              <span className="label">Your north-star goal</span>
              <input
                className="input"
                value={p.north_star}
                onChange={(e) => setP({ ...p, north_star: e.target.value })}
                placeholder={
                  agentKey === "atlas"
                    ? "Hit $1M net worth by 30"
                    : agentKey === "maven"
                      ? "10K qualified leads / quarter"
                      : "$10K MRR by year-end"
                }
              />
            </label>
          </div>
          <div className="mt-5 flex items-center justify-between">
            <button onClick={() => setStep(1)} className="btn-secondary text-sm">
              Back
            </button>
            <button onClick={() => setStep(3)} className="btn-send">
              Generate install <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </Card>
      )}

      {/* Step 3 — install + buy */}
      {step === 3 && (
        <Card title="Install on your machine" icon={<Check className="w-4 h-4" />}>
          <p className="text-sm text-fg-muted mb-4">
            Open a terminal on your computer and paste one of these. The installer clones the <code className="text-accent">{agent.repo}</code> repo, runs the setup wizard with your answers pre-filled, and starts the local bridge so the dashboard connects automatically.
          </p>

          {os !== "unknown" ? (
            <>
              <div className="text-[11px] uppercase tracking-wider font-bold text-fg-muted mb-1.5">
                Detected: <span className="text-accent">{os === "windows" ? "Windows" : os === "macos" ? "macOS" : "Linux"}</span> — paste this in your terminal
              </div>
              <CodeBlock
                label={os === "windows" ? "Windows · PowerShell" : os === "macos" ? "macOS · Terminal" : "Linux · bash"}
                code={os === "windows" ? psInstall : bashInstall}
                onCopy={copy}
                copied={copied}
              />
              <button
                type="button"
                onClick={() => setShowAllPlatforms((v) => !v)}
                className="text-xs text-fg-dim hover:text-accent transition-colors inline-flex items-center gap-1 mb-3"
              >
                <ChevronDown className={`w-3 h-3 transition-transform ${showAllPlatforms ? "rotate-180" : ""}`} />
                {showAllPlatforms ? "Hide" : "Show"} other platforms
              </button>
              {showAllPlatforms && (
                <div className="rounded-md border border-bg-border bg-bg-deep/50 p-3 mb-4">
                  {os !== "windows" && <CodeBlock label="Windows · PowerShell" code={psInstall} onCopy={copy} copied={copied} />}
                  {os === "windows" && <CodeBlock label="macOS / Linux / WSL · bash" code={bashInstall} onCopy={copy} copied={copied} />}
                </div>
              )}
            </>
          ) : (
            <>
              <CodeBlock label="Windows · PowerShell" code={psInstall} onCopy={copy} copied={copied} />
              <CodeBlock label="macOS / Linux / WSL · bash" code={bashInstall} onCopy={copy} copied={copied} />
            </>
          )}

          <div className="rounded-lg border border-accent/30 bg-accent/5 p-4 mt-5">
            <h3 className="text-sm font-bold text-fg mb-1.5 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-accent" /> After install
            </h3>
            <ol className="text-xs text-fg-muted space-y-1 list-decimal list-inside leading-relaxed">
              <li>
                Sign up at <Link href="/signup" className="text-accent hover:underline">
                  the dashboard
                </Link> with the same email the wizard asked for.
              </li>
              <li>
                The bridge starts automatically. Open <code className="text-accent">agent-dashboard-cc90210.vercel.app/agents</code> — chat header turns cyan when paired.
              </li>
              <li>
                Paste an OpenRouter key (or Anthropic / OpenAI) when the wizard asks. <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer" className="text-accent hover:underline inline-flex items-center gap-0.5">Get OpenRouter key <ExternalLink className="w-3 h-3" /></a>
              </li>
            </ol>
          </div>

          <div className="rounded-lg border border-bg-border bg-bg-elev p-4 mt-4">
            <h3 className="text-sm font-bold text-fg mb-1.5">Want a managed deploy?</h3>
            <p className="text-xs text-fg-muted mb-3 leading-relaxed">
              If you&apos;d rather not run the bridge yourself, OASIS AI offers managed deploys — we host the agent on your behalf with full support and SOC 2 compliance.
            </p>
            <a
              href="https://oasisai.work#pricing"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary inline-flex items-center gap-1.5 text-xs"
            >
              See pricing on oasisai.work <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          <div className="mt-5 flex items-center justify-between">
            <button onClick={() => setStep(2)} className="btn-secondary text-sm">
              Back
            </button>
            <Link href="/signup" className="btn-send">
              I have it installed → Sign up <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </Card>
      )}
    </div>
  );
}

function Card({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
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

function CodeBlock({
  label,
  code,
  onCopy,
  copied,
}: {
  label: string;
  code: string;
  onCopy: (s: string) => void;
  copied: boolean;
}) {
  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] uppercase tracking-wider font-bold text-fg-muted">
          {label}
        </span>
        <button
          onClick={() => onCopy(code)}
          className="text-xs text-fg-dim hover:text-accent transition-colors inline-flex items-center gap-1"
        >
          {copied ? <Check className="w-3 h-3 text-status-engaged" /> : <Copy className="w-3 h-3" />}
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre className="rounded-md bg-bg-deep border border-bg-border p-3 text-[11px] font-mono text-fg overflow-x-auto whitespace-pre">
        <code>{code}</code>
      </pre>
    </div>
  );
}
