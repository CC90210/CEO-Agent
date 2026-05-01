"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { PlanTemplate } from "@/lib/supabase";
import { Plus, Trash2, ArrowUp, ArrowDown, Save, Wand2 } from "lucide-react";

type Block = {
  time_label: string;
  title: string;
  body: string;
  intensity?: "intense" | "normal" | "break" | "carryover";
};

const DEFAULT_WEEKDAY: Block[] = [
  { time_label: "08:00 — 09:00", title: "Morning routine", body: "Body is the platform. Phone DND.", intensity: "break" },
  { time_label: "09:00 — 09:30", title: "Workspace setup", body: "Open Command Center. Headset on. Water + coffee.", intensity: "normal" },
  { time_label: "09:30 — 11:00", title: "Cold-call block #1", body: "Pull eligible leads from Pipeline. 12 dials.", intensity: "intense" },
  { time_label: "11:00 — 11:30", title: "Lunch", body: "Step outside. Replay best/worst calls.", intensity: "break" },
  { time_label: "11:30 — 13:00", title: "Cold-call block #2", body: "Switch verticals. 15 dials.", intensity: "intense" },
  { time_label: "13:00 — 14:00", title: "Email batch", body: "10 follow-ups via send_gateway.", intensity: "normal" },
  { time_label: "14:00 — 15:00", title: "Content / build", body: "1 piece shipped or 1 hour of build time.", intensity: "normal" },
  { time_label: "15:00 — 15:30", title: "Pipeline review", body: "Log every call. Score: dials/conversations/bookings.", intensity: "normal" },
  { time_label: "15:30 — 16:30", title: "Strategic outreach", body: "3 partner reach-outs. Recruitment, not selling.", intensity: "intense" },
  { time_label: "16:30 — 17:00", title: "Day retro + state sync", body: "Pre-stage tomorrow's leads.", intensity: "normal" },
];

const DEFAULT_WEEKEND: Block[] = [
  { time_label: "09:00 — 10:00", title: "Slow morning", body: "No phone. Read or walk.", intensity: "break" },
  { time_label: "10:00 — 11:30", title: "Weekly retro", body: "Review week's calls + KPIs. What worked, what broke, what objection caught you.", intensity: "intense" },
  { time_label: "11:30 — 13:00", title: "Content block", body: "1 long-form + 1 video. Build once, distribute via Maven.", intensity: "intense" },
  { time_label: "13:00 — 14:30", title: "Hobby / off", body: "Mind off work.", intensity: "break" },
  { time_label: "14:30 — 16:00", title: "Next-week plan", body: "Set Monday's primary lead. Adjust weekday template if last week's data demanded it.", intensity: "normal" },
];

export function PlanTemplateEditor({
  kind,
  existing,
}: {
  kind: "weekday" | "weekend";
  existing: PlanTemplate | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [mission, setMission] = useState(existing?.mission || "");
  const [calls, setCalls] = useState(String(existing?.target_calls ?? 0));
  const [emails, setEmails] = useState(String(existing?.target_emails ?? 0));
  const [bookings, setBookings] = useState(String(existing?.target_bookings ?? 1));
  const [schedule, setSchedule] = useState<Block[]>(
    existing?.schedule?.length
      ? (existing.schedule as Block[])
      : kind === "weekday"
        ? DEFAULT_WEEKDAY
        : DEFAULT_WEEKEND
  );

  function update(i: number, patch: Partial<Block>) {
    setSchedule((s) => s.map((b, idx) => (idx === i ? { ...b, ...patch } : b)));
  }
  function addBlock() {
    setSchedule((s) => [...s, { time_label: "00:00 — 00:00", title: "New block", body: "", intensity: "normal" }]);
  }
  function removeBlock(i: number) {
    setSchedule((s) => s.filter((_, idx) => idx !== i));
  }
  function move(i: number, dir: -1 | 1) {
    setSchedule((s) => {
      const ni = i + dir;
      if (ni < 0 || ni >= s.length) return s;
      const next = [...s];
      [next[i], next[ni]] = [next[ni], next[i]];
      return next;
    });
  }
  function loadDefaults() {
    setSchedule(kind === "weekday" ? DEFAULT_WEEKDAY : DEFAULT_WEEKEND);
  }

  async function onSave() {
    setBusy(true);
    setMsg(null);
    setErr(null);
    try {
      const r = await fetch("/api/plan-templates", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind,
          mission: mission || null,
          target_calls: Number(calls) || 0,
          target_emails: Number(emails) || 0,
          target_bookings: Number(bookings) || 1,
          schedule,
          enabled: true,
        }),
      });
      const body = await r.json();
      if (!r.ok || !body.ok) {
        setErr(body.error || `error ${r.status}`);
        return;
      }
      // Re-materialize today's plan if it matches this template's day type
      const todayDow = new Date().getDay();
      const isWeekend = todayDow === 0 || todayDow === 6;
      const matchesToday = (kind === "weekend" && isWeekend) || (kind === "weekday" && !isWeekend);
      if (matchesToday) {
        await fetch("/api/daily-plan/materialize", { method: "POST" }).catch(() => {});
      }
      setMsg("Saved.");
      router.refresh();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid sm:grid-cols-4 gap-3">
        <div className="sm:col-span-4">
          <div className="label">Mission</div>
          <input
            className="input"
            placeholder="e.g. 27 cold calls + Jonathan close + 10 follow-ups"
            value={mission}
            onChange={(e) => setMission(e.target.value)}
          />
        </div>
        <div>
          <div className="label">Target calls</div>
          <input className="input" type="number" value={calls} onChange={(e) => setCalls(e.target.value)} />
        </div>
        <div>
          <div className="label">Target emails</div>
          <input className="input" type="number" value={emails} onChange={(e) => setEmails(e.target.value)} />
        </div>
        <div>
          <div className="label">Target bookings</div>
          <input className="input" type="number" value={bookings} onChange={(e) => setBookings(e.target.value)} />
        </div>
      </div>

      <div className="flex items-center justify-between pt-2">
        <div className="label !mb-0">Blocks ({schedule.length})</div>
        <div className="flex items-center gap-2">
          <button onClick={loadDefaults} className="btn-secondary inline-flex items-center gap-1.5 !text-xs !py-1.5">
            <Wand2 size={12} /> Load defaults
          </button>
          <button onClick={addBlock} className="btn-secondary inline-flex items-center gap-1.5 !text-xs !py-1.5">
            <Plus size={12} /> Add block
          </button>
        </div>
      </div>

      <ul className="space-y-2">
        {schedule.map((b, i) => (
          <li key={i} className="rounded-lg border border-bg-border bg-bg-elev p-3">
            <div className="grid sm:grid-cols-[8rem_1fr_8rem_auto] gap-2">
              <input
                className="input !py-1.5 !text-xs font-mono"
                placeholder="08:00 — 09:00"
                value={b.time_label}
                onChange={(e) => update(i, { time_label: e.target.value })}
              />
              <input
                className="input !py-1.5"
                placeholder="Block title"
                value={b.title}
                onChange={(e) => update(i, { title: e.target.value })}
              />
              <select
                className="select !py-1.5 !text-xs"
                value={b.intensity || "normal"}
                onChange={(e) => update(i, { intensity: e.target.value as Block["intensity"] })}
              >
                <option value="intense">intense</option>
                <option value="normal">normal</option>
                <option value="break">break</option>
              </select>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => move(i, -1)}
                  disabled={i === 0}
                  className="text-fg-muted hover:text-fg disabled:opacity-30 p-1"
                  title="Move up"
                >
                  <ArrowUp size={14} />
                </button>
                <button
                  onClick={() => move(i, 1)}
                  disabled={i === schedule.length - 1}
                  className="text-fg-muted hover:text-fg disabled:opacity-30 p-1"
                  title="Move down"
                >
                  <ArrowDown size={14} />
                </button>
                <button onClick={() => removeBlock(i)} className="btn-danger !p-1.5" title="Remove">
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
            <textarea
              className="textarea !mt-2 !min-h-[44px]"
              placeholder="What to do in this block."
              value={b.body}
              onChange={(e) => update(i, { body: e.target.value })}
              rows={2}
            />
          </li>
        ))}
      </ul>

      <div className="flex items-center gap-3 pt-2">
        <button onClick={onSave} disabled={busy} className="btn-primary inline-flex items-center gap-2">
          <Save size={14} /> {busy ? "Saving…" : `Save ${kind} template`}
        </button>
        {msg && <span className="text-status-engaged text-sm">{msg}</span>}
        {err && <span className="text-status-hot text-sm">{err}</span>}
      </div>
    </div>
  );
}
