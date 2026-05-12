import { createHash, randomBytes } from "node:crypto";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";

export type TeamRole =
  | "owner"
  | "admin"
  | "loan_officer"
  | "processor"
  | "read_only"
  | "member";

export const INVITABLE_ROLES: Exclude<TeamRole, "owner">[] = [
  "admin",
  "loan_officer",
  "processor",
  "read_only",
  "member",
];

export type MemberRow = {
  id: string;
  auth_user_id: string | null;
  email: string;
  full_name: string;
  display_name: string | null;
  team_role: TeamRole;
  is_owner: boolean;
  invited_by: string | null;
  joined_at: string;
};

export type InviteRow = {
  id: string;
  tenant_id: string;
  email: string | null;
  team_role: Exclude<TeamRole, "owner">;
  created_by: string;
  expires_at: string;
  redeemed_at: string | null;
  redeemed_by: string | null;
  revoked_at: string | null;
  created_at: string;
};

export type SessionContext = {
  authUserId: string;
  profileId: string;
  tenantId: string;
  teamRole: TeamRole;
  isOwner: boolean;
};

export function canManageTeam(role: TeamRole): boolean {
  return role === "owner" || role === "admin";
}

export function hashInviteToken(rawToken: string): string {
  return createHash("sha256").update(rawToken).digest("hex");
}

export function generateInviteToken(): { raw: string; hash: string } {
  const raw = randomBytes(32).toString("base64url");
  return { raw, hash: hashInviteToken(raw) };
}

export async function getSessionContext(): Promise<SessionContext | null> {
  const user = await getSessionUser();
  if (!user) return null;
  const supa = getServiceSupabase();
  const { data, error } = await supa
    .from("user_profiles")
    .select("id, tenant_id, team_role, is_owner")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  if (error || !data || !data.tenant_id) return null;
  return {
    authUserId: user.id,
    profileId: data.id,
    tenantId: data.tenant_id,
    teamRole: (data.team_role as TeamRole) ?? "member",
    isOwner: !!data.is_owner,
  };
}

export async function getTenantMembers(tenantId: string): Promise<MemberRow[]> {
  const supa = getServiceSupabase();
  const { data, error } = await supa
    .from("user_profiles")
    .select(
      "id, auth_user_id, email, full_name, display_name, team_role, is_owner, invited_by, joined_at"
    )
    .eq("tenant_id", tenantId)
    .order("is_owner", { ascending: false })
    .order("joined_at", { ascending: true });
  if (error) throw error;
  return (data ?? []) as MemberRow[];
}

export async function listActiveInvites(tenantId: string): Promise<InviteRow[]> {
  const supa = getServiceSupabase();
  const { data, error } = await supa
    .from("tenant_invites")
    .select(
      "id, tenant_id, email, team_role, created_by, expires_at, redeemed_at, redeemed_by, revoked_at, created_at"
    )
    .eq("tenant_id", tenantId)
    .is("redeemed_at", null)
    .is("revoked_at", null)
    .gt("expires_at", new Date().toISOString())
    .order("created_at", { ascending: false });
  if (error) throw error;
  return (data ?? []) as InviteRow[];
}

export async function createInvite(args: {
  tenantId: string;
  role: Exclude<TeamRole, "owner">;
  createdBy: string;
  email?: string | null;
}): Promise<{ id: string; rawToken: string; expiresAt: string }> {
  const supa = getServiceSupabase();
  const { raw, hash } = generateInviteToken();
  const { data, error } = await supa
    .from("tenant_invites")
    .insert({
      tenant_id: args.tenantId,
      email: args.email ?? null,
      team_role: args.role,
      token_hash: hash,
      created_by: args.createdBy,
    })
    .select("id, expires_at")
    .single();
  if (error || !data) throw error ?? new Error("invite_create_failed");
  return { id: data.id, rawToken: raw, expiresAt: data.expires_at as string };
}

export async function revokeInvite(inviteId: string, tenantId: string): Promise<void> {
  const supa = getServiceSupabase();
  const { error } = await supa
    .from("tenant_invites")
    .update({ revoked_at: new Date().toISOString() })
    .eq("id", inviteId)
    .eq("tenant_id", tenantId);
  if (error) throw error;
}

export async function redeemInvite(
  rawToken: string,
  redeemerAuthId: string
): Promise<{ ok: true; tenantId: string; teamRole: TeamRole } | { ok: false; error: string }> {
  const supa = getServiceSupabase();
  const hash = hashInviteToken(rawToken);
  const { data, error } = await supa.rpc("redeem_tenant_invite", {
    p_token_hash: hash,
    p_redeemer_auth_id: redeemerAuthId,
  });
  if (error) return { ok: false, error: error.message };
  if (!data?.ok) return { ok: false, error: data?.error ?? "invalid_or_expired" };
  return { ok: true, tenantId: data.tenant_id, teamRole: data.team_role as TeamRole };
}

export async function setMemberRole(args: {
  tenantId: string;
  targetProfileId: string;
  newRole: TeamRole;
  actor: SessionContext;
}): Promise<void> {
  if (!canManageTeam(args.actor.teamRole)) {
    throw new Error("forbidden");
  }
  if (args.newRole === "owner") {
    throw new Error("ownership_transfer_not_supported");
  }
  const supa = getServiceSupabase();
  const { data: target, error: tErr } = await supa
    .from("user_profiles")
    .select("id, is_owner, tenant_id")
    .eq("id", args.targetProfileId)
    .single();
  if (tErr || !target) throw new Error("member_not_found");
  if (target.tenant_id !== args.tenantId) throw new Error("forbidden");
  if (target.is_owner) throw new Error("cannot_demote_owner");

  const { error } = await supa
    .from("user_profiles")
    .update({ team_role: args.newRole })
    .eq("id", args.targetProfileId);
  if (error) throw error;
}

export async function removeMember(args: {
  tenantId: string;
  targetProfileId: string;
  actor: SessionContext;
}): Promise<void> {
  if (!canManageTeam(args.actor.teamRole)) {
    throw new Error("forbidden");
  }
  const supa = getServiceSupabase();
  const { data: target, error: tErr } = await supa
    .from("user_profiles")
    .select("id, is_owner, tenant_id, auth_user_id")
    .eq("id", args.targetProfileId)
    .single();
  if (tErr || !target) throw new Error("member_not_found");
  if (target.tenant_id !== args.tenantId) throw new Error("forbidden");
  if (target.is_owner) throw new Error("cannot_remove_owner");

  const { error } = await supa
    .from("user_profiles")
    .update({ tenant_id: null, team_role: "member" })
    .eq("id", args.targetProfileId);
  if (error) throw error;
}
