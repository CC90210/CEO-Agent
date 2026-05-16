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
import { AlertCircle, CheckCircle2, Loader2, Save, Trash2, Plus, X, Code2, ListTree, MessageSquare, Mail } from "lucide-react";
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
  // Two editor modes for the steps body — structured (one card per step,
  // operator-friendly default) and raw (monospace JSON for advanced
  // operators or shapes the structured editor doesn't cover). Same goes
  // for the trigger filter. The serialized JSON strings remain the source
  // of truth feeding `parsed` below; the structured editor writes back
  // through the same setStepsJson / setFilterJson hooks on every edit.
  const [stepsJson, setStepsJson] = useState(() =>
    JSON.stringify(initialSequence.steps, null, 2),
  );
  const [filterJson, setFilterJson] = useState(() =>
    JSON.stringify(initialSequence.trigger_filter, null, 2),
  );
  const [stepsMode, setStepsMode] = useState<"structured" | "raw">("structured");
  const [filterMode, setFilterMode] = useState<"structured" | "raw">("structured");

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
            <div className="flex items-center justify-between mb-1">
              <label className="block text-[11px] uppercase tracking-wider font-bold text-fg-dim">
                Filter
              </label>
              <button
                type="button"
                onClick={() => {
                  // Re-serialize when leaving structured mode so the
                  // textarea picks up whatever the operator clicked in.
                  if (filterMode === "structured" && parsed.filter) {
                    setFilterJson(JSON.stringify(parsed.filter, null, 2));
                  }
                  setFilterMode(filterMode === "structured" ? "raw" : "structured");
                }}
                className="text-[10px] uppercase tracking-wider text-fg-dim hover:text-fg inline-flex items-center gap-1"
              >
                {filterMode === "structured" ? (
                  <><Code2 className="h-3 w-3" /> Advanced</>
                ) : (
                  <><ListTree className="h-3 w-3" /> Simple</>
                )}
              </button>
            </div>
            {filterMode === "structured" ? (
              <FilterEditor
                filter={parsed.filter || {}}
                onChange={(next) => setFilterJson(JSON.stringify(next, null, 2))}
              />
            ) : (
              <>
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
                </p>
              </>
            )}
          </div>
        </section>

        <section className="space-y-3 rounded-xl border border-bg-border bg-bg-elev/40 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-fg-muted">
              Steps
            </h3>
            <button
              type="button"
              onClick={() => {
                if (stepsMode === "structured" && parsed.steps) {
                  setStepsJson(JSON.stringify(parsed.steps, null, 2));
                }
                setStepsMode(stepsMode === "structured" ? "raw" : "structured");
              }}
              className="text-[10px] uppercase tracking-wider text-fg-dim hover:text-fg inline-flex items-center gap-1"
            >
              {stepsMode === "structured" ? (
                <><Code2 className="h-3 w-3" /> Advanced (raw JSON)</>
              ) : (
                <><ListTree className="h-3 w-3" /> Simple</>
              )}
            </button>
          </div>
          {stepsMode === "structured" ? (
            <StepsEditor
              steps={parsed.steps || []}
              onChange={(next) => setStepsJson(JSON.stringify(next, null, 2))}
            />
          ) : (
            <>
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
            </>
          )}
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

/**
 * StepsEditor — structured editor for a DripStep[]. Operator gets one
 * card per step with channel dropdown, delay number, optional subject
 * (email only), body textarea, and an optional from_label. Add / remove
 * / reorder via the card chrome.
 *
 * Source of truth is the parent's stepsJson string. On every change we
 * call onChange with the full updated array; parent re-serializes to
 * JSON and runs it through parseDripSteps, so validation behavior is
 * identical to the raw textarea path.
 */
function StepsEditor({
  steps,
  onChange,
}: {
  steps: DripStep[];
  onChange: (steps: DripStep[]) => void;
}) {
  function update(idx: number, patch: Partial<DripStep>) {
    const next = steps.map((s, i) => (i === idx ? { ...s, ...patch } : s));
    onChange(next);
  }
  function remove(idx: number) {
    onChange(steps.filter((_, i) => i !== idx));
  }
  function move(idx: number, delta: -1 | 1) {
    const target = idx + delta;
    if (target < 0 || target >= steps.length) return;
    const next = [...steps];
    [next[idx], next[target]] = [next[target], next[idx]];
    onChange(next);
  }
  function addStep(channel: "sms" | "email") {
    const last = steps[steps.length - 1];
    onChange([
      ...steps,
      {
        channel,
        delay_minutes: last ? Math.max(60, last.delay_minutes) : 0,
        ...(channel === "email" ? { subject: "" } : {}),
        body: "",
      },
    ]);
  }

  return (
    <div className="space-y-3">
      {steps.length === 0 && (
        <div className="text-xs text-fg-dim italic px-3 py-4 rounded-md border border-dashed border-bg-border">
          No steps yet. Add an SMS or email step below to start the drip.
        </div>
      )}
      {steps.map((step, idx) => (
        <div key={idx} className="rounded-lg border border-bg-border bg-bg-deep/40 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs">
              <span className="font-bold text-fg-muted">Step {idx + 1}</span>
              {step.channel === "email" ? (
                <Mail className="h-3 w-3 text-accent" />
              ) : (
                <MessageSquare className="h-3 w-3 text-accent" />
              )}
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => move(idx, -1)}
                disabled={idx === 0}
                className="text-fg-dim hover:text-fg disabled:opacity-30 px-1"
                title="Move up"
              >
                ↑
              </button>
              <button
                type="button"
                onClick={() => move(idx, 1)}
                disabled={idx === steps.length - 1}
                className="text-fg-dim hover:text-fg disabled:opacity-30 px-1"
                title="Move down"
              >
                ↓
              </button>
              <button
                type="button"
                onClick={() => remove(idx)}
                className="text-fg-dim hover:text-rose-400 px-1"
                title="Remove step"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-fg-dim block mb-0.5">
                Channel
              </span>
              <select
                value={step.channel}
                onChange={(e) => {
                  const ch = e.target.value as "sms" | "email";
                  // Email needs a subject — supply a sensible default
                  // when switching to email so the operator isn't
                  // staring at a "subject required" error from validation.
                  update(idx, {
                    channel: ch,
                    ...(ch === "email" && !step.subject ? { subject: "Following up" } : {}),
                  });
                }}
                className="w-full rounded-md border border-bg-border bg-bg-elev px-2 py-1.5 text-xs text-fg"
              >
                <option value="sms">SMS (Twilio / TextTorrent)</option>
                <option value="email">Email (Gmail)</option>
              </select>
            </label>
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-fg-dim block mb-0.5">
                Delay after previous step (minutes)
              </span>
              <input
                type="number"
                value={step.delay_minutes}
                onChange={(e) =>
                  update(idx, { delay_minutes: Math.max(0, Number(e.target.value) || 0) })
                }
                min={0}
                className="w-full rounded-md border border-bg-border bg-bg-elev px-2 py-1.5 text-xs text-fg"
              />
            </label>
          </div>
          {step.channel === "email" && (
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-fg-dim block mb-0.5">
                Subject
              </span>
              <input
                type="text"
                value={step.subject || ""}
                onChange={(e) => update(idx, { subject: e.target.value })}
                placeholder="Following up on your application"
                className="w-full rounded-md border border-bg-border bg-bg-elev px-2 py-1.5 text-xs text-fg"
              />
            </label>
          )}
          <label className="block">
            <span className="text-[10px] uppercase tracking-wider text-fg-dim block mb-0.5">
              Body
              <span className="ml-2 normal-case tracking-normal text-fg-dim/70">
                Mustache vars: {`{{lead.first_name}}`} {`{{lead.business_name}}`}
              </span>
            </span>
            <textarea
              value={step.body}
              onChange={(e) => update(idx, { body: e.target.value })}
              rows={step.channel === "email" ? 6 : 3}
              placeholder={
                step.channel === "sms"
                  ? "Hey {{lead.first_name}}, quick follow-up on the application — let me know if I can answer anything. — Solara"
                  : "Hi {{lead.first_name}},\n\nFollowing up on the application. Let me know if I can help."
              }
              className="w-full rounded-md border border-bg-border bg-bg-elev px-2 py-1.5 text-xs text-fg font-mono"
            />
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-wider text-fg-dim block mb-0.5">
              From label (optional)
            </span>
            <input
              type="text"
              value={step.from_label || ""}
              onChange={(e) => update(idx, { from_label: e.target.value || undefined })}
              placeholder="Solara"
              className="w-full rounded-md border border-bg-border bg-bg-elev px-2 py-1.5 text-xs text-fg"
            />
          </label>
        </div>
      ))}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => addStep("sms")}
          className="inline-flex items-center gap-1.5 text-xs rounded-md border border-bg-border bg-bg-elev hover:bg-bg-elev/80 px-3 py-1.5 text-fg-muted hover:text-fg"
        >
          <Plus className="h-3 w-3" /> SMS step
        </button>
        <button
          type="button"
          onClick={() => addStep("email")}
          className="inline-flex items-center gap-1.5 text-xs rounded-md border border-bg-border bg-bg-elev hover:bg-bg-elev/80 px-3 py-1.5 text-fg-muted hover:text-fg"
        >
          <Plus className="h-3 w-3" /> Email step
        </button>
      </div>
    </div>
  );
}

/**
 * FilterEditor — structured editor for the DripTriggerFilter shape.
 * Three of the four supported keys (entity, field, to) cover ~all real
 * use cases; `from` is exposed under an expandable "Advanced" disclosure
 * since it's rarely needed (matches a specific transition pair).
 */
function FilterEditor({
  filter,
  onChange,
}: {
  filter: DripTriggerFilter;
  onChange: (next: DripTriggerFilter) => void;
}) {
  const [showFrom, setShowFrom] = useState(!!filter.from);
  function patch(p: Partial<DripTriggerFilter>) {
    onChange({ ...filter, ...p });
  }
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 gap-2">
        <label className="block">
          <span className="text-[10px] uppercase tracking-wider text-fg-dim block mb-0.5">
            Entity
          </span>
          <select
            value={filter.entity || ""}
            onChange={(e) => patch({ entity: e.target.value || undefined })}
            className="w-full rounded-md border border-bg-border bg-bg-elev px-2 py-1.5 text-xs text-fg"
          >
            <option value="">— any —</option>
            <option value="lead">Lead</option>
            <option value="application">Application</option>
            <option value="offer">Offer</option>
            <option value="funded_deal">Funded deal</option>
          </select>
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wider text-fg-dim block mb-0.5">
            Field
          </span>
          <select
            value={filter.field || ""}
            onChange={(e) => patch({ field: e.target.value || undefined })}
            className="w-full rounded-md border border-bg-border bg-bg-elev px-2 py-1.5 text-xs text-fg"
          >
            <option value="">— any —</option>
            <option value="stage">stage</option>
            <option value="status">status</option>
          </select>
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wider text-fg-dim block mb-0.5">
            To (target value)
          </span>
          <input
            type="text"
            value={filter.to || ""}
            onChange={(e) => patch({ to: e.target.value || undefined })}
            placeholder="viewed_application"
            className="w-full rounded-md border border-bg-border bg-bg-elev px-2 py-1.5 text-xs text-fg"
          />
        </label>
      </div>
      {showFrom ? (
        <label className="block">
          <span className="text-[10px] uppercase tracking-wider text-fg-dim block mb-0.5">
            From (source value, rare)
            <button
              type="button"
              onClick={() => {
                setShowFrom(false);
                patch({ from: undefined });
              }}
              className="ml-2 text-fg-dim hover:text-fg normal-case tracking-normal"
            >
              hide
            </button>
          </span>
          <input
            type="text"
            value={filter.from || ""}
            onChange={(e) => patch({ from: e.target.value || undefined })}
            placeholder="sent_application"
            className="w-full rounded-md border border-bg-border bg-bg-elev px-2 py-1.5 text-xs text-fg"
          />
        </label>
      ) : (
        <button
          type="button"
          onClick={() => setShowFrom(true)}
          className="text-[10px] uppercase tracking-wider text-fg-dim hover:text-fg"
        >
          + Match only a specific transition
        </button>
      )}
    </div>
  );
}
