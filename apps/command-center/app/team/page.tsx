import { Card, PageHeader, EmptyState } from "@/components/Card";
import { UsersRound } from "lucide-react";
import {
  canManageTeam,
  getSessionContext,
  getTenantMembers,
  listActiveInvites,
} from "@/lib/team";
import { TeamInviteActions, RemoveMemberClientButton } from "./TeamInviteActions";
import { redirect } from "next/navigation";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ROLE_LABEL: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  loan_officer: "Loan officer",
  processor: "Processor",
  read_only: "Read only",
  member: "Member",
};

export default async function TeamPage() {
  const ctx = await getSessionContext();
  if (!ctx) redirect("/login?next=%2Fteam");

  const [members, invites] = await Promise.all([
    getTenantMembers(ctx.tenantId),
    canManageTeam(ctx.teamRole) ? listActiveInvites(ctx.tenantId) : Promise.resolve([]),
  ]);
  const canManage = canManageTeam(ctx.teamRole);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Team"
        subtitle={canManage ? "Invite, manage, and remove team members." : "Members on this tenant."}
      />

      {canManage && (
        <Card title="Invite a teammate" subtitle="Generate a one-time invite link.">
          <TeamInviteActions activeInvites={invites.map((i) => ({
            id: i.id,
            email: i.email,
            team_role: i.team_role,
            expires_at: i.expires_at,
          }))} />
        </Card>
      )}

      <Card
        title="Members"
        subtitle={`${members.length} on the team`}
      >
        {members.length === 0 ? (
          <EmptyState message="The team is empty." />
        ) : (
          <ul className="divide-y divide-bg-border">
            {members.map((m) => (
              <li
                key={m.id}
                className="grid grid-cols-[1fr_8rem_5rem] gap-4 py-3 items-center"
              >
                <div>
                  <div className="font-semibold text-fg flex items-center gap-2">
                    {m.display_name || m.full_name || m.email}
                    {m.is_owner && (
                      <span className="text-[10px] uppercase tracking-wider text-accent font-mono">
                        owner
                      </span>
                    )}
                    {m.id === ctx.profileId && (
                      <span className="text-[10px] uppercase tracking-wider text-fg-dim font-mono">
                        you
                      </span>
                    )}
                  </div>
                  {canManage && m.email && (
                    <div className="text-xs text-fg-muted font-mono mt-0.5">{m.email}</div>
                  )}
                </div>
                <div className="text-sm text-fg-muted">
                  {ROLE_LABEL[m.team_role] ?? m.team_role}
                </div>
                <div className="text-xs text-fg-dim text-right">
                  {canManage && !m.is_owner && m.id !== ctx.profileId ? (
                    <RemoveMemberClientButton profileId={m.id} />
                  ) : (
                    ""
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {!canManage && (
        <Card title="Want to invite teammates?" subtitle="Ask an admin or the tenant owner.">
          <p className="text-sm text-fg-muted">
            Only owners and admins can generate invite links. Talk to your owner if you
            need to expand the team.
          </p>
        </Card>
      )}

      <div className="text-xs text-fg-dim flex items-center gap-2">
        <UsersRound className="w-4 h-4" />
        <span>
          Invites are single-use, hashed at rest, and expire after 7 days.
        </span>
      </div>
    </div>
  );
}

