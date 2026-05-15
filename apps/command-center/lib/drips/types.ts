/**
 * drips/types.ts — shared shape for drip sequences.
 *
 * Phase 4 of the SunBiz CRM build (2026-05-15). The dashboard's
 * sequence builder (/sequences/[id]/edit) writes these shapes into
 * drip_sequences.steps + drip_sequences.trigger_filter; the Python
 * runner (bravo_cli/sequence_runner.py) reads them back to fire sends.
 *
 * Two languages, one schema — keep this file's shape in lockstep with
 * the runner's expectations. The runner does shape validation at load
 * time; mismatches surface in the daemon log.
 */

// ---------------------------------------------------------------------------
// Channel + step types
// ---------------------------------------------------------------------------

export type DripChannel = "sms" | "email";

export type DripStep = {
  channel: DripChannel;
  /**
   * Wait this long after the previous step (or after enrollment for
   * step 0) before firing. 0 = fire immediately. The daemon clamps
   * negative or non-finite values to 0 defensively.
   */
  delay_minutes: number;
  /** Email subject — required when channel === "email". */
  subject?: string;
  /**
   * Message body. Mustache-style substitution via lib/drips/templates.ts:
   *   {{lead.first_name}} {{lead.business_name}} {{lender.name}}
   * Missing values render as empty string (operator-friendly default
   * vs throwing on the send path).
   */
  body: string;
  /** Optional sender label — agent name, e.g. "Solara" or "Helios". */
  from_label?: string;
};

export type DripTriggerFilter = {
  /** Entity type — e.g. "lead", "offer". */
  entity?: string;
  /** Field name that changed — e.g. "stage", "status". */
  field?: string;
  /** Target stage / status the change landed on. */
  to?: string;
  /** Source stage / status the change came from (rarely useful — exposed
   *  for completeness so an operator can express
   *  "only when going from sent_application directly to declined"). */
  from?: string;
};

export type DripSequence = {
  id: string;
  tenant_id: string;
  name: string;
  description: string | null;
  trigger_event: string;
  trigger_filter: DripTriggerFilter;
  steps: DripStep[];
  enabled: boolean;
  one_per_lead: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

// ---------------------------------------------------------------------------
// Runtime validation
// ---------------------------------------------------------------------------

export class DripDefinitionError extends Error {
  constructor(public path: string, public reason: string) {
    super(`drip definition invalid at ${path}: ${reason}`);
    this.name = "DripDefinitionError";
  }
}

const VALID_CHANNELS: ReadonlySet<DripChannel> = new Set(["sms", "email"]);

function isStringRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function requireString(obj: Record<string, unknown>, key: string, path: string): string {
  const v = obj[key];
  if (typeof v !== "string" || !v.trim()) {
    throw new DripDefinitionError(`${path}.${key}`, "expected non-empty string");
  }
  return v;
}

function optionalString(obj: Record<string, unknown>, key: string): string | undefined {
  const v = obj[key];
  return typeof v === "string" && v.length > 0 ? v : undefined;
}

function parseStep(v: unknown, path: string): DripStep {
  if (!isStringRecord(v)) throw new DripDefinitionError(path, "expected object");
  const channel = requireString(v, "channel", path);
  if (!VALID_CHANNELS.has(channel as DripChannel)) {
    throw new DripDefinitionError(`${path}.channel`, `unknown channel "${channel}"`);
  }
  const delayRaw = v.delay_minutes;
  if (typeof delayRaw !== "number" || !Number.isFinite(delayRaw)) {
    throw new DripDefinitionError(`${path}.delay_minutes`, "expected finite number");
  }
  const body = requireString(v, "body", path);
  const step: DripStep = {
    channel: channel as DripChannel,
    delay_minutes: Math.max(0, Math.floor(delayRaw)),
    body,
  };
  if (channel === "email") {
    step.subject = requireString(v, "subject", path);
  } else if (typeof v.subject === "string" && v.subject.length > 0) {
    // SMS doesn't use subject but accept it without error so operators
    // can switch a step from email -> sms without re-typing.
    step.subject = v.subject;
  }
  const fromLabel = optionalString(v, "from_label");
  if (fromLabel) step.from_label = fromLabel;
  return step;
}

/**
 * Validate a `drip_sequences.steps` jsonb value. Returns the typed
 * array. Throws DripDefinitionError on shape violations so callers
 * can surface a 400 with the offending path.
 */
export function parseDripSteps(value: unknown): DripStep[] {
  if (!Array.isArray(value)) {
    throw new DripDefinitionError("$", "expected steps to be an array");
  }
  if (value.length === 0) {
    throw new DripDefinitionError("$", "drip must have at least one step");
  }
  return value.map((s, idx) => parseStep(s, `$[${idx}]`));
}

export function parseDripTriggerFilter(value: unknown): DripTriggerFilter {
  if (value === null || value === undefined) return {};
  if (!isStringRecord(value)) {
    throw new DripDefinitionError("$.trigger_filter", "expected object");
  }
  const out: DripTriggerFilter = {};
  if (typeof value.entity === "string") out.entity = value.entity;
  if (typeof value.field === "string") out.field = value.field;
  if (typeof value.to === "string") out.to = value.to;
  if (typeof value.from === "string") out.from = value.from;
  return out;
}
