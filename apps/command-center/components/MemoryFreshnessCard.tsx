/**
 * A3: Memory freshness panel — surfaces CLAUDE.md Rule 0 staleness gate
 * in the dashboard. Shows each tracked brain/* + memory/* file with its
 * relative age and a STALE tag if it's older than 7 days.
 *
 * Server-only data — receives the rows pre-computed from
 * lib/memory-freshness.ts so this stays a pure presentational component.
 */

import { Card, Tag } from "./Card";
import { type MemoryFreshness, STALE_DAYS } from "@/lib/memory-freshness";

function _ageLabel(days: number | null): string {
  if (days === null) return "—";
  if (days < 1 / 24) return "just now";
  if (days < 1) {
    const h = Math.floor(days * 24);
    return `${h}h ago`;
  }
  return `${Math.floor(days)}d ago`;
}

export function MemoryFreshnessCard({ rows }: { rows: MemoryFreshness[] }) {
  const stale = rows.filter((r) => r.isStale).length;
  const missing = rows.filter((r) => !r.exists).length;
  const subtitle =
    stale > 0 || missing > 0
      ? `${stale} stale · ${missing} missing — refresh per CLAUDE.md Rule 0`
      : "All tracked memory files updated within the last 7 days.";
  return (
    <Card title="Memory freshness" subtitle={subtitle}>
      <ul className="divide-y divide-bg-border">
        {rows.map((r) => (
          <li
            key={r.label}
            className="flex items-center justify-between py-2 text-sm"
          >
            <div className="flex items-center gap-2 min-w-0">
              <span
                className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                  !r.exists
                    ? "bg-fg-faint"
                    : r.isStale
                      ? "bg-status-warm"
                      : "bg-status-engaged"
                }`}
              />
              <span className="font-mono text-fg truncate">{r.label}</span>
              {r.source === "frontmatter" && (
                <span className="text-[10px] uppercase tracking-wider text-fg-dim">
                  fm
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {!r.exists ? (
                <Tag tone="warm">missing</Tag>
              ) : r.isStale ? (
                <Tag tone="warm">stale &gt; {STALE_DAYS}d</Tag>
              ) : null}
              <span className="text-xs text-fg-muted font-mono">
                {_ageLabel(r.ageDays)}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
