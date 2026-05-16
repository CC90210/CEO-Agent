"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, CheckCircle2, Loader2, Save, AlertCircle, Plus, X, Code2 } from "lucide-react";
import Link from "next/link";
import type { ManifestEntityDef, ManifestEntityField } from "@/lib/manifest/schema";

type Props = {
  tenantSlug: string;
  entity: ManifestEntityDef;
  /** Relative path of the page that brought us here (e.g. "applications").
   *  Used for the cancel/return link. */
  backPath: string;
  /** Optional pre-populated values for edit mode (Phase 5.1). */
  initial?: Record<string, unknown>;
  /** Optional record id for edit mode (Phase 5.1). */
  editId?: string;
};

/**
 * Create-record form for a manifest entity. Renders one input per field
 * in the entity schema; submits to POST /api/manifest/<slug>/records/<entity>.
 *
 * Field-type → control mapping:
 *   string      → text input
 *   number      → number input
 *   boolean     → checkbox
 *   date        → date input
 *   datetime    → datetime-local input
 *   enum        → select (uses enum_values from the field def)
 *   json        → key-value editor with an Advanced (raw JSON) toggle
 *
 * Required fields render with an asterisk and HTML-level required=true.
 * Field names are humanized (snake_case → Title Case); the underlying
 * field type is intentionally NOT surfaced — operators don't need to
 * think about whether a field is a string or number. Per-field validation
 * errors render below each input (not in a single banner) so the
 * operator can fix them in place. Server-side validation in the records
 * API + RecordsError catches anything the client missed.
 */

/** snake_case → "Title Case" for human-friendly labels. */
function humanize(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Per-field example placeholder. Helps operators infer the expected shape
 *  without having to read the underlying type. Kept conservative — only
 *  fields with universally obvious examples get a placeholder; everything
 *  else falls back to the empty string. */
function placeholderFor(field: ManifestEntityField): string {
  const n = field.name.toLowerCase();
  if (field.type === "number") {
    if (n.includes("amount") || n.includes("revenue") || n.includes("funded") || n.includes("price")) return "25000";
    if (n.includes("rate") || n.includes("factor")) return "1.35";
    if (n.includes("months") || n.includes("term")) return "12";
    if (n.includes("fico") || n.includes("score")) return "650";
    return "";
  }
  if (field.type === "date" || field.type === "datetime") return "";
  if (n === "email" || n.endsWith("_email")) return "name@example.com";
  if (n === "phone" || n.endsWith("_phone")) return "+1 555 123 4567";
  if (n === "url" || n.endsWith("_url")) return "https://...";
  if (n === "first_name") return "Hunter";
  if (n === "last_name") return "Smith";
  if (n === "business_name" || n === "company") return "Hunter Construction Inc.";
  return "";
}
export function ManifestRecordForm({
  tenantSlug,
  entity,
  backPath,
  initial,
  editId,
}: Props) {
  const router = useRouter();
  const [values, setValues] = useState<Record<string, unknown>>(initial || {});
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const isEdit = !!editId;

  function setField(name: string, value: unknown) {
    setValues((v) => ({ ...v, [name]: value }));
    // Clear the field's error as soon as the operator edits it — feels
    // like a normal form, not a punitive one.
    if (fieldErrors[name]) {
      setFieldErrors((errs) => {
        const next = { ...errs };
        delete next[name];
        return next;
      });
    }
  }

  /** Build payload + per-field errors. Returns null when there are errors;
   *  the caller surfaces them inline. Server still re-validates. */
  function buildPayload(): { payload: Record<string, unknown> } | { errors: Record<string, string> } {
    const out: Record<string, unknown> = {};
    const errs: Record<string, string> = {};
    for (const f of entity.fields) {
      const raw = values[f.name];
      const empty = raw === undefined || raw === "" || raw === null;
      if (empty) {
        if (f.required) errs[f.name] = "Required";
        continue;
      }
      if (f.type === "number") {
        const n = Number(raw);
        if (Number.isNaN(n)) {
          errs[f.name] = "Must be a number";
          continue;
        }
        out[f.name] = n;
      } else if (f.type === "boolean") {
        out[f.name] = !!raw;
      } else if (f.type === "json") {
        // JSON fields accept either an object (from the key-value editor)
        // or a string (raw-JSON Advanced mode). Object → pass through;
        // string → parse with a friendly error.
        if (typeof raw === "object") {
          out[f.name] = raw;
        } else {
          try {
            out[f.name] = JSON.parse(String(raw));
          } catch {
            errs[f.name] = "Invalid JSON — try the simple editor instead";
          }
        }
      } else {
        out[f.name] = raw;
      }
    }
    if (Object.keys(errs).length > 0) return { errors: errs };
    return { payload: out };
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (saving) return;
    setFieldErrors({});
    setFormError(null);
    setFlash(null);
    setSaving(true);

    const result = buildPayload();
    if ("errors" in result) {
      setFieldErrors(result.errors);
      setFormError("Fix the highlighted fields and try again.");
      setSaving(false);
      return;
    }

    try {
      const url = isEdit
        ? `/api/manifest/${tenantSlug}/records/${entity.name}?id=${encodeURIComponent(editId!)}`
        : `/api/manifest/${tenantSlug}/records/${entity.name}`;
      const res = await fetch(url, {
        method: isEdit ? "PATCH" : "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(isEdit ? { patch: result.payload } : { data: result.payload }),
      });
      const data = (await res.json()) as
        | { ok: true; record: { id: string } }
        | { ok: false; error: string; message?: string };
      if (!data.ok) {
        setFormError(data.message || data.error);
        setSaving(false);
        return;
      }
      setFlash("Saved. Redirecting...");
      router.push(`/t/${tenantSlug}/${backPath}`);
      router.refresh();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "network_error");
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4 rounded-2xl border border-bg-border bg-bg-elev/40 p-5">
      {entity.fields.map((field) => (
        <FieldInput
          key={field.name}
          field={field}
          value={values[field.name]}
          error={fieldErrors[field.name] ?? null}
          onChange={(v) => setField(field.name, v)}
          disabled={saving}
        />
      ))}

      {flash && (
        <div className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-sm text-emerald-100 inline-flex items-start gap-2">
          <CheckCircle2 className="h-4 w-4 mt-0.5" />
          <span>{flash}</span>
        </div>
      )}
      {formError && (
        <div className="rounded-xl border border-red-400/30 bg-red-400/10 px-3 py-2 text-sm text-red-200 inline-flex items-start gap-2">
          <AlertCircle className="h-4 w-4 mt-0.5" />
          <span>{formError}</span>
        </div>
      )}

      <div className="flex items-center gap-2 pt-3 border-t border-bg-border">
        <button
          type="submit"
          disabled={saving}
          className="btn-send inline-flex items-center gap-1.5 !px-4 !py-2 text-sm"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {isEdit ? "Save changes" : `Create ${entity.label.toLowerCase()}`}
        </button>
        <Link
          href={`/t/${tenantSlug}/${backPath}`}
          className="btn-secondary inline-flex items-center gap-1.5 !px-3 !py-2 text-sm"
        >
          <ArrowLeft className="h-4 w-4" />
          Cancel
        </Link>
      </div>
    </form>
  );
}

function FieldInput({
  field,
  value,
  error,
  onChange,
  disabled,
}: {
  field: ManifestEntityField;
  value: unknown;
  error: string | null;
  onChange: (v: unknown) => void;
  disabled?: boolean;
}) {
  const labelText = humanize(field.name);
  const label = (
    <span className="text-xs font-semibold text-fg block mb-1">
      {labelText}
      {field.required && <span className="ml-1 text-accent">*</span>}
    </span>
  );

  // Red ring when this field has a validation error. Otherwise the
  // standard ring + accent focus state.
  const ringClass = error
    ? "border-red-400/60 focus:border-red-400/80"
    : "border-bg-border focus:border-accent/50";
  const baseClass =
    `w-full rounded-xl border ${ringClass} bg-bg-deep/80 px-3 py-2 text-sm text-fg placeholder:text-fg-faint focus:outline-none disabled:opacity-50`;

  const placeholder = placeholderFor(field);

  // Inline error renderer — appears immediately below each input. Kept
  // out of the per-type branches so every field renders errors the same
  // way.
  const errorNode = error ? (
    <div className="text-[11px] text-red-300 mt-1 inline-flex items-center gap-1">
      <AlertCircle className="h-3 w-3" />
      <span>{error}</span>
    </div>
  ) : null;

  if (field.type === "enum" && field.enum_values && field.enum_values.length > 0) {
    return (
      <label className="block">
        {label}
        <select
          value={(value as string) || ""}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className={baseClass}
        >
          <option value="">— pick one —</option>
          {field.enum_values.map((v) => (
            <option key={v} value={v}>
              {humanize(v)}
            </option>
          ))}
        </select>
        {errorNode}
      </label>
    );
  }
  if (field.type === "boolean") {
    return (
      <label className="flex items-center gap-2 text-sm text-fg">
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(e.target.checked)}
          disabled={disabled}
        />
        <span>
          {labelText}
          {field.required && <span className="ml-1 text-accent">*</span>}
        </span>
        {errorNode}
      </label>
    );
  }
  if (field.type === "number") {
    return (
      <label className="block">
        {label}
        <input
          type="number"
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder={placeholder}
          className={baseClass}
        />
        {errorNode}
      </label>
    );
  }
  if (field.type === "date") {
    return (
      <label className="block">
        {label}
        <input
          type="date"
          value={(value as string) || ""}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className={baseClass}
        />
        {errorNode}
      </label>
    );
  }
  if (field.type === "datetime") {
    return (
      <label className="block">
        {label}
        <input
          type="datetime-local"
          value={(value as string) || ""}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className={baseClass}
        />
        {errorNode}
      </label>
    );
  }
  if (field.type === "json") {
    return (
      <JsonField
        label={label}
        value={value}
        onChange={onChange}
        disabled={disabled}
        baseClass={baseClass}
        errorNode={errorNode}
      />
    );
  }
  // string default — picks email/phone/url input mode from the field
  // name so the mobile keyboard surfaces the right keys.
  const n = field.name.toLowerCase();
  const inputType =
    n === "email" || n.endsWith("_email") ? "email"
    : n === "phone" || n.endsWith("_phone") ? "tel"
    : n === "url" || n.endsWith("_url") ? "url"
    : "text";
  return (
    <label className="block">
      {label}
      <input
        type={inputType}
        value={(value as string) || ""}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        placeholder={placeholder}
        className={baseClass}
      />
      {errorNode}
    </label>
  );
}

/**
 * Editor for `type: "json"` fields. Default surface is a key/value list
 * (one row per top-level key, value is a plain text input). An "Advanced
 * (raw JSON)" toggle reveals a monospace textarea for operators who need
 * nested structures.
 *
 * The committed value is always an object — the consuming form serializes
 * it as JSON on submit. If the operator pastes invalid JSON in the
 * Advanced view, the parent form catches it during buildPayload() and
 * surfaces an inline error.
 */
function JsonField({
  label,
  value,
  onChange,
  disabled,
  baseClass,
  errorNode,
}: {
  label: React.ReactNode;
  value: unknown;
  onChange: (v: unknown) => void;
  disabled?: boolean;
  baseClass: string;
  errorNode: React.ReactNode;
}) {
  // Normalize the current value to a row list. The form may hand us an
  // object (the common case), a string (legacy / Advanced-mode draft),
  // or nothing.
  const initialRows = (() => {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return Object.entries(value as Record<string, unknown>).map(([k, v]) => ({
        key: k,
        value: typeof v === "string" ? v : JSON.stringify(v),
      }));
    }
    return [] as { key: string; value: string }[];
  })();
  const [rows, setRows] = useState(initialRows);
  const [rawMode, setRawMode] = useState(false);
  const [rawText, setRawText] = useState(() => {
    if (typeof value === "string") return value;
    if (value && typeof value === "object") return JSON.stringify(value, null, 2);
    return "";
  });

  function commitRows(next: { key: string; value: string }[]) {
    setRows(next);
    const obj: Record<string, string> = {};
    for (const r of next) {
      if (!r.key.trim()) continue;
      obj[r.key.trim()] = r.value;
    }
    onChange(obj);
  }

  if (rawMode) {
    return (
      <label className="block">
        <div className="flex items-center justify-between mb-1">
          {label}
          <button
            type="button"
            onClick={() => setRawMode(false)}
            className="text-[10px] uppercase tracking-wider text-fg-dim hover:text-fg inline-flex items-center gap-1"
          >
            <X className="h-3 w-3" /> Simple
          </button>
        </div>
        <textarea
          rows={4}
          value={rawText}
          onChange={(e) => {
            setRawText(e.target.value);
            // Keep the parent's value in sync as a string — buildPayload
            // will parse it. This lets the operator type incomplete JSON
            // without us erroring on every keystroke.
            onChange(e.target.value);
          }}
          disabled={disabled}
          placeholder='{"key":"value"}'
          className={`${baseClass} font-mono`}
        />
        {errorNode}
      </label>
    );
  }

  return (
    <div className="block">
      <div className="flex items-center justify-between mb-1">
        {label}
        <button
          type="button"
          onClick={() => setRawMode(true)}
          className="text-[10px] uppercase tracking-wider text-fg-dim hover:text-fg inline-flex items-center gap-1"
          title="Switch to raw JSON for nested structures"
        >
          <Code2 className="h-3 w-3" /> Advanced
        </button>
      </div>
      <div className="space-y-2">
        {rows.map((row, idx) => (
          <div key={idx} className="flex items-center gap-2">
            <input
              type="text"
              value={row.key}
              onChange={(e) => {
                const next = [...rows];
                next[idx] = { ...row, key: e.target.value };
                commitRows(next);
              }}
              disabled={disabled}
              placeholder="key"
              className={`${baseClass} w-1/3`}
            />
            <input
              type="text"
              value={row.value}
              onChange={(e) => {
                const next = [...rows];
                next[idx] = { ...row, value: e.target.value };
                commitRows(next);
              }}
              disabled={disabled}
              placeholder="value"
              className={baseClass}
            />
            <button
              type="button"
              onClick={() => commitRows(rows.filter((_, i) => i !== idx))}
              disabled={disabled}
              className="shrink-0 p-1 text-fg-dim hover:text-red-300"
              title="Remove"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => commitRows([...rows, { key: "", value: "" }])}
          disabled={disabled}
          className="inline-flex items-center gap-1 text-xs text-fg-muted hover:text-fg"
        >
          <Plus className="h-3 w-3" /> Add field
        </button>
      </div>
      {errorNode}
    </div>
  );
}
