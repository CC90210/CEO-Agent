/**
 * /overrides — V6 Apex Phase 2 dashboard-driven override approvals.
 *
 * Server component reads exec_overrides via the service-role client. Each
 * pending row gets Approve / Deny buttons that submit a Server Action.
 * The action validates the session (must be a signed-in dashboard user),
 * resolves the operator profile, and calls record_exec_override_decision_v1
 * with OASIS_OUTBOUND_HMAC_SECRET hashed server-side. The local
 * exec_override_consumer daemon picks up the decision and applies it to
 * SQLite via state_manager.approve_override_request / deny_override_request.
 *
 * ─── HMAC secrets used in this flow (two of them, deliberately) ─────────
 * OASIS_OUTBOUND_HMAC_SECRET (this file, line 90):
 *   Cloud-side. Set as Vercel env var + matched in Supabase
 *   n8n_webhook_secrets. Authenticates THIS server action's call to
 *   record_exec_override_decision_v1. The hash is what the RPC compares.
 *
 * EMPIRE_OVERRIDE_HMAC_KEY (scripts/lib/override_crypto.py):
 *   Local-only. Never set on Vercel. Signs the at-rest approval row in
 *   state/empire_state.db (SQLite) on CC's machine so the local
 *   exec_guard can verify "yes, this approval is real" before letting a
 *   blocked command through.
 *
 * Two layers, two secrets — compromise of one does not yield the other.
 * If you find yourself unifying them, STOP and read override_crypto.py.
 * ────────────────────────────────────────────────────────────────────────
 */

import { revalidatePath } from "next/cache";
import { headers } from "next/headers";
import { createHash } from "crypto";
import { ShieldAlert, Activity } from "lucide-react";
import { Card, PageHeader, Tag } from "@/components/Card";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";
import { OverrideDecisionForms } from "./OverrideDecisionForms";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type Row = {
  request_id: string;
  ts: string;
  expires_at: string;
  command: string;
  command_hash: string;
  layer: string;
  reason: string | null;
  status: string;
  approved_at: string | null;
  approved_by: string | null;
  consumed_at: string | null;
  dashboard_decision: "approve" | "deny" | null;
  dashboard_decided_at: string | null;
  dashboard_decided_by: string | null;
  dashboard_reason: string | null;
  consumer_synced_at: string | null;
  updated_at: string;
};

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  const diff = Date.now() - t;
  if (diff < 60_000)        return `${Math.round(diff / 1000)}s ago`;
  if (diff < 3_600_000)     return `${Math.round(diff / 60_000)}m ago`;
  if (diff < 86_400_000)    return `${Math.round(diff / 3_600_000)}h ago`;
  return `${Math.round(diff / 86_400_000)}d ago`;
}

function statusBadge(row: Row): React.ReactNode {
  // Dashboard intent OVERRIDES local status for the badge — if the operator
  // clicked approve and the consumer hasn't synced yet, show "approving…"
  // so it's obvious the local SQLite hasn't caught up.
  if (row.dashboard_decision && !row.consumer_synced_at) {
    return <Tag tone={row.dashboard_decision === "approve" ? "accent" : "hot"}>
      {row.dashboard_decision === "approve" ? "approving…" : "denying…"}
    </Tag>;
  }
  const tone =
    row.status === "approved" || row.status === "consumed" ? "engaged" :
    row.status === "denied"   || row.status === "expired"  ? "neutral" :
    "warm";
  return <Tag tone={tone}>{row.status}</Tag>;
}

async function decisionAction(formData: FormData): Promise<void> {
  "use server";

  const user = await getSessionUser();
  if (!user) {
    throw new Error("not authenticated");
  }

  const requestId = String(formData.get("request_id") || "");
  const decision = String(formData.get("decision") || "");
  const reason = String(formData.get("reason") || "").slice(0, 500);

  if (!/^req-[0-9a-f]{8}$/i.test(requestId)) {
    throw new Error("invalid request_id");
  }
  if (decision !== "approve" && decision !== "deny") {
    throw new Error("decision must be approve or deny");
  }

  const profileId = (process.env.OASIS_PROFILE_ID || "").trim();
  const secret = (process.env.OASIS_OUTBOUND_HMAC_SECRET || "").trim();
  if (!profileId || !secret) {
    throw new Error(
      "OASIS_PROFILE_ID + OASIS_OUTBOUND_HMAC_SECRET not configured on the dashboard",
    );
  }

  const db = getServiceSupabase();
  const r = await db.rpc("record_exec_override_decision_v1", {
    p_profile_id: profileId,
    p_secret_hash: createHash("sha256").update(secret, "utf8").digest("hex"),
    p_request_id: requestId,
    p_decision: decision,
    p_reason: reason || null,
  });
  if (r.error) {
    throw new Error(r.error.message || "decision rpc failed");
  }

  revalidatePath("/overrides");
}

async function fetchRows(): Promise<{ rows: Row[]; error?: string }> {
  try {
    const db = getServiceSupabase();
    const cutoff = new Date(Date.now() - 48 * 3600 * 1000).toISOString();
    const r = await db
      .from("exec_overrides")
      .select(
        "request_id, ts, expires_at, command, command_hash, layer, reason, " +
          "status, approved_at, approved_by, consumed_at, dashboard_decision, " +
          "dashboard_decided_at, dashboard_decided_by, dashboard_reason, " +
          "consumer_synced_at, updated_at",
      )
      .gte("ts", cutoff)
      .order("ts", { ascending: false })
      .limit(100);
    if (r.error) {
      return { rows: [], error: r.error.message };
    }
    return { rows: ((r.data || []) as unknown) as Row[] };
  } catch (err) {
    return { rows: [], error: err instanceof Error ? err.message : "fetch failed" };
  }
}

export default async function OverridesPage() {
  // Force-evaluate the headers so Next streams this as a dynamic route — same
  // pattern as system-health/page.tsx. Without this, prerender tries to bake
  // the page at build-time and the Supabase call falls back to anon.
  await headers();
  const { rows, error } = await fetchRows();

  const pending = rows.filter((r) => r.status === "pending" && !r.dashboard_decision);
  const inFlight = rows.filter((r) => r.dashboard_decision && !r.consumer_synced_at);
  const recent = rows.filter(
    (r) => r.consumer_synced_at || r.status !== "pending" || r.dashboard_decision,
  );

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Override Approvals"
        subtitle="V6 exec_guard blocks land here. Approve releases the agent's next retry of the EXACT same command (single-use, command-hash-bound)."
        action={<Tag tone={pending.length > 0 ? "hot" : "engaged"}>
          {pending.length} pending
        </Tag>}
      />

      {error && (
        <Card>
          <div className="flex items-start gap-3 p-2">
            <ShieldAlert size={20} className="text-status-hot shrink-0 mt-0.5" />
            <div>
              <div className="font-bold text-fg">Could not load override mirror</div>
              <p className="text-sm text-fg-muted mt-1">{error}</p>
            </div>
          </div>
        </Card>
      )}

      {pending.length === 0 && inFlight.length === 0 && !error && (
        <Card>
          <div className="text-sm text-fg-muted p-2">
            No pending override requests. exec_guard hasn't blocked anything that
            needs your sign-off in the last 48h.
          </div>
        </Card>
      )}

      {pending.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <ShieldAlert size={16} className="text-status-hot" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-fg-muted">
              Awaiting your decision ({pending.length})
            </h2>
          </div>
          <div className="space-y-3">
            {pending.map((row) => (
              <OverrideRow key={row.request_id} row={row} interactive />
            ))}
          </div>
        </section>
      )}

      {inFlight.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Activity size={16} className="text-accent" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-fg-muted">
              In flight — waiting for local consumer
            </h2>
          </div>
          <div className="space-y-3">
            {inFlight.map((row) => (
              <OverrideRow key={row.request_id} row={row} interactive={false} />
            ))}
          </div>
        </section>
      )}

      <section>
        <div className="flex items-center gap-2 mb-3">
          <h2 className="text-sm font-bold uppercase tracking-wider text-fg-muted">
            Recent activity (last 48h)
          </h2>
        </div>
        <div className="space-y-2">
          {recent.length === 0 && (
            <div className="text-xs text-fg-faint">No decisions logged in this window.</div>
          )}
          {recent.slice(0, 30).map((row) => (
            <div key={row.request_id} className="flex items-center gap-3 text-xs text-fg-muted">
              <span className="font-mono text-fg w-28">{row.request_id}</span>
              {statusBadge(row)}
              <span className="text-fg-dim">{row.layer}</span>
              <span className="font-mono text-fg-faint truncate flex-1">
                {row.command.slice(0, 120)}
              </span>
              <span className="text-fg-faint">{relativeTime(row.updated_at)}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function OverrideRow({ row, interactive }: { row: Row; interactive: boolean }) {
  const expiresIn = Math.max(
    0,
    Math.round((new Date(row.expires_at).getTime() - Date.now()) / 1000),
  );
  return (
    <Card>
      <div className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-fg">{row.request_id}</span>
              {statusBadge(row)}
              <span className="text-xs text-fg-dim">{row.layer}</span>
              <span className="text-xs text-fg-faint ml-auto">
                TTL {expiresIn}s · created {relativeTime(row.ts)}
              </span>
            </div>
            {row.reason && (
              <div className="text-xs text-fg-muted mt-1">reason: {row.reason}</div>
            )}
          </div>
        </div>

        <code className="text-xs font-mono block p-3 bg-bg-elev rounded border border-bg-border whitespace-pre-wrap break-all text-accent">
          {row.command.slice(0, 1500)}
        </code>

        {interactive && (
          <OverrideDecisionForms requestId={row.request_id} action={decisionAction} />
        )}

        {!interactive && row.dashboard_decision && (
          <div className="text-xs text-fg-muted">
            Decided by dashboard {relativeTime(row.dashboard_decided_at)}
            {row.dashboard_reason ? ` — ${row.dashboard_reason}` : ""}
            {row.consumer_synced_at
              ? ` · synced to local SQLite ${relativeTime(row.consumer_synced_at)}`
              : " · waiting on local consumer poller"}
          </div>
        )}
      </div>
    </Card>
  );
}
