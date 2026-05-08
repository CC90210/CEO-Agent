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
import { AGENT_QUESTIONS, answersToEnvLines, type Question } from "@/lib/agent-questionnaire";

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
    key: "life-preservation",
    label: "Lumen",
    role: "Memory keeper — captures voice, stories, and presence of loved ones for surviving family",
    repo: "life-preservation",
    color: "text-amber-200",
  },
  {
    key: "custom",
    label: "Custom",
    role: "Build your own from a Bravo fork — wizard scaffolds the new role",
    repo: "Business-Empire-Agent",
    color: "text-fg",
  },
];

export function ConfigureFlow() {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [agentKey, setAgentKey] = useState<string>("bravo");
  // Per-agent answers — keyed by question.key (the env-var suffix).
  // Switching agents resets answers since each agent has its own schema.
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [copied, setCopied] = useState(false);
  const [os, setOs] = useState<OS>("unknown");
  const [showAllPlatforms, setShowAllPlatforms] = useState(false);

  useEffect(() => {
    setOs(_detectOS());
  }, []);

  // Reset answers when the agent changes — each agent has its own schema.
  useEffect(() => {
    setAnswers({});
  }, [agentKey]);

  const agent = AGENTS.find((a) => a.key === agentKey)!;
  const questions: Question[] = AGENT_QUESTIONS[agentKey] || AGENT_QUESTIONS.custom;

  // The OASIS_PROFILE env var carries the agent slug so the post-install
  // wizard knows which agent + which schema to load. All other answers
  // get baked as OASIS_<KEY>=<VALUE> via answersToEnvLines.
  const profileLine = (kind: "powershell" | "bash") =>
    kind === "powershell"
      ? `$env:OASIS_PROFILE="${agentKey}"`
      : `export OASIS_PROFILE="${agentKey}"`;

  const psInstall = [
    "# Windows (PowerShell, run as your user — no admin needed)",
    profileLine("powershell"),
    answersToEnvLines(answers, "powershell"),
    "irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.ps1 | iex",
  ]
    .filter((s) => s && s.length > 0)
    .join("\n");
  const bashInstall = [
    "# macOS / Linux / WSL",
    profileLine("bash"),
    answersToEnvLines(answers, "bash"),
    "curl -fsSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.sh | bash",
  ]
    .filter((s) => s && s.length > 0)
    .join("\n");

  // Validation — block the Generate-install button until all required
  // questions have answers. Otherwise the install command bakes empty
  // env vars and the wizard can't pre-fill the profile correctly.
  const missingRequired = questions
    .filter((q) => q.required)
    .filter((q) => !(answers[q.key] && answers[q.key].trim().length > 0));
  const canAdvance = missingRequired.length === 0;

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

      {/* Step 2 — personalize (dynamic per-agent questionnaire) */}
      {step === 2 && (
        <Card title={`Personalize ${agent.label}`} icon={<Sparkles className="w-4 h-4" />}>
          <p className="text-sm text-fg-muted mb-4">
            These answers are tailored to <strong className="text-fg">{agent.label}</strong> — they get baked into the install command and pre-fill the setup wizard. You can edit any of them later in your dashboard.
          </p>
          <div className="space-y-4">
            {questions.map((q) => (
              <QuestionField
                key={q.key}
                question={q}
                value={answers[q.key] || ""}
                onChange={(v) => setAnswers({ ...answers, [q.key]: v })}
              />
            ))}
          </div>
          {!canAdvance && (
            <div className="mt-4 text-[11px] text-status-warm">
              {missingRequired.length} required question{missingRequired.length === 1 ? "" : "s"} left: {missingRequired.map((q) => q.label).join(", ")}.
            </div>
          )}
          <div className="mt-5 flex items-center justify-between">
            <button onClick={() => setStep(1)} className="btn-secondary text-sm">
              Back
            </button>
            <button
              onClick={() => canAdvance && setStep(3)}
              disabled={!canAdvance}
              className={`btn-send ${!canAdvance ? "opacity-50 cursor-not-allowed" : ""}`}
            >
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

function QuestionField({
  question,
  value,
  onChange,
}: {
  question: Question;
  value: string;
  onChange: (v: string) => void;
}) {
  const id = `q-${question.key}`;
  return (
    <label htmlFor={id} className="block">
      <span className="label flex items-center gap-1.5">
        {question.label}
        {question.required && (
          <span className="text-status-warm text-[10px]" aria-label="required">*</span>
        )}
      </span>
      {question.type === "select" && question.options ? (
        <select
          id={id}
          className="input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">— pick one —</option>
          {question.options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      ) : question.type === "textarea" ? (
        <textarea
          id={id}
          className="input min-h-[88px] font-mono text-xs"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={question.placeholder}
          rows={4}
        />
      ) : (
        <input
          id={id}
          className="input"
          type={question.type === "number" ? "number" : "text"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={question.placeholder}
        />
      )}
      {question.help && (
        <span className="block text-[11px] text-fg-dim mt-1 leading-relaxed">
          {question.help}
        </span>
      )}
    </label>
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
