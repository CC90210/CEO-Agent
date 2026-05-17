/**
 * /automations — operator-facing cron job manager (Phase I).
 *
 * Server-component shell renders the page chrome. The editor + list are
 * client components that talk to /api/cron-jobs. Jobs created here are
 * picked up by the operator's bridge daemon on its next poll (~60s).
 */

import { PageHeader } from "@/components/Card";
import { CronJobsManager } from "@/components/automations/CronJobsManager";
import { BackgroundWorkersPanel } from "@/components/automations/BackgroundWorkersPanel";
import { DescribeAutomationFlow } from "@/components/automations/DescribeAutomationFlow";
import { getActiveProfile, getBridgeOnline } from "@/lib/queries";
import { chatAgentKeys } from "@/lib/agent-personas";
import { safe } from "@/lib/api-helpers";
import { Clock, Cpu, Cloud, Download } from "lucide-react";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function AutomationsPage() {
  const profile = await safe("automations.profile", getActiveProfile(), null);
  const bridgeOnline = await safe(
    "automations.bridge_online",
    getBridgeOnline(profile?.tenant_id || null),
    false,
  );

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Automations"
        subtitle="Scheduled jobs your agents run for you — daily briefs, follow-up reminders, lead scoring, anything you describe in plain English."
      />

      <div className="rounded-xl border border-bg-border bg-bg-deep/40 p-4 flex items-start gap-3">
        {bridgeOnline ? (
          <Cpu className="w-5 h-5 text-status-engaged shrink-0 mt-0.5" />
        ) : (
          <Cloud className="w-5 h-5 text-fg-dim shrink-0 mt-0.5" />
        )}
        <div className="flex-1 text-xs leading-relaxed">
          {bridgeOnline ? (
            <>
              <span className="text-status-engaged font-bold">Your computer is connected.</span>{" "}
              Jobs run on the schedule below. Edits take effect within a minute. Switch any job off
              and it stops firing — the spec stays saved so you can flip it back on later.
            </>
          ) : (
            <>
              <span className="text-fg-muted font-bold">Computer not connected yet.</span>{" "}
              Jobs you create here are saved, but they won&apos;t start running until you pair a
              machine. Click <span className="text-fg font-medium">Install bridge</span> —
              it takes about a minute, one command to copy-paste, and you&apos;re live.
            </>
          )}
        </div>
        {!bridgeOnline && (
          <Link
            href="/settings/devices/install"
            className="btn-primary inline-flex items-center gap-1.5 text-xs shrink-0"
          >
            <Download className="w-3 h-3" />
            Install bridge
          </Link>
        )}
        <Clock className="w-4 h-4 text-fg-dim shrink-0 mt-0.5 hidden sm:block" />
      </div>

      {/* Phase 9.5 — "How automations work" expander. CC asked: where do
          these run, who pays for them, where does the output go. Short
          answer in plain English, behind a one-click open so it doesn't
          clutter the daily-use view. */}
      <details className="rounded-xl border border-bg-border bg-bg-elev/30 p-4 text-sm">
        <summary className="cursor-pointer select-none flex items-center gap-2 text-fg font-bold">
          <span className="inline-block">▸</span>
          How automations work, in plain English
        </summary>
        <div className="mt-3 space-y-3 text-fg-muted leading-relaxed">
          <p>
            <span className="text-fg font-bold">Where they run.</span> Each automation runs
            on YOUR computer, not the cloud. Your machine wakes up every minute, checks the
            schedule, and runs anything that&apos;s due — quietly in the background, no windows
            pop up, nothing leaves your laptop unless the job itself sends a message somewhere.
          </p>
          <p>
            <span className="text-fg font-bold">What it costs.</span> Most jobs are free
            (pulling data, taking snapshots, syncing Stripe). The ones that cost something are
            the AI-powered ones — a daily summary written by Claude costs roughly 25¢; scoring
            a single lead costs about a penny. If a job sends emails or texts, that uses your
            Gmail or Twilio account directly. We don&apos;t add any markup.
          </p>
          <p>
            <span className="text-fg font-bold">Where the output ends up.</span> Three places,
            depending on the job:
          </p>
          <ul className="ml-5 space-y-1.5 list-disc">
            <li>
              <span className="text-fg font-medium">Telegram</span> — for things you want a
              ping about: daily briefs, follow-up reminders, alerts when something needs your
              attention.
            </li>
            <li>
              <span className="text-fg font-medium">Files on your machine</span> — snapshot
              jobs save pre-computed data your agents read later (so the dashboard stays fast).
              No notification, just quietly available.
            </li>
            <li>
              <span className="text-fg font-medium">The dashboard itself</span> — scoring +
              sync jobs write back to your pipeline so Today / Pipeline / Health stay current.
            </li>
          </ul>
          <p>
            <span className="text-fg font-bold">Switching jobs on and off.</span> Each row
            has a toggle. Flip it off and the job stops firing within a minute — the spec
            stays saved so you can switch it back on later. No restart needed.
          </p>
          <p>
            <span className="text-fg font-bold">Making your own.</span> Type what you want
            in the &quot;Describe an automation&quot; box below — &quot;Every Monday at 9am,
            text me a summary of last week&apos;s funded deals,&quot; that kind of thing.
            Bravo writes the script, shows you what it does, and saves it switched-off so
            nothing fires until you&apos;ve read it.
          </p>
          <p>
            <span className="text-fg font-bold">Empire vs tenant.</span>{" "}
            Empire jobs (locked badge) come from <code className="font-mono text-fg-dim">scripts/cron_engine.py
            SEED_JOBS</code> and only the on/off toggle is operator-controlled —
            schedule + action stay locked to the code. Tenant jobs are
            anything you create via &quot;+ New automation&quot; — fully
            editable.
          </p>
        </div>
      </details>

      {profile ? (
        <>
          <DescribeAutomationFlow />
          <CronJobsManager
            agentKeys={chatAgentKeys().filter((k) =>
              (profile.agents_enabled || chatAgentKeys()).includes(k),
            )}
          />
          <div className="border-t border-bg-border pt-6">
            <BackgroundWorkersPanel />
          </div>
        </>
      ) : (
        <div className="rounded-xl border border-bg-border bg-bg-elev/40 p-8 text-center text-fg-muted">
          Sign in to manage your automations.
        </div>
      )}
    </div>
  );
}
