"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowRight,
  Building2,
  CheckCircle2,
  ChevronLeft,
  Loader2,
  ShoppingBag,
  Sparkles,
  Store,
  Users,
} from "lucide-react";
import {
  TEMPLATES,
  WIZARD_QUESTIONS,
  type TemplateKey,
  type WizardQuestion,
} from "@/lib/manifest/templates";
import { AGENT_REGISTRY } from "@/lib/agents";

type Answers = Record<string, string | string[]>;

type Step =
  | "industry"
  | "questions"
  | "agents"
  | "agent_setup" // Phase J — per-agent setup questions for picked agents
  | "brand"
  | "confirm"
  | "submitting"
  | "done";

/**
 * Agent packages — declarative groups exposed in the multi-select step.
 * The wizard pre-checks the industry-template defaults, but the user can
 * pick any combination across packages (e.g. SunBiz + a Lumen sub-agent).
 *
 * Each entry references AGENT_REGISTRY by slug; if a slug isn't in the
 * registry it's filtered out at render time so deprecated agents auto-
 * disappear from the picker.
 */
const AGENT_PACKAGES: { id: string; label: string; description: string; agents: string[] }[] = [
  {
    id: "oasis_csuite",
    label: "OASIS C-Suite",
    description: "Bravo runs operations, Atlas is your CFO, Maven your CMO. Aura, Hermes, Lumen handle life, commerce, memory.",
    agents: ["bravo", "atlas", "maven", "aura", "hermes", "life-preservation"],
  },
  {
    id: "sunbiz",
    label: "SunBiz Funding Pack",
    description: "Solara runs the back office (pipeline, applications, lender match, renewals). Helios is the sales voice (cold SMS, follow-ups, closing).",
    agents: ["solara", "helios"],
  },
];

/**
 * Default agents pre-checked when the user picks an industry. Derived from
 * each template's own agents[] list so there's one source of truth — if a
 * template changes which agents it ships with, the wizard reflects it
 * automatically with no second edit.
 */
function defaultAgentsForTemplate(k: TemplateKey): string[] {
  return TEMPLATES[k].agents.filter((a) => a.enabled).map((a) => a.slug);
}

const INDUSTRIES: {
  key: TemplateKey;
  title: string;
  blurb: string;
  Icon: typeof Building2;
}[] = [
  { key: "real_estate", title: "Real Estate", blurb: "Brokerages, teams, individual agents. Leads → properties → deals → commissions.", Icon: Building2 },
  { key: "business_funding", title: "Business Funding", blurb: "MCAs, term loans, broker shops. Applications → offers → funded deals → renewals.", Icon: Store },
  { key: "ecommerce", title: "E-commerce", blurb: "Stores moving real product. Orders → customers → inventory → marketing.", Icon: ShoppingBag },
  { key: "agency", title: "Agency", blurb: "Service businesses delivering client work. Clients → projects → retainers → invoices.", Icon: Users },
  { key: "custom", title: "Custom (C-suite)", blurb: "Premium done-for-you package with Bravo, Atlas, and Maven. Setup required — we tailor it to your operation before you go live.", Icon: Sparkles },
];

/** Color tag per tier label — kept declarative so it's easy to retune. */
function tierToneClasses(label: string): string {
  switch (label) {
    case "Free":       return "border-fg-dim/40 bg-fg-dim/10 text-fg-muted";
    case "Starter":    return "border-emerald-400/40 bg-emerald-400/10 text-emerald-300";
    case "Pro":        return "border-accent/40 bg-accent/10 text-accent";
    case "Enterprise": return "border-amber-400/40 bg-amber-400/10 text-amber-300";
    default:           return "border-bg-border bg-bg-elev text-fg-muted";
  }
}

function slugifyClient(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 62) || "tenant";
}

export function OnboardingWizardClient({ userEmail }: { userEmail?: string }) {
  const router = useRouter();
  const [step, setStep] = useState<Step>("industry");
  const [template, setTemplate] = useState<TemplateKey | null>(null);
  const [answers, setAnswers] = useState<Answers>({});
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
  // Phase J — per-agent setup answers. Map<agentSlug, Map<questionId, value>>.
  // Populated during the agent_setup step from AGENT_REGISTRY[slug].setup_questions.
  // Submitted alongside the wizard body so the API can write each agent
  // binding's setup_answers field. Defaults pre-filled from question.default
  // when the step first renders so operators only adjust what differs.
  const [agentSetupAnswers, setAgentSetupAnswers] = useState<
    Record<string, Record<string, string | number | boolean>>
  >({});
  const [slug, setSlug] = useState<string>("");
  const [slugManuallyEdited, setSlugManuallyEdited] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const questions: WizardQuestion[] = useMemo(
    () => (template ? WIZARD_QUESTIONS[template] : []),
    [template]
  );

  const brandName = (answers.brand_name as string) || "";
  const tagline = (answers.tagline as string) || "";

  const derivedSlug = brandName ? slugifyClient(brandName) : "";
  const effectiveSlug = slugManuallyEdited ? slug : derivedSlug;

  function pickIndustry(k: TemplateKey) {
    setTemplate(k);
    // Pre-fill agent selection with the industry's default package so the
    // user can confirm without unchecking anything. They can still add/
    // remove anything in the agents step.
    setSelectedAgents(defaultAgentsForTemplate(k));
    setStep("questions");
  }

  function toggleAgent(slug: string) {
    setSelectedAgents((prev) =>
      prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug]
    );
  }

  function answerKeyChange(id: string, value: string | string[]) {
    setAnswers((prev) => ({ ...prev, [id]: value }));
  }

  function requiredQuestionsAnswered(): boolean {
    return questions
      .filter((q) => q.required)
      .every((q) => {
        const v = answers[q.id];
        if (v === undefined) return false;
        if (typeof v === "string") return v.trim().length > 0;
        return Array.isArray(v) && v.length > 0;
      });
  }

  async function submit() {
    if (!template) return;
    setError(null);
    setStep("submitting");
    try {
      // Stamp selected_agents into answers so wizard-finalize can override
      // the template's default agents[] with the user's actual picks.
      const finalAnswers = { ...answers, selected_agents: selectedAgents };
      const res = await fetch("/api/onboarding/wizard", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          template,
          slug: effectiveSlug,
          answers: finalAnswers,
          // Phase J — per-agent setup answers. Map<agentSlug, Record<qid, val>>.
          // wizard-finalize stamps these onto each agent binding's
          // setup_answers field; the persona resolver folds them into
          // the agent's system prompt on every chat turn.
          agent_setup_answers: agentSetupAnswers,
        }),
      });
      const data = (await res.json()) as
        | { ok: true; slug: string; version: number }
        | { ok: false; error: string; message?: string };
      if (!data.ok) {
        if (data.error === "slug_taken") {
          setError("That URL slug is already in use. Edit it and try again.");
          setStep("confirm");
          return;
        }
        setError(data.message || data.error);
        setStep("confirm");
        return;
      }
      setStep("done");
      router.push(`/t/${data.slug}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "network_error");
      setStep("confirm");
    }
  }

  return (
    <div className="min-h-screen bg-bg-deep text-fg flex items-center justify-center px-6 py-10">
      <div className="w-full max-w-4xl space-y-8">
        <Header step={step} />

        {step === "industry" && (
          <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {INDUSTRIES.map(({ key, title, blurb, Icon }) => {
              const tpl = TEMPLATES[key];
              const tier = tpl.tier;
              const agents = tpl.agents || [];
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => pickIndustry(key)}
                  className="group text-left rounded-2xl border border-bg-border bg-bg-elev/40 hover:border-accent/40 hover:bg-bg-elev/70 p-5 transition-all flex flex-col"
                >
                  <div className="flex items-center justify-between gap-2.5">
                    <div className="flex items-center gap-2.5">
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 text-accent group-hover:bg-accent group-hover:text-bg transition-all">
                        <Icon className="h-5 w-5" />
                      </div>
                      <div className="font-bold text-base text-fg">{title}</div>
                    </div>
                    {tier && (
                      <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${tierToneClasses(tier.label)}`}>
                        {tier.label}
                      </span>
                    )}
                  </div>
                  <p className="mt-3 text-sm text-fg-muted leading-relaxed">{blurb}</p>
                  {tier && (
                    <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
                      <TierMetaRow label="Setup" value={tier.setup_complexity} />
                      <TierMetaRow label="Price" value={tier.monthly_price_hint || "—"} />
                      <TierMetaRow
                        label="Agents"
                        value={`${agents.length} included`}
                        full
                      />
                      {tier.summary && (
                        <div className="col-span-2 text-[11px] text-fg-dim italic">
                          {tier.summary}
                        </div>
                      )}
                    </div>
                  )}
                  <div className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-accent">
                    Pick this template <ArrowRight className="h-3.5 w-3.5" />
                  </div>
                </button>
              );
            })}
          </section>
        )}

        {step === "questions" && template && (
          <section className="rounded-2xl border border-bg-border bg-bg-elev/40 p-6 space-y-5">
            <div>
              <div className="text-[10px] uppercase tracking-[0.16em] text-fg-dim font-bold">
                {INDUSTRIES.find((i) => i.key === template)?.title}
              </div>
              <h2 className="mt-1 text-xl font-bold">A few quick questions</h2>
              <p className="text-sm text-fg-muted mt-1">
                Skip anything optional. The AI editor can change all of this later.
              </p>
            </div>

            <div className="space-y-4">
              {questions.map((q) => (
                <QuestionField
                  key={q.id}
                  question={q}
                  value={answers[q.id]}
                  onChange={(v) => answerKeyChange(q.id, v)}
                />
              ))}
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={() => setStep("industry")}
                className="btn-secondary inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Back
              </button>
              <button
                type="button"
                onClick={() => setStep("agents")}
                disabled={!requiredQuestionsAnswered()}
                className="btn-send inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
              >
                Continue <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </section>
        )}

        {step === "agents" && template && (
          <section className="rounded-2xl border border-bg-border bg-bg-elev/40 p-6 space-y-5">
            <div>
              <h2 className="text-xl font-bold">Pick your agents</h2>
              <p className="text-sm text-fg-muted mt-1">
                Multi-select across packages — your shell can run the C-suite, a SunBiz pack, or any mix. We pre-checked the typical setup for{" "}
                <strong className="text-fg">{INDUSTRIES.find((i) => i.key === template)?.title}</strong>; adjust freely. You can chat with all enabled agents and switch in the dropdown.
              </p>
            </div>

            <div className="space-y-4">
              {AGENT_PACKAGES.map((pkg) => {
                const agentsInPackage = pkg.agents.filter((slug) => AGENT_REGISTRY[slug]);
                if (agentsInPackage.length === 0) return null;
                const allChecked = agentsInPackage.every((a) => selectedAgents.includes(a));
                const someChecked = agentsInPackage.some((a) => selectedAgents.includes(a));
                return (
                  <div key={pkg.id} className="rounded-xl border border-bg-border bg-bg-deep/40 p-4 space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <div className="font-bold text-sm text-fg">{pkg.label}</div>
                        <p className="mt-1 text-xs text-fg-muted leading-relaxed">{pkg.description}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          if (allChecked) {
                            setSelectedAgents((prev) => prev.filter((s) => !agentsInPackage.includes(s)));
                          } else {
                            setSelectedAgents((prev) => Array.from(new Set([...prev, ...agentsInPackage])));
                          }
                        }}
                        className="shrink-0 text-[10px] uppercase tracking-wider font-bold text-accent hover:text-accent/80"
                      >
                        {allChecked ? "Clear all" : someChecked ? "Add the rest" : "Select all"}
                      </button>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {agentsInPackage.map((slug) => {
                        const info = AGENT_REGISTRY[slug];
                        const active = selectedAgents.includes(slug);
                        return (
                          <button
                            key={slug}
                            type="button"
                            onClick={() => toggleAgent(slug)}
                            className={`text-left rounded-lg border px-3 py-2 text-sm transition-all ${
                              active
                                ? "border-accent bg-accent/10 text-fg"
                                : "border-bg-border bg-bg-deep/40 text-fg-muted hover:border-accent/40 hover:bg-bg-elev/40"
                            }`}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className={`font-bold ${active ? "text-fg" : "text-fg-muted"} text-xs`}>
                                {info.label}
                              </span>
                              <span className={`text-[10px] ${active ? "text-accent" : "text-fg-dim"}`}>
                                {active ? "✓" : ""}
                              </span>
                            </div>
                            <div className="text-[10px] text-fg-dim mt-0.5 truncate">{info.tagline}</div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="rounded-xl border border-bg-border bg-bg-deep/40 px-4 py-2.5 text-xs text-fg-muted">
              {selectedAgents.length === 0
                ? "No agents selected — your shell will render with zero agents. You can add them later in Settings."
                : `${selectedAgents.length} agent${selectedAgents.length === 1 ? "" : "s"} selected.`}
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={() => setStep("questions")}
                className="btn-secondary inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Back
              </button>
              <button
                type="button"
                onClick={() => {
                  // Phase J — if any selected agent has setup_questions, route
                  // through agent_setup step first. Otherwise skip straight
                  // to brand (existing behavior). Pre-fill defaults so the
                  // operator only adjusts what differs.
                  const needsSetup = selectedAgents.some(
                    (slug) => (AGENT_REGISTRY[slug]?.setup_questions?.length || 0) > 0,
                  );
                  if (needsSetup) {
                    setAgentSetupAnswers((prev) => {
                      const next = { ...prev };
                      for (const slug of selectedAgents) {
                        const qs = AGENT_REGISTRY[slug]?.setup_questions || [];
                        if (!qs.length) continue;
                        next[slug] = { ...(next[slug] || {}) };
                        for (const q of qs) {
                          if (next[slug][q.id] === undefined && q.default !== undefined) {
                            next[slug][q.id] = q.default;
                          }
                        }
                      }
                      return next;
                    });
                    setStep("agent_setup");
                  } else {
                    setStep("brand");
                  }
                }}
                className="btn-send inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
              >
                Continue <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </section>
        )}

        {step === "agent_setup" && (
          <section className="rounded-2xl border border-bg-border bg-bg-elev/40 p-6 space-y-5">
            <div>
              <h2 className="text-xl font-bold">Configure your agents</h2>
              <p className="text-sm text-fg-muted mt-1">
                Quick setup per agent so each one knows your specifics from
                turn one. You can change any of this later in{" "}
                <span className="font-mono text-fg">/settings</span>.
              </p>
            </div>

            <div className="space-y-5">
              {selectedAgents
                .filter((slug) => (AGENT_REGISTRY[slug]?.setup_questions?.length || 0) > 0)
                .map((slug) => {
                  const info = AGENT_REGISTRY[slug];
                  if (!info) return null;
                  const qs = info.setup_questions || [];
                  const slugAnswers = agentSetupAnswers[slug] || {};
                  const setAnswer = (qid: string, val: string | number | boolean) => {
                    setAgentSetupAnswers((prev) => ({
                      ...prev,
                      [slug]: { ...(prev[slug] || {}), [qid]: val },
                    }));
                  };
                  return (
                    <div key={slug} className="rounded-xl border border-bg-border bg-bg-deep/40 p-4 space-y-3">
                      <div className="flex items-baseline gap-2 flex-wrap">
                        <div className={`font-bold text-base ${info.textClass}`}>{info.label}</div>
                        <div className="text-xs text-fg-dim">{info.role}</div>
                      </div>
                      <div className="space-y-3">
                        {qs.map((q) => (
                          <div key={q.id} className="space-y-1">
                            <label className="block">
                              <span className="text-xs font-bold text-fg block">
                                {q.label}
                                {q.required && <span className="text-status-warm ml-1">*</span>}
                              </span>
                              {q.description && (
                                <span className="text-[11px] text-fg-dim block mt-0.5 leading-relaxed">
                                  {q.description}
                                </span>
                              )}
                              {q.type === "text" && (
                                <input
                                  type="text"
                                  value={String(slugAnswers[q.id] ?? "")}
                                  onChange={(e) => setAnswer(q.id, e.target.value)}
                                  placeholder={q.placeholder}
                                  className="mt-1 w-full rounded-lg border border-bg-border bg-bg-deep/80 px-3 py-2 text-sm text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none"
                                />
                              )}
                              {q.type === "textarea" && (
                                <textarea
                                  value={String(slugAnswers[q.id] ?? "")}
                                  onChange={(e) => setAnswer(q.id, e.target.value)}
                                  placeholder={q.placeholder}
                                  rows={3}
                                  className="mt-1 w-full rounded-lg border border-bg-border bg-bg-deep/80 px-3 py-2 text-sm text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none"
                                />
                              )}
                              {q.type === "number" && (
                                <input
                                  type="number"
                                  value={String(slugAnswers[q.id] ?? "")}
                                  onChange={(e) => {
                                    const n = Number(e.target.value);
                                    setAnswer(q.id, isFinite(n) ? n : 0);
                                  }}
                                  placeholder={q.placeholder}
                                  className="mt-1 w-full rounded-lg border border-bg-border bg-bg-deep/80 px-3 py-2 text-sm text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none"
                                />
                              )}
                              {q.type === "select" && (
                                <select
                                  value={String(slugAnswers[q.id] ?? "")}
                                  onChange={(e) => setAnswer(q.id, e.target.value)}
                                  className="mt-1 w-full rounded-lg border border-bg-border bg-bg-deep/80 px-3 py-2 text-sm text-fg focus:border-accent/50 focus:outline-none"
                                >
                                  <option value="">— select —</option>
                                  {(q.options || []).map((o) => (
                                    <option key={o.value} value={o.value}>
                                      {o.label}
                                    </option>
                                  ))}
                                </select>
                              )}
                              {q.type === "boolean" && (
                                <label className="mt-1 inline-flex items-center gap-2 text-sm text-fg cursor-pointer">
                                  <input
                                    type="checkbox"
                                    checked={!!slugAnswers[q.id]}
                                    onChange={(e) => setAnswer(q.id, e.target.checked)}
                                    className="accent-accent"
                                  />
                                  <span>{slugAnswers[q.id] ? "Yes" : "No"}</span>
                                </label>
                              )}
                            </label>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={() => setStep("agents")}
                className="btn-secondary inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Back
              </button>
              <button
                type="button"
                onClick={() => {
                  // Validate required answers per agent. Block progression
                  // until they're filled.
                  const missing: string[] = [];
                  for (const slug of selectedAgents) {
                    const qs = AGENT_REGISTRY[slug]?.setup_questions || [];
                    const slugAnswers = agentSetupAnswers[slug] || {};
                    for (const q of qs) {
                      if (!q.required) continue;
                      const v = slugAnswers[q.id];
                      if (v === undefined || v === "" || v === null) {
                        missing.push(`${AGENT_REGISTRY[slug]?.label || slug}: ${q.label}`);
                      }
                    }
                  }
                  if (missing.length > 0) {
                    setError(`Required: ${missing.join(" · ")}`);
                    return;
                  }
                  setError(null);
                  setStep("brand");
                }}
                className="btn-send inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
              >
                Continue <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {error && (
              <div className="rounded-xl border border-status-warm/40 bg-status-warm/10 px-4 py-2.5 text-xs text-status-warm inline-flex items-start gap-2">
                <AlertCircle className="h-3.5 w-3.5 mt-0.5" />
                <span>{error}</span>
              </div>
            )}
          </section>
        )}

        {step === "brand" && (
          <section className="rounded-2xl border border-bg-border bg-bg-elev/40 p-6 space-y-5">
            <div>
              <h2 className="text-xl font-bold">Brand the shell</h2>
              <p className="text-sm text-fg-muted mt-1">
                The name shows in the sidebar and across every page. Pick the
                URL slug too — that&apos;s the path your team will use.
              </p>
            </div>

            <FieldRow label="Brand name" required>
              <input
                type="text"
                value={brandName}
                onChange={(e) => answerKeyChange("brand_name", e.target.value)}
                placeholder="OASIS AI"
                className="w-full rounded-xl border border-bg-border bg-bg-deep/80 px-4 py-2.5 text-sm text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none"
              />
            </FieldRow>

            <FieldRow label="Footer tagline">
              <input
                type="text"
                value={tagline}
                onChange={(e) => answerKeyChange("tagline", e.target.value)}
                placeholder="Only good things from now on."
                className="w-full rounded-xl border border-bg-border bg-bg-deep/80 px-4 py-2.5 text-sm text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none"
              />
            </FieldRow>

            <FieldRow
              label="URL slug"
              hint={`Your Command Center will live at /t/${effectiveSlug || "<slug>"}`}
            >
              <input
                type="text"
                value={effectiveSlug}
                onChange={(e) => {
                  setSlugManuallyEdited(true);
                  setSlug(e.target.value.toLowerCase());
                }}
                placeholder={derivedSlug || "your-tenant"}
                className="w-full rounded-xl border border-bg-border bg-bg-deep/80 px-4 py-2.5 text-sm text-fg font-mono focus:border-accent/50 focus:outline-none"
              />
            </FieldRow>

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={() => {
                  // Route back through agent_setup if any picked agent has
                  // setup questions, otherwise straight to agents (matches
                  // forward routing).
                  const needsSetup = selectedAgents.some(
                    (s) => (AGENT_REGISTRY[s]?.setup_questions?.length || 0) > 0,
                  );
                  setStep(needsSetup ? "agent_setup" : "agents");
                }}
                className="btn-secondary inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Back
              </button>
              <button
                type="button"
                onClick={() => setStep("confirm")}
                disabled={!brandName.trim() || !effectiveSlug}
                className="btn-send inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
              >
                Review <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </section>
        )}

        {step === "confirm" && template && (
          <section className="rounded-2xl border border-accent/25 bg-accent/5 p-6 space-y-5">
            <div>
              <h2 className="text-xl font-bold">Ready to create your Command Center</h2>
              <p className="text-sm text-fg-muted mt-1">
                We&apos;ll seed your manifest from the{" "}
                <strong className="text-fg">{INDUSTRIES.find((i) => i.key === template)?.title}</strong>{" "}
                template, fold in your answers, and drop you into{" "}
                <span className="font-mono text-accent">/t/{effectiveSlug}</span>.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <Summary label="Brand" value={brandName} />
              <Summary label="Slug" value={`/t/${effectiveSlug}`} mono />
              <Summary label="Industry" value={template.replace("_", " ")} />
              <Summary label="Tagline" value={tagline || "(default)"} />
              <Summary
                label="Agents"
                value={
                  selectedAgents.length === 0
                    ? "None — add later in Settings"
                    : selectedAgents
                        .map((slug) => AGENT_REGISTRY[slug]?.label || slug)
                        .join(", ")
                }
                full
              />
              {userEmail && <Summary label="Signed in as" value={userEmail} full />}
            </div>

            {/* Post-onboarding pointer. The wizard creates the manifest but
                doesn't wire an AI provider — the user does that in Settings
                immediately after. Surfacing the next step here means they
                don't land on /t/<slug> wondering why chat doesn't work. */}
            <div className="rounded-xl border border-bg-border bg-bg-deep/40 p-3 text-xs text-fg-muted leading-relaxed flex items-start gap-2">
              <Sparkles className="h-4 w-4 text-accent shrink-0 mt-0.5" />
              <div>
                <span className="text-fg font-bold">Next: connect an AI provider.</span>{" "}
                After this you'll land on your Command Center.
                Open <span className="font-mono text-accent">Settings → AI provider accounts</span>{" "}
                and connect an Anthropic, OpenRouter, OpenAI, or Google key — one click applies it to every enabled agent.
                Anthropic unlocks the native tool_use loop (records read/write, http, integrations).
              </div>
            </div>

            {error && (
              <div className="rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-2.5 text-sm text-red-200 inline-flex items-start gap-2">
                <AlertCircle className="h-4 w-4 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={() => setStep("brand")}
                className="btn-secondary inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Back
              </button>
              <button
                type="button"
                onClick={submit}
                className="btn-send inline-flex items-center gap-1.5 !px-4 !py-2 text-sm"
              >
                <CheckCircle2 className="h-4 w-4" />
                Create my Command Center
              </button>
            </div>
          </section>
        )}

        {step === "submitting" && (
          <section className="rounded-2xl border border-accent/30 bg-accent/10 p-8 text-center">
            <Loader2 className="h-8 w-8 animate-spin text-accent mx-auto" />
            <div className="mt-3 font-bold">Building your manifest...</div>
            <p className="text-sm text-fg-muted mt-1">
              Saving template + folding in your answers + creating audit row.
            </p>
          </section>
        )}

        {step === "done" && (
          <section className="rounded-2xl border border-emerald-400/30 bg-emerald-400/10 p-8 text-center">
            <CheckCircle2 className="h-8 w-8 text-emerald-300 mx-auto" />
            <div className="mt-3 font-bold">Created. Redirecting...</div>
          </section>
        )}
      </div>
    </div>
  );
}

function Header({ step }: { step: Step }) {
  const labels: Record<Step, string> = {
    industry: "Pick your industry",
    questions: "Tell us about your operation",
    agents: "Pick your agents",
    agent_setup: "Configure your agents",
    brand: "Brand the shell",
    confirm: "Review & create",
    submitting: "Building",
    done: "Done",
  };
  // 6 visible steps when agent_setup is rendered; we always show the
  // higher numerator so the agent_setup step lands on "4 / 6" rather
  // than re-labelling earlier steps. Steps that don't appear (e.g.
  // operators with no setup_questions on their agents) skip the number
  // — Header still renders cleanly because Step is a string union, not
  // an index.
  const number: Record<Step, string> = {
    industry: "1 / 6",
    questions: "2 / 6",
    agents: "3 / 6",
    agent_setup: "4 / 6",
    brand: "5 / 6",
    confirm: "6 / 6",
    submitting: "",
    done: "",
  };
  return (
    <header className="text-center space-y-2">
      <div className="inline-flex items-center gap-2 rounded-full border border-accent/25 bg-accent/5 px-3 py-1 text-xs text-accent">
        <Sparkles className="h-3.5 w-3.5" />
        Onboarding wizard {number[step] && <>· {number[step]}</>}
      </div>
      <h1 className="text-3xl font-black tracking-tight sm:text-4xl">{labels[step]}</h1>
    </header>
  );
}

function FieldRow({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-semibold text-fg">
        {label}
        {required && <span className="ml-1 text-accent">*</span>}
      </span>
      {children}
      {hint && <span className="block text-xs text-fg-dim">{hint}</span>}
    </label>
  );
}

function TierMetaRow({ label, value, full }: { label: string; value: string; full?: boolean }) {
  return (
    <div className={`flex items-baseline gap-1.5 ${full ? "col-span-2" : ""}`}>
      <span className="text-fg-dim uppercase tracking-wider font-bold text-[9px]">{label}</span>
      <span className="text-fg-muted">{value}</span>
    </div>
  );
}

function Summary({ label, value, mono, full }: { label: string; value: string; mono?: boolean; full?: boolean }) {
  return (
    <div className={`rounded-xl border border-bg-border bg-bg-elev/40 px-4 py-2.5 ${full ? "sm:col-span-2" : ""}`}>
      <div className="text-[10px] uppercase tracking-[0.16em] text-fg-dim font-bold">{label}</div>
      <div className={`mt-0.5 text-sm text-fg ${mono ? "font-mono text-accent truncate" : ""}`}>
        {value || "(empty)"}
      </div>
    </div>
  );
}

function QuestionField({
  question,
  value,
  onChange,
}: {
  question: WizardQuestion;
  value: string | string[] | undefined;
  onChange: (v: string | string[]) => void;
}) {
  if (question.kind === "text") {
    return (
      <FieldRow label={question.prompt} hint={question.hint} required={question.required}>
        <input
          type="text"
          value={(value as string) || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={question.placeholder}
          className="w-full rounded-xl border border-bg-border bg-bg-deep/80 px-4 py-2.5 text-sm text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none"
        />
      </FieldRow>
    );
  }
  if (question.kind === "longtext") {
    return (
      <FieldRow label={question.prompt} hint={question.hint} required={question.required}>
        <textarea
          rows={3}
          value={(value as string) || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={question.placeholder}
          className="w-full resize-none rounded-xl border border-bg-border bg-bg-deep/80 px-4 py-2.5 text-sm text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none"
        />
      </FieldRow>
    );
  }
  if (question.kind === "number") {
    return (
      <FieldRow label={question.prompt} hint={question.hint} required={question.required}>
        <input
          type="number"
          value={(value as string) || ""}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-xl border border-bg-border bg-bg-deep/80 px-4 py-2.5 text-sm text-fg focus:border-accent/50 focus:outline-none"
        />
      </FieldRow>
    );
  }
  if (question.kind === "single_choice") {
    return (
      <FieldRow label={question.prompt} hint={question.hint} required={question.required}>
        <div className="grid gap-2 sm:grid-cols-2">
          {(question.choices || []).map((c) => {
            const active = value === c.value;
            return (
              <button
                key={c.value}
                type="button"
                onClick={() => onChange(c.value)}
                className={`text-left rounded-xl border px-4 py-2.5 text-sm transition-all ${
                  active
                    ? "border-accent bg-accent-soft text-fg"
                    : "border-bg-border bg-bg-deep/40 text-fg-muted hover:border-accent/40 hover:bg-bg-elev/40"
                }`}
              >
                {c.label}
              </button>
            );
          })}
        </div>
      </FieldRow>
    );
  }
  // multi_choice
  const arr = Array.isArray(value) ? value : [];
  return (
    <FieldRow label={question.prompt} hint={question.hint} required={question.required}>
      <div className="grid gap-2 sm:grid-cols-2">
        {(question.choices || []).map((c) => {
          const active = arr.includes(c.value);
          return (
            <button
              key={c.value}
              type="button"
              onClick={() => {
                const next = active ? arr.filter((v) => v !== c.value) : [...arr, c.value];
                onChange(next);
              }}
              className={`text-left rounded-xl border px-4 py-2.5 text-sm transition-all ${
                active
                  ? "border-accent bg-accent-soft text-fg"
                  : "border-bg-border bg-bg-deep/40 text-fg-muted hover:border-accent/40 hover:bg-bg-elev/40"
              }`}
            >
              {c.label}
            </button>
          );
        })}
      </div>
    </FieldRow>
  );
}
