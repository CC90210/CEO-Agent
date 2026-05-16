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
        subtitle="Cron-style scheduled jobs your agents run on your machine. Stored here, executed by your local bridge."
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
              <span className="text-status-engaged font-bold">Bridge online.</span>{" "}
              Your jobs run on your machine on the schedule below. The bridge
              polls this list every ~60 seconds — new jobs / edits take effect
              on the next poll cycle. Disabling a job stops it firing without
              losing the spec.
            </>
          ) : (
            <>
              <span className="text-fg-muted font-bold">Bridge not connected.</span>{" "}
              Jobs created here are saved but won&apos;t fire until you pair a
              machine. Click <span className="text-fg font-medium">Install
              bridge</span> to set this up in about a minute — one command,
              copy-paste, and you&apos;re live.
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
          How do these automations work? (cost, output, what runs where)
        </summary>
        <div className="mt-3 space-y-3 text-fg-muted leading-relaxed">
          <p>
            <span className="text-fg font-bold">Where they run.</span> Each
            automation is a Python script in <code className="font-mono text-fg-dim">scripts/</code>{" "}
            on YOUR machine. The local bridge daemon
            (<code className="font-mono text-fg-dim">bravo-scheduler</code> in PM2) polls
            this list every 60 seconds and fires due jobs as background
            subprocesses — no terminal windows pop up, nothing leaves your
            laptop unless the script itself makes an API call.
          </p>
          <p>
            <span className="text-fg font-bold">Cost model.</span> Most jobs
            are free (Supabase reads, Stripe webhook sync, file snapshots).
            The ones that cost money are the AI-narrated ones — Daily Bravo
            Brief and OASIS Auto-Score Leads both call Claude Sonnet (~$0.25/day
            for the brief, ~$0.01 per scored lead). Anything that hits Stripe
            or Twilio uses your accounts directly. Nothing is metered by us.
          </p>
          <p>
            <span className="text-fg font-bold">Where output goes.</span>{" "}
            Three destinations depending on the job:
          </p>
          <ul className="ml-5 space-y-1.5 list-disc">
            <li>
              <span className="text-fg font-medium">Telegram</span> — Daily
              Brief, Lead Follow-up alerts, daemon crash alerts. Goes to
              the chat IDs in your <code className="font-mono text-fg-dim">TELEGRAM_ALLOWED_USERS</code>{" "}
              env. If you&apos;re not seeing messages, that var isn&apos;t set
              or the chat ID doesn&apos;t include you.
            </li>
            <li>
              <span className="text-fg font-medium">Local files</span> —
              snapshot jobs write to <code className="font-mono text-fg-dim">state/snapshots/latest_*.json</code>{" "}
              for the agents to read later. These don&apos;t notify anyone;
              they&apos;re the &quot;Prep Table&quot; layer.
            </li>
            <li>
              <span className="text-fg font-medium">Supabase</span> — Stripe
              sync writes to <code className="font-mono text-fg-dim">revenue_events</code>;
              the auto-scorer updates <code className="font-mono text-fg-dim">tenant_records.data.ai_score</code>.
              You see these reflected on Today / Pipeline / Health.
            </li>
          </ul>
          <p>
            <span className="text-fg font-bold">Toggle behaviour.</span>{" "}
            Flipping the On / Off switch on any row updates{" "}
            <code className="font-mono text-fg-dim">cron_jobs.is_active</code>{" "}
            (empire) or <code className="font-mono text-fg-dim">tenant_cron_jobs.enabled</code>{" "}
            (tenant). The scheduler checks this on every 60-second poll —
            disabled jobs stay in the list but stop firing within one cycle.
            No restart needed.
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
