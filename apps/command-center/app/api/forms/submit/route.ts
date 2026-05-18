/**
 * POST /api/forms/submit
 *
 * Public-facing submission endpoint for a personalized form link.
 * Authenticated via HMAC bearer token in the request body (not a session
 * cookie) so prospects can submit without an OASIS account.
 *
 * Flow:
 *   1. Verify the HMAC token via lib/form-links.ts.
 *   2. Look up the form to confirm it's still enabled.
 *   3. Insert a form_submissions row (one per step completion).
 *   4. If form.step_outcomes maps this step_index to a lead.stage value,
 *      transition the lead via updateRecord. The Phase 2 publisher fires
 *      BRAVO_RECORD_STATUS_CHANGED automatically, which the Phase 4 drip
 *      engine consumes.
 *
 * Body:
 *   {
 *     token: string,         // the HMAC-signed lead_token from the URL
 *     step_index: number,    // 0-based index into form.steps
 *     payload: {...},        // field-name -> value map
 *     file_attachments?: [...]
 *   }
 *
 * Response: { ok, submission_id, next_step?, lead_stage? }
 *
 * Rate-limit: 30 submissions per minute per token (lead-bound). Hand-
 * rolled in-memory bucket so a runaway client can't flood the dashboard.
 * Tracks by token rather than IP because forms are personalized links —
 * one IP could legitimately submit forms for multiple leads.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { verifyFormLink, signFormLink, type FormLinkPayload } from "@/lib/form-links";
import {
  parseFormSteps,
  type FormStep,
  FormDefinitionError,
} from "@/lib/forms/types";
import { rateLimit } from "@/lib/rate-limit";
import { createRecord, updateRecord, RecordsError } from "@/lib/manifest/data";
import { sanitizeStorageFilename } from "@/lib/storage-helpers";
import { createHash } from "node:crypto";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type SubmitBody = {
  token?: string;
  step_index?: number;
  payload?: Record<string, unknown>;
  file_attachments?: Array<{
    field_name: string;
    storage_path: string;
    mime_type: string;
    size_bytes: number;
  }>;
  // Anonymous-form mode (shareable-link, no per-lead HMAC): on the first
  // submit the client sends anonymous_init {tenant_slug, form_slug} and
  // no token. The server creates a fresh lead, signs a token tied to it,
  // and returns it for the rest of the multi-step funnel.
  anonymous_init?: {
    tenant_slug?: string;
    form_slug?: string;
  };
};

// The public client embeds files as `inline_base64` inside payload[field].
// This shape unwraps them so the server can move bytes to Supabase Storage.
type InlineFile = {
  inline_base64: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
};

function isInlineFile(v: unknown): v is InlineFile {
  if (!v || typeof v !== "object") return false;
  const obj = v as Record<string, unknown>;
  return (
    typeof obj.inline_base64 === "string" &&
    typeof obj.filename === "string" &&
    typeof obj.mime_type === "string" &&
    typeof obj.size_bytes === "number"
  );
}


export async function POST(req: NextRequest) {
  let body: SubmitBody;
  try {
    body = (await req.json()) as SubmitBody;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  // Two auth shapes:
  //   1. Personalized link (Solara's mint): body.token is an HMAC.
  //   2. Anonymous share link: body.anonymous_init = {tenant_slug, form_slug}
  //      with no token. The server creates a fresh lead, signs a token,
  //      and returns it so subsequent steps in the same session re-use it.
  let link: FormLinkPayload;
  let mintedTokenForResponse: string | null = null;
  if (body.token) {
    const sigResult = verifyFormLink(body.token);
    if (!sigResult.ok) {
      return NextResponse.json(
        { ok: false, error: `token_${sigResult.reason}` },
        { status: sigResult.reason === "server_misconfigured" ? 503 : 400 },
      );
    }
    link = sigResult.payload;
  } else if (body.anonymous_init?.tenant_slug && body.anonymous_init?.form_slug) {
    // Pre-create rate limit on the anonymous_init path. The token-bucket
    // BELOW keys on lead_id, which is freshly minted here — so without
    // this gate every anonymous request would land in its own bucket and
    // a bot could spam-create leads unbounded. Key the limiter on
    // (ip, tenant_slug, form_slug) so legitimate humans aren't blocked
    // by someone else hammering the same form. 10 inits/minute per
    // (ip, form) is roughly one human filling the form every 6 seconds,
    // well above retry-after-typo but far below scripted abuse.
    const ip =
      req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
      req.headers.get("x-real-ip")?.trim() ||
      "no-ip";
    const tenantSlug = body.anonymous_init.tenant_slug.toLowerCase();
    const formSlug = body.anonymous_init.form_slug.toLowerCase();
    const initLimit = rateLimit({
      key: `forms-anon-init:${ip}:${tenantSlug}:${formSlug}`,
      capacity: 10,
      refillPerSec: 10 / 60,
    });
    if (!initLimit.allowed) {
      return NextResponse.json(
        { ok: false, error: "rate_limited", retry_in_sec: initLimit.resetIn },
        { status: 429 },
      );
    }
    const anonResult = await initAnonymousLead({
      tenantSlug,
      formSlug,
      payload: body.payload || {},
      ip,
    });
    if (!anonResult.ok) {
      return NextResponse.json(
        { ok: false, error: anonResult.error },
        { status: anonResult.status },
      );
    }
    link = anonResult.link;
    mintedTokenForResponse = anonResult.token;
  } else {
    return NextResponse.json(
      { ok: false, error: "no_auth_provided" },
      { status: 400 },
    );
  }

  // Per-token rate limit. 30/min is roughly 1 submission every 2s, enough
  // for legitimate multi-step funnels (basic -> app -> upload) but well
  // below abusive-bot territory.
  const limit = rateLimit({
    key: `forms-submit:${link.lead_id}:${link.form_id}`,
    capacity: 30,
    refillPerSec: 0.5,
  });
  if (!limit.allowed) {
    return NextResponse.json(
      { ok: false, error: "rate_limited", retry_in_sec: limit.resetIn },
      { status: 429 },
    );
  }

  const stepIndex = Number(body.step_index);
  if (!Number.isInteger(stepIndex) || stepIndex < 0) {
    return NextResponse.json(
      { ok: false, error: "invalid_step_index" },
      { status: 400 },
    );
  }

  const payload =
    body.payload && typeof body.payload === "object" ? body.payload : {};
  const fileAttachments = Array.isArray(body.file_attachments)
    ? body.file_attachments
    : [];

  // Inline files arrive base64-encoded inside payload. Pull them out so we
  // can upload to Supabase Storage and stop persisting the bytes in jsonb
  // (form_submissions.payload would otherwise grow unbounded). The mutated
  // payload retains a reference to the storage_path so operators can still
  // see what was uploaded against each field.
  const inlineFiles: Array<{ fieldName: string; file: InlineFile }> = [];
  for (const [fieldName, value] of Object.entries(payload)) {
    if (isInlineFile(value)) {
      inlineFiles.push({ fieldName, file: value });
    }
  }

  // Look up the form to confirm it's still enabled + step_index is in
  // range. Tenant scoping comes from the verified token's tenant slug;
  // we double-check the form's tenant_id row matches that slug to defeat
  // tenant-id forgery via a leaked token.
  const db = getServiceSupabase();
  const formRow = await db
    .from("forms")
    .select(
      "id, tenant_id, slug, steps, on_complete_stage, step_outcomes, enabled, redirect_url, tenant:tenants!inner(slug)",
    )
    .eq("id", link.form_id)
    .maybeSingle();
  if (formRow.error || !formRow.data) {
    return NextResponse.json({ ok: false, error: "form_not_found" }, { status: 404 });
  }
  const form = formRow.data as {
    id: string;
    tenant_id: string;
    slug: string;
    steps: unknown;
    on_complete_stage: string | null;
    step_outcomes: Record<string, string> | null;
    enabled: boolean;
    redirect_url: string | null;
    tenant: { slug: string } | { slug: string }[] | null;
  };
  if (!form.enabled) {
    return NextResponse.json({ ok: false, error: "form_disabled" }, { status: 400 });
  }
  const tenantRow = Array.isArray(form.tenant) ? form.tenant[0] : form.tenant;
  if (!tenantRow || tenantRow.slug !== link.tenant) {
    return NextResponse.json({ ok: false, error: "tenant_mismatch" }, { status: 400 });
  }

  // Parse the steps to validate step_index range. parseFormSteps throws
  // on malformed data — if a DB row is somehow corrupt we 500 cleanly.
  let steps: FormStep[];
  try {
    steps = parseFormSteps(form.steps);
  } catch (err) {
    if (err instanceof FormDefinitionError) {
      return NextResponse.json(
        { ok: false, error: "form_definition_corrupt", path: err.path, reason: err.reason },
        { status: 500 },
      );
    }
    throw err;
  }
  if (stepIndex >= steps.length) {
    return NextResponse.json(
      { ok: false, error: "step_index_out_of_range", max: steps.length - 1 },
      { status: 400 },
    );
  }

  // Insert the submission row. service-role write — RLS doesn't see this
  // path; HMAC token + tenant_id match is the auth boundary.
  const ipHeader =
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || null;
  const userAgent = req.headers.get("user-agent")?.slice(0, 500) || null;

  // Move inline files to Supabase Storage. The bucket + RLS policies live
  // in migration 055. Each file lands under <tenant_id>/<lead_id>/<filename>
  // — the tenant-prefix anchors the read RLS policy without an extra join.
  //
  // Errors here don't abort the whole submission: a stage-transition can
  // still go through with missing docs, and the operator sees the gap on
  // the lead detail page. We log to stage_warning style so the UI can
  // surface the partial-success state.
  const uploadedDocs: Array<{
    field_name: string;
    storage_path: string;
    filename: string;
    mime_type: string;
    size_bytes: number;
    doc_type: string;
  }> = [];
  const uploadWarnings: Array<{ field_name: string; reason: string }> = [];

  // Schema-driven file validation. Without this an attacker could embed
  // arbitrary {inline_base64, ...} blobs against any payload key (even
  // ones the form doesn't declare as file_upload) and we'd happily push
  // bytes to Storage with attacker-controlled MIME types. Enforce on
  // the server: (a) the field must exist on THIS step, (b) it must be
  // type=file_upload, (c) the file's mime_type must be in the field's
  // accept[] list, (d) decoded length must agree with the claimed
  // size, (e) total decoded bytes per request cap so a base64-bomb can
  // never knock the runtime over.
  const currentStepFields = new Map(steps[stepIndex].fields.map((f) => [f.name, f]));
  const PER_FILE_DECODED_CAP_BYTES = 15 * 1024 * 1024;
  const PER_REQUEST_DECODED_CAP_BYTES = 60 * 1024 * 1024;
  const MAX_FILES_PER_STEP = 10;
  let totalDecodedBytes = 0;
  if (inlineFiles.length > MAX_FILES_PER_STEP) {
    return NextResponse.json(
      { ok: false, error: "too_many_files", max: MAX_FILES_PER_STEP },
      { status: 400 },
    );
  }
  for (const { fieldName, file } of inlineFiles) {
    const fieldDef = currentStepFields.get(fieldName);
    if (!fieldDef || fieldDef.type !== "file_upload") {
      // Drop silently from inlineFiles; clear the payload entry so the
      // form_submissions row doesn't keep the attacker bytes either.
      uploadWarnings.push({
        field_name: fieldName,
        reason: "field_not_file_upload",
      });
      delete payload[fieldName];
      continue;
    }
    // MIME allowlist from the form schema. When the operator left
    // accept empty we fall back to a conservative inert-image / PDF
    // set — never allow application/* freeform.
    const allowedMime = (fieldDef.accept && fieldDef.accept.length > 0)
      ? fieldDef.accept
      : ["application/pdf", "image/png", "image/jpeg", "image/webp"];
    const mimeAllowed = allowedMime.some((rule) =>
      rule.endsWith("/*")
        ? file.mime_type.startsWith(rule.slice(0, -1))
        : file.mime_type === rule
    );
    if (!mimeAllowed) {
      uploadWarnings.push({
        field_name: fieldName,
        reason: `mime_not_allowed: ${file.mime_type}`,
      });
      delete payload[fieldName];
      continue;
    }
    // Decoded-length check. Computing Buffer length once here means we
    // pay the base64-decode cost regardless, but it bounds memory: a
    // 60MB request bomb still gets rejected before storage.
    let bytes: Buffer;
    try {
      bytes = Buffer.from(file.inline_base64, "base64");
    } catch {
      uploadWarnings.push({ field_name: fieldName, reason: "base64_invalid" });
      delete payload[fieldName];
      continue;
    }
    if (bytes.length > PER_FILE_DECODED_CAP_BYTES) {
      uploadWarnings.push({
        field_name: fieldName,
        reason: `file_too_large: ${bytes.length}`,
      });
      delete payload[fieldName];
      continue;
    }
    totalDecodedBytes += bytes.length;
    if (totalDecodedBytes > PER_REQUEST_DECODED_CAP_BYTES) {
      return NextResponse.json(
        { ok: false, error: "request_payload_too_large" },
        { status: 413 },
      );
    }
    try {
      const cleanName = sanitizeStorageFilename(file.filename);
      // Use the field name as doc_type so it lines up with the classifier
      // enum in migration 049 (bank_statements_3mo / drivers_license /
      // proof_of_ownership / …). Anything else falls under "unclassified".
      const docType = fieldName.replace(/[^a-z0-9_]/gi, "_").toLowerCase()
        || "unclassified";
      const storagePath = `${form.tenant_id}/${link.lead_id}/${Date.now()}_${cleanName}`;
      const upload = await db.storage
        .from("lead-documents")
        .upload(storagePath, bytes, {
          contentType: file.mime_type,
          upsert: false,
        });
      if (upload.error) {
        uploadWarnings.push({ field_name: fieldName, reason: upload.error.message });
        continue;
      }
      // Strip the bytes from the payload now that they're persisted —
      // form_submissions.payload should not carry the file contents.
      payload[fieldName] = {
        filename: file.filename,
        mime_type: file.mime_type,
        size_bytes: file.size_bytes,
        storage_path: storagePath,
      };
      const docInsert = await db
        .from("lead_documents")
        .insert({
          tenant_id: form.tenant_id,
          lead_id: link.lead_id,
          filename: cleanName,
          storage_path: storagePath,
          mime_type: file.mime_type,
          size_bytes: file.size_bytes,
          doc_type: docType,
          uploaded_by: "form_intake",
          metadata: { form_id: form.id, field_name: fieldName, step_index: stepIndex },
        })
        .select("id")
        .single();
      if (docInsert.error) {
        uploadWarnings.push({
          field_name: fieldName,
          reason: `metadata_insert_failed: ${docInsert.error.message}`,
        });
        continue;
      }
      uploadedDocs.push({
        field_name: fieldName,
        storage_path: storagePath,
        filename: cleanName,
        mime_type: file.mime_type,
        size_bytes: file.size_bytes,
        doc_type: docType,
      });
    } catch (err) {
      uploadWarnings.push({
        field_name: fieldName,
        reason: err instanceof Error ? err.message : "unknown",
      });
    }
  }

  // Replace the public client's `inline:<field>` placeholders with the real
  // storage paths so form_submissions.file_attachments is honest about what
  // landed where.
  const resolvedAttachments = fileAttachments.map((att) => {
    const matched = uploadedDocs.find((d) => d.field_name === att.field_name);
    if (matched) {
      return {
        ...att,
        storage_path: matched.storage_path,
      };
    }
    return att;
  });

  const insertRes = await db
    .from("form_submissions")
    .insert({
      form_id: form.id,
      tenant_id: form.tenant_id,
      lead_id: link.lead_id,
      step_index: stepIndex,
      payload,
      file_attachments: resolvedAttachments,
      ip_address: ipHeader,
      user_agent: userAgent,
    })
    .select("id")
    .single();
  if (insertRes.error) {
    return NextResponse.json(
      { ok: false, error: insertRes.error.message },
      { status: 500 },
    );
  }
  const submissionId = (insertRes.data as { id: string }).id;

  // Stage transition — if step_outcomes has a target for this step,
  // patch the lead via updateRecord. Phase 2's BRAVO_RECORD_STATUS_CHANGED
  // publisher fires automatically; the Phase 4 drip engine consumes it.
  // The final step also honors on_complete_stage as a fallback.
  let appliedStage: string | null = null;
  const stepOutcomes = form.step_outcomes || {};
  const isLastStep = stepIndex === steps.length - 1;
  const targetStage =
    stepOutcomes[String(stepIndex)] ||
    (isLastStep && form.on_complete_stage) ||
    null;

  // Round 3 R3-10: stage-transition failure used to swallow the error
  // and return ok:true, hiding from the operator that the drip never
  // fired. Now we capture the reason + surface it in the response so
  // the public form page can flag a partial success and the operator
  // sees in their /feed event tape that the lead landed but the
  // pipeline didn't advance.
  let stageWarning: { reason: string; target_stage: string } | null = null;
  if (targetStage) {
    try {
      await updateRecord({
        tenant_id: form.tenant_id,
        entity: "lead",
        id: link.lead_id,
        patch: { stage: targetStage },
      });
      appliedStage = targetStage;
    } catch (err) {
      const reason = err instanceof RecordsError ? err.code : "unknown";
      console.error("[forms.submit.stage_transition]", {
        lead_id: link.lead_id,
        target_stage: targetStage,
        reason,
      });
      stageWarning = { reason, target_stage: targetStage };
    }
  }

  return NextResponse.json({
    ok: true,
    submission_id: submissionId,
    next_step: isLastStep ? null : stepIndex + 1,
    lead_stage: appliedStage,
    redirect_url: isLastStep ? form.redirect_url : null,
    // Non-null when the prospect's submission landed but the lead's
    // stage didn't advance — drip didn't fire, operator needs to look
    // (typical causes: lead row was deleted between view + submit;
    // entity_type mismatch from a manifest edit mid-flight).
    stage_warning: stageWarning,
    // Per-file outcome: how many uploads landed in storage, which
    // failed. The public client doesn't show this to the prospect (it
    // would just confuse them) but the operator-facing /forms/[id]/
    // detail surface can.
    uploads: {
      attempted: inlineFiles.length,
      succeeded: uploadedDocs.length,
      warnings: uploadWarnings,
    },
    // Anonymous-share flow only: returned on the first step so the
    // client can carry the freshly-signed token through subsequent
    // steps. Null on every personalized (Solara-minted) submit.
    minted_token: mintedTokenForResponse,
  });
}

/**
 * Anonymous-share intake: validate the (tenant_slug, form_slug) pair,
 * create a fresh lead seeded with whatever name/email/phone we can pull
 * out of the first-step payload, sign a token for it. The signed token
 * becomes the auth boundary for the rest of the submission flow.
 */
async function initAnonymousLead(input: {
  tenantSlug: string;
  formSlug: string;
  payload: Record<string, unknown>;
  ip: string | null;
}): Promise<
  | { ok: true; link: FormLinkPayload; token: string }
  | { ok: false; error: string; status: number }
> {
  const tenantSlug = input.tenantSlug.trim().toLowerCase();
  const formSlug = input.formSlug.trim().toLowerCase();
  if (!tenantSlug || !formSlug) {
    return { ok: false, error: "not_found", status: 404 };
  }
  const db = getServiceSupabase();

  // Resolve tenant_id FIRST so the form lookup is scoped (avoids
  // multi-tenant slug collisions where two tenants both have a form
  // with slug='application'). All public negatives return a single
  // 'not_found' so the route can't be used to enumerate tenants /
  // form names by diffing 404 vs form_disabled vs tenant_mismatch.
  const tenantQ = await db
    .from("tenants")
    .select("id")
    .eq("slug", tenantSlug)
    .maybeSingle();
  const tenantId = (tenantQ.data as { id: string } | null)?.id;
  if (!tenantId) {
    return { ok: false, error: "not_found", status: 404 };
  }
  const row = await db
    .from("forms")
    .select("id, tenant_id, enabled")
    .eq("tenant_id", tenantId)
    .eq("slug", formSlug)
    .maybeSingle();
  if (row.error || !row.data) {
    return { ok: false, error: "not_found", status: 404 };
  }
  const form = row.data as { id: string; tenant_id: string; enabled: boolean };
  if (!form.enabled) {
    return { ok: false, error: "not_found", status: 404 };
  }

  // Seed the lead with whatever common contact fields the operator
  // already collected on this step. Falls back gracefully when the
  // form's field names don't match — the operator can still see the
  // raw payload in the form_submissions row.
  const pick = (k: string) =>
    typeof input.payload[k] === "string" ? (input.payload[k] as string) : undefined;
  const leadData: Record<string, unknown> = {
    stage: "imported",
    source: "public_form",
    created_from_form_id: form.id,
    created_from_ip_hash: input.ip ? hashIp(input.ip) : null,
  };
  const name = pick("contact_name") || pick("name") || pick("full_name");
  if (name) leadData.contact_name = name;
  const business = pick("business_name") || pick("company");
  if (business) leadData.business_name = business;
  const email = pick("email");
  if (email) leadData.email = email;
  const phone = pick("phone");
  if (phone) leadData.phone = phone;

  let lead;
  try {
    lead = await createRecord({
      tenant_id: form.tenant_id,
      entity: "lead",
      data: leadData,
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "unknown";
    return { ok: false, error: `lead_create_failed: ${detail}`, status: 500 };
  }

  const token = signFormLink({
    tenant: tenantSlug,
    form_id: form.id,
    lead_id: lead.id,
  });
  if (token === null) {
    return { ok: false, error: "form_links_misconfigured", status: 503 };
  }

  return {
    ok: true,
    token,
    link: {
      tenant: tenantSlug,
      form_id: form.id,
      lead_id: lead.id,
      iat: Math.floor(Date.now() / 1000),
    },
  };
}

/** Truncated SHA-256 of the IP — used for lightweight per-IP dedup
 *  without persisting raw IPs in tenant data. */
function hashIp(ip: string): string {
  return createHash("sha256").update(ip).digest("hex").slice(0, 16);
}
