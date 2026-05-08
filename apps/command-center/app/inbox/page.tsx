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
        subtitle="Log of agent-to-agent handoffs. You probably don't need this page in day-to-day use."
      />

      <Card title="The honest answer to 'what is this?'">
        <div className="space-y-4 text-sm text-fg-muted leading-relaxed">
          <p>
            <span className="text-fg font-medium">You don&apos;t use the inbox page directly. The chat does.</span>{" "}
            When you chat any agent, their unread inbox messages get
            auto-injected into the conversation context — they see and
            handle the message before answering you. So this page is just
            a logbook of what&apos;s already flowing between your agents.
          </p>
          <p>
            <span className="text-fg font-medium">When the inbox actually matters:</span>{" "}
            agents post here when they finish a task and need a sibling to
            pick up. Bravo wraps a sales draft → posts to Atlas: &ldquo;tax
            review please.&rdquo; Atlas spots a cashflow issue → posts to Bravo:
            &ldquo;hold the new hire offer.&rdquo; You see the trail here; the
            recipient sees and acts on it the next time you chat them.
          </p>
          <p className="text-fg-dim">
            <span className="text-fg font-medium">When to look here directly:</span>{" "}
            (1) you want a record of agent-to-agent decisions, (2) you want
            to leave an agent a non-urgent note for next time it runs
            (admin composer below), (3) something feels off and you want
            to see what an agent saw.
          </p>
        </div>
      </Card>

      <Card title="The closed loop — what happens when you post">
        <div className="space-y-3 text-sm text-fg-muted leading-relaxed">
          <ol className="list-decimal pl-5 space-y-2">
            <li>
              You hit <span className="font-mono text-fg">Post message</span> →
              the message is written to Supabase (visible across all your
              machines) and to <span className="font-mono">tmp/agent_inbox/inbox/</span> on
              this machine.
            </li>
            <li>
              <span className="text-fg font-medium">Cloud-mode chat:</span> the next
              time you chat the recipient agent through the dashboard, your
              unread messages are auto-injected into its system prompt
              under <span className="font-mono">INBOX FOR YOU</span>. The agent
              addresses them BEFORE answering whatever else you asked.
              Once it responds, those messages are auto-marked read.
            </li>
            <li>
              <span className="text-fg font-medium">Local-bridge / CLI:</span> Bravo
              runs <span className="font-mono">scripts/agent_inbox.py list --to bravo</span> on
              session start (per CLAUDE.md). Same effect — messages come up
              before normal work, the agent processes and archives.
            </li>
            <li>
              Either way: agents that reply post back to your inbox
              addressed to <span className="font-mono">cc</span>; processed
              messages move to <span className="font-mono">tmp/agent_inbox/read/</span>
              and get <span className="font-mono">read_at</span> stamped in
              Supabase.
            </li>
          </ol>
          <p className="text-fg-dim">
            <span className="text-fg font-medium">Not real-time.</span> Posting
            here doesn&apos;t interrupt anything — it waits until the next
            chat or session start with that agent. Use it for non-urgent
            handoffs and background tasks. For something you need <em>now</em>,
            chat the agent directly.
          </p>
        </div>
      </Card>

      <Card title="What handoffs look like">
        <ul className="grid md:grid-cols-3 gap-4 text-sm">
          <li className="rounded-md border border-bd bg-bg-elev/40 p-4">
            <div className="text-xs uppercase tracking-wide text-fg-muted mb-2">
              Bravo → Atlas
            </div>
            <div className="text-fg">
              &ldquo;I just quoted a $5K retainer. Confirm tax treatment
              before we send.&rdquo;
            </div>
          </li>
          <li className="rounded-md border border-bd bg-bg-elev/40 p-4">
            <div className="text-xs uppercase tracking-wide text-fg-muted mb-2">
              Atlas → Bravo
            </div>
            <div className="text-fg">
              &ldquo;Cashflow tight this week — push the new hire offer to
              next month.&rdquo;
            </div>
          </li>
          <li className="rounded-md border border-bd bg-bg-elev/40 p-4">
            <div className="text-xs uppercase tracking-wide text-fg-muted mb-2">
              Codex → Bravo
            </div>
            <div className="text-fg">
              &ldquo;Migration 031 deployed. Verify pair-code redemption
              path before client onboarding.&rdquo;
            </div>
          </li>
        </ul>
      </Card>

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
        <details className="rounded-lg border border-bg-border bg-bg-elev/40">
          <summary className="cursor-pointer px-5 py-4 text-sm font-bold uppercase tracking-[0.14em] text-fg-muted hover:text-fg">
            Post a message (admin · expand)
          </summary>
          <div className="px-5 pb-5">
            <p className="text-xs text-fg-dim mb-3">
              You usually don&apos;t need this — chat the agent directly
              instead. Use this only for a non-urgent note that should
              wait until the next time that agent runs.
            </p>
            <AgentInboxComposer />
          </div>
        </details>
      )}
    </div>
  );
}
