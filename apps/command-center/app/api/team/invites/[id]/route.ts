import { NextResponse } from "next/server";
import { bad } from "@/lib/api-helpers";
import { getAuthedSupabase } from "@/lib/supabase-server";
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
    // Audit-log the revoke (Phase D). Best-effort.
    try {
      const authed = await getAuthedSupabase();
      await authed.rpc("log_tenant_event", {
        p_tenant_id: session.tenantId,
        p_action_type: "invite.revoke",
        p_target_table: "tenant_invites",
        p_target_id: id,
      });
    } catch {
      // audit-log soft-fail
    }
    return NextResponse.json({ ok: true });
  } catch (err) {
    return bad(500, err instanceof Error ? err.message : "revoke_failed");
  }
}
