import { Card, PageHeader } from "@/components/Card";
import { AgentInboxList, AgentInboxComposer } from "@/components/AgentInboxList";
import { listUnread, listRead } from "@/lib/agent-inbox-fs";
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

  const [unread, read] = await Promise.all([
    safe(listUnread(), []),
    safe(listRead(50), []),
  ]);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Agent Inbox"
        subtitle="Async messages between Bravo, Atlas, Maven, Aura, and Codex. Backed by tmp/agent_inbox/."
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
        <Card title="Post a message" subtitle="Send to a sibling agent. Lands in their inbox dir if their repo is installed locally; otherwise stays in Bravo's inbox.">
          <AgentInboxComposer />
        </Card>
      )}
    </div>
  );
}
