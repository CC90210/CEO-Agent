"use client";

/**
 * FormBuilderClient — JSON-schema editor + live preview for /forms/[id]/edit.
 *
 * Phase 3.3 of the SunBiz CRM build. v1 is intentionally a schema-editor
 * (left pane: monospace JSON textareas for steps + branding; right pane:
 * FormRenderer live preview). v2 will add drag-drop on top — but the
 * schema editor ships in a day; drag-drop is a week. Schema-editor is
 * enough for operators to design real forms today.
 *
 * Save semantics: PATCH /api/forms/[id]. On 400 invalid_steps the route
 * returns { path, reason } from FormDefinitionError; we surface that as
 * an inline message above the textarea so the operator knows exactly
 * which field is malformed.
 */

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, Loader2, Save, Trash2 } from "lucide-react";
import { FormRenderer } from "./FormRenderer";
import {
  parseFormSteps,
  parseFormBranding,
  parseStepOutcomes,
  FormDefinitionError,
  type FormStep,
  type FormBranding,
} from "@/lib/forms/types";

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

export function FormBuilderClient({ initialForm }: Props) {
  const router = useRouter();

  // Core mutable state — name/desc as inputs, steps + branding + outcomes
  // as raw JSON textareas (operators copy-paste between forms; raw is
  // honest about that). The parsed shapes derived from the JSON power
  // the preview pane.
  const [name, setName] = useState(initialForm.name);
  const [description, setDescription] = useState(initialForm.description || "");
  const [enabled, setEnabled] = useState(initialForm.enabled);
  const [onCompleteStage, setOnCompleteStage] = useState(initialForm.on_complete_stage || "");
  const [redirectUrl, setRedirectUrl] = useState(initialForm.redirect_url || "");
  const [stepsJson, setStepsJson] = useState(() => JSON.stringify(initialForm.steps, null, 2));
  const [brandingJson, setBrandingJson] = useState(() =>
    JSON.stringify(initialForm.branding, null, 2),
  );
  const [outcomesJson, setOutcomesJson] = useState(() =>
    JSON.stringify(initialForm.step_outcomes, null, 2),
  );

  // Parse the raw JSON every keystroke so the preview reflects the
  // live state. Errors land in parseError and skip the preview render.
  type ParseState = {
    steps: FormStep[] | null;
    branding: FormBranding | null;
    outcomes: Record<string, string> | null;
    error: { path: string; reason: string } | null;
  };

  const parsed: ParseState = useMemo(() => {
    try {
      const steps = parseFormSteps(JSON.parse(stepsJson));
      const branding = parseFormBranding(JSON.parse(brandingJson));
      const outcomes = parseStepOutcomes(JSON.parse(outcomesJson));
      return { steps, branding, outcomes, error: null };
    } catch (err) {
      if (err instanceof FormDefinitionError) {
        return {
          steps: null,
          branding: null,
          outcomes: null,
          error: { path: err.path, reason: err.reason },
        };
      }
      if (err instanceof SyntaxError) {
        return {
          steps: null,
          branding: null,
          outcomes: null,
          error: { path: "$", reason: `invalid JSON: ${err.message}` },
        };
      }
      throw err;
    }
  }, [stepsJson, brandingJson, outcomesJson]);

  const [previewStepIndex, setPreviewStepIndex] = useState(0);
  const [previewValues, setPreviewValues] = useState<Record<string, unknown>>({});

  // Clamp the preview step when the steps array shrinks.
  useEffect(() => {
    if (parsed.steps && previewStepIndex >= parsed.steps.length) {
      setPreviewStepIndex(Math.max(0, parsed.steps.length - 1));
    }
  }, [parsed.steps, previewStepIndex]);

  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<
    null | { kind: "ok" | "err"; text: string }
  >(null);

  async function save() {
    if (parsed.error) {
      setSaveMessage({
        kind: "err",
        text: `Fix the definition first — ${parsed.error.path}: ${parsed.error.reason}`,
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
          branding: parsed.branding,
          steps: parsed.steps,
          step_outcomes: parsed.outcomes,
          on_complete_stage: onCompleteStage || null,
          enabled,
          redirect_url: redirectUrl || null,
        }),
      });
      const data = (await res.json()) as { ok: boolean; error?: string; path?: string; reason?: string };
      if (!data.ok) {
        setSaveMessage({
          kind: "err",
          text: data.path && data.reason
            ? `Save failed — ${data.path}: ${data.reason}`
            : `Save failed: ${data.error || `http_${res.status}`}`,
        });
        return;
      }
      setSaveMessage({ kind: "ok", text: "Saved." });
      router.refresh();
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
      // Invalidate the /forms RSC cache so the just-deleted form
      // doesn't reappear when we push back to the list.
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

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      {/* ── Left: editor ──────────────────────────────────────────── */}
      <div className="space-y-5">
        <div className="rounded-xl border border-accent/30 bg-accent/5 p-3 text-xs text-fg-muted flex items-start gap-2">
          <AlertCircle className="h-3.5 w-3.5 text-accent shrink-0 mt-0.5" />
          <span>
            <strong className="text-fg">Power-user editor.</strong> The form
            fields, branding, and outcomes are edited as raw JSON below — a
            visual drag-and-drop builder is on the next round. The live
            preview on the right shows exactly what your prospects will see;
            iterate there to know your changes are valid.
          </span>
        </div>
        <section className="space-y-3 rounded-xl border border-bg-border bg-bg-elev/40 p-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-fg-muted">Basics</h3>
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
            Steps (JSON)
          </h3>
          <p className="text-[11px] text-fg-dim leading-relaxed">
            Each step has a key, title, optional description, and a fields array.
            Field types: text, textarea, email, phone, number, currency, date,
            select, multiselect, rating, file_upload, signature, hidden.
          </p>
          <textarea
            value={stepsJson}
            onChange={(e) => setStepsJson(e.target.value)}
            className="w-full rounded-md border border-bg-border bg-bg-deep px-3 py-2 font-mono text-[11px] text-fg min-h-[20rem]"
            spellCheck={false}
          />
        </section>

        <section className="space-y-3 rounded-xl border border-bg-border bg-bg-elev/40 p-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-fg-muted">Branding</h3>
          <textarea
            value={brandingJson}
            onChange={(e) => setBrandingJson(e.target.value)}
            className="w-full rounded-md border border-bg-border bg-bg-deep px-3 py-2 font-mono text-[11px] text-fg min-h-[8rem]"
            spellCheck={false}
          />
        </section>

        <section className="space-y-3 rounded-xl border border-bg-border bg-bg-elev/40 p-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-fg-muted">
            Lead-stage transitions
          </h3>
          <p className="text-[11px] text-fg-dim leading-relaxed">
            step_outcomes maps step index (string) → lead.stage value. The
            on_complete_stage applies on the final step if no per-step
            outcome is set. Common SunBiz flow: 0 → sent_application,
            1 → signed_application, 2 → submitted.
          </p>
          <textarea
            value={outcomesJson}
            onChange={(e) => setOutcomesJson(e.target.value)}
            className="w-full rounded-md border border-bg-border bg-bg-deep px-3 py-2 font-mono text-[11px] text-fg min-h-[6rem]"
            spellCheck={false}
          />
          <div>
            <label className="block text-[11px] uppercase tracking-wider font-bold text-fg-dim mb-1">
              on_complete_stage (fallback for last step)
            </label>
            <input
              value={onCompleteStage}
              onChange={(e) => setOnCompleteStage(e.target.value)}
              placeholder="submitted"
              className="w-full rounded-md border border-bg-border bg-bg-elev px-3 py-2 text-sm text-fg"
            />
          </div>
          <div>
            <label className="block text-[11px] uppercase tracking-wider font-bold text-fg-dim mb-1">
              redirect_url (optional — sends prospect here after final submit)
            </label>
            <input
              value={redirectUrl}
              onChange={(e) => setRedirectUrl(e.target.value)}
              placeholder="https://..."
              className="w-full rounded-md border border-bg-border bg-bg-elev px-3 py-2 text-sm text-fg"
            />
          </div>
        </section>

        <div className="flex items-center gap-3">
          <button
            onClick={save}
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-lg bg-accent text-bg-deep px-4 py-2 text-sm font-bold hover:bg-accent-bright disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
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
                saveMessage.kind === "ok" ? "text-status-engaged" : "text-rose-400"
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

          {parsed.error ? (
            <div className="rounded-md border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-400 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <div>
                <div className="font-bold">Definition invalid</div>
                <div className="text-xs mt-0.5 font-mono">
                  {parsed.error.path}: {parsed.error.reason}
                </div>
              </div>
            </div>
          ) : parsed.steps && parsed.branding ? (
            <>
              {(parsed.branding.headline || parsed.branding.subheadline) && (
                <div className="text-center pb-3 border-b border-bg-border">
                  {parsed.branding.logo_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={parsed.branding.logo_url}
                      alt="Brand logo"
                      className="mx-auto h-10 mb-3"
                    />
                  )}
                  {parsed.branding.headline && (
                    <h2 className="text-lg font-bold text-fg">
                      {parsed.branding.headline}
                    </h2>
                  )}
                  {parsed.branding.subheadline && (
                    <p className="text-sm text-fg-muted mt-1">
                      {parsed.branding.subheadline}
                    </p>
                  )}
                </div>
              )}

              <div className="flex gap-2 text-[11px]">
                {parsed.steps.map((s, i) => (
                  <button
                    key={s.key}
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

              <FormRenderer
                step={parsed.steps[previewStepIndex]}
                values={previewValues}
                errors={{}}
                branding={parsed.branding}
                onFieldChange={(name, v) =>
                  setPreviewValues((prev) => ({ ...prev, [name]: v }))
                }
                onSubmit={() => {
                  /* preview mode — disabled below */
                }}
                previewMode
                showBack={previewStepIndex > 0}
                onBack={() => setPreviewStepIndex((i) => Math.max(0, i - 1))}
                ctaLabelOverride={
                  previewStepIndex === parsed.steps.length - 1 ? "Submit" : undefined
                }
              />
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
