"use client";

export function ChannelGauge({
  channel,
  used,
  cap,
  pct,
}: {
  channel: string;
  used: number;
  cap: number;
  pct: number;
}) {
  const safe = Math.min(pct, 100);
  const color =
    pct >= 90
      ? "#ef4444"
      : pct >= 60
        ? "#f59e0b"
        : pct > 0
          ? "#e8c547"
          : "#5b6068";

  // Half-doughnut: stroke-dasharray trick on an SVG circle
  const radius = 36;
  const circ = Math.PI * radius;
  const stroke = (safe / 100) * circ;

  return (
    <div className="flex flex-col items-center justify-between bg-bg-elev rounded-xl border border-bg-border p-4">
      <div className="text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold mb-1">
        {channel}
      </div>
      <div className="relative h-20 w-24 mt-1">
        <svg viewBox="0 0 100 60" className="w-full h-full">
          {/* Track */}
          <path
            d={`M 14 50 A ${radius} ${radius} 0 0 1 86 50`}
            fill="none"
            stroke="#22262e"
            strokeWidth="6"
            strokeLinecap="round"
          />
          {/* Fill */}
          <path
            d={`M 14 50 A ${radius} ${radius} 0 0 1 86 50`}
            fill="none"
            stroke={color}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={`${stroke} ${circ}`}
            style={{ transition: "stroke-dasharray 0.6s ease-out" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-end pb-0.5">
          <div
            className="text-lg font-bold leading-none"
            style={{ color }}
          >
            {used}
          </div>
          <div className="text-[10px] text-fg-dim mt-0.5">/ {cap}</div>
        </div>
      </div>
    </div>
  );
}
