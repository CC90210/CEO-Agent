/**
 * /automations — operator-facing cron job manager (Phase I).
 *
 * Server-component shell renders the page chrome. The editor + list are
 * client components that talk to /api/cron-jobs. Jobs created here are
 * picked up by the operator's bridge daemon on its next poll (~60s).
 */

import { PageHeader } from "@/components/Card";
import { CronJobsManager } from "@/components/automations/CronJobsManager";
import { getActiveProfile, getBridgeOnline } from "@/lib/queries";
import { chatAgentKeys } from "@/lib/agent-personas";
import { safe } from "@/lib/api-helpers";
import { Clock, Cpu, Cloud } from "lucide-react";

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
              <span className="text-fg-muted font-bold">Bridge offline.</span>{" "}
              Jobs created here are saved but won&apos;t fire until your local
              bridge is back up. Run{" "}
              <code className="font-mono text-accent bg-bg-elev px-1 rounded">
                pm2 restart claude-bridge
              </code>{" "}
              on your machine to start the poller.
            </>
          )}
        </div>
        <Clock className="w-4 h-4 text-fg-dim shrink-0 mt-0.5 hidden sm:block" />
      </div>

      {profile ? (
        <CronJobsManager
          agentKeys={chatAgentKeys().filter((k) =>
            (profile.agents_enabled || chatAgentKeys()).includes(k),
          )}
        />
      ) : (
        <div className="rounded-xl border border-bg-border bg-bg-elev/40 p-8 text-center text-fg-muted">
          Sign in to manage your automations.
        </div>
      )}
    </div>
  );
}
