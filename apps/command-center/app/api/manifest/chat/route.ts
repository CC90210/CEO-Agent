/**
 * POST /api/manifest/chat
 *
 * Conversational manifest editor. The operator sends a natural-language
 * request (with optional prior turns); we ask their configured LLM to
 * propose mutations as a JSON envelope, dry-run them against the live
 * manifest, and return:
 *
 *   {
 *     explanation: string,        // AI's narration
 *     mutations:   MutationArgs[],// proposed mutations (possibly [])
 *     preview_manifest: TenantManifest,
 *     diff:        DiffEntry[],
 *     ai_message:  string         // the raw assistant message for chat history
 *   }
 *
 * The user then reviews the diff. Hitting "Apply" sends the same `mutations`
 * to POST /api/manifest/<slug> for atomic persistence + audit logging. The
 * AI never persists directly — proposals require explicit human consent.
 *
 * This endpoint is auth-gated and admin-gated (same as /api/manifest/<slug>
 * POST). It reads the caller's encrypted Anthropic / OpenRouter / OpenAI /
 * Google / Ollama key from agent_model_config (agent_key="bravo") just like
 * /api/chat does, so manifest editing uses the tenant's own provider quota.
 */

import { NextResponse, type NextRequest } from "next/server";
import { decryptField } from "@/lib/field-encryption";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { streamChat, type ChatMessage, type Provider } from "@/lib/providers";
import { isOperatorEmail, operatorPlatformFallback } from "@/lib/operator-credentials";
import { getManifest, manifestExists } from "@/lib/manifest/loader";
import {
  applyMutations,
  ManifestMutationError,
  type MutationArgs,
} from "@/lib/manifest/mutators";
import { diffManifests } from "@/lib/manifest/diff";
import { buildManifestEditorPrompt } from "@/lib/manifest/ai-prompt";
import { parseAIEnvelope } from "@/lib/manifest/ai-parser";
import { getManifestRow } from "@/lib/manifest/persistence";

const PROTECTED_SLUGS = new Set(["default", "oasis", "sun", "suga"]);

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 90;

type Body = {
  slug?: string;
  message?: string;
  history?: ChatMessage[];
};

export async function POST(req: NextRequest) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });

  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const slug = (body.slug || "").trim().toLowerCase();
  const message = (body.message || "").trim();
  if (!slug || !(await manifestExists(slug))) {
    return NextResponse.json({ ok: false, error: "unknown_tenant" }, { status: 400 });
  }
  if (!message) {
    return NextResponse.json({ ok: false, error: "empty_message" }, { status: 400 });
  }

  // Authorisation — must belong to a tenant and have admin/owner role.
  const service = getServiceSupabase();
  const profileQuery = await service
    .from("user_profiles")
    .select("tenant_id, team_role, is_owner")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const profile = profileQuery.data as
    | { tenant_id: string | null; team_role: string; is_owner: boolean }
    | null;
  if (!profile?.tenant_id) {
    return NextResponse.json({ ok: false, error: "no_tenant" }, { status: 403 });
  }
  if (!profile.is_owner && profile.team_role !== "admin" && profile.team_role !== "owner") {
    return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  }

  // Defense-in-depth — same guards the POST persistence endpoint enforces.
  // Surface them HERE so we never waste an LLM call on a request the save
  // step would reject anyway.
  if (PROTECTED_SLUGS.has(slug)) {
    return NextResponse.json(
      { ok: false, error: "protected_slug", reason: "Platform seed manifests cannot be edited. This includes default, oasis, sun, suga." },
      { status: 403 }
    );
  }
  const existingRow = await getManifestRow(slug).catch(() => null);
  if (existingRow && existingRow.tenant_id && existingRow.tenant_id !== profile.tenant_id) {
    return NextResponse.json(
      { ok: false, error: "cross_tenant_forbidden", reason: "This manifest belongs to another tenant." },
      { status: 403 }
    );
  }

  // Provider resolution — borrow the operator's bravo config so manifest
  // editing uses the tenant's own LLM quota and configured persona.
  const cfgQuery = await service
    .from("agent_model_config")
    .select("provider, model, encrypted_api_key, enabled")
    .eq("tenant_id", profile.tenant_id)
    .eq("agent_key", "bravo")
    .maybeSingle();
  const cfg = cfgQuery.data as
    | { provider: string; model: string; encrypted_api_key: string | null; enabled: boolean }
    | null;

  let provider: Provider;
  let model: string;
  let apiKey = "";

  if (cfg && cfg.enabled && cfg.encrypted_api_key) {
    provider = cfg.provider as Provider;
    model = cfg.model;
    try {
      apiKey = decryptField(cfg.encrypted_api_key);
    } catch {
      return NextResponse.json({ ok: false, error: "key_decrypt_failed" }, { status: 500 });
    }
  } else {
    const fallback = isOperatorEmail(user.email || "") ? operatorPlatformFallback() : null;
    if (!fallback) {
      return NextResponse.json(
        { ok: false, error: "agent_not_configured", hint: "Configure your Bravo provider key in Settings before using the manifest editor." },
        { status: 412 }
      );
    }
    provider = fallback.provider;
    model = fallback.model;
    apiKey = fallback.apiKey;
  }

  const manifest = await getManifest(slug);
  const system = buildManifestEditorPrompt({ tenantSlug: slug, manifest });

  const history = Array.isArray(body.history) ? body.history : [];
  const messages: ChatMessage[] = [
    ...history.filter((m) => m.role === "user" || m.role === "assistant"),
    { role: "user", content: message },
  ];

  // Single-shot consume of streamChat. We don't stream to the browser for the
  // editor — the UX is "user types, AI proposes, diff renders, user clicks
  // Apply." A streaming explanation would feel chatty without helping the
  // operator make a faster decision. Streaming can come back in a Phase 2.1
  // polish pass.
  const isOllama = provider === "ollama";
  let aiText = "";
  let streamError: string | null = null;
  try {
    for await (const ev of streamChat({
      provider,
      model,
      apiKey: isOllama ? "" : apiKey,
      baseUrl: isOllama ? apiKey : undefined,
      system,
      messages,
      maxTokens: 2048,
    })) {
      if (ev.type === "delta") aiText += ev.text;
      else if (ev.type === "error") streamError = ev.message;
    }
  } catch (err) {
    streamError = err instanceof Error ? err.message : "stream_failed";
  }

  if (streamError) {
    return NextResponse.json({ ok: false, error: "llm_call_failed", message: streamError }, { status: 502 });
  }

  const parsed = parseAIEnvelope(aiText);
  if (!parsed.ok) {
    return NextResponse.json(
      { ok: false, error: "ai_envelope_invalid", reason: parsed.error, ai_message: aiText },
      { status: 502 }
    );
  }

  // Dry-run mutations against the current manifest to validate + diff.
  let preview;
  try {
    preview = applyMutations(manifest, parsed.envelope.mutations);
  } catch (err) {
    if (err instanceof ManifestMutationError) {
      return NextResponse.json({
        ok: false,
        error: "mutation_rejected",
        field: err.field,
        reason: err.reason,
        explanation: parsed.envelope.explanation,
        mutations: parsed.envelope.mutations,
        ai_message: aiText,
      }, { status: 422 });
    }
    throw err;
  }

  const diff = diffManifests(manifest, preview);

  return NextResponse.json({
    ok: true,
    explanation: parsed.envelope.explanation,
    mutations: parsed.envelope.mutations as MutationArgs[],
    preview_manifest: preview,
    diff,
    ai_message: aiText,
  });
}
