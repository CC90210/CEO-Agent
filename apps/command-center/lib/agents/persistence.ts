/**
 * Persistence for user-created custom agents. Mirrors the patterns used for
 * tenant_manifests in lib/manifest/persistence.ts: service-role writes,
 * defensive validation, structured error type.
 *
 * Platform-managed seeds (is_oasis_managed=true) are NEVER created or
 * mutated through this layer — they live in lib/agents/library.ts under
 * tsc supervision. This layer only handles user customs (is_oasis_managed
 * is forced to false on every write).
 */

import { getServiceSupabase } from "@/lib/supabase-server";
import type {
  AgentCategory,
  AgentLibraryEntry,
  AgentPricing,
} from "./library";

export class AgentPersistenceError extends Error {
  constructor(
    public code: "validation" | "duplicate_slug" | "not_found" | "forbidden" | "db",
    message: string
  ) {
    super(message);
    this.name = "AgentPersistenceError";
  }
}

const SLUG_RE = /^[a-z0-9][a-z0-9-]{1,62}$/;

const ALLOWED_CATEGORIES = new Set<AgentCategory>([
  "ceo", "cfo", "cmo", "coo", "operations", "sales", "support",
  "research", "content", "engineering", "finance", "legal",
  "industry_real_estate", "industry_funding", "industry_ecommerce",
  "industry_agency", "custom",
]);

export type CreateAgentInput = {
  slug: string;
  name: string;
  category: AgentCategory;
  short_description: string;
  description?: string;
  base_prompt: string;
  required_tools?: string[];
  suggested_model?: string;
  pricing?: AgentPricing;
  is_public?: boolean;
  created_by: string;
  tenant_id: string;
};

function validateAgentInput(input: CreateAgentInput): void {
  const slug = input.slug.trim().toLowerCase();
  if (!SLUG_RE.test(slug)) {
    throw new AgentPersistenceError("validation", "slug must match /^[a-z0-9][a-z0-9-]{1,62}$/");
  }
  if (!input.name.trim()) {
    throw new AgentPersistenceError("validation", "name is required");
  }
  if (!ALLOWED_CATEGORIES.has(input.category)) {
    throw new AgentPersistenceError("validation", `unknown category "${input.category}"`);
  }
  if (!input.short_description.trim()) {
    throw new AgentPersistenceError("validation", "short_description is required");
  }
  if (!input.base_prompt.trim() || input.base_prompt.length < 30) {
    throw new AgentPersistenceError("validation", "base_prompt is required (minimum 30 characters)");
  }
  if (input.base_prompt.length > 16000) {
    throw new AgentPersistenceError("validation", "base_prompt too long (max 16000 characters)");
  }
  if (input.required_tools && input.required_tools.length > 32) {
    throw new AgentPersistenceError("validation", "required_tools capped at 32");
  }
}

export async function createCustomAgent(input: CreateAgentInput): Promise<AgentLibraryEntry> {
  validateAgentInput(input);
  const slug = input.slug.trim().toLowerCase();
  const db = getServiceSupabase();

  const existing = await db.from("agents").select("slug").eq("slug", slug).maybeSingle();
  if (existing.error) throw new AgentPersistenceError("db", existing.error.message);
  if (existing.data) throw new AgentPersistenceError("duplicate_slug", `slug "${slug}" already taken`);

  const row = {
    slug,
    name: input.name.trim(),
    category: input.category,
    short_description: input.short_description.trim(),
    description: input.description?.trim() || null,
    base_prompt: input.base_prompt.trim(),
    required_tools: input.required_tools || [],
    suggested_model: input.suggested_model || null,
    pricing: (input.pricing || { tier: "free" }) as unknown as Record<string, unknown>,
    is_public: input.is_public ?? false,
    is_oasis_managed: false,
    created_by: input.created_by,
    tenant_id: input.tenant_id,
  };
  const inserted = await db.from("agents").insert(row).select("*").single();
  if (inserted.error) throw new AgentPersistenceError("db", inserted.error.message);
  return inserted.data as AgentLibraryEntry;
}

export type UpdateAgentInput = Partial<Omit<CreateAgentInput, "slug" | "tenant_id" | "created_by">> & {
  slug: string;
  tenant_id: string;
};

export async function updateCustomAgent(input: UpdateAgentInput): Promise<AgentLibraryEntry> {
  const slug = input.slug.trim().toLowerCase();
  const db = getServiceSupabase();
  const existing = await db
    .from("agents")
    .select("id, tenant_id, is_oasis_managed")
    .eq("slug", slug)
    .maybeSingle();
  if (existing.error) throw new AgentPersistenceError("db", existing.error.message);
  if (!existing.data) throw new AgentPersistenceError("not_found", `agent "${slug}" not found`);
  const row = existing.data as { id: string; tenant_id: string | null; is_oasis_managed: boolean };
  if (row.is_oasis_managed) {
    throw new AgentPersistenceError("forbidden", "platform-managed agents cannot be edited through this endpoint");
  }
  if (row.tenant_id !== input.tenant_id) {
    throw new AgentPersistenceError("forbidden", "this agent belongs to a different tenant");
  }

  const patch: Record<string, unknown> = {};
  if (input.name !== undefined) patch.name = input.name.trim();
  if (input.category !== undefined) {
    if (!ALLOWED_CATEGORIES.has(input.category)) {
      throw new AgentPersistenceError("validation", `unknown category "${input.category}"`);
    }
    patch.category = input.category;
  }
  if (input.short_description !== undefined) patch.short_description = input.short_description.trim();
  if (input.description !== undefined) patch.description = input.description.trim() || null;
  if (input.base_prompt !== undefined) {
    if (input.base_prompt.length < 30 || input.base_prompt.length > 16000) {
      throw new AgentPersistenceError("validation", "base_prompt must be 30-16000 characters");
    }
    patch.base_prompt = input.base_prompt.trim();
  }
  if (input.required_tools !== undefined) {
    if (input.required_tools.length > 32) {
      throw new AgentPersistenceError("validation", "required_tools capped at 32");
    }
    patch.required_tools = input.required_tools;
  }
  if (input.suggested_model !== undefined) patch.suggested_model = input.suggested_model || null;
  if (input.pricing !== undefined) patch.pricing = input.pricing as unknown as Record<string, unknown>;
  if (input.is_public !== undefined) patch.is_public = input.is_public;

  if (Object.keys(patch).length === 0) {
    return (await db.from("agents").select("*").eq("id", row.id).single()).data as AgentLibraryEntry;
  }

  const updated = await db.from("agents").update(patch).eq("id", row.id).select("*").single();
  if (updated.error) throw new AgentPersistenceError("db", updated.error.message);
  return updated.data as AgentLibraryEntry;
}

export async function deleteCustomAgent(slug: string, tenantId: string): Promise<void> {
  const db = getServiceSupabase();
  const existing = await db
    .from("agents")
    .select("id, tenant_id, is_oasis_managed")
    .eq("slug", slug)
    .maybeSingle();
  if (existing.error) throw new AgentPersistenceError("db", existing.error.message);
  if (!existing.data) throw new AgentPersistenceError("not_found", `agent "${slug}" not found`);
  const row = existing.data as { id: string; tenant_id: string | null; is_oasis_managed: boolean };
  if (row.is_oasis_managed) {
    throw new AgentPersistenceError("forbidden", "platform-managed agents cannot be deleted");
  }
  if (row.tenant_id !== tenantId) {
    throw new AgentPersistenceError("forbidden", "this agent belongs to a different tenant");
  }
  const deleted = await db.from("agents").delete().eq("id", row.id);
  if (deleted.error) throw new AgentPersistenceError("db", deleted.error.message);
}
