"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Area,
  AreaChart,
} from "recharts";

export function MRRProgressChart({
  data,
  target,
}: {
  data: Array<{ date: string; mrr: number }>;
  target: number;
}) {
  return (
    <div className="h-48">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="mrrGold" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#e8c547" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#e8c547" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="date"
            tick={{ fill: "#5b6068", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "#22262e" }}
          />
          <YAxis
            tick={{ fill: "#5b6068", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => `$${(v / 1000).toFixed(1)}k`}
            domain={[0, Math.max(target, ...data.map((d) => d.mrr)) * 1.1]}
          />
          <Tooltip
            contentStyle={{
              background: "#0e1014",
              border: "1px solid #22262e",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#9ca0a8" }}
            formatter={(v: number) => [`$${v.toLocaleString()}`, "Net MRR"]}
          />
          <ReferenceLine
            y={target}
            stroke="#10b981"
            strokeDasharray="3 3"
            label={{
              value: `$${target.toLocaleString()}`,
              fill: "#10b981",
              fontSize: 11,
              position: "right",
            }}
          />
          <Area
            type="monotone"
            dataKey="mrr"
            stroke="#e8c547"
            strokeWidth={2}
            fill="url(#mrrGold)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
