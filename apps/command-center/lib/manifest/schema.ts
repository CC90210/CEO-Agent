/**
 * Tenant Manifest — the single source of truth for one tenant's Command Center.
 *
 * A manifest describes everything that makes "OASIS for CC" visually and
 * behaviourally different from "Sun Biz Funding" or "PropFlow for a real estate
 * brokerage" — brand, sidebar nav, enabled agents, declarative page definitions,
 * the data model the AI editor is allowed to mutate, integration bindings, and
 * the prompts that populate the Reasoning tab.
 *
 * Phase 1 ships the schema + a manifest-driven shell. Phase 2 (AI chat editor)
 * uses this schema as the function-calling tool surface — every mutation runs
 * through `parseManifest` so a malformed AI tool call cannot corrupt the
 * persisted manifest.
 *
 * Storage: a `tenant_manifests` row holds the JSONB blob + version + audit ref.
 * Loading: see ./loader.ts — Supabase first, in-code seeds as fallback so the
 * shell renders even when the DB is unreachable / migration not yet applied.
 *
 * Versioning: bump `MANIFEST_SCHEMA_VERSION` whenever the schema changes in a
 * way that breaks older manifests, and add a migration in ./migrations/<n>.ts
 * that upgrades version N → N+1. `parseManifest` runs migrations transparently.
 */

export const MANIFEST_SCHEMA_VERSION = 1 as const;

// ---------------------------------------------------------------------------
// Primitive types
// ---------------------------------------------------------------------------

export type ManifestNavIconKey =
  | "LayoutDashboard"
  | "GitBranch"
  | "Brain"
  | "BookOpen"
  | "Bot"
  | "BarChart3"
  | "Plug"
  | "Settings"
  | "Activity"
  | "Inbox"
  | "History"
  | "ShieldCheck"
  | "ShieldAlert"
  | "Radio"
  | "Users"
  | "BookUser"
  | "FileText"
  | "Upload"
  | "HandCoins"
  | "BadgeDollarSign"
  | "RefreshCcw"
  | "DollarSign"
  | "MessageSquare"
  | "Mail"
  | "Landmark"
  | "FileCode2"
  | "UsersRound"
  | "Code2"
  | "Megaphone"
  | "ShoppingBag"
  | "Heart"
  | "Sparkles";

export type ManifestLogoKey = "oasis" | "sunbiz" | "suga" | "custom";

export type ManifestDataBackend = "supabase" | "turso";
export type ManifestDeploymentMode = "shared" | "dedicated";

// ---------------------------------------------------------------------------
// Brand + Nav
// ---------------------------------------------------------------------------

export type ManifestBrand = {
  /** Display name in the sidebar and page titles. */
  name: string;
  /** Built-in logo key, or "custom" if logo_url is set. */
  logo: ManifestLogoKey;
  /** Optional custom logo (used when logo === "custom"). */
  logo_url?: string;
  /** One-line subtitle shown below the brand name. */
  subtitle: string;
  /** Footer text rendered below the main content area. */
  footer_label: string;
  /** Pithy tagline shown opposite the footer label. */
  footer_tagline: string;
  /** Optional theme override — accent/primary CSS variable. */
  primary_color?: string;
};

export type ManifestNavItem = {
  href: string;
  label: string;
  icon: ManifestNavIconKey;
  group: string;
  badge_key?: string;
  expandable?: boolean;
};

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

export type ManifestAgentBinding = {
  /** Stable agent slug — "bravo", "atlas", "maven", "solara", or a custom slug. */
  slug: string;
  /** Display name in this tenant's UI (rename support without forking the agent). */
  display_name: string;
  /** Whether this agent currently shows in this tenant's shell. */
  enabled: boolean;
  /** Whether this agent is the tenant's "primary" — drives the sidebar live indicator. */
  primary?: boolean;
  /** Optional model override (e.g. force Opus for a premium tier). */
  model_override?: string;
  /** Optional prompt overlay appended to the agent's base prompt for this tenant. */
  prompt_overlay?: string;
};

// ---------------------------------------------------------------------------
// Pages & Data Model (Phase 2 renderer consumes these; Phase 1 keeps them
// optional and lets the existing route layer render until the catch-all
// renderer is ready)
// ---------------------------------------------------------------------------

export type ManifestPageKind = "dashboard" | "table" | "kanban" | "form" | "markdown";

export type ManifestPageDef = {
  path: string;           // relative path under /t/<slug>/ e.g. "leads"
  label: string;
  kind: ManifestPageKind;
  entity?: string;        // foreign key into data_model.entities[].name
  config?: Record<string, unknown>;
};

export type ManifestEntityField = {
  name: string;
  type: "string" | "number" | "boolean" | "date" | "datetime" | "enum" | "json";
  required?: boolean;
  enum_values?: string[];
  default?: unknown;
};

export type ManifestEntityDef = {
  name: string;
  label: string;
  fields: ManifestEntityField[];
};

// ---------------------------------------------------------------------------
// Integrations + Permissions + Prompts + Meta
// ---------------------------------------------------------------------------

export type ManifestIntegrationKind =
  | "twilio"
  | "jotform"
  | "stripe"
  | "google_workspace"
  | "supabase"
  | "turso"
  | "custom";

export type ManifestIntegration = {
  kind: ManifestIntegrationKind;
  enabled: boolean;
  /** Reference key into .env.agents OR Supabase vault — NEVER the raw secret. */
  credential_env_key?: string;
  config?: Record<string, unknown>;
};

export type ManifestPermissions = {
  local_files: boolean;
  computer_control: boolean;
  web_access: boolean;
};

export type ManifestPromptDef = {
  agent_slug: string;
  label: string;
  prompt: string;
};

export type ManifestOnboardingIndustry =
  | "real_estate"
  | "business_funding"
  | "ecommerce"
  | "agency"
  | "custom";

// ---------------------------------------------------------------------------
// Tier metadata — declarative pricing/setup signals surfaced in the wizard's
// industry-card grid, in marketplace, and (eventually) by the billing layer.
// Pure metadata, no enforcement; an "Enterprise" label here doesn't gate any
// feature — it just tells the wizard which copy + price hint to render.
// ---------------------------------------------------------------------------

export type ManifestTierLabel = "Free" | "Starter" | "Pro" | "Enterprise";
export type ManifestSetupComplexity = "Self-serve" | "Guided" | "Done-for-you";

export type ManifestTier = {
  label: ManifestTierLabel;
  setup_complexity: ManifestSetupComplexity;
  /** Free-text price hint, e.g. "$49/mo" or "Custom". Not parsed; rendered as-is. */
  monthly_price_hint?: string;
  /** One-line summary for the wizard card. Keep it 8 words or fewer. */
  summary?: string;
};

export type ManifestMeta = {
  created_at?: string;
  updated_at?: string;
  schema_version: number;
  audit_history_ref?: string;
};

// ---------------------------------------------------------------------------
// Top-level TenantManifest
// ---------------------------------------------------------------------------

export type TenantManifest = {
  version: number;
  tenant_slug: string;
  brand: ManifestBrand;
  agents: ManifestAgentBinding[];
  nav: ManifestNavItem[];
  pages?: ManifestPageDef[];
  data_model?: ManifestEntityDef[];
  integrations?: ManifestIntegration[];
  permissions?: ManifestPermissions;
  default_prompts?: ManifestPromptDef[];
  onboarding_industry?: ManifestOnboardingIndustry;
  data_backend?: ManifestDataBackend;
  deployment_mode?: ManifestDeploymentMode;
  tier?: ManifestTier;
  meta: ManifestMeta;
};

// ---------------------------------------------------------------------------
// Runtime validation
//
// Zero-dependency, hand-written parser. Throws ManifestParseError on invalid
// input. Returns the (possibly migrated) manifest on success. Callers that
// can tolerate a fallback should use safeParseManifest instead.
// ---------------------------------------------------------------------------

export class ManifestParseError extends Error {
  constructor(public path: string, public reason: string) {
    super(`manifest invalid at ${path}: ${reason}`);
    this.name = "ManifestParseError";
  }
}

type Json = unknown;
function isObject(v: Json): v is Record<string, Json> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}
function isString(v: Json): v is string {
  return typeof v === "string";
}
function isBoolean(v: Json): v is boolean {
  return typeof v === "boolean";
}
function isArray(v: Json): v is Json[] {
  return Array.isArray(v);
}

function requireString(obj: Record<string, Json>, key: string, path: string): string {
  const v = obj[key];
  if (!isString(v) || !v.trim()) throw new ManifestParseError(`${path}.${key}`, "expected non-empty string");
  return v;
}
function optionalString(obj: Record<string, Json>, key: string): string | undefined {
  const v = obj[key];
  return isString(v) && v.trim() ? v : undefined;
}
function requireBoolean(obj: Record<string, Json>, key: string, path: string): boolean {
  const v = obj[key];
  if (!isBoolean(v)) throw new ManifestParseError(`${path}.${key}`, "expected boolean");
  return v;
}
function optionalBoolean(obj: Record<string, Json>, key: string): boolean | undefined {
  const v = obj[key];
  return isBoolean(v) ? v : undefined;
}
function requireArray<T>(
  obj: Record<string, Json>,
  key: string,
  path: string,
  itemFn: (item: Json, idx: number) => T
): T[] {
  const v = obj[key];
  if (!isArray(v)) throw new ManifestParseError(`${path}.${key}`, "expected array");
  return v.map((item, idx) => itemFn(item, idx));
}
function optionalArray<T>(
  obj: Record<string, Json>,
  key: string,
  path: string,
  itemFn: (item: Json, idx: number) => T
): T[] | undefined {
  const v = obj[key];
  if (v === undefined) return undefined;
  if (!isArray(v)) throw new ManifestParseError(`${path}.${key}`, "expected array");
  return v.map((item, idx) => itemFn(item, idx));
}

const NAV_ICON_KEYS = new Set<ManifestNavIconKey>([
  "LayoutDashboard", "GitBranch", "Brain", "BookOpen", "Bot", "BarChart3",
  "Plug", "Settings", "Activity", "Inbox", "History", "ShieldCheck",
  "ShieldAlert", "Radio", "Users", "BookUser", "FileText", "Upload",
  "HandCoins", "BadgeDollarSign", "RefreshCcw", "DollarSign", "MessageSquare",
  "Mail", "Landmark", "FileCode2", "UsersRound", "Code2", "Megaphone",
  "ShoppingBag", "Heart", "Sparkles",
]);

const LOGO_KEYS = new Set<ManifestLogoKey>(["oasis", "sunbiz", "suga", "custom"]);
const PAGE_KINDS = new Set<ManifestPageKind>(["dashboard", "table", "kanban", "form", "markdown"]);
const ENTITY_FIELD_TYPES = new Set(["string", "number", "boolean", "date", "datetime", "enum", "json"]);
const INTEGRATION_KINDS = new Set<ManifestIntegrationKind>([
  "twilio", "jotform", "stripe", "google_workspace", "supabase", "turso", "custom",
]);
const ONBOARDING_INDUSTRIES = new Set<ManifestOnboardingIndustry>([
  "real_estate", "business_funding", "ecommerce", "agency", "custom",
]);
const TIER_LABELS = new Set<ManifestTierLabel>(["Free", "Starter", "Pro", "Enterprise"]);
const SETUP_COMPLEXITIES = new Set<ManifestSetupComplexity>(["Self-serve", "Guided", "Done-for-you"]);

function parseBrand(v: Json, path: string): ManifestBrand {
  if (!isObject(v)) throw new ManifestParseError(path, "expected object");
  const logo = requireString(v, "logo", path);
  if (!LOGO_KEYS.has(logo as ManifestLogoKey)) {
    throw new ManifestParseError(`${path}.logo`, `unknown logo key "${logo}"`);
  }
  return {
    name: requireString(v, "name", path),
    logo: logo as ManifestLogoKey,
    logo_url: optionalString(v, "logo_url"),
    subtitle: requireString(v, "subtitle", path),
    footer_label: requireString(v, "footer_label", path),
    footer_tagline: requireString(v, "footer_tagline", path),
    primary_color: optionalString(v, "primary_color"),
  };
}

function parseNavItem(v: Json, path: string): ManifestNavItem {
  if (!isObject(v)) throw new ManifestParseError(path, "expected object");
  const icon = requireString(v, "icon", path);
  if (!NAV_ICON_KEYS.has(icon as ManifestNavIconKey)) {
    throw new ManifestParseError(`${path}.icon`, `unknown icon "${icon}"`);
  }
  return {
    href: requireString(v, "href", path),
    label: requireString(v, "label", path),
    icon: icon as ManifestNavIconKey,
    group: requireString(v, "group", path),
    badge_key: optionalString(v, "badge_key"),
    expandable: optionalBoolean(v, "expandable"),
  };
}

function parseAgent(v: Json, path: string): ManifestAgentBinding {
  if (!isObject(v)) throw new ManifestParseError(path, "expected object");
  return {
    slug: requireString(v, "slug", path),
    display_name: requireString(v, "display_name", path),
    enabled: requireBoolean(v, "enabled", path),
    primary: optionalBoolean(v, "primary"),
    model_override: optionalString(v, "model_override"),
    prompt_overlay: optionalString(v, "prompt_overlay"),
  };
}

function parsePage(v: Json, path: string): ManifestPageDef {
  if (!isObject(v)) throw new ManifestParseError(path, "expected object");
  const kind = requireString(v, "kind", path);
  if (!PAGE_KINDS.has(kind as ManifestPageKind)) {
    throw new ManifestParseError(`${path}.kind`, `unknown page kind "${kind}"`);
  }
  return {
    path: requireString(v, "path", path),
    label: requireString(v, "label", path),
    kind: kind as ManifestPageKind,
    entity: optionalString(v, "entity"),
    config: isObject(v.config) ? (v.config as Record<string, unknown>) : undefined,
  };
}

function parseEntityField(v: Json, path: string): ManifestEntityField {
  if (!isObject(v)) throw new ManifestParseError(path, "expected object");
  const type = requireString(v, "type", path);
  if (!ENTITY_FIELD_TYPES.has(type)) {
    throw new ManifestParseError(`${path}.type`, `unknown field type "${type}"`);
  }
  return {
    name: requireString(v, "name", path),
    type: type as ManifestEntityField["type"],
    required: optionalBoolean(v, "required"),
    enum_values: optionalArray(v, "enum_values", `${path}.enum_values`, (e, idx) => {
      if (!isString(e)) throw new ManifestParseError(`${path}.enum_values[${idx}]`, "expected string");
      return e;
    }),
    default: v.default,
  };
}

function parseEntity(v: Json, path: string): ManifestEntityDef {
  if (!isObject(v)) throw new ManifestParseError(path, "expected object");
  return {
    name: requireString(v, "name", path),
    label: requireString(v, "label", path),
    fields: requireArray(v, "fields", path, (f, idx) => parseEntityField(f, `${path}.fields[${idx}]`)),
  };
}

function parseIntegration(v: Json, path: string): ManifestIntegration {
  if (!isObject(v)) throw new ManifestParseError(path, "expected object");
  const kind = requireString(v, "kind", path);
  if (!INTEGRATION_KINDS.has(kind as ManifestIntegrationKind)) {
    throw new ManifestParseError(`${path}.kind`, `unknown integration kind "${kind}"`);
  }
  return {
    kind: kind as ManifestIntegrationKind,
    enabled: requireBoolean(v, "enabled", path),
    credential_env_key: optionalString(v, "credential_env_key"),
    config: isObject(v.config) ? (v.config as Record<string, unknown>) : undefined,
  };
}

function parsePermissions(v: Json, path: string): ManifestPermissions {
  if (!isObject(v)) throw new ManifestParseError(path, "expected object");
  return {
    local_files: requireBoolean(v, "local_files", path),
    computer_control: requireBoolean(v, "computer_control", path),
    web_access: requireBoolean(v, "web_access", path),
  };
}

function parsePrompt(v: Json, path: string): ManifestPromptDef {
  if (!isObject(v)) throw new ManifestParseError(path, "expected object");
  return {
    agent_slug: requireString(v, "agent_slug", path),
    label: requireString(v, "label", path),
    prompt: requireString(v, "prompt", path),
  };
}

function parseTier(v: Json, path: string): ManifestTier {
  if (!isObject(v)) throw new ManifestParseError(path, "expected object");
  const label = requireString(v, "label", path);
  if (!TIER_LABELS.has(label as ManifestTierLabel)) {
    throw new ManifestParseError(`${path}.label`, `unknown tier label "${label}"`);
  }
  const setup = requireString(v, "setup_complexity", path);
  if (!SETUP_COMPLEXITIES.has(setup as ManifestSetupComplexity)) {
    throw new ManifestParseError(`${path}.setup_complexity`, `unknown setup_complexity "${setup}"`);
  }
  return {
    label: label as ManifestTierLabel,
    setup_complexity: setup as ManifestSetupComplexity,
    monthly_price_hint: optionalString(v, "monthly_price_hint"),
    summary: optionalString(v, "summary"),
  };
}

function parseMeta(v: Json, path: string): ManifestMeta {
  if (!isObject(v)) throw new ManifestParseError(path, "expected object");
  const schemaVersionRaw = v.schema_version;
  const schema_version = typeof schemaVersionRaw === "number" && Number.isFinite(schemaVersionRaw)
    ? schemaVersionRaw
    : MANIFEST_SCHEMA_VERSION;
  return {
    created_at: optionalString(v, "created_at"),
    updated_at: optionalString(v, "updated_at"),
    schema_version,
    audit_history_ref: optionalString(v, "audit_history_ref"),
  };
}

export function parseManifest(input: Json): TenantManifest {
  if (!isObject(input)) throw new ManifestParseError("$", "expected object");

  const versionRaw = input.version;
  const version = typeof versionRaw === "number" && Number.isFinite(versionRaw)
    ? versionRaw
    : MANIFEST_SCHEMA_VERSION;

  const slug = requireString(input, "tenant_slug", "$");
  if (!/^[a-z0-9][a-z0-9_-]{1,62}$/.test(slug)) {
    throw new ManifestParseError("$.tenant_slug", "must match /^[a-z0-9][a-z0-9_-]{1,62}$/");
  }

  const dataBackend = optionalString(input, "data_backend");
  if (dataBackend && dataBackend !== "supabase" && dataBackend !== "turso") {
    throw new ManifestParseError("$.data_backend", `unknown backend "${dataBackend}"`);
  }
  const deploymentMode = optionalString(input, "deployment_mode");
  if (deploymentMode && deploymentMode !== "shared" && deploymentMode !== "dedicated") {
    throw new ManifestParseError("$.deployment_mode", `unknown mode "${deploymentMode}"`);
  }

  const industry = optionalString(input, "onboarding_industry");
  if (industry && !ONBOARDING_INDUSTRIES.has(industry as ManifestOnboardingIndustry)) {
    throw new ManifestParseError("$.onboarding_industry", `unknown industry "${industry}"`);
  }

  return {
    version,
    tenant_slug: slug,
    brand: parseBrand(input.brand, "$.brand"),
    agents: requireArray(input, "agents", "$", (a, idx) => parseAgent(a, `$.agents[${idx}]`)),
    nav: requireArray(input, "nav", "$", (n, idx) => parseNavItem(n, `$.nav[${idx}]`)),
    pages: optionalArray(input, "pages", "$.pages", (p, idx) => parsePage(p, `$.pages[${idx}]`)),
    data_model: optionalArray(input, "data_model", "$.data_model", (e, idx) => parseEntity(e, `$.data_model[${idx}]`)),
    integrations: optionalArray(input, "integrations", "$.integrations", (i, idx) =>
      parseIntegration(i, `$.integrations[${idx}]`)
    ),
    permissions: input.permissions !== undefined ? parsePermissions(input.permissions, "$.permissions") : undefined,
    default_prompts: optionalArray(input, "default_prompts", "$.default_prompts", (p, idx) =>
      parsePrompt(p, `$.default_prompts[${idx}]`)
    ),
    onboarding_industry: industry as ManifestOnboardingIndustry | undefined,
    data_backend: dataBackend as ManifestDataBackend | undefined,
    deployment_mode: deploymentMode as ManifestDeploymentMode | undefined,
    tier: input.tier !== undefined ? parseTier(input.tier, "$.tier") : undefined,
    meta: parseMeta(input.meta ?? {}, "$.meta"),
  };
}

export function safeParseManifest(input: Json): { ok: true; manifest: TenantManifest } | { ok: false; error: ManifestParseError } {
  try {
    return { ok: true, manifest: parseManifest(input) };
  } catch (err) {
    if (err instanceof ManifestParseError) return { ok: false, error: err };
    throw err;
  }
}

/** Find the primary agent binding, or fall back to the first enabled agent. */
export function primaryAgent(m: TenantManifest): ManifestAgentBinding | null {
  return (
    m.agents.find((a) => a.primary && a.enabled) ||
    m.agents.find((a) => a.enabled) ||
    null
  );
}
