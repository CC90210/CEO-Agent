"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const TZ = process.env.NEXT_PUBLIC_OPERATOR_TIMEZONE || "America/Toronto";

function fmt(opts: Intl.DateTimeFormatOptions, d: Date) {
  return new Intl.DateTimeFormat("en-US", { timeZone: TZ, ...opts }).format(d);
}

function operatorDateKey(d: Date): string {
  const parts: Record<string, string> = {};
  for (const p of new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(d)) {
    if (p.type !== "literal") parts[p.type] = p.value;
  }
  return `${parts.year}-${parts.month}-${parts.day}`;
}

/**
 * Renders the operator-timezone-correct date + clock and auto-refreshes:
 *   - Clock ticks every 30s (no page reload).
 *   - When the wall-clock date rolls over (midnight in operator TZ), the
 *     route is server-refreshed so the schedule + Today plan re-fetch for
 *     the new day. CC's tab can stay open across midnight without showing
 *     stale "yesterday".
 */
export function LiveClock({ initialDateKey }: { initialDateKey: string }) {
  const router = useRouter();
  const [now, setNow] = useState<Date>(() => new Date());

  useEffect(() => {
    const tick = () => {
      const d = new Date();
      setNow(d);
      if (operatorDateKey(d) !== initialDateKey) {
        router.refresh();
      }
    };
    tick();
    const id = setInterval(tick, 30_000);
    return () => clearInterval(id);
  }, [initialDateKey, router]);

  const dateLabel = fmt(
    { weekday: "long", month: "long", day: "numeric" },
    now
  );
  const timeLabel = fmt(
    { hour: "numeric", minute: "2-digit", hour12: true },
    now
  );

  return (
    <span className="inline-flex items-baseline gap-2">
      <span>{dateLabel}</span>
      <span className="text-fg-dim text-xs font-mono tabular-nums">
        {timeLabel}
      </span>
    </span>
  );
}
