"use client";

/**
 * WelcomeWizardClient — 3-step personalisation flow shown on first login
 * for invitees (Phase C of master multi-tenant infra plan, 2026-05-17).
 *
 * State machine: step ∈ {identity, preferences, ai} → save → router.push("/").
 *
 * Each step is opt-in past identity — the operator can skip preferences
 * + AI and still land on a working dashboard. The minimum bar for
 * completion is name + display name (so other teammates see something
 * sensible in the team list).
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2, Sparkles, User, Settings as SettingsIcon, CheckCircle2 } from "lucide-react";

type InitialProfile = {
  full_name: string;
  display_name: string;
  primary_agent: string;
  custom_fields: Record<string, unknown>;
};

type Step = "identity" | "preferences" | "ai" | "saving" | "done";

const AGENT_LABELS: Record<string, string> = {
  bravo: "Bravo (lead architect)",
  solara: "Solara (operations + pipeline)",
  helios: "Helios (sales + outreach)",
  maven: "Maven (content + marketing)",
  atlas: "Atlas (finance + strategy)",
  aura: "Aura (personal assistant)",
};

const TIMEZONES: Array<{ value: string; label: string }> = [
  { value: "America/New_York", label: "Eastern (New York)" },
  { value: "America/Chicago", label: "Central (Chicago)" },
  { value: "America/Denver", label: "Mountain (Denver)" },
  { value: "America/Los_Angeles", label: "Pacific (Los Angeles)" },
  { value: "America/Toronto", label: "Eastern (Toronto)" },
  { value: "Europe/London", label: "London" },
  { value: "Europe/Paris", label: "Paris" },
  { value: "Asia/Tokyo", label: "Tokyo" },
  { value: "Australia/Sydney", label: "Sydney" },
];

export function WelcomeWizardClient({
  initialProfile,
  enabledAgents,
  alreadyCompleted,
}: {
  initialProfile: InitialProfile;
  enabledAgents: string[];
  alreadyCompleted: boolean;
}) {
  const router = useRouter();

  const [step, setStep] = useState<Step>("identity");
  const [fullName, setFullName] = useState(initialProfile.full_name);
  const [displayName, setDisplayName] = useState(initialProfile.display_name || initialProfile.full_name.split(" ")[0] || "");
  const [primaryAgent, setPrimaryAgent] = useState(initialProfile.primary_agent);
  const [timezone, setTimezone] = useState(
    (initialProfile.custom_fields?.timezone as string) ||
      (typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : "America/New_York"),
  );
  const [briefingChannel, setBriefingChannel] = useState<"email" | "telegram" | "none">(
    (initialProfile.custom_fields?.briefing_channel as "email" | "telegram" | "none") || "email",
  );
  const [error, setError] = useState<string | null>(null);

  async function save(extra?: { skip_ai?: boolean }) {
    setError(null);
    setStep("saving");
    try {
      const r = await fetch("/api/profile", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          full_name: fullName.trim(),
          display_name: displayName.trim() || fullName.trim().split(" ")[0] || "Member",
          primary_agent: primaryAgent,
          custom_fields: {
            ...initialProfile.custom_fields,
            timezone,
            briefing_channel: briefingChannel,
            welcomed_at: new Date().toISOString(),
            skipped_ai_step: extra?.skip_ai === true ? true : undefined,
          },
          onboarding_completed_at: new Date().toISOString(),
        }),
      });
      const body = (await r.json().catch(() => ({}))) as { ok?: boolean; error?: string };
      if (!r.ok || !body.ok) {
        setError(body.error || `save_failed:${r.status}`);
        setStep("ai");
        return;
      }
      setStep("done");
      // Small delay so the operator sees the "all set" state, then route home.
      setTimeout(() => {
        router.push("/");
        router.refresh();
      }, 900);
    } catch (e) {
      setError(e instanceof Error ? e.message : "save failed");
      setStep("ai");
    }
  }

  if (step === "done") {
    return (
      <div className="rounded-2xl border border-emerald-500/40 bg-emerald-500/5 p-8 text-center space-y-3">
        <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto" />
        <div className="text-lg font-bold text-fg">You&apos;re all set</div>
        <div className="text-sm text-fg-muted">Loading your dashboard…</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <StepProgress current={step} />

      {step === "identity" && (
        <StepCard
          icon={<User className="w-5 h-5" />}
          title="Who you are"
          subtitle="How teammates and your agents will refer to you."
        >
          <div className="space-y-3">
            <Field
              label="Full name"
              value={fullName}
              onChange={setFullName}
              autoFocus
              required
              placeholder="Alex Johnson"
            />
            <Field
              label="Display name"
              value={displayName}
              onChange={setDisplayName}
              required
              placeholder="Alex"
              hint="Short name your agents use in chat. Defaults to your first name."
            />
            <Field
              label="Timezone"
              value={timezone}
              onChange={setTimezone}
              kind="select"
              options={TIMEZONES.map((tz) => ({ value: tz.value, label: tz.label }))}
              hint="Used for daily briefings + drip-send windows."
            />
          </div>
          <Footer
            onNext={() => {
              if (!fullName.trim()) {
                setError("Add your full name first.");
                return;
              }
              setError(null);
              setStep("preferences");
            }}
            nextLabel="Next — preferences"
          />
        </StepCard>
      )}

      {step === "preferences" && (
        <StepCard
          icon={<SettingsIcon className="w-5 h-5" />}
          title="How you want to work"
          subtitle="Pick the agent you'll talk to most and where you want updates."
        >
          <div className="space-y-3">
            <Field
              label="Your default agent"
              value={primaryAgent}
              onChange={setPrimaryAgent}
              kind="select"
              options={enabledAgents.map((slug) => ({
                value: slug,
                label: AGENT_LABELS[slug] || slug,
              }))}
              hint="The agent that opens first when you click 'Chat' anywhere."
            />
            <Field
              label="Daily briefing channel"
              value={briefingChannel}
              onChange={(v) => setBriefingChannel(v as "email" | "telegram" | "none")}
              kind="select"
              options={[
                { value: "email", label: "Email me" },
                { value: "telegram", label: "Telegram me" },
                { value: "none", label: "Don't send a briefing" },
              ]}
              hint="Daily summary of what your agents did. You can change this anytime in Settings."
            />
          </div>
          <Footer
            onBack={() => setStep("identity")}
            onNext={() => setStep("ai")}
            nextLabel="Next — AI account"
          />
        </StepCard>
      )}

      {step === "ai" && (
        <StepCard
          icon={<Sparkles className="w-5 h-5" />}
          title="Connect your own AI (optional)"
          subtitle="Skip for now and your workspace's shared key kicks in. You can connect your own anytime from Settings → My Agents."
        >
          <div className="rounded-lg border border-bg-border bg-bg-elev/40 p-4 text-sm text-fg-muted leading-relaxed">
            <div className="font-semibold text-fg mb-1">Why connect your own?</div>
            <ul className="list-disc pl-5 space-y-1 text-[12.5px]">
              <li>Use your personal Claude Pro / OpenAI / Gemini subscription instead of the workspace key.</li>
              <li>Your chat usage stays on your account — no shared metering.</li>
              <li>Pick a different model per agent (e.g. Sonnet for daily, Opus for hard problems).</li>
            </ul>
          </div>
          <div className="text-[12px] text-fg-dim leading-relaxed">
            You don&apos;t need to do this right now. The workspace already has a working AI setup — skip
            and you can come back to it when it&apos;s convenient.
          </div>
          {error && (
            <div className="text-[12px] text-red-300 bg-red-500/10 border border-red-500/30 rounded-md p-2">
              {error}
            </div>
          )}
          <Footer
            onBack={() => setStep("preferences")}
            onNext={() => save({ skip_ai: false })}
            nextLabel={alreadyCompleted ? "Save changes" : "Open dashboard"}
            secondaryLabel="Skip for now"
            onSecondary={() => save({ skip_ai: true })}
          />
        </StepCard>
      )}

      {step === "saving" && (
        <div className="rounded-2xl border border-bg-border bg-bg-elev/40 p-8 text-center space-y-3">
          <Loader2 className="w-8 h-8 text-accent mx-auto animate-spin" />
          <div className="text-sm text-fg-muted">Saving your preferences…</div>
        </div>
      )}
    </div>
  );
}

function StepProgress({ current }: { current: Step }) {
  const order: Step[] = ["identity", "preferences", "ai"];
  const idx = order.indexOf(current);
  return (
    <ol className="flex items-center gap-2 text-[11px] uppercase tracking-wider font-bold text-fg-dim">
      {order.map((s, i) => (
        <li key={s} className="flex items-center gap-2">
          <span
            className={`w-6 h-6 rounded-full inline-flex items-center justify-center text-[11px] ${
              i < idx
                ? "bg-accent text-bg-deep"
                : i === idx
                  ? "bg-accent/20 text-accent border border-accent"
                  : "bg-bg-elev/60 text-fg-dim border border-bg-border"
            }`}
          >
            {i + 1}
          </span>
          <span className={i === idx ? "text-fg" : "text-fg-dim"}>
            {s === "identity" ? "You" : s === "preferences" ? "Preferences" : "AI"}
          </span>
          {i < order.length - 1 && <span className="text-fg-dim mx-1">→</span>}
        </li>
      ))}
    </ol>
  );
}

function StepCard({
  icon,
  title,
  subtitle,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-bg-border bg-bg-elev/40 p-6 space-y-4">
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-accent/15 border border-accent/30 p-2 text-accent">{icon}</div>
        <div>
          <h2 className="text-base font-bold text-fg">{title}</h2>
          <p className="text-[12.5px] text-fg-muted leading-relaxed mt-0.5">{subtitle}</p>
        </div>
      </div>
      {children}
    </div>
  );
}

function Footer({
  onBack,
  onNext,
  nextLabel,
  secondaryLabel,
  onSecondary,
}: {
  onBack?: () => void;
  onNext: () => void;
  nextLabel: string;
  secondaryLabel?: string;
  onSecondary?: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2 pt-2">
      <div className="flex items-center gap-2">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="text-[12px] text-fg-dim hover:text-fg underline underline-offset-2"
          >
            Back
          </button>
        )}
        {secondaryLabel && onSecondary && (
          <button
            type="button"
            onClick={onSecondary}
            className="text-[12px] text-fg-dim hover:text-fg underline underline-offset-2"
          >
            {secondaryLabel}
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={onNext}
        className="inline-flex items-center gap-1.5 rounded-md bg-accent text-bg-deep px-3 py-1.5 text-[12.5px] font-bold hover:bg-accent/90 transition-colors"
      >
        {nextLabel} <ArrowRight className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

type FieldProps = {
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  placeholder?: string;
  hint?: string;
  autoFocus?: boolean;
  kind?: "text" | "select";
  options?: Array<{ value: string; label: string }>;
};

function Field({
  label,
  value,
  onChange,
  required,
  placeholder,
  hint,
  autoFocus,
  kind = "text",
  options,
}: FieldProps) {
  return (
    <label className="block">
      <div className="text-[11px] uppercase tracking-wider font-bold text-fg-dim mb-1">
        {label}
        {required && <span className="text-red-300 ml-1">*</span>}
      </div>
      {kind === "select" ? (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full bg-bg-deep border border-bg-border rounded-md px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none"
          autoFocus={autoFocus}
        >
          {options?.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          required={required}
          autoFocus={autoFocus}
          className="w-full bg-bg-deep border border-bg-border rounded-md px-3 py-2 text-sm text-fg placeholder:text-fg-dim focus:border-accent focus:outline-none"
        />
      )}
      {hint && <div className="mt-1 text-[11px] text-fg-dim leading-snug">{hint}</div>}
    </label>
  );
}
