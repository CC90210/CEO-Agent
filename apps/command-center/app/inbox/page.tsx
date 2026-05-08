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
        subtitle="Where your agents hand off work to each other."
      />

      <Card title="What this is">
        <div className="space-y-4 text-sm text-fg-muted leading-relaxed">
          <p>
            Your agents work on different parts of the business — Bravo runs
            ops and architecture, Atlas handles cashflow and tax, Maven
            ships content and ads, Aura runs your home and habits, Lumen
            keeps voice and presence of loved ones, Codex executes backend
            code. They don&apos;t share a brain. The inbox is how they leave
            each other notes so they can work in parallel without you
            relaying every message.
          </p>
          <p>
            <span className="text-fg font-medium">Why it matters:</span>{" "}
            without it, every cross-agent handoff has to go through you.
            With it, Bravo can finish a sales draft and ping Atlas for a
            tax review, then keep moving. You don&apos;t notice the message
            unless you want to.
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
              The recipient agent reads its inbox at the start of every
              session — Bravo runs <span className="font-mono">scripts/agent_inbox.py list --to bravo</span> on
              boot. Your message lands at the top of its context for that
              session, before it answers anything else.
            </li>
            <li>
              When the agent processes the message it can either reply
              (post back to your inbox addressed to <span className="font-mono">cc</span>) or
              archive it. Either way the file moves to <span className="font-mono">tmp/agent_inbox/read/</span> and
              the row gets <span className="font-mono">read_at</span> stamped in Supabase.
            </li>
          </ol>
          <p className="text-fg-dim">
            <span className="text-fg font-medium">Not real-time.</span> A message
            you post here doesn&apos;t interrupt anything — it waits until the
            next time that agent runs. Use it for non-urgent handoffs and
            background tasks. For something you need <em>now</em>, just chat
            the agent directly.
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
        <Card
          title="Post a message"
          subtitle="You usually don't post here — agents do. Use this to leave a specific agent a note for the next time it runs."
        >
          <AgentInboxComposer />
        </Card>
      )}
    </div>
  );
}
