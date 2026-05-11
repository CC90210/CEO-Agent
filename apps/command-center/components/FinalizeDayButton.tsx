"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Loader2 } from "lucide-react";
import { subscribeInflight } from "@/lib/today-inflight";

/**
 * Operator's nightly checkpoint. Sets daily_plans.finalized_at via PATCH so
 * tomorrow's materializer + the streak computer can read the signal. The
 * server doesn't reset anything here — tomorrow's cron rebuilds the plan
 * from the template regardless. Finalize is just the wrap.
 *
 * Subscribes to today-inflight: if any TodayBlockToggle PATCH is still in
 * transit, refuse to fire so the streak computer can't read a stale
 * schedule against a fresh finalized_at.
 */
export function FinalizeDayButton({ disabled, planId }: { disabled: boolean; planId: string | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [toggleInflight, setToggleInflight] = useState(0);

  useEffect(() => subscribeInflight(setToggleInflight), []);

  const blockedByToggle = toggleInflight > 0;

  async function finalize() {
    if (busy || disabled || blockedByToggle) return;
    setBusy(true);
    try {
      const r = await fetch("/api/daily-plan", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ finalized_at: new Date().toISOString() }),
      });
      if (r.ok) router.refresh();
    } finally {
      setBusy(false);
    }
  }

  const isDisabled = disabled || busy || blockedByToggle || !planId;
  const title = blockedByToggle
    ? "Waiting for the last toggle to land…"
    : disabled
    ? "Check every item to enable"
    : "Mark today done";

  return (
    <button
      type="button"
      onClick={finalize}
      disabled={isDisabled}
      className={`btn-send text-sm ${isDisabled ? "opacity-40 cursor-not-allowed" : ""}`}
      title={title}
    >
      {busy || blockedByToggle ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
      Finalize day
    </button>
  );
}
