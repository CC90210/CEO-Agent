import { Card, PageHeader } from "@/components/Card";
import { AgentInboxList, AgentInboxComposer } from "@/components/AgentInboxList";
import { listUnread, listRead } from "@/lib/agent-inbox-fs";
import { listUnreadDb, listReadDb, dbToUiShape } from "@/lib/agent-inbox-db";
import { getActiveProfile } from "@/lib/queries";
import { safe } from "@/lib/api-helpers";
import { getSessionUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

function isOperatorEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  const e = email.trim().toLowerCase();
  const operator = (process.env.OPERATOR_EMAIL || "").trim().toLowerCase();
  if (operator && e === operator) return true;
  const admins = (process.env.ADMIN_EMAILS || "")
    .split(",")
    .map((x) => x.trim().toLowerCase())
    .filter(Boolean);
  return admins.includes(e);
}

export default async function InboxPage() {
  const user = await getSessionUser();
  const isAdmin = isOperatorEmail(user?.email);
  const profile = await safe(getActiveProfile(), null);
  const tenantId = profile?.tenant_id || "";

  // Pull from BOTH sources: Supabase (multi-machine, source of truth)
  // and filesystem (legacy, local-only). Merge by message_id so a row
  // that exists in both surfaces only once. Supabase wins on conflict
  // since it's the canonical store going forward.
  const [dbUnread, dbRead, fsUnread, fsRead] = await Promise.all([
    tenantId ? safe(listUnreadDb(tenantId), []) : Promise.resolve([]),
    tenantId ? safe(listReadDb(tenantId, undefined, 50), []) : Promise.resolve([]),
    safe(listUnread(), []),
    safe(listRead(50), []),
  ]);

  const dbUnreadShaped = dbUnread.map(dbToUiShape);
  const dbReadShaped = dbRead.map(dbToUiShape);
  const dbIds = new Set([...dbUnread, ...dbRead].map((m) => m.message_id));
  const unread = [
    ...dbUnreadShaped,
    ...fsUnread.filter((m) => !dbIds.has(m.message_id)),
  ];
  const read = [
    ...dbReadShaped,
    ...fsRead.filter((m) => !dbIds.has(m.message_id)),
  ].slice(0, 50);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Agent Inbox"
        subtitle="Async messages between Bravo, Atlas, Maven, Aura, Lumen, and Codex. Multi-machine via Supabase + tmp/agent_inbox/ legacy mirror."
      />
      <Card
        title="Messages"
        subtitle={
          unread.length > 0
            ? `${unread.length} unread · ${read.length} archived`
            : `${read.length} archived · no new messages`
        }
      >
        <AgentInboxList unread={unread} read={read} />
      </Card>
      {isAdmin && (
        <Card title="Post a message" subtitle="Sends to Supabase (visible across all your machines) AND to the local filesystem so legacy local agents see it too.">
          <AgentInboxComposer />
        </Card>
      )}
    </div>
  );
}
