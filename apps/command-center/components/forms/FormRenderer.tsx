"use client";

/**
 * FormRenderer — pure-presentation renderer for a single form step.
 *
 * Shared between:
 *   1. The builder's live preview pane (/forms/[id]/edit)
 *   2. The public form page (/f/<tenant>/<form_slug>/<lead_token>)
 *
 * Both surfaces consume the same component so the operator sees exactly
 * what the prospect will see — no "looks right in the builder, broken
 * on prod" surprises. The renderer is stateless: parent owns the
 * step_index, the field values, and the submit handler. This component
 * just paints what it's given.
 *
 * Field types covered: text, textarea, email, phone, currency, number,
 * date, select, multiselect, signature (deferred to v2), file_upload,
 * hidden, rating.
 */

import { useId } from "react";
import type { FormStep, FormField, FormBranding } from "@/lib/forms/types";

type Props = {
  step: FormStep;
  values: Record<string, unknown>;
  errors: Partial<Record<string, string>>;
  branding?: FormBranding;
  onFieldChange: (name: string, value: unknown) => void;
  onSubmit: () => void;
  submitting?: boolean;
  /** Used by the builder preview to disable real submission. */
  previewMode?: boolean;
  /** When true, render a "Back" button alongside the CTA. */
  showBack?: boolean;
  onBack?: () => void;
  /** Override the CTA label. Falls back to step.cta_label, then "Continue". */
  ctaLabelOverride?: string;
};

export function FormRenderer({
  step,
  values,
  errors,
  branding,
  onFieldChange,
  onSubmit,
  submitting,
  previewMode,
  showBack,
  onBack,
  ctaLabelOverride,
}: Props) {
  const primary = branding?.primary_color || "#0ea5e9";
  const accent = branding?.accent_color || "#06b6d4";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!previewMode) onSubmit();
      }}
      className="space-y-5"
    >
      <header className="space-y-1">
        <h2 className="text-xl font-bold text-fg">{step.title}</h2>
        {step.description && (
          <p className="text-sm text-fg-muted leading-relaxed">{step.description}</p>
        )}
      </header>

      <div className="space-y-4">
        {step.fields.map((field) => (
          <FieldRow
            key={field.name}
            field={field}
            value={values[field.name]}
            error={errors[field.name]}
            onChange={(v) => onFieldChange(field.name, v)}
          />
        ))}
      </div>

      <div className="flex items-center gap-3 pt-2">
        {showBack && onBack && (
          <button
            type="button"
            onClick={onBack}
            className="text-sm text-fg-muted hover:text-fg underline-offset-2 hover:underline"
          >
            ← Back
          </button>
        )}
        <button
          type="submit"
          disabled={submitting || previewMode}
          className="ml-auto inline-flex items-center justify-center rounded-lg px-5 py-2.5 text-sm font-bold text-white shadow-sm transition-colors disabled:opacity-50"
          style={{ backgroundColor: primary }}
        >
          {submitting
            ? "Submitting…"
            : ctaLabelOverride || step.cta_label || "Continue"}
        </button>
      </div>

      {previewMode && (
        <p className="text-[11px] text-fg-dim italic">
          Live preview — submit is disabled. Color sample:{" "}
          <span
            className="inline-block w-3 h-3 rounded align-middle"
            style={{ backgroundColor: primary }}
          />{" "}
          primary,{" "}
          <span
            className="inline-block w-3 h-3 rounded align-middle"
            style={{ backgroundColor: accent }}
          />{" "}
          accent
        </p>
      )}
    </form>
  );
}

// ---------------------------------------------------------------------------
// Per-field renderer
// ---------------------------------------------------------------------------

function FieldRow({
  field,
  value,
  error,
  onChange,
}: {
  field: FormField;
  value: unknown;
  error: string | undefined;
  onChange: (v: unknown) => void;
}) {
  const inputId = useId();

  if (field.type === "hidden") {
    // No-op visual. Value comes from field.value at form-init time;
    // parent should ensure values[field.name] is seeded.
    return null;
  }

  return (
    <div className="space-y-1.5">
      <label htmlFor={inputId} className="block text-xs font-bold uppercase tracking-wider text-fg-muted">
        {field.label}
        {field.required && <span className="text-rose-400 ml-1">*</span>}
      </label>

      {renderInput(field, inputId, value, onChange)}

      {field.help && <p className="text-[11px] text-fg-dim">{field.help}</p>}
      {error && <p className="text-[11px] text-rose-400">{error}</p>}
    </div>
  );
}

function renderInput(
  field: FormField,
  inputId: string,
  value: unknown,
  onChange: (v: unknown) => void,
): React.ReactNode {
  const base =
    "w-full rounded-md border border-bg-border bg-bg-elev px-3 py-2 text-sm text-fg focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors placeholder-fg-dim";

  switch (field.type) {
    case "text":
    case "email":
    case "phone":
      return (
        <input
          id={inputId}
          type={field.type === "email" ? "email" : field.type === "phone" ? "tel" : "text"}
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          maxLength={field.maxLength}
          className={base}
        />
      );

    case "textarea":
      return (
        <textarea
          id={inputId}
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          maxLength={field.maxLength}
          rows={4}
          className={`${base} resize-y min-h-[6rem]`}
        />
      );

    case "number":
    case "currency":
      return (
        <div className="relative">
          {field.type === "currency" && (
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-fg-muted text-sm pointer-events-none">$</span>
          )}
          <input
            id={inputId}
            type="number"
            inputMode="decimal"
            value={typeof value === "number" || typeof value === "string" ? String(value ?? "") : ""}
            onChange={(e) => {
              const raw = e.target.value;
              onChange(raw === "" ? null : Number(raw));
            }}
            placeholder={field.placeholder}
            min={field.min}
            max={field.max}
            className={`${base} ${field.type === "currency" ? "pl-7" : ""}`}
          />
        </div>
      );

    case "date":
      return (
        <input
          id={inputId}
          type="date"
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value)}
          className={base}
        />
      );

    case "select":
      return (
        <select
          id={inputId}
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value)}
          className={base}
        >
          <option value="">— Select —</option>
          {(field.options || []).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      );

    case "multiselect": {
      const arr = Array.isArray(value) ? (value as string[]) : [];
      return (
        <div className="space-y-1.5">
          {(field.options || []).map((o) => {
            const checked = arr.includes(o.value);
            return (
              <label
                key={o.value}
                className="flex items-center gap-2 text-sm text-fg cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => {
                    const next = e.target.checked
                      ? Array.from(new Set([...arr, o.value]))
                      : arr.filter((v) => v !== o.value);
                    onChange(next);
                  }}
                  className="rounded accent-accent"
                />
                <span>{o.label}</span>
              </label>
            );
          })}
        </div>
      );
    }

    case "rating": {
      const n = typeof value === "number" ? value : 0;
      return (
        <div className="flex items-center gap-1">
          {[1, 2, 3, 4, 5].map((star) => (
            <button
              key={star}
              type="button"
              onClick={() => onChange(star)}
              className={`text-2xl transition-colors ${
                star <= n ? "text-amber-400" : "text-fg-dim hover:text-fg-muted"
              }`}
              aria-label={`${star} star${star > 1 ? "s" : ""}`}
            >
              ★
            </button>
          ))}
        </div>
      );
    }

    case "file_upload": {
      const fileVal = value as File | null;
      return (
        <input
          id={inputId}
          type="file"
          accept={field.accept?.join(",")}
          onChange={(e) => {
            const f = e.target.files?.[0] || null;
            onChange(f);
          }}
          className="block w-full text-sm text-fg file:mr-3 file:rounded-md file:border-0 file:bg-accent/15 file:px-3 file:py-2 file:text-xs file:font-bold file:text-accent file:cursor-pointer hover:file:bg-accent/25"
        />
        // The file is held in component state; the public form page's
        // submit handler base64-encodes small files or uploads to Supabase
        // Storage for larger ones. File metadata is what lands in
        // form_submissions.file_attachments[].
      );
    }

    case "signature":
      // Deferred to v2 — a canvas-based signature widget needs more
      // care than the v1 schema editor warrants. For v1, operators
      // can ask the prospect to type their name as confirmation.
      return (
        <input
          id={inputId}
          type="text"
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Type your full name as signature"
          className={base}
        />
      );

    case "hidden":
      // Unreachable — handled above. Keep for exhaustiveness.
      return null;

    default:
      // Exhaustive default — shouldn't trigger if FormField type is
      // honored by callers. Renders nothing so a future field type
      // added to the union doesn't crash the page until the renderer
      // catches up.
      return null;
  }
}
