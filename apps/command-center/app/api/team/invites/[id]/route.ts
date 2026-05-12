import { NextResponse } from "next/server";
import { bad } from "@/lib/api-helpers";
import { canManageTeam, getSessionContext, revokeInvite } from "@/lib/team";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function DELETE(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const session = await getSessionContext();
  if (!session) return bad(401, "unauthorized");
  if (!canManageTeam(session.teamRole)) return bad(403, "forbidden");
  const { id } = await ctx.params;
  if (!id) return bad(400, "missing id");
  try {
    await revokeInvite(id, session.tenantId);
    return NextResponse.json({ ok: true });
  } catch (err) {
    return bad(500, err instanceof Error ? err.message : "revoke_failed");
  }
}
