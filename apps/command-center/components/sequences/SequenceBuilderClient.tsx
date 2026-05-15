"use client";

/**
 * SequenceBuilderClient — JSON-schema editor + token-reference helper
 * for /sequences/[id]/edit (Phase 4.4 of SunBiz CRM).
 *
 * Same pattern as FormBuilderClient: left pane is monospace JSON for
 * the steps array + trigger_filter object; right pane is a token
 * reference showing every {{path}} the steps body uses, with hints
 * about which paths actually resolve against the runtime context.
 * Live preview of an actual send isn't possible (we'd need a real
 * lead to render against) so we settle for the token-list view.
 */

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, Loader2, Save, Trash2 } from "lucide-react";
import {
  parseDripSteps,
  parseDripTriggerFilter,
  DripDefinitionError,
  type DripStep,
  type DripTriggerFilter,
} from "@/lib/drips/types";
import { extractTokens } from "@/lib/drips/templates";

type SequenceRecord = {
  id: string;
  name: string;
  description: string | null;
  trigger_event: string;
  trigger_filter: DripTriggerFilter;
  steps: DripStep[];
  enabled: boolean;
  one_per_lead: boolean;
};

type Props = {
  initialSequence: SequenceRecord;
};

export function SequenceBuilderClient({ initialSequence }: Props) {
  const router = useRouter();

  const [name, setName] = useState(initialSequence.name);
  const [description, setDescription] = useState(initialSequence.description || "");
  const [enabled, setEnabled] = useState(initialSequence.enabled);
  const [onePerLead, setOnePerLead] = useState(initialSequence.one_per_lead);
  const [triggerEvent, setTriggerEvent] = useState(initialSequence.trigger_event);
  const [stepsJson, setStepsJson] = useState(() =>
    JSON.stringify(initialSequence.steps, null, 2),
  );
  const [filterJson, setFilterJson] = useState(() =>
    JSON.stringify(initialSequence.trigger_filter, null, 2),
  );

  type ParseState = {
    steps: DripStep[] | null;
    filter: DripTriggerFilter | null;
    error: { path: string; reason: string } | null;
  };

  const parsed: ParseState = useMemo(() => {
    try {
      const steps = parseDripSteps(JSON.parse(stepsJson));
      const filter = parseDripTriggerFilter(JSON.parse(filterJson));
      return { steps, filter, error: null };
    } catch (err) {
      if (err instanceof DripDefinitionError) {
        return {
          steps: null,
          filter: null,
          error: { path: err.path, reason: err.reason },
        };
      }
      if (err instanceof SyntaxError) {
        return {
          steps: null,
          filter: null,
          error: { path: "$", reason: `invalid JSON: ${err.message}` },
        };
      }
      throw err;
    }
  }, [stepsJson, filterJson]);

  const referencedTokens = useMemo(() => {
    if (!parsed.steps) return [];
    const tokens = new Set<string>();
    for (const step of parsed.steps) {
      for (const t of extractTokens(step.body || "")) tokens.add(t);
      if (step.subject) {
        for (const t of extractTokens(step.subject)) tokens.add(t);
      }
    }
    return Array.from(tokens).sort();
  }, [parsed.steps]);

  // Hint resolution — common token roots the daemon will resolve:
  //   lead.*  → from tenant_records lead row's data jsonb
  //   event.* → from the triggering event's payload
  const tokenHint = (token: string): string => {
    if (token.startsWith("lead.")) {
      return "Resolves from the lead row in tenant_records.data.";
    }
    if (token.startsWith("event.")) {
      return "Resolves from the triggering event payload.";
    }
    return "Unknown root — will render as empty string unless added to context.";
  };

  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<
    null | { kind: "ok" | "err"; text: string }
  >(null);

  async function save() {
    if (parsed.error) {
      setSaveMessage({
        kind: "err",
        text: `Fix the definition first — ${parsed.error.path}: ${parsed.error.reason}`,
      });
      return;
    }
    setSaving(true);
    setSaveMessage(null);
    try {
      const res = await fetch(`/api/sequences/${initialSequence.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name,
          description: description || null,
          trigger_event: triggerEvent,
          trigger_filter: parsed.filter,
          steps: parsed.steps,
          enabled,
          one_per_lead: onePerLead,
        }),
      });
      const data = (await res.json()) as { ok: boolean; error?: string; path?: string; reason?: string };
      if (!data.ok) {
        setSaveMessage({
          kind: "err",
          text: data.path && data.reason
            ? `Save failed — ${data.path}: ${data.reason}`
            : `Save failed: ${data.error || `http_${res.status}`}`,
        });
        return;
      }
      setSaveMessage({ kind: "ok", text: "Saved." });
      router.refresh();
    } catch (err) {
      setSaveMessage({
        kind: "err",
        text: `Network error: ${err instanceof Error ? err.message : "unknown"}`,
      });
    } finally {
      setSaving(false);
    }
  }

  async function destroy() {
    if (
      !confirm(
        `Delete sequence "${name}"? In-flight enrollments will be cancelled too. This can't be undone.`,
      )
    )
      return;
    const res = await fetch(`/api/sequences/${initialSequence.id}`, { method: "DELETE" });
    if (res.ok) {
      router.push("/sequences");
    } else {
      const data = await res.json().catch(() => ({}));
      setSaveMessage({
        kind: "err",
        text: `Delete failed: ${data.error || `http_${res.status}`}`,
      });
    }
  }

  // In-flight state snapshot — fetched once on mount so the operator
  // can see how many leads are currently enrolled. Live updates would
  // require SSE which is overkill for a Phase 4 ship.
  type StateRow = {
    id: string;
    lead_id: string;
    step_index: number;
    scheduled_for: string;
    status: string;
    last_error: string | null;
  };
  const [stateRows, setStateRows] = useState<StateRow[] | null>(null);
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await fetch(`/api/sequences/${initialSequence.id}/state`);
        const data = (await res.json()) as { ok: boolean; rows?: StateRow[] };
        if (alive && data.ok) setStateRows(data.rows || []);
      } catch {
        // Best-effort; not fatal.
      }
    })();
    return () => {
      alive = false;
    };
  }, [initialSequence.id]);

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      {/* ── Left: editor ──────────────────────────────────────────── */}
      <div className="space-y-5">
        <section className="space-y-3 rounded-xl border border-bg-border bg-bg-elev/40 p-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-fg-muted">Basics</h3>
          <div>
            <label className="block text-[11px] uppercase tracking-wider font-bold text-fg-dim mb-1">
              Name
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-md border border-bg-border bg-bg-elev px-3 py-2 text-sm text-fg"
            />
          </div>
          <div>
            <label className="block text-[11px] uppercase tracking-wider font-bold text-fg-dim mb-1">
              Description
            </label>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full rounded-md border border-bg-border bg-bg-elev px-3 py-2 text-sm text-fg"
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-fg cursor-pointer">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              className="rounded accent-accent"
            />
            <span>Enabled (new enrollments only — in-flight rows continue)</span>
          </label>
          <label className="flex items-center gap-2 text-sm text-fg cursor-pointer">
            <input
              type="checkbox"
              checked={onePerLead}
              onChange={(e) => setOnePerLead(e.target.checked)}
              className="rounded accent-accent"
            />
            <span>One enrollment per lead (idempotent re-triggers)</span>
          </label>
        </section>

        <section className="space-y-3 rounded-xl border border-bg-border bg-bg-elev/40 p-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-fg-muted">Trigger</h3>
          <div>
            <label className="block text-[11px] uppercase tracking-wider font-bold text-fg-dim mb-1">
              Event type
            </label>
            <input
              value={triggerEvent}
              onChange={(e) => setTriggerEvent(e.target.value)}
              className="w-full rounded-md border border-bg-border bg-bg-elev px-3 py-2 text-sm font-mono text-fg"
              placeholder="BRAVO_RECORD_STATUS_CHANGED"
            />
          </div>
          <div>
            <label className="block text-[11px] uppercase tracking-wider font-bold text-fg-dim mb-1">
              Filter (JSON — shallow equality against payload)
            </label>
            <textarea
              value={filterJson}
              onChange={(e) => setFilterJson(e.target.value)}
              className="w-full rounded-md border border-bg-border bg-bg-deep px-3 py-2 font-mono text-[11px] text-fg min-h-[5rem]"
              spellCheck={false}
            />
            <p className="text-[11px] text-fg-dim mt-1 leading-relaxed">
              Common shapes:
              <br />
              <code className="text-fg-muted">{`{ "entity": "lead", "field": "stage", "to": "viewed_application" }`}</code>
              <br />
              <code className="text-fg-muted">{`{ "entity": "offer", "field": "stage", "to": "no_offer" }`}</code>
            </p>
          </div>
        </section>

        <section className="space-y-3 rounded-xl border border-bg-border bg-bg-elev/40 p-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-fg-muted">
            Steps (JSON)
          </h3>
          <p className="text-[11px] text-fg-dim leading-relaxed">
            Each step:{" "}
            <code className="text-fg-muted">
              {`{ "channel": "sms" | "email", "delay_minutes": N, "subject"?: "...", "body": "..." }`}
            </code>
            <br />
            Subject required when channel is email. Body supports{" "}
            <code className="text-fg-muted">{`{{lead.first_name}}`}</code> mustache
            substitution.
          </p>
          <textarea
            value={stepsJson}
            onChange={(e) => setStepsJson(e.target.value)}
            className="w-full rounded-md border border-bg-border bg-bg-deep px-3 py-2 font-mono text-[11px] text-fg min-h-[20rem]"
            spellCheck={false}
          />
        </section>

        <div className="flex items-center gap-3">
          <button
            onClick={save}
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-lg bg-accent text-bg-deep px-4 py-2 text-sm font-bold hover:bg-accent-bright disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save
          </button>
          <button
            onClick={destroy}
            className="inline-flex items-center gap-2 rounded-lg border border-rose-500/40 text-rose-400 px-4 py-2 text-sm font-bold hover:bg-rose-500/10"
          >
            <Trash2 className="w-4 h-4" />
            Delete
          </button>
          {saveMessage && (
            <div
              className={`flex items-center gap-2 text-sm ${
                saveMessage.kind === "ok" ? "text-status-engaged" : "text-rose-400"
              }`}
            >
              {saveMessage.kind === "ok" ? (
                <CheckCircle2 className="w-4 h-4" />
              ) : (
                <AlertCircle className="w-4 h-4" />
              )}
              {saveMessage.text}
            </div>
          )}
        </div>
      </div>

      {/* ── Right: validation + state ─────────────────────────────── */}
      <div className="space-y-4">
        <section className="rounded-xl border border-bg-border bg-bg-elev/40 p-4 sticky top-4 space-y-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-fg-muted">
            Validation
          </h3>
          {parsed.error ? (
            <div className="rounded-md border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-400 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <div>
                <div className="font-bold">Definition invalid</div>
                <div className="text-xs mt-0.5 font-mono">
                  {parsed.error.path}: {parsed.error.reason}
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-md border border-status-engaged/40 bg-status-engaged/5 p-3 text-sm text-status-engaged flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
              <div>
                <div className="font-bold">Definition OK.</div>
                <div className="text-xs mt-0.5 text-fg-muted">
                  {parsed.steps?.length} step{parsed.steps?.length === 1 ? "" : "s"} —{" "}
                  {parsed.steps?.filter((s) => s.channel === "sms").length} SMS,{" "}
                  {parsed.steps?.filter((s) => s.channel === "email").length} email
                </div>
              </div>
            </div>
          )}

          <div>
            <div className="text-[11px] uppercase tracking-wider font-bold text-fg-dim mb-2">
              Variables referenced
            </div>
            {referencedTokens.length === 0 ? (
              <p className="text-xs text-fg-dim italic">
                No mustache variables in any step body. Drips with static copy
                still work, but they won&apos;t personalize.
              </p>
            ) : (
              <ul className="space-y-1.5 text-xs">
                {referencedTokens.map((t) => (
                  <li key={t} className="flex items-start gap-2">
                    <code className="font-mono text-accent shrink-0">{`{{${t}}}`}</code>
                    <span className="text-fg-muted text-[11px] leading-relaxed">
                      {tokenHint(t)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <section className="rounded-xl border border-bg-border bg-bg-elev/40 p-4 space-y-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-fg-muted">
            In-flight state
          </h3>
          {stateRows === null ? (
            <p className="text-xs text-fg-dim italic">Loading…</p>
          ) : stateRows.length === 0 ? (
            <p className="text-xs text-fg-dim italic">
              No enrollments yet. The first matching status-change event will
              create a row here.
            </p>
          ) : (
            <ul className="space-y-1 text-xs">
              {stateRows.slice(0, 10).map((r) => (
                <li key={r.id} className="flex items-center gap-2 font-mono">
                  <span
                    className={`w-2 h-2 rounded-full shrink-0 ${
                      r.status === "scheduled"
                        ? "bg-status-engaged"
                        : r.status === "sent"
                          ? "bg-fg-muted"
                          : r.status === "failed"
                            ? "bg-rose-500"
                            : "bg-fg-dim"
                    }`}
                  />
                  <span className="text-fg-muted text-[10px] uppercase">{r.status}</span>
                  <span className="text-fg-dim">step {r.step_index}</span>
                  <span className="text-fg-dim truncate">lead:{r.lead_id.slice(0, 8)}…</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
