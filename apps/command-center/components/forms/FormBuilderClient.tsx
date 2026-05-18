"use client";

/**
 * FormBuilderClient — visual editor + live preview for /forms/[id]/edit.
 *
 * Non-technical operators land here, so every control is structured UI:
 * a theme picker (no hex codes), a fields editor (no JSON), and a per-step
 * "what stage does the lead move to?" dropdown (no string keys). The old
 * JSON tabs and free-form textareas are gone — if a form's stored
 * definition is malformed, the page-level loader surfaces a corrupt-row
 * error before we ever try to render the builder.
 *
 * Save semantics: PATCH /api/forms/[id]. On 400 invalid_definition the
 * route returns { path, reason } from FormDefinitionError; we surface
 * that inline so the operator knows which field broke.
 */

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Loader2,
  Save,
  Trash2,
} from "lucide-react";
import { FormRenderer } from "./FormRenderer";
import { VisualFieldsEditor } from "./VisualFieldsEditor";
import {
  FormDefinitionError,
  parseFormBranding,
  parseFormSteps,
  parseStepOutcomes,
  type FormBranding,
  type FormStep,
} from "@/lib/forms/types";
import { FORM_THEMES, inferActiveThemeId } from "@/lib/forms/themes";
import {
  LEAD_PIPELINE_STAGES,
  OPPORTUNITY_PIPELINE_STAGES,
} from "@/lib/sunbiz-stage-meta";

type FormRecord = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  branding: FormBranding;
  steps: FormStep[];
  on_complete_stage: string | null;
  step_outcomes: Record<string, string>;
  enabled: boolean;
  redirect_url: string | null;
};

type Props = {
  initialForm: FormRecord;
};

// Operator-friendly stage options for the per-step "what happens next?"
// dropdown. The Lead and Opportunity pipelines are the two stage families
// a SunBiz form can transition into; rendered as optgroups so a flat list
// of 20+ stages doesn't overwhelm.
const STAGE_GROUPS: Array<{ label: string; options: { value: string; label: string }[] }> = [
  {
    label: "Lead Pipeline",
    options: LEAD_PIPELINE_STAGES.map((s) => ({ value: s.key, label: s.label })),
  },
  {
    label: "Opportunity Pipeline",
    options: OPPORTUNITY_PIPELINE_STAGES.map((s) => ({
      value: s.key,
      label: s.label,
    })),
  },
];

export function FormBuilderClient({ initialForm }: Props) {
  const router = useRouter();

  const [name, setName] = useState(initialForm.name);
  const [description, setDescription] = useState(initialForm.description || "");
  const [enabled, setEnabled] = useState(initialForm.enabled);
  const [redirectUrl, setRedirectUrl] = useState(initialForm.redirect_url || "");
  const [steps, setSteps] = useState<FormStep[]>(initialForm.steps);
  const [branding, setBranding] = useState<FormBranding>(initialForm.branding);
  const [stepOutcomes, setStepOutcomes] = useState<Record<string, string>>(
    initialForm.step_outcomes,
  );
  const [onCompleteStage, setOnCompleteStage] = useState(
    initialForm.on_complete_stage || "",
  );

  const activeThemeId = useMemo(() => inferActiveThemeId(branding), [branding]);

  // Live-validate via the same parsers the server runs so we surface
  // FormDefinitionError messages before the save round-trip.
  const definitionError = useMemo(() => {
    try {
      parseFormSteps(steps);
      parseFormBranding(branding);
      parseStepOutcomes(stepOutcomes);
      return null;
    } catch (err) {
      if (err instanceof FormDefinitionError) {
        return { path: err.path, reason: err.reason };
      }
      return { path: "$", reason: err instanceof Error ? err.message : "unknown" };
    }
  }, [steps, branding, stepOutcomes]);

  const [previewStepIndex, setPreviewStepIndex] = useState(0);
  const [previewValues, setPreviewValues] = useState<Record<string, unknown>>(
    {},
  );

  // Clamp the preview step when the steps array shrinks.
  useEffect(() => {
    if (previewStepIndex >= steps.length) {
      setPreviewStepIndex(Math.max(0, steps.length - 1));
    }
  }, [steps.length, previewStepIndex]);

  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<
    null | { kind: "ok" | "err"; text: string }
  >(null);

  function applyTheme(themeId: string) {
    const theme = FORM_THEMES.find((t) => t.id === themeId);
    if (!theme) return;
    // Merge so operator-customized logo_url survives.
    setBranding({ ...branding, ...theme.branding });
  }

  function updateStepOutcome(stepIdx: number, target: string) {
    const isLast = stepIdx === steps.length - 1;
    if (isLast) {
      // Final step writes on_complete_stage. Keeps the existing data
      // contract — server still reads step_outcomes for non-final
      // transitions and on_complete_stage for the terminal one.
      setOnCompleteStage(target);
      const next = { ...stepOutcomes };
      delete next[String(stepIdx)];
      setStepOutcomes(next);
    } else {
      const next = { ...stepOutcomes };
      if (target) next[String(stepIdx)] = target;
      else delete next[String(stepIdx)];
      setStepOutcomes(next);
    }
  }

  function outcomeForStep(stepIdx: number): string {
    const isLast = stepIdx === steps.length - 1;
    if (isLast) return onCompleteStage;
    return stepOutcomes[String(stepIdx)] || "";
  }

  async function save() {
    if (definitionError) {
      setSaveMessage({
        kind: "err",
        text: `Fix the definition first — ${definitionError.path}: ${definitionError.reason}`,
      });
      return;
    }
    setSaving(true);
    setSaveMessage(null);
    try {
      const res = await fetch(`/api/forms/${initialForm.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name,
          description: description || null,
          branding,
          steps,
          step_outcomes: stepOutcomes,
          on_complete_stage: onCompleteStage || null,
          enabled,
          redirect_url: redirectUrl || null,
        }),
      });
      const data = (await res.json()) as {
        ok: boolean;
        error?: string;
        path?: string;
        reason?: string;
      };
      if (!data.ok) {
        setSaveMessage({
          kind: "err",
          text:
            data.path && data.reason
              ? `Save failed — ${data.path}: ${data.reason}`
              : `Save failed: ${data.error || `http_${res.status}`}`,
        });
        return;
      }
      setSaveMessage({ kind: "ok", text: "Saved. Returning to forms…" });
      // Send the operator back to the forms list after a successful save
      // — same pattern Delete uses. router.refresh() first to invalidate
      // the RSC cache so the list reflects the freshly-saved row.
      router.refresh();
      router.push("/forms?saved=1");
    } catch (err) {
      setSaveMessage({
        kind: "err",
        text: `Network error: ${err instanceof Error ? err.message : "unknown"}`,
      });
    } finally {
      setSaving(false);
    }
  }

  async function destroy() {
    if (!confirm(`Delete form "${name}"? This can't be undone.`)) return;
    const res = await fetch(`/api/forms/${initialForm.id}`, { method: "DELETE" });
    if (res.ok) {
      router.refresh();
      router.push("/forms");
    } else {
      const data = await res.json().catch(() => ({}));
      setSaveMessage({
        kind: "err",
        text: `Delete failed: ${data.error || `http_${res.status}`}`,
      });
    }
  }

  const hasFileUploadField = steps.some((s) =>
    s.fields.some((f) => f.type === "file_upload"),
  );

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      {/* ── Left: editor ──────────────────────────────────────────── */}
      <div className="space-y-5">
        <div className="rounded-xl border border-accent/30 bg-accent/5 p-3 text-xs text-fg-muted flex items-start gap-2">
          <AlertCircle className="h-3.5 w-3.5 text-accent shrink-0 mt-0.5" />
          <span>
            <strong className="text-fg">Build your form visually.</strong>{" "}
            Pick a theme, add the questions you want to ask, and tell us where
            the lead should land after each step. The live preview on the
            right matches exactly what your prospect will see.
          </span>
        </div>

        {!hasFileUploadField && (
          <div className="rounded-xl border border-status-warn/40 bg-status-warn/10 p-3 text-xs text-fg flex items-start gap-2">
            <AlertCircle className="h-3.5 w-3.5 text-status-warn shrink-0 mt-0.5" />
            <span>
              <strong>This form has no file uploads.</strong> SunBiz
              onboarding usually needs at least one document step (bank
              statements, ID, proof of ownership). Use the{" "}
              <strong>Add SunBiz docs step</strong> button below the steps
              list to add the standard three-document upload step in one
              click.
            </span>
          </div>
        )}

        <section className="space-y-3 rounded-xl border border-bg-border bg-bg-elev/40 p-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-fg-muted">
            Basics
          </h3>
          <div>
            <label className="block text-[11px] uppercase tracking-wider font-bold text-fg-dim mb-1">
              Name
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-md border border-bg-border bg-bg-elev px-3 py-2 text-sm text-fg"
            />
          </div>
          <div>
            <label className="block text-[11px] uppercase tracking-wider font-bold text-fg-dim mb-1">
              Description (operator-facing)
            </label>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full rounded-md border border-bg-border bg-bg-elev px-3 py-2 text-sm text-fg"
            />
          </div>
          <div>
            <label className="block text-[11px] uppercase tracking-wider font-bold text-fg-dim mb-1">
              Slug (URL segment — immutable after create)
            </label>
            <div className="font-mono text-sm text-fg-muted bg-bg-deep border border-bg-border rounded px-3 py-2">
              {initialForm.slug}
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-fg cursor-pointer">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              className="rounded accent-accent"
            />
            <span>Enabled (public form page renders only when checked)</span>
          </label>
        </section>

        <section className="space-y-3 rounded-xl border border-bg-border bg-bg-elev/40 p-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-fg-muted">
            Look & feel
          </h3>
          <p className="text-[11px] text-fg-dim leading-relaxed">
            Pick the design that fits the prospect. The preview on the right
            updates instantly. Email and ad templates aren&apos;t shown here —
            those live under Settings → Templates.
          </p>
          <div className="grid sm:grid-cols-2 gap-2">
            {FORM_THEMES.map((theme) => {
              const active = activeThemeId === theme.id;
              return (
                <button
                  key={theme.id}
                  type="button"
                  onClick={() => applyTheme(theme.id)}
                  className={`text-left rounded-lg border p-3 transition ${
                    active
                      ? "border-accent bg-accent/10"
                      : "border-bg-border bg-bg-elev hover:border-accent/40"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-block h-3 w-3 rounded-full border border-bg-border"
                      style={{ background: theme.branding.primary_color }}
                    />
                    <span
                      className="inline-block h-3 w-3 rounded-full border border-bg-border"
                      style={{ background: theme.branding.accent_color }}
                    />
                    <span className="text-sm font-bold text-fg">
                      {theme.label}
                    </span>
                    {active && (
                      <Check className="w-3.5 h-3.5 text-accent ml-auto" />
                    )}
                  </div>
                  <div className="text-[11px] text-fg-dim mt-1">
                    {theme.description}
                  </div>
                </button>
              );
            })}
          </div>
          <div>
            <label className="block text-[11px] uppercase tracking-wider font-bold text-fg-dim mb-1">
              Logo URL (optional)
            </label>
            <input
              value={branding.logo_url || ""}
              onChange={(e) =>
                setBranding({
                  ...branding,
                  logo_url: e.target.value || undefined,
                })
              }
              placeholder="https://… (shown at the top of the public form)"
              className="w-full rounded-md border border-bg-border bg-bg-elev px-3 py-2 text-sm text-fg"
            />
            <p className="text-[11px] text-fg-dim mt-1">
              New forms inherit the logo you set in{" "}
              <a
                href="/settings"
                className="text-accent hover:text-accent-bright underline underline-offset-2"
              >
                Settings → Branding
              </a>
              . Override here only if this form needs a different mark.
            </p>
          </div>
        </section>

        <section className="space-y-3 rounded-xl border border-bg-border bg-bg-elev/40 p-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-fg-muted">
            Steps & fields
          </h3>
          <VisualFieldsEditor steps={steps} onChange={setSteps} />
        </section>

        <section className="space-y-3 rounded-xl border border-bg-border bg-bg-elev/40 p-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-fg-muted">
            What happens after each step?
          </h3>
          <p className="text-[11px] text-fg-dim leading-relaxed">
            When the prospect finishes a step, optionally move their lead to
            a new pipeline stage. The standard SunBiz flow is to advance to
            <strong> Sent Application</strong> after the first step, then{" "}
            <strong>Submitted</strong> after the docs are uploaded.
          </p>
          <div className="space-y-2">
            {steps.map((step, idx) => (
              <div
                key={step.key || idx}
                className="flex items-center gap-3 rounded-md border border-bg-border bg-bg-deep/60 px-3 py-2"
              >
                <span className="text-[11px] font-bold uppercase tracking-wider text-fg-dim shrink-0">
                  Step {idx + 1}
                </span>
                <span className="text-sm text-fg truncate flex-1">
                  {step.title || `(untitled)`}
                </span>
                <select
                  value={outcomeForStep(idx)}
                  onChange={(e) => updateStepOutcome(idx, e.target.value)}
                  className="rounded-md border border-bg-border bg-bg-elev px-2 py-1 text-xs text-fg"
                >
                  <option value="">Don&apos;t change the stage</option>
                  {STAGE_GROUPS.map((group) => (
                    <optgroup key={group.label} label={group.label}>
                      {group.options.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>
            ))}
          </div>
          <div>
            <label className="block text-[11px] uppercase tracking-wider font-bold text-fg-dim mb-1">
              After the prospect finishes, send them to (optional)
            </label>
            <input
              value={redirectUrl}
              onChange={(e) => setRedirectUrl(e.target.value)}
              placeholder="https://… leave blank for our default thank-you screen"
              className="w-full rounded-md border border-bg-border bg-bg-elev px-3 py-2 text-sm text-fg"
            />
          </div>
        </section>

        {definitionError && (
          <div className="rounded-md border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-400 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <div>
              <div className="font-bold">Definition invalid</div>
              <div className="text-xs mt-0.5 font-mono">
                {definitionError.path}: {definitionError.reason}
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            onClick={save}
            disabled={saving || !!definitionError}
            className="inline-flex items-center gap-2 rounded-lg bg-accent text-bg-deep px-4 py-2 text-sm font-bold hover:bg-accent-bright disabled:opacity-50"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            Save
          </button>
          <button
            onClick={destroy}
            className="inline-flex items-center gap-2 rounded-lg border border-rose-500/40 text-rose-400 px-4 py-2 text-sm font-bold hover:bg-rose-500/10"
          >
            <Trash2 className="w-4 h-4" />
            Delete form
          </button>
          {saveMessage && (
            <div
              className={`flex items-center gap-2 text-sm ${
                saveMessage.kind === "ok"
                  ? "text-status-engaged"
                  : "text-rose-400"
              }`}
            >
              {saveMessage.kind === "ok" ? (
                <CheckCircle2 className="w-4 h-4" />
              ) : (
                <AlertCircle className="w-4 h-4" />
              )}
              {saveMessage.text}
            </div>
          )}
        </div>
      </div>

      {/* ── Right: preview ────────────────────────────────────────── */}
      <div className="space-y-3">
        <div className="rounded-xl border border-bg-border bg-bg-elev/40 p-4 space-y-3 sticky top-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-fg-muted">
            Live preview
          </h3>

          {(branding.headline || branding.subheadline) && (
            <div className="text-center pb-3 border-b border-bg-border">
              {branding.logo_url && (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={branding.logo_url}
                  alt="Brand logo"
                  className="mx-auto h-10 mb-3"
                />
              )}
              {branding.headline && (
                <h2 className="text-lg font-bold text-fg">{branding.headline}</h2>
              )}
              {branding.subheadline && (
                <p className="text-sm text-fg-muted mt-1">
                  {branding.subheadline}
                </p>
              )}
            </div>
          )}

          <div className="flex flex-wrap gap-2 text-[11px]">
            {steps.map((s, i) => (
              <button
                key={s.key || i}
                type="button"
                onClick={() => setPreviewStepIndex(i)}
                className={`px-2 py-1 rounded ${
                  i === previewStepIndex
                    ? "bg-accent/20 text-accent font-bold"
                    : "text-fg-dim hover:text-fg"
                }`}
              >
                {i + 1}. {s.title}
              </button>
            ))}
          </div>

          {steps[previewStepIndex] && (
            <FormRenderer
              step={steps[previewStepIndex]}
              values={previewValues}
              errors={{}}
              branding={branding}
              onFieldChange={(fieldName, v) =>
                setPreviewValues((prev) => ({ ...prev, [fieldName]: v }))
              }
              onSubmit={() => {
                /* preview mode — disabled below */
              }}
              previewMode
              showBack={previewStepIndex > 0}
              onBack={() => setPreviewStepIndex((i) => Math.max(0, i - 1))}
              ctaLabelOverride={
                previewStepIndex === steps.length - 1 ? "Submit" : undefined
              }
            />
          )}
        </div>
      </div>
    </div>
  );
}
