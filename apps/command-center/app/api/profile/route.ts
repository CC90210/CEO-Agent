/**
 * GET /api/profile     — return the authed operator's profile
 * PATCH /api/profile   — update editable fields on the authed operator's profile
 */
import { NextResponse, type NextRequest } from "next/server";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";
import { bad } from "@/lib/api-helpers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const EDITABLE = new Set([
  "full_name",
  "display_name",
  "brand",
  "mrr_target_usd",
  "mrr_current_usd",
  "mrr_target_date",
  "manifesto",
  "primary_agent",
  "agents_enabled",
  "preferred_language",
  "prospect_focus",
  // Free-form per-user prefs blob (timezone, briefing_channel, photo url,
  // anything the welcome wizard or settings page wants to store without a
  // dedicated column). Whitelisted because the welcome wizard writes here.
  "custom_fields",
  // Set by the OnboardingFlow's "Finish" button. Middleware uses this to
  // decide whether to force-route a signed-in user back to /onboarding.
  // The user can only set this on themselves; the only side effect of a
  // forged value is letting them skip the wizard, which is non-critical.
  "onboarding_completed_at",
]);

export async function GET() {
  const user = await getSessionUser();
  if (!user) return bad(401, "unauthorized");

  const db = getServiceSupabase();
  const r = await db.from("user_profiles").select("*").eq("auth_user_id", user.id).maybeSingle();
  if (r.error) return bad(500, r.error.message);
  if (!r.data) return bad(404, "profile not found — re-run signup");

  return NextResponse.json({ ok: true, profile: r.data });
}

export async function PATCH(req: NextRequest) {
  const user = await getSessionUser();
  if (!user) return bad(401, "unauthorized");

  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return bad(400, "invalid JSON");
  }

  const update: Record<string, unknown> = {};
  for (const k of Object.keys(body)) {
    if (EDITABLE.has(k)) update[k] = body[k];
  }
  if (Object.keys(update).length === 0) return bad(400, "no editable fields provided");

  const db = getServiceSupabase();
  const r = await db
    .from("user_profiles")
    .update(update)
    .eq("auth_user_id", user.id)
    .select("*")
    .maybeSingle();
  if (r.error) return bad(500, r.error.message);
  if (!r.data) return bad(404, "profile not found");

  return NextResponse.json({ ok: true, profile: r.data });
}
