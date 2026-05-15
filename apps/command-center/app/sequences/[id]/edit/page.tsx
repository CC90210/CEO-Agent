/**
 * /sequences/[id]/edit — operator sequence-builder page (Phase 4.4).
 */

import { PageHeader } from "@/components/Card";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { SequenceBuilderClient } from "@/components/sequences/SequenceBuilderClient";
import Link from "next/link";
import { redirect, notFound } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import {
  parseDripSteps,
  parseDripTriggerFilter,
  type DripStep,
  type DripTriggerFilter,
} from "@/lib/drips/types";

export const dynamic = "force-dynamic";

type SequenceDbRow = {
  id: string;
  tenant_id: string;
  name: string;
  description: string | null;
  trigger_event: string;
  trigger_filter: unknown;
  steps: unknown;
  enabled: boolean;
  one_per_lead: boolean;
};

async function loadSequence(id: string, userId: string): Promise<SequenceDbRow | null> {
  const db = getServiceSupabase();
  const profileRow = await db
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", userId)
    .maybeSingle();
  const tenantId = (profileRow.data as { tenant_id: string | null } | null)?.tenant_id;
  if (!tenantId) return null;
  const { data, error } = await db
    .from("drip_sequences")
    .select("*")
    .eq("id", id)
    .eq("tenant_id", tenantId)
    .maybeSingle();
  if (error || !data) return null;
  return data as SequenceDbRow;
}

export default async function EditSequencePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const user = await getSessionUser();
  if (!user) redirect("/login");
  const { id } = await params;
  const row = await loadSequence(id, user.id);
  if (!row) notFound();

  let steps: DripStep[];
  let triggerFilter: DripTriggerFilter;
  try {
    steps = parseDripSteps(row.steps);
    triggerFilter = parseDripTriggerFilter(row.trigger_filter);
  } catch (err) {
    return (
      <div className="space-y-6 animate-fade-in">
        <PageHeader
          title="Sequence definition corrupt"
          subtitle={`drip_sequences.id=${row.id} has malformed jsonb. Edit to fix.`}
        />
        <pre className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-xs font-mono text-rose-400 overflow-x-auto">
          {err instanceof Error ? err.message : String(err)}
        </pre>
        <Link href="/sequences" className="text-sm text-accent hover:text-accent-bright">
          ← Back to sequences
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <Link
        href="/sequences"
        className="inline-flex items-center gap-1.5 text-xs text-fg-muted hover:text-accent"
      >
        <ChevronLeft className="w-3 h-3" />
        Back to sequences
      </Link>
      <PageHeader
        title={row.name || "Untitled sequence"}
        subtitle={`${row.enabled ? "Live" : "Paused"} · ${row.one_per_lead ? "one enrollment per lead" : "re-enrollable"}`}
      />
      <SequenceBuilderClient
        initialSequence={{
          id: row.id,
          name: row.name,
          description: row.description,
          trigger_event: row.trigger_event,
          trigger_filter: triggerFilter,
          steps,
          enabled: row.enabled,
          one_per_lead: row.one_per_lead,
        }}
      />
    </div>
  );
}
