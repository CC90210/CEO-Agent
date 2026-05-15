/**
 * POST /api/forms/[id]/mint-link
 *
 * Operator-facing — generates a personalized URL for a specific lead.
 * The returned URL embeds an HMAC-signed token (see lib/form-links.ts)
 * so the prospect can open the form without an OASIS account, and the
 * public /api/forms/submit route can verify the request came from this
 * minted link rather than a guessed UUID.
 *
 * Body: { lead_id: string }
 * Response: { ok, url, token, expires_at }
 *
 * URL shape:
 *   <origin>/f/<tenant_slug>/<form_slug>/<token>
 *
 * The tenant slug is read from the tenant row (not the manifest) since
 * tenant.slug is the authoritative URL segment everywhere else.
 */

import { NextRequest, NextResponse } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { signFormLink } from "@/lib/form-links";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const DEFAULT_TTL_DAYS = 60;

async function resolveTenant(): Promise<
  | { tenant_id: string; tenant_slug: string }
  | null
> {
  const user = await getSessionUser();
  if (!user) return null;
  const db = getServiceSupabase();
  const { data } = await db
    .from("user_profiles")
    .select("tenant_id, tenant:tenants!inner(slug)")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  if (!data) return null;
  const row = data as { tenant_id: string | null; tenant: { slug: string } | { slug: string }[] | null };
  if (!row.tenant_id) return null;
  // PostgREST returns the joined table as either an object or an array
  // depending on the relationship cardinality declared in the select.
  // Normalize either way so the slug is reliable.
  const t = Array.isArray(row.tenant) ? row.tenant[0] : row.tenant;
  if (!t?.slug) return null;
  return { tenant_id: row.tenant_id, tenant_slug: t.slug };
}

export async function POST(
  req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const tenant = await resolveTenant();
  if (!tenant) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }
  const { id: formId } = await ctx.params;

  let body: { lead_id?: unknown };
  try {
    body = (await req.json()) as { lead_id?: unknown };
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const leadId = typeof body.lead_id === "string" ? body.lead_id.trim() : "";
  if (!leadId) {
    return NextResponse.json(
      { ok: false, error: "lead_id_required" },
      { status: 400 },
    );
  }

  // Verify the form exists + belongs to this tenant before signing — the
  // HMAC alone doesn't prove the (form, tenant) pairing is real, just
  // that the OPERATOR minted it. Public form page would 404 on a fake
  // form_id, but minting one is still bad UX.
  const db = getServiceSupabase();
  const formRow = await db
    .from("forms")
    .select("id, slug, enabled")
    .eq("id", formId)
    .eq("tenant_id", tenant.tenant_id)
    .maybeSingle();
  if (formRow.error || !formRow.data) {
    return NextResponse.json({ ok: false, error: "form_not_found" }, { status: 404 });
  }
  const form = formRow.data as { id: string; slug: string; enabled: boolean };
  if (!form.enabled) {
    return NextResponse.json({ ok: false, error: "form_disabled" }, { status: 400 });
  }

  const token = signFormLink({
    tenant: tenant.tenant_slug,
    form_id: form.id,
    lead_id: leadId,
  });
  if (token === null) {
    // Production with no HMAC key — refuse to mint, same fail-closed
    // posture /api/chat/resume uses when CHAT_RESUME_HMAC_KEY is unset.
    return NextResponse.json(
      {
        ok: false,
        error: "form_links_misconfigured",
        hint:
          "FORM_LINK_HMAC_KEY is not set in this environment. Set a ≥32 char random string in Vercel env vars and redeploy.",
      },
      { status: 503 },
    );
  }

  const origin = req.nextUrl.origin;
  const url = `${origin}/f/${tenant.tenant_slug}/${form.slug}/${token}`;
  const expiresAt = new Date(Date.now() + DEFAULT_TTL_DAYS * 86400 * 1000).toISOString();

  return NextResponse.json({
    ok: true,
    url,
    token,
    expires_at: expiresAt,
    form_id: form.id,
    lead_id: leadId,
  });
}
