"use client";

const STAGE_ORDER = ["new", "contacted", "qualified", "proposal", "won", "lost"] as const;
type Stage = (typeof STAGE_ORDER)[number];

const STAGE_COLORS: Record<Stage, string> = {
  new: "#60a5fa",
  contacted: "#9ca0a8",
  qualified: "#e8c547",
  proposal: "#f59e0b",
  won: "#10b981",
  lost: "#1f2937",
};

export function PipelineFunnel({
  stages,
}: {
  stages: Record<string, number>;
}) {
  const max = Math.max(1, ...STAGE_ORDER.map((s) => stages[s] || 0));

  return (
    <div className="space-y-2">
      {STAGE_ORDER.map((stage) => {
        const count = stages[stage] || 0;
        const pct = (count / max) * 100;
        return (
          <div key={stage} className="flex items-center gap-3">
            <div className="w-20 text-xs uppercase tracking-wider text-fg-muted font-bold">
              {stage}
            </div>
            <div className="flex-1 h-7 bg-bg-elev rounded-md overflow-hidden relative border border-bg-border">
              <div
                className="h-full transition-all duration-500 flex items-center px-2 text-xs font-bold"
                style={{
                  width: `${Math.max(pct, count > 0 ? 4 : 0)}%`,
                  background: STAGE_COLORS[stage],
                  color: stage === "lost" ? "#9ca0a8" : "#06070a",
                }}
              >
                {count > 0 && pct > 8 && count}
              </div>
              {pct <= 8 && count > 0 && (
                <div className="absolute right-2 top-0 h-full flex items-center text-xs text-fg-muted font-bold">
                  {count}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
