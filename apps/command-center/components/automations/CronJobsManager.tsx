"use client";

/**
 * CronJobsManager — client-side editor for the operator's tenant_cron_jobs.
 *
 * Phase I of giggly-reef harness completeness. Talks to /api/cron-jobs
 * (list + create) and /api/cron-jobs/[id] (patch + delete). The bridge
 * daemon polls the table independently every ~60s; this component only
 * manages the spec.
 *
 * Two surfaces:
 *   - List of existing jobs with toggle / edit / delete / "last run" UX
 *   - Inline "New automation" form with action-type-aware payload editor
 */

import { useEffect, useState } from "react";
import {
  Plus,
  Trash2,
  ToggleLeft,
  ToggleRight,
  Clock,
  Check,
  AlertCircle,
  Sparkles,
  Edit3,
  Save,
  X,
  PlayCircle,
  XCircle,
} from "lucide-react";

type ActionType = "script_run" | "snapshot_run" | "agent_prompt" | "webhook_post";

type CronJob = {
  id: string;
  agent_key: string;
  name: string;
  description: string | null;
  schedule: string;
  // Empire rows (source: "empire") carry action_type values from
  // cron_engine.py SEED_JOBS that aren't in the tenant ActionType union
  // (e.g. "stripe_sync", "funnel_sync"). UI just shows the string; the
  // editor never opens for empire rows so the type narrowing on
  // ActionType only matters for tenant rows.
  action_type: ActionType | string;
  action_payload: Record<string, unknown>;
  enabled: boolean;
  last_run_at: string | null;
  last_run_status: "success" | "error" | null;
  last_run_output: string | null;
  last_run_error: string | null;
  run_count: number;
  created_at: string;
  updated_at: string;
  source: "tenant" | "empire";
};

type Props = { agentKeys: string[] };

// Operator-friendly schedule presets — solves the "what cron expression
// do I write?" UX gap without forcing operators to learn cron syntax.
// "Custom" reveals the raw 5-field input.
const SCHEDULE_PRESETS: Array<{ label: string; value: string; hint: string }> = [
  { label: "Every minute", value: "* * * * *", hint: "Tests / dev loops." },
  { label: "Every 5 minutes", value: "*/5 * * * *", hint: "Polling-style checks." },
  { label: "Every 15 minutes", value: "*/15 * * * *", hint: "Frequent low-cost work." },
  { label: "Every hour, on the hour", value: "0 * * * *", hint: "Hourly health checks." },
  { label: "Daily at 06:00", value: "0 6 * * *", hint: "Morning briefings, daily snapshots." },
  { label: "Daily at 09:00 weekdays", value: "0 9 * * 1-5", hint: "Workday-only sends." },
  { label: "Sundays at 20:00", value: "0 20 * * 0", hint: "Weekly digest / recap." },
];

export function CronJobsManager({ agentKeys }: Props) {
  const [jobs, setJobs] = useState<CronJob[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [migrationGap, setMigrationGap] = useState<null | {
    migration: string;
    command: string;
    hint: string;
  }>(null);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  async function refresh() {
    try {
      const res = await fetch("/api/cron-jobs");
      const j = await res.json();
      if (!j.ok) {
        // Special-case the "migration not applied" 503 — the route emits
        // structured fields the UI uses to render an actionable message
        // (with the actual apply_migration.py command) instead of a generic
        // "couldn't load" red banner.
        if (j.error === "migration_not_applied") {
          setMigrationGap({
            migration: j.migration || "database/041_tenant_cron_jobs.sql",
            command: j.how_to_apply || "python scripts/apply_migration.py database/041_tenant_cron_jobs.sql",
            hint: j.hint || "Apply the migration to enable Automations.",
          });
          setLoadError(null);
          setJobs([]);
          return;
        }
        setLoadError(j.error || `http_${res.status}`);
        setMigrationGap(null);
        return;
      }
      setJobs(j.jobs || []);
      setLoadError(null);
      setMigrationGap(null);
    } catch (e) {
      // Network error / fetch threw — clear the migration banner too so
      // the operator doesn't see "One-time setup required" + "Load failed"
      // stacked from a previous load while the new state is unknown.
      setLoadError(e instanceof Error ? e.message : "load_failed");
      setMigrationGap(null);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function toggleEnabled(job: CronJob) {
    const next = !job.enabled;
    // Optimistic update
    setJobs((prev) => prev?.map((j) => (j.id === job.id ? { ...j, enabled: next } : j)) ?? null);
    const res = await fetch(`/api/cron-jobs/${job.id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ enabled: next }),
    });
    if (!res.ok) {
      // Revert on failure
      setJobs((prev) => prev?.map((j) => (j.id === job.id ? { ...j, enabled: !next } : j)) ?? null);
    }
  }

  async function deleteJob(id: string) {
    if (!confirm("Delete this automation? This can't be undone.")) return;
    const res = await fetch(`/api/cron-jobs/${id}`, { method: "DELETE" });
    if (res.ok) {
      setJobs((prev) => prev?.filter((j) => j.id !== id) ?? null);
    }
  }

  return (
    <div className="space-y-4">
      {migrationGap && (
        <div className="rounded-xl border border-accent/40 bg-accent/5 p-4 space-y-2">
          <div className="flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-accent shrink-0 mt-0.5" />
            <div className="flex-1 text-sm">
              <div className="font-bold text-fg">One-time setup required</div>
              <p className="text-xs text-fg-muted mt-1 leading-relaxed">{migrationGap.hint}</p>
            </div>
          </div>
          <div className="rounded-md bg-bg-deep border border-bg-border p-2.5 font-mono text-[11px] text-fg-muted select-all">
            {migrationGap.command}
          </div>
          <div className="text-[11px] text-fg-dim">
            Migration file: <span className="font-mono">{migrationGap.migration}</span>
          </div>
        </div>
      )}
      {loadError && (
        <div className="rounded-lg border border-status-warm/40 bg-status-warm/10 p-3 text-sm text-status-warm flex items-start gap-2">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>Couldn&apos;t load automations: {loadError}</span>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="text-xs text-fg-muted">
          {(() => {
            if (jobs === null) return "Loading…";
            if (jobs.length === 0) return "No automations yet.";
            const tenantCount = jobs.filter((j) => j.source === "tenant").length;
            const empireCount = jobs.filter((j) => j.source === "empire").length;
            const activeCount = jobs.filter((j) => j.enabled).length;
            const parts = [
              `${jobs.length} automation${jobs.length === 1 ? "" : "s"}`,
              `${activeCount} active`,
            ];
            if (empireCount > 0) {
              parts.push(`${tenantCount} tenant · ${empireCount} empire`);
            }
            return parts.join(" · ");
          })()}
        </div>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="btn-primary inline-flex items-center gap-1.5 text-xs"
          disabled={creating}
        >
          <Plus className="w-3.5 h-3.5" />
          New automation
        </button>
      </div>

      {creating && (
        <JobEditor
          mode="create"
          agentKeys={agentKeys}
          onCancel={() => setCreating(false)}
          onSaved={() => {
            setCreating(false);
            refresh();
          }}
        />
      )}

          {jobs && jobs.length > 0 && (() => {
        const tenantJobs = jobs.filter((j) => j.source === "tenant");
        const empireJobs = jobs.filter((j) => j.source === "empire");
        return (
          <div className="space-y-6">
            {tenantJobs.length > 0 && (
              <div className="space-y-2">
                {empireJobs.length > 0 && (
                  <div className="text-[10px] font-bold uppercase tracking-wider text-fg-dim">
                    Tenant automations
                  </div>
                )}
                {tenantJobs.map((job) =>
                  editingId === job.id ? (
                    <JobEditor
                      key={job.id}
                      mode="edit"
                      job={job}
                      agentKeys={agentKeys}
                      onCancel={() => setEditingId(null)}
                      onSaved={() => {
                        setEditingId(null);
                        refresh();
                      }}
                    />
                  ) : (
                    <JobRow
                      key={job.id}
                      job={job}
                      onToggle={() => toggleEnabled(job)}
                      onEdit={() => setEditingId(job.id)}
                      onDelete={() => deleteJob(job.id)}
                    />
                  ),
                )}
              </div>
            )}
            {empireJobs.length > 0 && (
              <div className="space-y-2">
                <div className="text-[10px] font-bold uppercase tracking-wider text-fg-dim">
                  Empire automations
                  <span className="ml-2 text-fg-dim/70 normal-case font-normal tracking-normal">
                    Managed by <span className="font-mono">scripts/cron_engine.py</span> SEED_JOBS · read-only here
                  </span>
                </div>
                {empireJobs.map((job) => (
                  <JobRow
                    key={job.id}
                    job={job}
                    onToggle={() => {/* empire toggling is intentionally a no-op */}}
                    onEdit={() => {/* empire editing is intentionally a no-op */}}
                    onDelete={() => {/* empire deletion is intentionally a no-op */}}
                  />
                ))}
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
}

function JobRow({
  job,
  onToggle,
  onEdit,
  onDelete,
}: {
  job: CronJob;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const preset = SCHEDULE_PRESETS.find((p) => p.value === job.schedule);
  // Empire rows live in cron_jobs and are seeded from scripts/cron_engine.py.
  // The UI shows their state read-only — no toggle, edit, or delete.
  const isEmpire = job.source === "empire";
  return (
    <div
      className={`rounded-lg border p-3 ${
        job.enabled ? "border-bg-border bg-bg-elev/30" : "border-bg-border bg-bg-deep/40 opacity-60"
      }`}
    >
      <div className="flex items-start gap-3">
        {isEmpire ? (
          <div
            className="shrink-0 mt-0.5"
            title={job.enabled ? "Empire automation (read-only)" : "Empire automation (disabled in cron_jobs)"}
          >
            {job.enabled ? (
              <ToggleRight className="w-5 h-5 text-fg-dim" />
            ) : (
              <ToggleLeft className="w-5 h-5 text-fg-dim" />
            )}
          </div>
        ) : (
          <button
            type="button"
            onClick={onToggle}
            className="shrink-0 mt-0.5"
            title={job.enabled ? "Disable (keeps the spec, stops firing)" : "Enable"}
          >
            {job.enabled ? (
              <ToggleRight className="w-5 h-5 text-status-engaged" />
            ) : (
              <ToggleLeft className="w-5 h-5 text-fg-dim" />
            )}
          </button>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="font-bold text-sm text-fg truncate">{job.name}</div>
            {isEmpire && (
              <span className="text-[10px] uppercase tracking-wider text-accent border border-accent/40 bg-accent/10 rounded-full px-1.5 py-0.5">
                Empire
              </span>
            )}
            <span className="text-[10px] uppercase tracking-wider text-fg-dim border border-bg-border rounded-full px-1.5 py-0.5">
              {job.agent_key}
            </span>
            <span className="text-[10px] uppercase tracking-wider text-fg-dim border border-bg-border rounded-full px-1.5 py-0.5">
              {job.action_type.replace(/_/g, " ")}
            </span>
          </div>
          {job.description && <div className="text-xs text-fg-muted mt-0.5">{job.description}</div>}
          <div className="text-[11px] text-fg-dim font-mono mt-1 inline-flex items-center gap-1.5">
            <Clock className="w-3 h-3" />
            {preset ? `${preset.label} · ${job.schedule}` : job.schedule}
          </div>
          {job.last_run_at && (
            <div className="text-[11px] mt-1 inline-flex items-center gap-1.5">
              {job.last_run_status === "success" ? (
                <PlayCircle className="w-3 h-3 text-status-engaged" />
              ) : (
                <XCircle className="w-3 h-3 text-status-warm" />
              )}
              <span className={job.last_run_status === "success" ? "text-fg-muted" : "text-status-warm"}>
                Last run: {new Date(job.last_run_at).toLocaleString()} · {job.run_count} total
              </span>
            </div>
          )}
        </div>
        {!isEmpire && (
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={onEdit}
              className="text-fg-dim hover:text-fg p-1"
              title="Edit"
            >
              <Edit3 className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={onDelete}
              className="text-fg-dim hover:text-status-warm p-1"
              title="Delete"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
      {job.last_run_error && (
        <div className="mt-2 text-[11px] text-status-warm bg-status-warm/5 border border-status-warm/30 rounded px-2 py-1.5 font-mono break-words">
          {job.last_run_error.slice(0, 240)}
        </div>
      )}
    </div>
  );
}

function JobEditor({
  mode,
  job,
  agentKeys,
  onCancel,
  onSaved,
}: {
  mode: "create" | "edit";
  job?: CronJob;
  agentKeys: string[];
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(job?.name || "");
  const [description, setDescription] = useState(job?.description || "");
  const [agentKey, setAgentKey] = useState(job?.agent_key || agentKeys[0] || "bravo");
  const [scheduleMode, setScheduleMode] = useState<"preset" | "custom">(() => {
    if (!job) return "preset";
    return SCHEDULE_PRESETS.some((p) => p.value === job.schedule) ? "preset" : "custom";
  });
  const [schedule, setSchedule] = useState(job?.schedule || SCHEDULE_PRESETS[4].value);
  // JobEditor is only opened for tenant rows (gated in JobRow above), so
  // job.action_type is always one of the four ActionType values here. Cast
  // is safe — empire rows never reach this code path.
  const [actionType, setActionType] = useState<ActionType>(
    (job?.action_type as ActionType) || "script_run",
  );
  const [actionPayload, setActionPayload] = useState<Record<string, unknown>>(
    job?.action_payload || { script: "" },
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    const body: Record<string, unknown> = {
      name,
      description: description || null,
      agent_key: agentKey,
      schedule,
    };
    if (mode === "create") {
      body.action_type = actionType;
      body.action_payload = actionPayload;
    }
    try {
      const url = mode === "create" ? "/api/cron-jobs" : `/api/cron-jobs/${job!.id}`;
      const method = mode === "create" ? "POST" : "PATCH";
      const res = await fetch(url, {
        method,
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await res.json();
      if (!j.ok) {
        setError(j.hint ? `${j.error} — ${j.hint}` : j.error);
        setSaving(false);
        return;
      }
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "save_failed");
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-accent/30 bg-accent/5 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="font-bold text-sm text-fg inline-flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-accent" />
          {mode === "create" ? "New automation" : `Edit · ${job?.name}`}
        </div>
        <button type="button" onClick={onCancel} className="text-fg-dim hover:text-fg-muted p-1">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        <label className="block">
          <span className="text-[10px] font-bold uppercase tracking-wider text-fg-dim block mb-1">
            Name
          </span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Daily CEO briefing"
            className="input w-full text-sm"
            maxLength={80}
          />
        </label>
        <label className="block">
          <span className="text-[10px] font-bold uppercase tracking-wider text-fg-dim block mb-1">
            Agent
          </span>
          <select
            value={agentKey}
            onChange={(e) => setAgentKey(e.target.value)}
            className="input w-full text-sm"
          >
            {agentKeys.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="block">
        <span className="text-[10px] font-bold uppercase tracking-wider text-fg-dim block mb-1">
          Description (optional)
        </span>
        <input
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Pulls revenue + pipeline + Atlas snapshot every morning"
          className="input w-full text-sm"
          maxLength={500}
        />
      </label>

      <div>
        <span className="text-[10px] font-bold uppercase tracking-wider text-fg-dim block mb-1">
          Schedule
        </span>
        <div className="flex items-center gap-2 mb-2">
          <button
            type="button"
            onClick={() => setScheduleMode("preset")}
            className={`text-xs px-2 py-1 rounded border ${scheduleMode === "preset" ? "border-accent bg-accent/10 text-accent" : "border-bg-border text-fg-muted"}`}
          >
            Preset
          </button>
          <button
            type="button"
            onClick={() => setScheduleMode("custom")}
            className={`text-xs px-2 py-1 rounded border ${scheduleMode === "custom" ? "border-accent bg-accent/10 text-accent" : "border-bg-border text-fg-muted"}`}
          >
            Custom cron
          </button>
        </div>
        {scheduleMode === "preset" ? (
          <select
            value={schedule}
            onChange={(e) => setSchedule(e.target.value)}
            className="input w-full text-sm"
          >
            {SCHEDULE_PRESETS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label} — {p.hint}
              </option>
            ))}
          </select>
        ) : (
          <input
            type="text"
            value={schedule}
            onChange={(e) => setSchedule(e.target.value)}
            placeholder="0 6 * * 1-5"
            className="input w-full text-sm font-mono"
          />
        )}
        <div className="text-[10px] text-fg-dim mt-1">
          5-field cron: <span className="font-mono">m h dom mon dow</span>. Time zone is your
          machine&apos;s local time.
        </div>
      </div>

      {mode === "create" && (
        <div className="space-y-2 border-t border-bg-border pt-3">
          <span className="text-[10px] font-bold uppercase tracking-wider text-fg-dim block">
            Action
          </span>
          <select
            value={actionType}
            onChange={(e) => {
              const t = e.target.value as ActionType;
              setActionType(t);
              // Reset payload to the new type's defaults
              if (t === "script_run") setActionPayload({ script: "", args: [] });
              else if (t === "snapshot_run") setActionPayload({ snapshot: "" });
              else if (t === "webhook_post") setActionPayload({ url: "", body: {} });
              else if (t === "agent_prompt") setActionPayload({ prompt: "" });
            }}
            className="input w-full text-sm"
          >
            <option value="script_run">Run a Python script (scripts/X.py)</option>
            <option value="snapshot_run">Run a snapshot (scripts/snapshots/X.py)</option>
            <option value="webhook_post">POST to a webhook URL</option>
            <option value="agent_prompt">Fire an agent prompt (coming soon)</option>
          </select>

          {actionType === "script_run" && (
            <>
              <label className="block">
                <span className="text-[10px] text-fg-dim block mb-0.5">Script filename</span>
                <input
                  type="text"
                  value={String(actionPayload.script || "")}
                  onChange={(e) => setActionPayload({ ...actionPayload, script: e.target.value })}
                  placeholder="leads_snapshot.py"
                  className="input w-full text-sm font-mono"
                />
              </label>
              <label className="block">
                <span className="text-[10px] text-fg-dim block mb-0.5">
                  Args (comma-separated)
                </span>
                <input
                  type="text"
                  defaultValue={Array.isArray(actionPayload.args) ? (actionPayload.args as string[]).join(", ") : ""}
                  onChange={(e) =>
                    setActionPayload({
                      ...actionPayload,
                      args: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })
                  }
                  placeholder="--json, --limit, 10"
                  className="input w-full text-sm font-mono"
                />
              </label>
            </>
          )}

          {actionType === "snapshot_run" && (
            <label className="block">
              <span className="text-[10px] text-fg-dim block mb-0.5">Snapshot filename</span>
              <input
                type="text"
                value={String(actionPayload.snapshot || "")}
                onChange={(e) => setActionPayload({ ...actionPayload, snapshot: e.target.value })}
                placeholder="briefing_snapshot.py"
                className="input w-full text-sm font-mono"
              />
            </label>
          )}

          {actionType === "webhook_post" && (
            <label className="block">
              <span className="text-[10px] text-fg-dim block mb-0.5">URL</span>
              <input
                type="url"
                value={String(actionPayload.url || "")}
                onChange={(e) => setActionPayload({ ...actionPayload, url: e.target.value })}
                placeholder="https://n8n.your-domain.com/webhook/..."
                className="input w-full text-sm font-mono"
              />
            </label>
          )}

          {actionType === "agent_prompt" && (
            <div className="text-[11px] text-status-warm bg-status-warm/5 border border-status-warm/30 rounded p-2">
              Agent prompts from cron aren&apos;t wired yet (v1 limitation —
              chat is an interactive surface). Use script_run with a Python
              wrapper if you need a scheduled agent invocation.
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="rounded-md border border-status-warm/40 bg-status-warm/10 p-2 text-xs text-status-warm flex items-start gap-1.5">
          <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex items-center justify-end gap-2 pt-1">
        <button type="button" onClick={onCancel} className="btn-secondary text-xs" disabled={saving}>
          Cancel
        </button>
        <button
          type="button"
          onClick={save}
          className="btn-primary text-xs inline-flex items-center gap-1.5"
          disabled={saving || !name.trim() || !schedule.trim()}
        >
          {saving ? <Sparkles className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
          {saving ? "Saving" : mode === "create" ? "Create" : "Save"}
        </button>
      </div>
    </div>
  );
}
