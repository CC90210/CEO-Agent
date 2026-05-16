"use client";

/**
 * SequencesListClient — table of tenant drip sequences with toggle /
 * edit / delete + a "New sequence" button (Phase 4.4 of SunBiz CRM).
 *
 * Server component loads initialRows; this client handles create
 * (POST /api/sequences with a starter stub then redirect to editor)
 * and per-row toggle/delete.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Plus, Edit3, ToggleLeft, ToggleRight, Trash2, Loader2 } from "lucide-react";

type SequenceRow = {
  id: string;
  name: string;
  description: string | null;
  trigger_event: string;
  trigger_filter: Record<string, unknown>;
  steps: Array<{ channel: string; delay_minutes: number }>;
  enabled: boolean;
  one_per_lead: boolean;
};

/**
 * Today's date in YYYY-MM-DD, computed at click time so operators who
 * leave the page open overnight don't get yesterday's date in the name.
 */
function todayStamp(): string {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}

const STARTER_SEQUENCE_TEMPLATE = {
  trigger_event: "BRAVO_RECORD_STATUS_CHANGED",
  trigger_filter: {
    entity: "lead",
    field: "stage",
    to: "viewed_application",
  },
  steps: [
    {
      channel: "sms",
      delay_minutes: 5,
      body: "Hi {{lead.contact_name}} — saw you opened the application. Any questions I can answer?",
      from_label: "Solara",
    },
    {
      channel: "email",
      delay_minutes: 60 * 24,
      subject: "Quick question on your application",
      body: "Hi {{lead.contact_name}},\n\nNoticed you started the application earlier — wanted to check if anything was unclear or holding you up. Reply here and I'll get back to you fast.\n\n— Solara, SunBiz Funding",
    },
  ],
  enabled: true,
  one_per_lead: true,
};

export function SequencesListClient({ initialRows }: { initialRows: SequenceRow[] }) {
  const router = useRouter();
  const [rows, setRows] = useState(initialRows);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function createSequence() {
    setCreating(true);
    setError(null);
    try {
      const res = await fetch("/api/sequences", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          ...STARTER_SEQUENCE_TEMPLATE,
          name: `New drip — ${todayStamp()}`,
        }),
      });
      const data = (await res.json()) as { ok: boolean; sequence?: { id: string }; error?: string };
      if (!data.ok || !data.sequence) {
        setError(data.error || `http_${res.status}`);
        return;
      }
      router.push(`/sequences/${data.sequence.id}/edit`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "network_error");
    } finally {
      setCreating(false);
    }
  }

  async function toggle(id: string, enabled: boolean) {
    const next = !enabled;
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, enabled: next } : r)));
    const res = await fetch(`/api/sequences/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ enabled: next }),
    });
    if (!res.ok) {
      setRows((prev) => prev.map((r) => (r.id === id ? { ...r, enabled } : r)));
      return;
    }
    // Invalidate the RSC cache so a future navigation to /sequences picks
    // up the new enabled state instead of replaying the cached page that
    // still shows the old toggle position.
    router.refresh();
  }

  async function destroy(id: string, name: string) {
    if (!confirm(`Delete sequence "${name}"? In-flight enrollments will be cancelled too.`)) return;
    const res = await fetch(`/api/sequences/${id}`, { method: "DELETE" });
    if (!res.ok) {
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      setError(data.error || `delete failed (${res.status})`);
      return;
    }
    setRows((prev) => prev.filter((r) => r.id !== id));
    // Same RSC-cache invalidation rationale as toggle — without this,
    // navigating away and back resurrects the row from the cached page.
    router.refresh();
  }

  function summarize(row: SequenceRow): string {
    const filter = row.trigger_filter || {};
    const entity = (filter as { entity?: string }).entity || "?";
    const to = (filter as { to?: string }).to || "any";
    return `${entity} → ${to} · ${row.steps?.length || 0} step${
      row.steps?.length === 1 ? "" : "s"
    }`;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-xs text-fg-muted">
          {rows.length} sequence{rows.length === 1 ? "" : "s"}
        </div>
        <button
          type="button"
          onClick={createSequence}
          disabled={creating}
          className="inline-flex items-center gap-2 rounded-lg bg-accent text-bg-deep px-4 py-2 text-sm font-bold hover:bg-accent-bright disabled:opacity-50"
        >
          {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          New sequence
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-400">
          Couldn&apos;t create sequence: {error}
        </div>
      )}

      {rows.length === 0 ? (
        <div className="rounded-xl border border-bg-border bg-bg-elev/40 p-8 text-center text-fg-muted">
          <div className="text-sm">No drip sequences yet.</div>
          <div className="text-xs mt-1 text-fg-dim">
            Click <span className="text-fg">New sequence</span> to scaffold one (2-step
            viewed_application drip). Edit the steps and hit Save to put it live.
          </div>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-bg-border">
          <table className="w-full text-sm">
            <thead className="bg-bg-elev/50">
              <tr className="text-left text-[10px] uppercase tracking-wider text-fg-dim">
                <th className="px-4 py-2 font-bold">Name</th>
                <th className="px-4 py-2 font-bold">Trigger</th>
                <th className="px-4 py-2 font-bold">Status</th>
                <th className="px-4 py-2 font-bold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-bg-border">
              {rows.map((r) => (
                <tr key={r.id} className="hover:bg-bg-elev/30">
                  <td className="px-4 py-3">
                    <div className="font-bold text-fg">{r.name}</div>
                    {r.description && (
                      <div className="text-xs text-fg-muted truncate max-w-md">
                        {r.description}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-fg-muted">
                    {summarize(r)}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => toggle(r.id, r.enabled)}
                      className={`inline-flex items-center gap-1.5 text-xs ${
                        r.enabled ? "text-status-engaged" : "text-fg-dim"
                      }`}
                    >
                      {r.enabled ? (
                        <ToggleRight className="w-4 h-4" />
                      ) : (
                        <ToggleLeft className="w-4 h-4" />
                      )}
                      {r.enabled ? "Live" : "Paused"}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-2">
                      <Link
                        href={`/sequences/${r.id}/edit`}
                        className="inline-flex items-center gap-1 text-accent hover:text-accent-bright text-xs"
                      >
                        <Edit3 className="w-3 h-3" />
                        Edit
                      </Link>
                      <button
                        type="button"
                        onClick={() => destroy(r.id, r.name)}
                        className="inline-flex items-center gap-1 text-rose-400 hover:text-rose-300 text-xs"
                      >
                        <Trash2 className="w-3 h-3" />
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="rounded-xl border border-bg-border bg-bg-elev/30 p-4 text-xs text-fg-muted leading-relaxed">
        <div className="font-bold text-fg mb-1">How sequences fire</div>
        Each sequence has a trigger (e.g. lead.stage → viewed_application) and an
        ordered list of steps (SMS or email, with a delay before each). When the
        triggering event lands on Bravo&apos;s event bus, the bridge-side{" "}
        <code className="text-accent bg-bg-deep px-1 rounded">sequence-runner</code> PM2
        daemon enrolls the lead, fires the first step after its delay, and continues
        through the steps until done. Sends route through{" "}
        <code className="text-accent bg-bg-deep px-1 rounded">send_gateway</code> so CASL +
        cooldown + daily-cap enforcement is automatic.
      </div>
    </div>
  );
}
