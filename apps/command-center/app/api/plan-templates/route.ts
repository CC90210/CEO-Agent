/**
 * GET /api/plan-templates              — return weekday + weekend templates
 * PUT /api/plan-templates              — upsert a template (body: kind + schedule + targets)
 * DELETE /api/plan-templates?kind=X    — disable a template
 */
import { NextResponse, type NextRequest } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { bad, profileForUser } from "@/lib/api-helpers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const profile = await profileForUser();
  if (!profile) return bad(401, "unauthorized");
  const db = getServiceSupabase();
  const r = await db
    .from("plan_templates")
    .select("*")
    .eq("profile_id", profile.id)
    .order("kind");
  if (r.error) return bad(500, r.error.message);
  return NextResponse.json({ ok: true, templates: r.data || [] });
}

export async function PUT(req: NextRequest) {
  const profile = await profileForUser();
  if (!profile) return bad(401, "unauthorized");

  let body: {
    kind?: "weekday" | "weekend";
    mission?: string;
    target_calls?: number;
    target_emails?: number;
    target_bookings?: number;
    schedule?: Array<{
      time_label: string;
      title: string;
      body: string;
      intensity?: "intense" | "normal" | "break" | "carryover";
    }>;
    enabled?: boolean;
  };
  try { body = await req.json(); } catch { return bad(400, "invalid JSON"); }

  if (body.kind !== "weekday" && body.kind !== "weekend") return bad(400, "kind must be 'weekday' or 'weekend'");
  if (!Array.isArray(body.schedule)) return bad(400, "schedule must be an array");

  const db = getServiceSupabase();
  const existing = await db
    .from("plan_templates")
    .select("id")
    .eq("profile_id", profile.id)
    .eq("kind", body.kind)
    .maybeSingle();

  const payload = {
    profile_id: profile.id,
    tenant_id: profile.tenant_id,
    kind: body.kind,
    mission: body.mission ?? null,
    target_calls: body.target_calls ?? 0,
    target_emails: body.target_emails ?? 0,
    target_bookings: body.target_bookings ?? 1,
    schedule: body.schedule,
    enabled: body.enabled ?? true,
  };

  const r = existing.data
    ? await db.from("plan_templates").update(payload).eq("id", existing.data.id).select("*").maybeSingle()
    : await db.from("plan_templates").insert(payload).select("*").maybeSingle();

  if (r.error) return bad(500, r.error.message);
  return NextResponse.json({ ok: true, template: r.data });
}

export async function DELETE(req: NextRequest) {
  const profile = await profileForUser();
  if (!profile) return bad(401, "unauthorized");
  const kind = req.nextUrl.searchParams.get("kind");
  if (kind !== "weekday" && kind !== "weekend") return bad(400, "kind must be 'weekday' or 'weekend'");

  const db = getServiceSupabase();
  const r = await db
    .from("plan_templates")
    .update({ enabled: false })
    .eq("profile_id", profile.id)
    .eq("kind", kind);
  if (r.error) return bad(500, r.error.message);
  return NextResponse.json({ ok: true });
}
