"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, CheckCircle2, Loader2, Save, AlertCircle } from "lucide-react";
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
 *   json        → textarea (operator pastes raw JSON)
 *
 * Required fields render with an asterisk and HTML-level required=true.
 * Server-side validation (the records API + RecordsError) catches anything
 * the client missed. Errors render inline below the buttons.
 */
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
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const isEdit = !!editId;

  function setField(name: string, value: unknown) {
    setValues((v) => ({ ...v, [name]: value }));
  }

  function buildPayload(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const f of entity.fields) {
      const raw = values[f.name];
      if (raw === undefined || raw === "" || raw === null) continue;
      if (f.type === "number") {
        const n = Number(raw);
        if (!Number.isNaN(n)) out[f.name] = n;
      } else if (f.type === "boolean") {
        out[f.name] = !!raw;
      } else if (f.type === "json") {
        try {
          out[f.name] = JSON.parse(String(raw));
        } catch {
          throw new Error(`${f.name}: invalid JSON`);
        }
      } else {
        out[f.name] = raw;
      }
    }
    return out;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (saving) return;
    setError(null);
    setFlash(null);
    setSaving(true);

    let payload: Record<string, unknown>;
    try {
      payload = buildPayload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "invalid input");
      setSaving(false);
      return;
    }

    // Required-field check on the client so the operator sees field-level
    // errors before the round-trip. Server still re-validates.
    for (const f of entity.fields) {
      if (f.required && (payload[f.name] === undefined || payload[f.name] === "")) {
        setError(`${f.name} is required`);
        setSaving(false);
        return;
      }
    }

    try {
      const url = isEdit
        ? `/api/manifest/${tenantSlug}/records/${entity.name}?id=${encodeURIComponent(editId!)}`
        : `/api/manifest/${tenantSlug}/records/${entity.name}`;
      const res = await fetch(url, {
        method: isEdit ? "PATCH" : "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(isEdit ? { patch: payload } : { data: payload }),
      });
      const data = (await res.json()) as
        | { ok: true; record: { id: string } }
        | { ok: false; error: string; message?: string };
      if (!data.ok) {
        setError(data.message || data.error);
        setSaving(false);
        return;
      }
      setFlash("Saved. Redirecting...");
      router.push(`/t/${tenantSlug}/${backPath}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "network_error");
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
      {error && (
        <div className="rounded-xl border border-red-400/30 bg-red-400/10 px-3 py-2 text-sm text-red-200 inline-flex items-start gap-2">
          <AlertCircle className="h-4 w-4 mt-0.5" />
          <span>{error}</span>
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
  onChange,
  disabled,
}: {
  field: ManifestEntityField;
  value: unknown;
  onChange: (v: unknown) => void;
  disabled?: boolean;
}) {
  const label = (
    <span className="text-xs font-semibold text-fg block mb-1">
      {field.name.replace(/_/g, " ")}
      {field.required && <span className="ml-1 text-accent">*</span>}
      <span className="ml-2 text-[10px] uppercase tracking-wider text-fg-dim font-mono">{field.type}</span>
    </span>
  );

  const baseClass =
    "w-full rounded-xl border border-bg-border bg-bg-deep/80 px-3 py-2 text-sm text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none disabled:opacity-50";

  if (field.type === "enum" && field.enum_values && field.enum_values.length > 0) {
    return (
      <label className="block">
        {label}
        <select
          value={(value as string) || ""}
          onChange={(e) => onChange(e.target.value)}
          required={field.required}
          disabled={disabled}
          className={baseClass}
        >
          <option value="">— pick one —</option>
          {field.enum_values.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
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
          {field.name.replace(/_/g, " ")}
          {field.required && <span className="ml-1 text-accent">*</span>}
        </span>
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
          required={field.required}
          disabled={disabled}
          className={baseClass}
        />
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
          required={field.required}
          disabled={disabled}
          className={baseClass}
        />
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
          required={field.required}
          disabled={disabled}
          className={baseClass}
        />
      </label>
    );
  }
  if (field.type === "json") {
    return (
      <label className="block">
        {label}
        <textarea
          rows={4}
          value={(value as string) || ""}
          onChange={(e) => onChange(e.target.value)}
          required={field.required}
          disabled={disabled}
          placeholder='{"key":"value"}'
          className={`${baseClass} font-mono`}
        />
      </label>
    );
  }
  // string default
  return (
    <label className="block">
      {label}
      <input
        type="text"
        value={(value as string) || ""}
        onChange={(e) => onChange(e.target.value)}
        required={field.required}
        disabled={disabled}
        className={baseClass}
      />
    </label>
  );
}
