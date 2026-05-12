import { NextResponse, type NextRequest } from "next/server";
import { bad } from "@/lib/api-helpers";
import {
  INVITABLE_ROLES,
  canManageTeam,
  createInvite,
  getSessionContext,
  listActiveInvites,
  type TeamRole,
} from "@/lib/team";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const ctx = await getSessionContext();
  if (!ctx) return bad(401, "unauthorized");
  if (!canManageTeam(ctx.teamRole)) return bad(403, "forbidden");
  const invites = await listActiveInvites(ctx.tenantId);
  return NextResponse.json({
    ok: true,
    invites: invites.map((i) => ({
      id: i.id,
      email: i.email,
      team_role: i.team_role,
      expires_at: i.expires_at,
      created_at: i.created_at,
    })),
  });
}

export async function POST(req: NextRequest) {
  const ctx = await getSessionContext();
  if (!ctx) return bad(401, "unauthorized");
  if (!canManageTeam(ctx.teamRole)) return bad(403, "forbidden");

  let body: { role?: string; email?: string | null };
  try {
    body = await req.json();
  } catch {
    return bad(400, "invalid JSON");
  }

  const role = (body.role ?? "member") as TeamRole;
  if (!INVITABLE_ROLES.includes(role as Exclude<TeamRole, "owner">)) {
    return bad(400, "invalid role");
  }
  const email = body.email?.trim() || null;

  try {
    const invite = await createInvite({
      tenantId: ctx.tenantId,
      role: role as Exclude<TeamRole, "owner">,
      createdBy: ctx.authUserId,
      email,
    });
    return NextResponse.json({
      ok: true,
      invite: {
        id: invite.id,
        raw_token: invite.rawToken,
        expires_at: invite.expiresAt,
      },
      message: "Copy this token now. It will not be shown again.",
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "invite_create_failed";
    return bad(500, msg);
  }
}
