"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { beginInflight } from "@/lib/today-inflight";

/**
 * Inline checkbox to mark a Today schedule block as completed. Optimistic
 * UI: flips locally, fires the PATCH, reverts on error. Registers with the
 * today-inflight counter so FinalizeDayButton refuses to fire while a
 * toggle PATCH is still in transit (race-vs-streak avoidance).
 */
export function TodayBlockToggle({
  index,
  initial,
  schedule,
}: {
  index: number;
  initial: boolean;
  schedule: Array<Record<string, unknown>>;
}) {
  const router = useRouter();
  const [done, setDone] = useState(initial);
  const [busy, setBusy] = useState(false);

  async function toggle() {
    if (busy) return;
    const next = !done;
    setDone(next);
    setBusy(true);
    const releaseInflight = beginInflight();
    try {
      // Stamp completed_at ISO when toggling on, null when toggling off,
      // so the streak computer + the "✓ done · 9:42 AM" pill have a
      // real timestamp instead of inferring from updated_at.
      const completedAt = next ? new Date().toISOString() : null;
      const updated = schedule.map((b, i) =>
        i === index
          ? { ...b, completed: next, completed_at: completedAt }
          : b
      );
      const r = await fetch("/api/daily-plan", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ schedule: updated }),
      });
      if (!r.ok) {
        setDone(!next);
      } else {
        router.refresh();
      }
    } catch {
      setDone(!next);
    } finally {
      releaseInflight();
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      title={done ? "Mark not done" : "Mark done"}
      className={`shrink-0 w-5 h-5 rounded border flex items-center justify-center transition-all ${
        done
          ? "bg-status-engaged border-status-engaged text-bg"
          : "border-bg-border bg-bg-elev text-transparent hover:border-accent"
      }`}
    >
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path
          d="M2.5 6.5L5 9L9.5 3.5"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
}
