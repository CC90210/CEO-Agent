"use client";

/**
 * Visual fields editor — replaces the raw "Steps (JSON)" textarea with a
 * structured per-step / per-field UI. Operators add fields with a type
 * dropdown, label, required toggle, and (for file_upload) accepted MIME
 * types + min/max file counts. The underlying state is still the same
 * FormStep[] shape so parseFormSteps still validates on save.
 *
 * Two top-level escape hatches the operator can grow into:
 *   - "Add file upload" preset stamps out the standard 3-document SunBiz
 *     intake (bank statements / ID / proof of ownership) since that's the
 *     overwhelming default.
 *   - The JSON power-user view is reachable from the builder via a tab
 *     (FormBuilderClient owns that toggle).
 */

import { useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  GripVertical,
  Plus,
  Trash2,
  Wand2,
} from "lucide-react";
import type { FormStep, FormField, FormFieldType } from "@/lib/forms/types";

const FIELD_TYPE_LABELS: Record<FormFieldType, string> = {
  text: "Text",
  textarea: "Long text",
  email: "Email",
  phone: "Phone",
  number: "Number",
  currency: "Currency ($)",
  date: "Date",
  select: "Single-select dropdown",
  multiselect: "Multi-select",
  rating: "Rating (1–5)",
  file_upload: "File upload",
  signature: "Signature",
  hidden: "Hidden (operator-set value)",
};

const FIELD_TYPES_ORDERED: FormFieldType[] = [
  "text",
  "textarea",
  "email",
  "phone",
  "number",
  "currency",
  "date",
  "select",
  "multiselect",
  "rating",
  "file_upload",
  "signature",
  "hidden",
];

// SunBiz canonical document intake. Each entry maps to a doc_type the
// classifier expects (database/049_crm_reconstructor.sql §lead_documents).
const SUNBIZ_DOC_PRESETS: Array<{
  name: string;
  label: string;
  help: string;
  accept: string[];
}> = [
  {
    name: "bank_statements_3mo",
    label: "Last 3 months of bank statements",
    help: "PDF preferred. One file per month is fine.",
    accept: ["application/pdf", "image/*"],
  },
  {
    name: "drivers_license",
    label: "Photo of your driver's license",
    help: "Front of card, clear and readable.",
    accept: ["image/*", "application/pdf"],
  },
  {
    name: "proof_of_ownership",
    label: "Proof of business ownership",
    help: "Articles of incorporation, EIN letter, or business license.",
    accept: ["application/pdf", "image/*"],
  },
];

function slugifyName(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 60) || "field";
}

function blankField(type: FormFieldType): FormField {
  const label =
    type === "file_upload"
      ? "Upload a document"
      : type === "email"
        ? "Email"
        : type === "phone"
          ? "Phone"
          : "New field";
  const field: FormField = {
    name: slugifyName(label),
    label,
    type,
  };
  if (type === "select" || type === "multiselect") {
    field.options = [
      { value: "option_1", label: "Option 1" },
      { value: "option_2", label: "Option 2" },
    ];
  }
  if (type === "file_upload") {
    field.accept = ["application/pdf", "image/*"];
    field.required = true;
  }
  return field;
}

type Props = {
  steps: FormStep[];
  onChange: (next: FormStep[]) => void;
};

export function VisualFieldsEditor({ steps, onChange }: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(steps.map((s, i) => [s.key || String(i), i === 0])),
  );

  function updateStep(idx: number, patch: Partial<FormStep>) {
    const next = steps.map((s, i) => (i === idx ? { ...s, ...patch } : s));
    onChange(next);
  }

  function removeStep(idx: number) {
    if (steps.length <= 1) return;
    onChange(steps.filter((_, i) => i !== idx));
  }

  function addStep() {
    const key = `step_${steps.length + 1}`;
    onChange([
      ...steps,
      { key, title: `Step ${steps.length + 1}`, fields: [] },
    ]);
    setExpanded((prev) => ({ ...prev, [key]: true }));
  }

  function moveStep(idx: number, dir: -1 | 1) {
    const target = idx + dir;
    if (target < 0 || target >= steps.length) return;
    const next = steps.slice();
    [next[idx], next[target]] = [next[target], next[idx]];
    onChange(next);
  }

  function updateField(
    stepIdx: number,
    fieldIdx: number,
    patch: Partial<FormField>,
  ) {
    const step = steps[stepIdx];
    const fields = step.fields.map((f, i) =>
      i === fieldIdx ? { ...f, ...patch } : f,
    );
    updateStep(stepIdx, { fields });
  }

  function removeField(stepIdx: number, fieldIdx: number) {
    const step = steps[stepIdx];
    updateStep(stepIdx, {
      fields: step.fields.filter((_, i) => i !== fieldIdx),
    });
  }

  function addField(stepIdx: number, type: FormFieldType) {
    const step = steps[stepIdx];
    updateStep(stepIdx, { fields: [...step.fields, blankField(type)] });
  }

  function moveField(stepIdx: number, fieldIdx: number, dir: -1 | 1) {
    const step = steps[stepIdx];
    const target = fieldIdx + dir;
    if (target < 0 || target >= step.fields.length) return;
    const fields = step.fields.slice();
    [fields[fieldIdx], fields[target]] = [fields[target], fields[fieldIdx]];
    updateStep(stepIdx, { fields });
  }

  function addSunBizDocsStep() {
    const fields: FormField[] = SUNBIZ_DOC_PRESETS.map((preset) => ({
      name: preset.name,
      label: preset.label,
      help: preset.help,
      type: "file_upload" as const,
      required: true,
      accept: preset.accept,
    }));
    const key = `documents_${steps.length + 1}`;
    onChange([
      ...steps,
      {
        key,
        title: "Upload your documents",
        description:
          "We need three files to underwrite your application. Each one's required.",
        fields,
      },
    ]);
    setExpanded((prev) => ({ ...prev, [key]: true }));
  }

  return (
    <div className="space-y-4">
      {steps.map((step, sIdx) => {
        const stepKey = step.key || String(sIdx);
        const open = expanded[stepKey] ?? false;
        return (
          <div
            key={stepKey}
            className="rounded-xl border border-bg-border bg-bg-elev/30"
          >
            <div className="flex items-center gap-2 p-3 border-b border-bg-border">
              <button
                type="button"
                onClick={() =>
                  setExpanded((prev) => ({ ...prev, [stepKey]: !open }))
                }
                className="text-fg-muted hover:text-fg"
                aria-label={open ? "Collapse step" : "Expand step"}
              >
                {open ? (
                  <ChevronUp className="w-4 h-4" />
                ) : (
                  <ChevronDown className="w-4 h-4" />
                )}
              </button>
              <span className="text-[11px] font-bold uppercase tracking-wider text-fg-dim">
                Step {sIdx + 1}
              </span>
              <input
                value={step.title}
                onChange={(e) => updateStep(sIdx, { title: e.target.value })}
                placeholder="Step title"
                className="flex-1 rounded-md border border-bg-border bg-bg-elev px-3 py-1.5 text-sm text-fg"
              />
              <div className="flex items-center gap-1 text-fg-muted">
                <button
                  type="button"
                  onClick={() => moveStep(sIdx, -1)}
                  disabled={sIdx === 0}
                  className="p-1 hover:text-fg disabled:opacity-30"
                  aria-label="Move step up"
                >
                  <ChevronUp className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => moveStep(sIdx, 1)}
                  disabled={sIdx === steps.length - 1}
                  className="p-1 hover:text-fg disabled:opacity-30"
                  aria-label="Move step down"
                >
                  <ChevronDown className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => removeStep(sIdx)}
                  disabled={steps.length <= 1}
                  className="p-1 hover:text-rose-400 disabled:opacity-30"
                  aria-label="Delete step"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {open && (
              <div className="p-3 space-y-3">
                <div className="grid sm:grid-cols-2 gap-3">
                  <input
                    value={step.key}
                    onChange={(e) =>
                      updateStep(sIdx, {
                        key: e.target.value
                          .toLowerCase()
                          .replace(/[^a-z0-9_]/g, "_"),
                      })
                    }
                    placeholder="step_key"
                    className="rounded-md border border-bg-border bg-bg-elev px-3 py-1.5 font-mono text-xs text-fg"
                  />
                  <input
                    value={step.cta_label || ""}
                    onChange={(e) =>
                      updateStep(sIdx, {
                        cta_label: e.target.value || undefined,
                      })
                    }
                    placeholder='Button label (default "Continue")'
                    className="rounded-md border border-bg-border bg-bg-elev px-3 py-1.5 text-sm text-fg"
                  />
                </div>
                <input
                  value={step.description || ""}
                  onChange={(e) =>
                    updateStep(sIdx, {
                      description: e.target.value || undefined,
                    })
                  }
                  placeholder="Short description shown under the title (optional)"
                  className="w-full rounded-md border border-bg-border bg-bg-elev px-3 py-1.5 text-sm text-fg"
                />

                <div className="space-y-2">
                  {step.fields.length === 0 && (
                    <div className="text-xs text-fg-dim italic py-2 text-center">
                      No fields yet. Add one below.
                    </div>
                  )}
                  {step.fields.map((field, fIdx) => (
                    <FieldRow
                      key={fIdx}
                      field={field}
                      onChange={(patch) => updateField(sIdx, fIdx, patch)}
                      onRemove={() => removeField(sIdx, fIdx)}
                      onMoveUp={
                        fIdx === 0 ? null : () => moveField(sIdx, fIdx, -1)
                      }
                      onMoveDown={
                        fIdx === step.fields.length - 1
                          ? null
                          : () => moveField(sIdx, fIdx, 1)
                      }
                    />
                  ))}
                </div>

                <AddFieldRow onAdd={(type) => addField(sIdx, type)} />
              </div>
            )}
          </div>
        );
      })}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={addStep}
          className="inline-flex items-center gap-2 rounded-lg border border-bg-border bg-bg-elev px-3 py-1.5 text-xs font-bold text-fg hover:border-accent/40"
        >
          <Plus className="w-3.5 h-3.5" />
          Add step
        </button>
        <button
          type="button"
          onClick={addSunBizDocsStep}
          className="inline-flex items-center gap-2 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-bold text-accent hover:bg-accent/20"
          title="Adds a 3-file upload step (bank statements, ID, proof of ownership)"
        >
          <Wand2 className="w-3.5 h-3.5" />
          Add SunBiz docs step
        </button>
      </div>
    </div>
  );
}

function FieldRow({
  field,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
}: {
  field: FormField;
  onChange: (patch: Partial<FormField>) => void;
  onRemove: () => void;
  onMoveUp: (() => void) | null;
  onMoveDown: (() => void) | null;
}) {
  return (
    <div className="rounded-lg border border-bg-border bg-bg-deep/60 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <GripVertical className="w-3.5 h-3.5 text-fg-dim shrink-0" />
        <select
          value={field.type}
          onChange={(e) =>
            onChange({ type: e.target.value as FormFieldType })
          }
          className="rounded-md border border-bg-border bg-bg-elev px-2 py-1 text-xs text-fg"
        >
          {FIELD_TYPES_ORDERED.map((t) => (
            <option key={t} value={t}>
              {FIELD_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
        <input
          value={field.label}
          onChange={(e) => {
            const label = e.target.value;
            // Auto-keep `name` slugged from label until operator manually
            // edits the name — this matches every visual builder users
            // expect (Tally, Typeform). Once name diverges, we leave it.
            const auto =
              slugifyName(field.label) === field.name
                ? slugifyName(label)
                : field.name;
            onChange({ label, name: auto });
          }}
          placeholder="Field label"
          className="flex-1 rounded-md border border-bg-border bg-bg-elev px-2 py-1 text-sm text-fg"
        />
        <label className="flex items-center gap-1.5 text-xs text-fg-muted cursor-pointer whitespace-nowrap">
          <input
            type="checkbox"
            checked={!!field.required}
            onChange={(e) => onChange({ required: e.target.checked })}
            className="accent-accent"
          />
          Required
        </label>
        <div className="flex items-center gap-0.5 text-fg-dim">
          <button
            type="button"
            onClick={onMoveUp || undefined}
            disabled={!onMoveUp}
            className="p-1 hover:text-fg disabled:opacity-30"
            aria-label="Move field up"
          >
            <ChevronUp className="w-3 h-3" />
          </button>
          <button
            type="button"
            onClick={onMoveDown || undefined}
            disabled={!onMoveDown}
            className="p-1 hover:text-fg disabled:opacity-30"
            aria-label="Move field down"
          >
            <ChevronDown className="w-3 h-3" />
          </button>
          <button
            type="button"
            onClick={onRemove}
            className="p-1 hover:text-rose-400"
            aria-label="Delete field"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-2 pl-5">
        <input
          value={field.name}
          onChange={(e) =>
            onChange({
              name: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"),
            })
          }
          placeholder="field_name"
          className="rounded-md border border-bg-border bg-bg-elev px-2 py-1 font-mono text-[11px] text-fg-muted"
        />
        <input
          value={field.placeholder || ""}
          onChange={(e) =>
            onChange({ placeholder: e.target.value || undefined })
          }
          placeholder="Placeholder text (optional)"
          className="rounded-md border border-bg-border bg-bg-elev px-2 py-1 text-xs text-fg"
        />
      </div>
      <input
        value={field.help || ""}
        onChange={(e) => onChange({ help: e.target.value || undefined })}
        placeholder="Help text shown under the input (optional)"
        className="w-full rounded-md border border-bg-border bg-bg-elev px-2 py-1 text-xs text-fg ml-5"
        style={{ width: "calc(100% - 1.25rem)" }}
      />

      {(field.type === "select" || field.type === "multiselect") && (
        <OptionsEditor
          options={field.options || []}
          onChange={(options) => onChange({ options })}
        />
      )}

      {field.type === "file_upload" && (
        <div className="pl-5 grid sm:grid-cols-2 gap-2">
          <label className="text-[11px] text-fg-dim">
            Accepted file types
            <input
              value={(field.accept || []).join(", ")}
              onChange={(e) =>
                onChange({
                  accept: e.target.value
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
              placeholder="application/pdf, image/*"
              className="mt-1 w-full rounded-md border border-bg-border bg-bg-elev px-2 py-1 text-xs text-fg"
            />
          </label>
        </div>
      )}

      {field.type === "hidden" && (
        <input
          value={field.value || ""}
          onChange={(e) =>
            onChange({ value: e.target.value || undefined })
          }
          placeholder="Static value written into the submission"
          className="ml-5 rounded-md border border-bg-border bg-bg-elev px-2 py-1 text-xs text-fg"
          style={{ width: "calc(100% - 1.25rem)" }}
        />
      )}
    </div>
  );
}

function OptionsEditor({
  options,
  onChange,
}: {
  options: { value: string; label: string }[];
  onChange: (next: { value: string; label: string }[]) => void;
}) {
  return (
    <div className="pl-5 space-y-1">
      <div className="text-[11px] text-fg-dim">Options</div>
      {options.map((opt, i) => (
        <div key={i} className="flex items-center gap-2">
          <input
            value={opt.label}
            onChange={(e) => {
              const next = options.slice();
              next[i] = { ...opt, label: e.target.value };
              onChange(next);
            }}
            placeholder="Display label"
            className="flex-1 rounded-md border border-bg-border bg-bg-elev px-2 py-1 text-xs text-fg"
          />
          <input
            value={opt.value}
            onChange={(e) => {
              const next = options.slice();
              next[i] = { ...opt, value: e.target.value };
              onChange(next);
            }}
            placeholder="storage_value"
            className="w-32 rounded-md border border-bg-border bg-bg-elev px-2 py-1 font-mono text-[11px] text-fg-muted"
          />
          <button
            type="button"
            onClick={() => onChange(options.filter((_, j) => j !== i))}
            className="text-fg-dim hover:text-rose-400 p-1"
            aria-label="Remove option"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() =>
          onChange([
            ...options,
            { value: `option_${options.length + 1}`, label: "New option" },
          ])
        }
        className="text-[11px] text-accent hover:text-accent-bright inline-flex items-center gap-1"
      >
        <Plus className="w-3 h-3" /> Add option
      </button>
    </div>
  );
}

function AddFieldRow({ onAdd }: { onAdd: (type: FormFieldType) => void }) {
  const [type, setType] = useState<FormFieldType>("text");
  return (
    <div className="flex items-center gap-2 pt-1">
      <select
        value={type}
        onChange={(e) => setType(e.target.value as FormFieldType)}
        className="rounded-md border border-bg-border bg-bg-elev px-2 py-1 text-xs text-fg"
      >
        {FIELD_TYPES_ORDERED.map((t) => (
          <option key={t} value={t}>
            {FIELD_TYPE_LABELS[t]}
          </option>
        ))}
      </select>
      <button
        type="button"
        onClick={() => onAdd(type)}
        className="inline-flex items-center gap-1 rounded-md border border-bg-border bg-bg-elev px-2 py-1 text-xs text-fg hover:border-accent/40"
      >
        <Plus className="w-3 h-3" />
        Add field
      </button>
    </div>
  );
}
