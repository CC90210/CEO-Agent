import { NextResponse, type NextRequest } from "next/server";
import { bad } from "@/lib/api-helpers";
import { getAuthedSupabase } from "@/lib/supabase-server";
import {
  canManageTeam,
  getSessionContext,
  getTenantMembers,
  removeMember,
  setMemberRole,
  type TeamRole,
} from "@/lib/team";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ROLE_VALUES: TeamRole[] = [
  "admin",
  "loan_officer",
  "processor",
  "read_only",
  "member",
];

export async function GET() {
  const ctx = await getSessionContext();
  if (!ctx) return bad(401, "unauthorized");
  const members = await getTenantMembers(ctx.tenantId);
  const canManage = canManageTeam(ctx.teamRole);
  return NextResponse.json({
    ok: true,
    self_profile_id: ctx.profileId,
    self_role: ctx.teamRole,
    self_is_owner: ctx.isOwner,
    can_manage: canManage,
    members: members.map((m) => ({
      id: m.id,
      email: canManage ? m.email : null,
      full_name: m.full_name,
      display_name: m.display_name,
      team_role: m.team_role,
      is_owner: m.is_owner,
      joined_at: m.joined_at,
    })),
  });
}

export async function PATCH(req: NextRequest) {
  const ctx = await getSessionContext();
  if (!ctx) return bad(401, "unauthorized");
  if (!canManageTeam(ctx.teamRole)) return bad(403, "forbidden");

  let body: { profile_id?: string; role?: string };
  try {
    body = await req.json();
  } catch {
    return bad(400, "invalid JSON");
  }
  if (!body.profile_id) return bad(400, "missing profile_id");
  const newRole = body.role as TeamRole;
  if (!ROLE_VALUES.includes(newRole)) return bad(400, "invalid role");

  try {
    await setMemberRole({
      tenantId: ctx.tenantId,
      targetProfileId: body.profile_id,
      newRole,
      actor: ctx,
    });
    // Audit-log the role change (Phase D).
    try {
      const authed = await getAuthedSupabase();
      await authed.rpc("log_tenant_event", {
        p_tenant_id: ctx.tenantId,
        p_action_type: "member.role_change",
        p_target_table: "user_profiles",
        p_target_id: body.profile_id,
        p_after: { team_role: newRole },
      });
    } catch {
      // audit-log soft-fail
    }
    return NextResponse.json({ ok: true });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "update_failed";
    const status =
      msg === "forbidden"
        ? 403
        : msg === "cannot_demote_owner" || msg === "ownership_transfer_not_supported"
          ? 409
          : msg === "member_not_found"
            ? 404
            : 500;
    return bad(status, msg);
  }
}

export async function DELETE(req: NextRequest) {
  const ctx = await getSessionContext();
  if (!ctx) return bad(401, "unauthorized");
  if (!canManageTeam(ctx.teamRole)) return bad(403, "forbidden");
  const url = new URL(req.url);
  const profileId = url.searchParams.get("profile_id");
  if (!profileId) return bad(400, "missing profile_id");
  try {
    await removeMember({
      tenantId: ctx.tenantId,
      targetProfileId: profileId,
      actor: ctx,
    });
    // Audit-log the removal (Phase D).
    try {
      const authed = await getAuthedSupabase();
      await authed.rpc("log_tenant_event", {
        p_tenant_id: ctx.tenantId,
        p_action_type: "member.remove",
        p_target_table: "user_profiles",
        p_target_id: profileId,
      });
    } catch {
      // audit-log soft-fail
    }
    return NextResponse.json({ ok: true });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "remove_failed";
    const status =
      msg === "forbidden" ? 403 : msg === "cannot_remove_owner" ? 409 : msg === "member_not_found" ? 404 : 500;
    return bad(status, msg);
  }
}
