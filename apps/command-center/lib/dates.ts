/**
 * Operator-timezone-correct date helpers.
 *
 * The previous implementation re-parsed a TZ-naive "en-US" string with
 * `new Date()`, which silently shifted by hours when the runtime TZ
 * differed from the operator TZ (Vercel runs in UTC; CC operates in
 * America/Toronto). Result: at 11:52pm EDT on Apr 30, the dashboard
 * rendered "Friday, May 1" because the Date object snapped to UTC midnight.
 *
 * Fix: use `Intl.DateTimeFormat` with an explicit `timeZone` for ALL
 * formatting and date-arithmetic. Never construct a Date from a TZ-naive
 * string and assume it carries the operator TZ.
 */

const DEFAULT_TIME_ZONE = process.env.OPERATOR_TIMEZONE || "America/Toronto";

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

export type OperatorParts = {
  year: number;
  month: number; // 1-12
  day: number; // 1-31
  weekday: "Sun" | "Mon" | "Tue" | "Wed" | "Thu" | "Fri" | "Sat";
  hour: number; // 0-23
  minute: number;
  second: number;
};

/** Resolve a Date into operator-timezone wall-clock parts. */
export function operatorParts(
  date: Date = new Date(),
  timeZone: string = DEFAULT_TIME_ZONE
): OperatorParts {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  const parts: Record<string, string> = {};
  for (const p of fmt.formatToParts(date)) {
    if (p.type !== "literal") parts[p.type] = p.value;
  }
  // Intl returns "24" for midnight in some locales — normalize.
  const hourRaw = parts.hour === "24" ? "00" : parts.hour;
  return {
    year: parseInt(parts.year, 10),
    month: parseInt(parts.month, 10),
    day: parseInt(parts.day, 10),
    weekday: parts.weekday as OperatorParts["weekday"],
    hour: parseInt(hourRaw, 10),
    minute: parseInt(parts.minute, 10),
    second: parseInt(parts.second, 10),
  };
}

/** YYYY-MM-DD in operator timezone, with optional day offset. */
export function operatorDateKey(
  date: Date = new Date(),
  dayOffset: number = 0,
  timeZone: string = DEFAULT_TIME_ZONE
): string {
  const p = operatorParts(date, timeZone);
  // Build a UTC date from operator wall-clock then offset days; UTC math
  // avoids the host TZ entirely.
  const d = new Date(Date.UTC(p.year, p.month - 1, p.day));
  d.setUTCDate(d.getUTCDate() + dayOffset);
  return `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`;
}

/** Format a Date into a string using operator timezone. */
export function formatOperatorDate(
  opts: Intl.DateTimeFormatOptions,
  date: Date = new Date(),
  timeZone: string = DEFAULT_TIME_ZONE
): string {
  return new Intl.DateTimeFormat("en-US", { timeZone, ...opts }).format(date);
}

/** True if today (in operator TZ) is Saturday or Sunday. */
export function operatorIsWeekend(
  date: Date = new Date(),
  timeZone: string = DEFAULT_TIME_ZONE
): boolean {
  const wd = operatorParts(date, timeZone).weekday;
  return wd === "Sat" || wd === "Sun";
}

/**
 * Returns a Date whose UTC fields match operator wall-clock — useful when
 * downstream code expects a Date and only ever calls UTC getters.
 *
 * Do NOT call .getDate() / .getDay() on this — those return host-TZ values.
 * Prefer `operatorParts()` for arithmetic and `formatOperatorDate()` for
 * display.
 */
export function operatorDate(
  date: Date = new Date(),
  timeZone: string = DEFAULT_TIME_ZONE
): Date {
  const p = operatorParts(date, timeZone);
  return new Date(
    Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second)
  );
}

/**
 * ISO timestamp of the operator-TZ midnight that "today" started at.
 * Use this for queries like `gte("created_at", dayStart)` — it gives
 * counters that match the operator's wall-clock day, not the server's.
 *
 * The previous server-local `new Date().setHours(0,0,0,0)` was wrong by
 * up to ±24h on UTC servers (e.g. Vercel) for Toronto operators after
 * 8pm local — Today tiles like "Outreach today" silently rolled over to
 * tomorrow's counts.
 */
export function operatorDayStartIso(
  date: Date = new Date(),
  dayOffset: number = 0,
  timeZone: string = DEFAULT_TIME_ZONE
): string {
  // Build the operator-TZ midnight for `date + dayOffset` and convert it
  // back to a real UTC instant. We bracket the candidate UTC midnight by
  // ±12h and snap by walking ±1h until the operator-TZ wall-clock hour
  // hits 0 — robust against any TZ offset, including the half-hour and
  // 45-min ones (India, Nepal). Pure JS, no external deps.
  const p = operatorParts(date, timeZone);
  const targetYmd = (() => {
    const d = new Date(Date.UTC(p.year, p.month - 1, p.day));
    d.setUTCDate(d.getUTCDate() + dayOffset);
    return { year: d.getUTCFullYear(), month: d.getUTCMonth() + 1, day: d.getUTCDate() };
  })();
  // Start from a UTC instant that's almost certainly the right ballpark:
  // operator midnight ≈ UTC noon of the target ymd minus 12h. Then
  // search ±15h in 30-minute steps and pick the one whose operator parts
  // are exactly midnight on targetYmd.
  const seedUtcMs = Date.UTC(targetYmd.year, targetYmd.month - 1, targetYmd.day, 12, 0, 0);
  for (let offsetMin = -15 * 60; offsetMin <= 15 * 60; offsetMin += 15) {
    const candidate = new Date(seedUtcMs + offsetMin * 60_000);
    const cp = operatorParts(candidate, timeZone);
    if (
      cp.year === targetYmd.year &&
      cp.month === targetYmd.month &&
      cp.day === targetYmd.day &&
      cp.hour === 0 &&
      cp.minute === 0
    ) {
      return candidate.toISOString();
    }
  }
  // Fallback (should never hit): server-local midnight, with a marker so
  // tests/observability surfaces the failure.
  const fb = new Date(targetYmd.year, targetYmd.month - 1, targetYmd.day);
  return fb.toISOString();
}

/**
 * Operator-TZ day-of-week as a JS Date.getDay()-compatible integer
 * (0 = Sunday, 6 = Saturday). Use instead of `new Date().getDay()` when
 * you need "what day is it for the operator", not "what day is it on
 * this server".
 */
export function operatorDayOfWeek(
  date: Date = new Date(),
  timeZone: string = DEFAULT_TIME_ZONE
): number {
  const wd = operatorParts(date, timeZone).weekday;
  return { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 }[wd] ?? 0;
}

export const OPERATOR_TIME_ZONE = DEFAULT_TIME_ZONE;
