/**
 * Gamified countdown card for the operator's north-star MRR goal.
 *
 * Two layers of motivation:
 *   1. The HARD numbers — gap to goal in dollars, days left, dollars/day
 *      needed (the math). No spin, just truth.
 *   2. A progress ring that fills with current/target so the operator
 *      sees the climb visually. Color shifts from amber (gap > 50%) to
 *      cyan (closing) to engaged-green (within 10%).
 *
 * Renders nothing if mrr.target is 0 (no goal set yet) so a fresh
 * tenant doesn't see a misleading "0 / 0" widget.
 */

import { Card } from "./Card";
import { Flame, Target, TrendingUp } from "lucide-react";

export function GoalCountdownCard({
  current,
  target,
  daysLeft,
  targetDate,
}: {
  current: number;
  target: number;
  daysLeft: number | null;
  targetDate: string | null;
}) {
  if (!target || target <= 0) return null;

  const pct = Math.max(0, Math.min(100, (current / target) * 100));
  const gap = Math.max(0, target - current);
  const dailyNeeded = daysLeft && daysLeft > 0 ? gap / daysLeft : null;

  // Color tier — the more behind, the warmer the color.
  const tier =
    pct >= 90
      ? { ring: "stroke-status-engaged", text: "text-status-engaged", glow: "0 0 16px rgba(16,185,129,0.45)" }
      : pct >= 60
        ? { ring: "stroke-accent", text: "text-accent", glow: "0 0 16px rgba(0,212,255,0.45)" }
        : pct >= 30
          ? { ring: "stroke-status-warm", text: "text-status-warm", glow: "0 0 16px rgba(245,158,11,0.45)" }
          : { ring: "stroke-status-hot", text: "text-status-hot", glow: "0 0 16px rgba(239,68,68,0.45)" };

  const radius = 52;
  const circ = 2 * Math.PI * radius;
  const dash = (pct / 100) * circ;

  return (
    <Card title="Goal countdown" subtitle="The climb to your north-star MRR — visible every day until it's done.">
      <div className="flex flex-col sm:flex-row items-center sm:items-stretch gap-6">
        {/* Progress ring */}
        <div className="relative flex-shrink-0" style={{ width: 140, height: 140 }}>
          <svg width="140" height="140" className="-rotate-90">
            <circle
              cx="70"
              cy="70"
              r={radius}
              fill="none"
              className="stroke-bg-border"
              strokeWidth="8"
            />
            <circle
              cx="70"
              cy="70"
              r={radius}
              fill="none"
              className={`${tier.ring} transition-all duration-700`}
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={`${dash} ${circ - dash}`}
              style={{ filter: `drop-shadow(${tier.glow})` }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={`text-2xl font-black ${tier.text}`}>{pct.toFixed(0)}%</span>
            <span className="text-[10px] uppercase tracking-wider text-fg-muted mt-0.5">of goal</span>
          </div>
        </div>

        {/* Stats grid */}
        <div className="flex-1 grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Tile
            icon={<Target className="w-4 h-4" />}
            label="Gap to goal"
            value={`$${Math.round(gap).toLocaleString()}`}
            hint={`of $${Math.round(target).toLocaleString()} target`}
          />
          <Tile
            icon={<Flame className="w-4 h-4" />}
            label="Days left"
            value={daysLeft !== null ? `${daysLeft}` : "—"}
            hint={targetDate ? `until ${targetDate.slice(5, 10)}` : "no deadline set"}
            urgent={!!daysLeft && daysLeft <= 14}
          />
          <Tile
            icon={<TrendingUp className="w-4 h-4" />}
            label="Daily need"
            value={dailyNeeded !== null && Number.isFinite(dailyNeeded) ? `$${Math.round(dailyNeeded).toLocaleString()}` : "—"}
            hint={dailyNeeded !== null ? "to hit on time" : "set a deadline"}
          />
        </div>
      </div>
    </Card>
  );
}

function Tile({
  icon,
  label,
  value,
  hint,
  urgent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
  urgent?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border p-3 ${
        urgent
          ? "border-status-hot/40 bg-status-hot/5"
          : "border-bg-border bg-bg-elev"
      }`}
    >
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-fg-muted">
        {icon}
        {label}
      </div>
      <div className={`text-xl font-black mt-1.5 ${urgent ? "text-status-hot" : "text-fg"}`}>
        {value}
      </div>
      {hint && (
        <div className="text-[11px] text-fg-dim mt-0.5">{hint}</div>
      )}
    </div>
  );
}
