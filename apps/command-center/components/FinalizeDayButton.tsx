"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Loader2 } from "lucide-react";

/**
 * Operator's nightly checkpoint. Sets daily_plans.finalized_at via PATCH so
 * tomorrow's materializer + the streak computer can read the signal. The
 * server doesn't reset anything here — tomorrow's cron rebuilds the plan
 * from the template regardless. Finalize is just the wrap.
 */
export function FinalizeDayButton({ disabled, planId }: { disabled: boolean; planId: string | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function finalize() {
    if (busy || disabled) return;
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

  return (
    <button
      type="button"
      onClick={finalize}
      disabled={disabled || busy || !planId}
      className={`btn-send text-sm ${disabled ? "opacity-40 cursor-not-allowed" : ""}`}
      title={disabled ? "Check every item to enable" : "Mark today done"}
    >
      {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
      Finalize day
    </button>
  );
}
