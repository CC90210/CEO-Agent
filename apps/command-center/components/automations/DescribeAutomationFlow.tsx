"use client";

/**
 * DescribeAutomationFlow — "Tell me what you want, AI writes the script".
 *
 * Phase 10.3 of the OASIS HQ redesign. CC's complaint: "I don't know how
 * easy it is to create a new automation — we may have to build a custom
 * Python script." This component lets him type a paragraph; Claude returns
 * a draft script + cron schedule; he reviews + saves.
 *
 * Three states:
 *   1. INPUT — textarea + "Draft with AI" button
 *   2. REVIEW — generated draft is editable inline; "Save automation" /
 *      "Re-draft" / "Cancel"
 *   3. SAVED — confirmation + link to the new cron row (disabled by
 *      default; operator flips on after inspecting the generated file).
 *
 * Save flow:
 *   - POST /api/automations/save-draft → returns {cron_id, script_path,
 *     script_content}
 *   - Then client POSTs to localhost:9100/exec-tool with write_file to
 *     persist the script to disk. Vercel can't write to the operator's
 *     disk; the bridge can.
 */

import { useState } from "react";
import { Sparkles, Loader2, AlertCircle, Save, RotateCcw, X, CheckCircle2 } from "lucide-react";
import { BRIDGE_CHAT_BASE } from "@/lib/agent-roots";

type Draft = {
  suggested_name: string;
  suggested_description: string;
  schedule: string;
  schedule_human: string;
  script_filename: string;
  script_content: string;
  agent_key: string;
  reasoning: string;
};

type State =
  | { kind: "input"; description: string }
  | { kind: "drafting"; description: string }
  | { kind: "review"; description: string; draft: Draft }
  | { kind: "saving"; description: string; draft: Draft }
  | { kind: "saved"; cronId: string; scriptPath: string }
  | { kind: "error"; message: string; description: string };

const EXAMPLES = [
  "Every Monday at 7am, pull my Stripe revenue for the prior week and send me a one-line summary to Telegram.",
  "Daily at noon, check my Calendly for tomorrow's bookings and Telegram me the list so I can prep.",
  "Every Friday at 4pm, run our lead scorer over any leads created in the last 7 days and email me the top 5.",
];

export function DescribeAutomationFlow() {
  const [state, setState] = useState<State>({ kind: "input", description: "" });

  async function draft() {
    if (state.kind !== "input") return;
    const description = state.description.trim();
    if (description.length < 10) {
      setState({ kind: "error", message: "Describe at least one full sentence — what should happen, when, and where the output goes.", description: state.description });
      return;
    }
    setState({ kind: "drafting", description });
    try {
      const r = await fetch("/api/automations/draft", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ description }),
      });
      const json = (await r.json()) as { ok: boolean; draft?: Draft; error?: string; message?: string };
      if (!json.ok || !json.draft) {
        setState({ kind: "error", message: json.message || json.error || "Drafting failed", description });
        return;
      }
      setState({ kind: "review", description, draft: json.draft });
    } catch (err) {
      setState({ kind: "error", message: (err as Error).message, description });
    }
  }

  async function save() {
    if (state.kind !== "review") return;
    const { description, draft } = state;
    setState({ kind: "saving", description, draft });

    // Step 1: server-side persist (cron row + return the script content)
    const r = await fetch("/api/automations/save-draft", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ draft, confirmed: true }),
    });
    const json = (await r.json()) as {
      ok: boolean;
      cron_id?: string;
      script_path?: string;
      script_content?: string;
      error?: string;
      message?: string;
    };
    if (!json.ok || !json.cron_id || !json.script_path || !json.script_content) {
      setState({
        kind: "error",
        message: json.message || json.error || "Save failed",
        description,
      });
      return;
    }

    // Step 2: write the actual Python file to the operator's disk via
    // the local bridge. Vercel can't reach the disk; the bridge can.
    try {
      const bridgeRes = await fetch(`${BRIDGE_CHAT_BASE}/exec-tool`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          tool_name: "write_file",
          input: { path: json.script_path, content: json.script_content },
        }),
      });
      const bridgeJson = (await bridgeRes.json()) as { ok?: boolean; output?: string; is_error?: boolean };
      if (!bridgeJson.ok || bridgeJson.is_error) {
        setState({
          kind: "error",
          message: `Cron row created but script file write failed: ${bridgeJson.output || "bridge offline"}. Edit ${json.script_path} manually before enabling.`,
          description,
        });
        return;
      }
    } catch (err) {
      setState({
        kind: "error",
        message: `Cron row created but bridge unreachable. Save ${json.script_path} manually before enabling. ${(err as Error).message}`,
        description,
      });
      return;
    }

    setState({ kind: "saved", cronId: json.cron_id, scriptPath: json.script_path });
  }

  function reset() {
    setState({ kind: "input", description: "" });
  }

  // ─── INPUT ────────────────────────────────────────────────────────────
  if (state.kind === "input" || state.kind === "error") {
    return (
      <div className="rounded-xl border border-accent/30 bg-accent/5 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-accent" />
            <span className="font-bold text-sm text-fg">Describe an automation — AI writes the script</span>
          </div>
        </div>
        <textarea
          value={state.description}
          onChange={(e) => setState({ kind: "input", description: e.target.value })}
          placeholder={EXAMPLES[Math.floor(Math.random() * EXAMPLES.length)]}
          rows={3}
          className="w-full rounded-lg border border-bg-border bg-bg-deep px-3 py-2 text-sm text-fg placeholder-fg-dim focus:outline-none focus:border-accent transition-colors resize-y"
        />
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-fg-dim leading-snug">
            Bravo drafts the Python script + cron schedule. You review, edit if needed, then save —
            created disabled so nothing fires until you flip it on.
          </span>
          <button
            type="button"
            onClick={draft}
            disabled={state.description.trim().length < 10}
            className="btn-send inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs shrink-0 disabled:opacity-40"
          >
            <Sparkles className="w-3.5 h-3.5" />
            Draft with AI
          </button>
        </div>
        {state.kind === "error" && (
          <div className="flex items-start gap-2 text-xs text-status-warm bg-status-warm/5 border border-status-warm/30 rounded p-2.5">
            <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            <div>{state.message}</div>
          </div>
        )}
      </div>
    );
  }

  // ─── DRAFTING ─────────────────────────────────────────────────────────
  if (state.kind === "drafting") {
    return (
      <div className="rounded-xl border border-accent/30 bg-accent/5 p-4 flex items-center gap-3">
        <Loader2 className="w-5 h-5 text-accent animate-spin" />
        <div>
          <div className="text-sm text-fg font-bold">Drafting your automation...</div>
          <div className="text-[11px] text-fg-muted mt-0.5">
            Bravo is writing the script + picking a schedule. ~10 seconds.
          </div>
        </div>
      </div>
    );
  }

  // ─── REVIEW ───────────────────────────────────────────────────────────
  if (state.kind === "review" || state.kind === "saving") {
    const { draft } = state;
    const saving = state.kind === "saving";
    return (
      <div className="rounded-xl border border-status-engaged/40 bg-status-engaged/5 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-status-engaged" />
            <span className="font-bold text-sm text-fg">Review the draft</span>
          </div>
          <button
            type="button"
            onClick={reset}
            disabled={saving}
            className="text-fg-dim hover:text-fg p-1 disabled:opacity-50"
            title="Discard + start over"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="grid sm:grid-cols-[8rem_1fr] gap-y-2 gap-x-3 text-sm">
          <div className="text-fg-muted text-xs uppercase tracking-wider font-bold">Name</div>
          <div className="text-fg font-medium">{draft.suggested_name}</div>

          <div className="text-fg-muted text-xs uppercase tracking-wider font-bold">Description</div>
          <div className="text-fg-muted">{draft.suggested_description}</div>

          <div className="text-fg-muted text-xs uppercase tracking-wider font-bold">Schedule</div>
          <div className="text-fg">
            {draft.schedule_human}{" "}
            <span className="text-fg-faint font-mono text-[11px]">({draft.schedule})</span>
          </div>

          <div className="text-fg-muted text-xs uppercase tracking-wider font-bold">Agent</div>
          <div className="text-fg">{draft.agent_key}</div>

          <div className="text-fg-muted text-xs uppercase tracking-wider font-bold">Script</div>
          <div className="text-fg font-mono text-xs">scripts/{draft.script_filename}</div>
        </div>

        <details className="rounded-lg border border-bg-border bg-bg-deep/40">
          <summary className="cursor-pointer select-none px-3 py-2 text-xs text-fg-muted hover:text-fg">
            ▸ Inspect generated Python ({draft.script_content.split("\n").length} lines)
          </summary>
          <pre className="px-3 pb-3 text-[10px] text-fg-dim font-mono overflow-x-auto max-h-96 overflow-y-auto">
            {draft.script_content}
          </pre>
        </details>

        <div className="text-[11px] text-fg-muted leading-snug bg-bg-deep/40 rounded p-2.5">
          <span className="font-bold text-fg">Bravo&apos;s reasoning:</span> {draft.reasoning}
        </div>

        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={reset}
            disabled={saving}
            className="btn-secondary inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs disabled:opacity-50"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Start over
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="btn-send inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs disabled:opacity-50"
          >
            {saving ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="w-3.5 h-3.5" />
                Save automation (disabled)
              </>
            )}
          </button>
        </div>
      </div>
    );
  }

  // ─── SAVED ────────────────────────────────────────────────────────────
  if (state.kind === "saved") {
    return (
      <div className="rounded-xl border border-status-engaged/40 bg-status-engaged/5 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="w-5 h-5 text-status-engaged" />
          <span className="font-bold text-sm text-fg">Automation saved (paused)</span>
        </div>
        <div className="text-sm text-fg-muted leading-relaxed">
          The script is at <code className="font-mono text-fg">{state.scriptPath}</code> and a
          paused cron row is in the list below. Inspect the file, then flip the toggle to
          activate. The scheduler picks up the change on its next 60s poll.
        </div>
        <button
          type="button"
          onClick={reset}
          className="btn-secondary inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
        >
          <Sparkles className="w-3.5 h-3.5" />
          Draft another
        </button>
      </div>
    );
  }

  return null;
}
