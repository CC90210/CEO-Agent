/**
 * Manifest mutators — pure functions that take a manifest plus a typed
 * mutation arg and return a new manifest.
 *
 * Properties this layer guarantees:
 *   - PURE: zero I/O, zero side effects, deterministic. Same input → same output.
 *   - SAFE: every mutator validates its args and throws ManifestMutationError
 *     with the offending field path. A failed mutation never half-applies.
 *   - SHALLOW-IMMUTABLE: returns a NEW manifest object; the input is never
 *     mutated. Callers can keep prior versions for diff / rollback.
 *
 * Things this layer EXPLICITLY does not allow:
 *   - changing `permissions` (local_files / computer_control / web_access).
 *     A future capability change is a human decision, not an AI tool call.
 *   - rewriting `integrations[].credential_env_key`. The AI must never
 *     redirect a credential reference because doing so silently rebinds
 *     secret material at runtime.
 *   - clearing `audit_history_ref` or rewriting `meta.created_at`. Audit is
 *     append-only at this layer; persistence handles the log.
 *
 * The chat endpoint (lib/manifest/chat-tools.ts in 2c) wraps these so the
 * AI's function-calling surface is exactly this set, no more, no less.
 */

import type {
  ManifestAgentBinding,
  ManifestBrand,
  ManifestEntityDef,
  ManifestEntityField,
  ManifestNavItem,
  ManifestOnboardingIndustry,
  ManifestPageDef,
  ManifestPromptDef,
  TenantManifest,
} from "./schema";

export class ManifestMutationError extends Error {
  constructor(public field: string, public reason: string) {
    super(`mutation rejected at ${field}: ${reason}`);
    this.name = "ManifestMutationError";
  }
}

function deepCloneManifest(m: TenantManifest): TenantManifest {
  // Structural clone via JSON. Manifests are pure data — no Dates, no Maps,
  // no functions — so this is safe and fast enough at our manifest sizes.
  return JSON.parse(JSON.stringify(m)) as TenantManifest;
}

function bumpMeta(m: TenantManifest): TenantManifest {
  return {
    ...m,
    meta: {
      ...m.meta,
      updated_at: new Date().toISOString(),
    },
  };
}

function nonEmptyString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new ManifestMutationError(field, "expected non-empty string");
  }
  return value;
}

// ===========================================================================
// Brand
// ===========================================================================

export type UpdateBrandArgs = Partial<Pick<
  ManifestBrand,
  "name" | "logo" | "logo_url" | "subtitle" | "footer_label" | "footer_tagline" | "primary_color"
>>;

const LOGO_VALUES = new Set<ManifestBrand["logo"]>(["oasis", "sunbiz", "suga", "custom"]);

export function updateBrand(m: TenantManifest, args: UpdateBrandArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const brand = next.brand;
  if (args.name !== undefined) brand.name = nonEmptyString(args.name, "brand.name");
  if (args.subtitle !== undefined) brand.subtitle = nonEmptyString(args.subtitle, "brand.subtitle");
  if (args.footer_label !== undefined) brand.footer_label = nonEmptyString(args.footer_label, "brand.footer_label");
  if (args.footer_tagline !== undefined) brand.footer_tagline = nonEmptyString(args.footer_tagline, "brand.footer_tagline");
  if (args.primary_color !== undefined) {
    if (args.primary_color === null) {
      brand.primary_color = undefined;
    } else {
      const c = nonEmptyString(args.primary_color, "brand.primary_color");
      if (!/^#[0-9a-fA-F]{3,8}$/.test(c)) {
        throw new ManifestMutationError("brand.primary_color", "expected hex colour like #1b1f23");
      }
      brand.primary_color = c;
    }
  }
  if (args.logo !== undefined) {
    if (!LOGO_VALUES.has(args.logo)) {
      throw new ManifestMutationError("brand.logo", `unknown logo "${args.logo}"`);
    }
    brand.logo = args.logo;
  }
  if (args.logo_url !== undefined) {
    brand.logo_url = args.logo_url === null ? undefined : nonEmptyString(args.logo_url, "brand.logo_url");
  }
  return bumpMeta(next);
}

// ===========================================================================
// Nav
// ===========================================================================

export type AddNavItemArgs = {
  href: string;
  label: string;
  icon: ManifestNavItem["icon"];
  group: string;
  badge_key?: string;
  expandable?: boolean;
  /** Insert position (0-based). Defaults to end of array. */
  position?: number;
};

export function addNavItem(m: TenantManifest, args: AddNavItemArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const href = nonEmptyString(args.href, "nav.href");
  if (next.nav.some((n) => n.href === href)) {
    throw new ManifestMutationError("nav.href", `duplicate href "${href}"`);
  }
  const item: ManifestNavItem = {
    href,
    label: nonEmptyString(args.label, "nav.label"),
    icon: args.icon,
    group: nonEmptyString(args.group, "nav.group"),
    badge_key: args.badge_key,
    expandable: args.expandable,
  };
  if (args.position === undefined) {
    next.nav.push(item);
  } else {
    const pos = Math.max(0, Math.min(args.position, next.nav.length));
    next.nav.splice(pos, 0, item);
  }
  return bumpMeta(next);
}

export type RemoveNavItemArgs = { href: string };

export function removeNavItem(m: TenantManifest, args: RemoveNavItemArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const idx = next.nav.findIndex((n) => n.href === args.href);
  if (idx < 0) throw new ManifestMutationError("nav.href", `no nav item with href "${args.href}"`);
  next.nav.splice(idx, 1);
  return bumpMeta(next);
}

export type UpdateNavItemArgs = {
  href: string;
  changes: Partial<Omit<ManifestNavItem, "href">>;
};

export function updateNavItem(m: TenantManifest, args: UpdateNavItemArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const item = next.nav.find((n) => n.href === args.href);
  if (!item) throw new ManifestMutationError("nav.href", `no nav item with href "${args.href}"`);
  const c = args.changes;
  if (c.label !== undefined) item.label = nonEmptyString(c.label, "nav.label");
  if (c.icon !== undefined) item.icon = c.icon;
  if (c.group !== undefined) item.group = nonEmptyString(c.group, "nav.group");
  if (c.badge_key !== undefined) item.badge_key = c.badge_key || undefined;
  if (c.expandable !== undefined) item.expandable = c.expandable;
  return bumpMeta(next);
}

export type ReorderNavArgs = { order: string[] };

export function reorderNav(m: TenantManifest, args: ReorderNavArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const want = args.order;
  if (want.length !== next.nav.length) {
    throw new ManifestMutationError(
      "nav.order",
      `length mismatch — manifest has ${next.nav.length} items, order has ${want.length}`
    );
  }
  const byHref = new Map(next.nav.map((n) => [n.href, n] as const));
  const reordered: ManifestNavItem[] = [];
  for (const href of want) {
    const item = byHref.get(href);
    if (!item) throw new ManifestMutationError("nav.order", `unknown href "${href}"`);
    if (reordered.includes(item)) {
      throw new ManifestMutationError("nav.order", `duplicate href "${href}"`);
    }
    reordered.push(item);
  }
  next.nav = reordered;
  return bumpMeta(next);
}

// ===========================================================================
// Agents
// ===========================================================================

export type EnableAgentArgs = {
  slug: string;
  display_name?: string;
  primary?: boolean;
};

export function enableAgent(m: TenantManifest, args: EnableAgentArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const slug = nonEmptyString(args.slug, "agent.slug");
  let agent = next.agents.find((a) => a.slug === slug);
  if (agent) {
    agent.enabled = true;
    if (args.display_name) agent.display_name = nonEmptyString(args.display_name, "agent.display_name");
    if (args.primary !== undefined) {
      if (args.primary) {
        for (const a of next.agents) a.primary = a.slug === slug;
      } else {
        agent.primary = false;
      }
    }
  } else {
    agent = {
      slug,
      display_name: nonEmptyString(args.display_name || slug, "agent.display_name"),
      enabled: true,
      primary: args.primary === true,
    };
    if (agent.primary) {
      for (const a of next.agents) a.primary = false;
    }
    next.agents.push(agent);
  }
  return bumpMeta(next);
}

export type DisableAgentArgs = { slug: string };

export function disableAgent(m: TenantManifest, args: DisableAgentArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const agent = next.agents.find((a) => a.slug === args.slug);
  if (!agent) throw new ManifestMutationError("agent.slug", `unknown agent "${args.slug}"`);
  agent.enabled = false;
  if (agent.primary) {
    agent.primary = false;
    const fallback = next.agents.find((a) => a.enabled);
    if (fallback) fallback.primary = true;
  }
  return bumpMeta(next);
}

/**
 * `model_override` is intentionally excluded from the changes surface.
 * Switching the model an agent runs on is a billing-affecting decision
 * that must be made explicitly in the AgentConfigEditor UI, never via the
 * AI editor. Keeping it out of the TYPE prevents the AI from being told it
 * can set the field and ensures parser layers reject envelopes that include
 * it (rather than the mutator silently no-op'ing — which it also still
 * does at line 268 as a defense-in-depth fallback).
 */
export type UpdateAgentArgs = {
  slug: string;
  changes: Partial<Omit<ManifestAgentBinding, "slug" | "model_override">>;
};

export function updateAgent(m: TenantManifest, args: UpdateAgentArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const agent = next.agents.find((a) => a.slug === args.slug);
  if (!agent) throw new ManifestMutationError("agent.slug", `unknown agent "${args.slug}"`);
  const c = args.changes;
  if (c.display_name !== undefined) agent.display_name = nonEmptyString(c.display_name, "agent.display_name");
  if (c.enabled !== undefined) agent.enabled = c.enabled;
  if (c.prompt_overlay !== undefined) {
    agent.prompt_overlay = c.prompt_overlay === null || c.prompt_overlay === "" ? undefined : c.prompt_overlay;
  }
  // model_override is intentionally NOT touched here. Switching the model an
  // agent runs on is a billing-affecting decision; it requires explicit human
  // action in the AgentConfigEditor UI, not an AI tool call.
  if (c.primary === true) {
    for (const a of next.agents) a.primary = a.slug === args.slug;
  } else if (c.primary === false && agent.primary) {
    agent.primary = false;
  }
  return bumpMeta(next);
}

// ===========================================================================
// Data model (entities + fields)
// ===========================================================================

const ENTITY_NAME_RE = /^[a-z][a-z0-9_]{0,62}$/;
const FIELD_NAME_RE = /^[a-z][a-z0-9_]{0,62}$/;

export type AddDataEntityArgs = {
  name: string;
  label: string;
  fields?: ManifestEntityField[];
};

export function addDataEntity(m: TenantManifest, args: AddDataEntityArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const name = nonEmptyString(args.name, "entity.name").toLowerCase();
  if (!ENTITY_NAME_RE.test(name)) {
    throw new ManifestMutationError("entity.name", "must match /^[a-z][a-z0-9_]{0,62}$/");
  }
  const model = next.data_model || [];
  if (model.some((e) => e.name === name)) {
    throw new ManifestMutationError("entity.name", `duplicate entity "${name}"`);
  }
  const entity: ManifestEntityDef = {
    name,
    label: nonEmptyString(args.label, "entity.label"),
    fields: args.fields ? args.fields.map((f, i) => validateField(f, `entity.fields[${i}]`)) : [],
  };
  next.data_model = [...model, entity];
  return bumpMeta(next);
}

export type RemoveDataEntityArgs = { name: string };

export function removeDataEntity(m: TenantManifest, args: RemoveDataEntityArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const model = next.data_model || [];
  const idx = model.findIndex((e) => e.name === args.name);
  if (idx < 0) throw new ManifestMutationError("entity.name", `unknown entity "${args.name}"`);
  next.data_model = [...model.slice(0, idx), ...model.slice(idx + 1)];
  // Cascade: any page referencing this entity becomes orphaned. Drop those
  // pages so the renderer can't crash on a missing reference.
  if (next.pages) {
    next.pages = next.pages.filter((p) => p.entity !== args.name);
  }
  return bumpMeta(next);
}

function validateField(f: ManifestEntityField, path: string): ManifestEntityField {
  const name = nonEmptyString(f.name, `${path}.name`).toLowerCase();
  if (!FIELD_NAME_RE.test(name)) {
    throw new ManifestMutationError(`${path}.name`, "must match /^[a-z][a-z0-9_]{0,62}$/");
  }
  const type = f.type;
  if (!["string", "number", "boolean", "date", "datetime", "enum", "json"].includes(type)) {
    throw new ManifestMutationError(`${path}.type`, `unknown field type "${type}"`);
  }
  if (type === "enum" && (!f.enum_values || f.enum_values.length === 0)) {
    throw new ManifestMutationError(`${path}.enum_values`, "enum field requires non-empty enum_values");
  }
  return { ...f, name };
}

export type AddFieldToEntityArgs = {
  entity: string;
  field: ManifestEntityField;
};

export function addFieldToEntity(m: TenantManifest, args: AddFieldToEntityArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const entity = (next.data_model || []).find((e) => e.name === args.entity);
  if (!entity) throw new ManifestMutationError("entity", `unknown entity "${args.entity}"`);
  const field = validateField(args.field, `field`);
  if (entity.fields.some((f) => f.name === field.name)) {
    throw new ManifestMutationError("field.name", `duplicate field "${field.name}" on entity "${args.entity}"`);
  }
  entity.fields.push(field);
  return bumpMeta(next);
}

export type RemoveFieldFromEntityArgs = {
  entity: string;
  field_name: string;
};

export function removeFieldFromEntity(m: TenantManifest, args: RemoveFieldFromEntityArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const entity = (next.data_model || []).find((e) => e.name === args.entity);
  if (!entity) throw new ManifestMutationError("entity", `unknown entity "${args.entity}"`);
  const idx = entity.fields.findIndex((f) => f.name === args.field_name);
  if (idx < 0) throw new ManifestMutationError("field.name", `unknown field "${args.field_name}"`);
  entity.fields.splice(idx, 1);
  return bumpMeta(next);
}

// ===========================================================================
// Pages
// ===========================================================================

export type AddPageArgs = {
  path: string;
  label: string;
  kind: ManifestPageDef["kind"];
  entity?: string;
  config?: Record<string, unknown>;
};

export function addPage(m: TenantManifest, args: AddPageArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const path = nonEmptyString(args.path, "page.path");
  const pages = next.pages || [];
  if (pages.some((p) => p.path === path)) {
    throw new ManifestMutationError("page.path", `duplicate path "${path}"`);
  }
  if (args.entity) {
    const model = next.data_model || [];
    if (!model.some((e) => e.name === args.entity)) {
      throw new ManifestMutationError("page.entity", `unknown entity "${args.entity}"`);
    }
  }
  next.pages = [
    ...pages,
    {
      path,
      label: nonEmptyString(args.label, "page.label"),
      kind: args.kind,
      entity: args.entity,
      config: args.config,
    },
  ];
  return bumpMeta(next);
}

export type RemovePageArgs = { path: string };

export function removePage(m: TenantManifest, args: RemovePageArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const pages = next.pages || [];
  const idx = pages.findIndex((p) => p.path === args.path);
  if (idx < 0) throw new ManifestMutationError("page.path", `no page "${args.path}"`);
  next.pages = [...pages.slice(0, idx), ...pages.slice(idx + 1)];
  return bumpMeta(next);
}

// ===========================================================================
// Default prompts (Reasoning tab quick-actions)
// ===========================================================================

export type UpsertPromptArgs = ManifestPromptDef;

export function upsertPrompt(m: TenantManifest, args: UpsertPromptArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const prompts = next.default_prompts || [];
  nonEmptyString(args.agent_slug, "prompt.agent_slug");
  nonEmptyString(args.label, "prompt.label");
  nonEmptyString(args.prompt, "prompt.prompt");
  const existing = prompts.findIndex((p) => p.agent_slug === args.agent_slug && p.label === args.label);
  if (existing >= 0) {
    prompts[existing] = { ...args };
  } else {
    prompts.push({ ...args });
  }
  next.default_prompts = prompts;
  return bumpMeta(next);
}

export type RemovePromptArgs = { agent_slug: string; label: string };

export function removePrompt(m: TenantManifest, args: RemovePromptArgs): TenantManifest {
  const next = deepCloneManifest(m);
  const prompts = next.default_prompts || [];
  const idx = prompts.findIndex((p) => p.agent_slug === args.agent_slug && p.label === args.label);
  if (idx < 0) throw new ManifestMutationError("prompt", `no prompt "${args.label}" for agent "${args.agent_slug}"`);
  next.default_prompts = [...prompts.slice(0, idx), ...prompts.slice(idx + 1)];
  return bumpMeta(next);
}

// ===========================================================================
// Industry
// ===========================================================================

const INDUSTRIES = new Set<ManifestOnboardingIndustry>([
  "real_estate", "business_funding", "ecommerce", "agency", "custom",
]);

export type UpdateIndustryArgs = { industry: ManifestOnboardingIndustry };

export function updateIndustry(m: TenantManifest, args: UpdateIndustryArgs): TenantManifest {
  if (!INDUSTRIES.has(args.industry)) {
    throw new ManifestMutationError("onboarding_industry", `unknown industry "${args.industry}"`);
  }
  const next = deepCloneManifest(m);
  next.onboarding_industry = args.industry;
  return bumpMeta(next);
}

// ===========================================================================
// Mutation dispatch — the chat endpoint resolves a tool name to a mutator
// through this table. Adding a mutator REQUIRES adding the dispatch entry,
// the tool declaration, AND the mutator export above; tsc enforces the link.
// ===========================================================================

export type MutationName =
  | "update_brand"
  | "add_nav_item"
  | "remove_nav_item"
  | "update_nav_item"
  | "reorder_nav"
  | "enable_agent"
  | "disable_agent"
  | "update_agent"
  | "add_data_entity"
  | "remove_data_entity"
  | "add_field_to_entity"
  | "remove_field_from_entity"
  | "add_page"
  | "remove_page"
  | "upsert_prompt"
  | "remove_prompt"
  | "update_industry";

export type MutationArgs =
  | { name: "update_brand"; args: UpdateBrandArgs }
  | { name: "add_nav_item"; args: AddNavItemArgs }
  | { name: "remove_nav_item"; args: RemoveNavItemArgs }
  | { name: "update_nav_item"; args: UpdateNavItemArgs }
  | { name: "reorder_nav"; args: ReorderNavArgs }
  | { name: "enable_agent"; args: EnableAgentArgs }
  | { name: "disable_agent"; args: DisableAgentArgs }
  | { name: "update_agent"; args: UpdateAgentArgs }
  | { name: "add_data_entity"; args: AddDataEntityArgs }
  | { name: "remove_data_entity"; args: RemoveDataEntityArgs }
  | { name: "add_field_to_entity"; args: AddFieldToEntityArgs }
  | { name: "remove_field_from_entity"; args: RemoveFieldFromEntityArgs }
  | { name: "add_page"; args: AddPageArgs }
  | { name: "remove_page"; args: RemovePageArgs }
  | { name: "upsert_prompt"; args: UpsertPromptArgs }
  | { name: "remove_prompt"; args: RemovePromptArgs }
  | { name: "update_industry"; args: UpdateIndustryArgs };

export function applyMutation(m: TenantManifest, mutation: MutationArgs): TenantManifest {
  switch (mutation.name) {
    case "update_brand": return updateBrand(m, mutation.args);
    case "add_nav_item": return addNavItem(m, mutation.args);
    case "remove_nav_item": return removeNavItem(m, mutation.args);
    case "update_nav_item": return updateNavItem(m, mutation.args);
    case "reorder_nav": return reorderNav(m, mutation.args);
    case "enable_agent": return enableAgent(m, mutation.args);
    case "disable_agent": return disableAgent(m, mutation.args);
    case "update_agent": return updateAgent(m, mutation.args);
    case "add_data_entity": return addDataEntity(m, mutation.args);
    case "remove_data_entity": return removeDataEntity(m, mutation.args);
    case "add_field_to_entity": return addFieldToEntity(m, mutation.args);
    case "remove_field_from_entity": return removeFieldFromEntity(m, mutation.args);
    case "add_page": return addPage(m, mutation.args);
    case "remove_page": return removePage(m, mutation.args);
    case "upsert_prompt": return upsertPrompt(m, mutation.args);
    case "remove_prompt": return removePrompt(m, mutation.args);
    case "update_industry": return updateIndustry(m, mutation.args);
  }
}

/** Apply a list of mutations in order; each subsequent mutation sees the
 *  result of the previous. Atomic: if any throws, the whole batch is
 *  discarded and the caller still has the pre-batch manifest. */
export function applyMutations(m: TenantManifest, mutations: MutationArgs[]): TenantManifest {
  let cur = m;
  for (const mut of mutations) {
    cur = applyMutation(cur, mut);
  }
  return cur;
}
