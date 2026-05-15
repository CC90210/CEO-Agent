/**
 * forms/types.ts — shared shape for tenant-defined forms.
 *
 * Phase 3 of the SunBiz CRM build (2026-05-15). The dashboard form
 * builder (/forms/[id]/edit) writes these shapes into the `forms.steps`
 * + `forms.branding` jsonb columns; the public form renderer at
 * /f/<tenant>/<slug>/<token> reads them back. Centralizing the types
 * prevents drift — every consumer (builder, renderer, /api/forms/submit
 * validator, Solara's tool calls) imports from here.
 *
 * Validation:
 *   - parseFormDefinition() is the runtime validator. Throws
 *     FormDefinitionError on shape violations. Use for any input crossing
 *     a trust boundary (POST body, agent-tool call, raw DB column).
 *   - Pure-TS callers (the builder UI, server components) can import the
 *     types directly without parsing — they construct values that match
 *     by construction.
 */

// ---------------------------------------------------------------------------
// Field types
// ---------------------------------------------------------------------------

export type FormFieldType =
  | "text"
  | "textarea"
  | "email"
  | "phone"
  | "number"
  | "currency"
  | "date"
  | "select"
  | "multiselect"
  | "signature"
  | "file_upload"
  | "hidden"
  | "rating";

export type FormFieldOption = {
  /** Storage value — written into form_submissions.payload. */
  value: string;
  /** Display label — shown to the prospect. */
  label: string;
};

export type FormField = {
  /** Key under form_submissions.payload. Must match /^[a-z][a-z0-9_]*$/. */
  name: string;
  /** Human label shown above the input. */
  label: string;
  type: FormFieldType;
  required?: boolean;
  /** Optional one-line help text shown below the input. */
  help?: string;
  /** Placeholder for text-style inputs. */
  placeholder?: string;
  /** For select / multiselect. */
  options?: FormFieldOption[];
  /** For number / currency — min/max bounds. */
  min?: number;
  max?: number;
  /** For text / textarea — max character length. */
  maxLength?: number;
  /** For file_upload — accepted MIME types (e.g. ["application/pdf"]). */
  accept?: string[];
  /** For hidden fields — the static value written into the submission. */
  value?: string;
};

// ---------------------------------------------------------------------------
// Steps + branding
// ---------------------------------------------------------------------------

export type FormStep = {
  /** Stable key — used in step_outcomes to map step → lead.stage. */
  key: string;
  /** Step title shown at the top of the public form page. */
  title: string;
  /** Optional one-line description under the title. */
  description?: string;
  /** Submit-button label. Defaults to "Continue" (or "Submit" on last step). */
  cta_label?: string;
  fields: FormField[];
};

export type FormBranding = {
  /** Primary brand color (CSS hex). Used for buttons + headings. */
  primary_color?: string;
  /** Accent color for secondary elements. */
  accent_color?: string;
  /** Logo URL — rendered at the top of the public form. */
  logo_url?: string;
  /** Headline shown above the first step (e.g. "Sun Biz Funding · Application"). */
  headline?: string;
  /** One-line subheadline below the headline. */
  subheadline?: string;
  /** "Thank you" screen text after final submission (if no redirect_url). */
  thanks_message?: string;
};

export type FormDefinition = {
  id: string;
  tenant_id: string;
  slug: string;
  name: string;
  description: string | null;
  branding: FormBranding;
  steps: FormStep[];
  on_complete_stage: string | null;
  /** Per-step stage transitions. Keys are stringified step indices. */
  step_outcomes: Record<string, string>;
  enabled: boolean;
  redirect_url: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

// ---------------------------------------------------------------------------
// Runtime validation — throws FormDefinitionError on shape violations
// ---------------------------------------------------------------------------

export class FormDefinitionError extends Error {
  constructor(public path: string, public reason: string) {
    super(`form definition invalid at ${path}: ${reason}`);
    this.name = "FormDefinitionError";
  }
}

const FIELD_NAME_RE = /^[a-z][a-z0-9_]{0,62}$/;
const STEP_KEY_RE = /^[a-z][a-z0-9_-]{0,62}$/;
const VALID_FIELD_TYPES: ReadonlySet<FormFieldType> = new Set([
  "text",
  "textarea",
  "email",
  "phone",
  "number",
  "currency",
  "date",
  "select",
  "multiselect",
  "signature",
  "file_upload",
  "hidden",
  "rating",
]);

function isStringRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function requireString(obj: Record<string, unknown>, key: string, path: string): string {
  const v = obj[key];
  if (typeof v !== "string" || !v.trim()) {
    throw new FormDefinitionError(`${path}.${key}`, "expected non-empty string");
  }
  return v;
}

function optionalString(obj: Record<string, unknown>, key: string): string | undefined {
  const v = obj[key];
  return typeof v === "string" && v.length > 0 ? v : undefined;
}

function parseField(v: unknown, path: string): FormField {
  if (!isStringRecord(v)) throw new FormDefinitionError(path, "expected object");
  const name = requireString(v, "name", path);
  if (!FIELD_NAME_RE.test(name)) {
    throw new FormDefinitionError(`${path}.name`, `must match /^[a-z][a-z0-9_]{0,62}$/`);
  }
  const type = requireString(v, "type", path);
  if (!VALID_FIELD_TYPES.has(type as FormFieldType)) {
    throw new FormDefinitionError(`${path}.type`, `unknown field type "${type}"`);
  }
  const field: FormField = {
    name,
    label: requireString(v, "label", path),
    type: type as FormFieldType,
    required: typeof v.required === "boolean" ? v.required : undefined,
    help: optionalString(v, "help"),
    placeholder: optionalString(v, "placeholder"),
    min: typeof v.min === "number" ? v.min : undefined,
    max: typeof v.max === "number" ? v.max : undefined,
    maxLength: typeof v.maxLength === "number" ? v.maxLength : undefined,
    value: optionalString(v, "value"),
  };
  if (Array.isArray(v.options)) {
    field.options = v.options.map((o, idx) => {
      if (!isStringRecord(o)) {
        throw new FormDefinitionError(`${path}.options[${idx}]`, "expected object");
      }
      return {
        value: requireString(o, "value", `${path}.options[${idx}]`),
        label: requireString(o, "label", `${path}.options[${idx}]`),
      };
    });
  }
  if (Array.isArray(v.accept)) {
    field.accept = v.accept.filter((m): m is string => typeof m === "string");
  }
  return field;
}

function parseStep(v: unknown, path: string): FormStep {
  if (!isStringRecord(v)) throw new FormDefinitionError(path, "expected object");
  const key = requireString(v, "key", path);
  if (!STEP_KEY_RE.test(key)) {
    throw new FormDefinitionError(`${path}.key`, `must match /^[a-z][a-z0-9_-]{0,62}$/`);
  }
  if (!Array.isArray(v.fields) || v.fields.length === 0) {
    throw new FormDefinitionError(`${path}.fields`, "expected non-empty array");
  }
  return {
    key,
    title: requireString(v, "title", path),
    description: optionalString(v, "description"),
    cta_label: optionalString(v, "cta_label"),
    fields: v.fields.map((f, idx) => parseField(f, `${path}.fields[${idx}]`)),
  };
}

/**
 * Validate a `forms.steps` jsonb value. Returns the typed array. Callers
 * that need the full FormDefinition (id, tenant_id, etc.) parse the row
 * + assemble themselves — this helper just covers the shape-volatile
 * jsonb columns.
 */
export function parseFormSteps(value: unknown): FormStep[] {
  if (!Array.isArray(value)) {
    throw new FormDefinitionError("$", "expected steps to be an array");
  }
  if (value.length === 0) {
    throw new FormDefinitionError("$", "form must have at least one step");
  }
  return value.map((s, idx) => parseStep(s, `$[${idx}]`));
}

export function parseFormBranding(value: unknown): FormBranding {
  if (value === null || value === undefined) return {};
  if (!isStringRecord(value)) {
    throw new FormDefinitionError("$.branding", "expected object");
  }
  return {
    primary_color: optionalString(value, "primary_color"),
    accent_color: optionalString(value, "accent_color"),
    logo_url: optionalString(value, "logo_url"),
    headline: optionalString(value, "headline"),
    subheadline: optionalString(value, "subheadline"),
    thanks_message: optionalString(value, "thanks_message"),
  };
}

/** Map of step index (stringified) → lead.stage target. */
export function parseStepOutcomes(value: unknown): Record<string, string> {
  if (value === null || value === undefined) return {};
  if (!isStringRecord(value)) {
    throw new FormDefinitionError("$.step_outcomes", "expected object");
  }
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(value)) {
    if (typeof v !== "string" || !v.trim()) {
      throw new FormDefinitionError(`$.step_outcomes.${k}`, "expected non-empty string");
    }
    out[k] = v;
  }
  return out;
}
