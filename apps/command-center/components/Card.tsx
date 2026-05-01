import type { ReactNode } from "react";

export function Card({
  title,
  subtitle,
  children,
  action,
  noPadding = false,
}: {
  title?: string;
  subtitle?: ReactNode;
  children: ReactNode;
  action?: ReactNode;
  noPadding?: boolean;
}) {
  return (
    <section className="rounded-xl border border-bg-border bg-bg-panel shadow-card card-glow transition-all">
      {(title || subtitle || action) && (
        <header className="flex items-start justify-between gap-4 border-b border-bg-border px-5 py-3.5">
          <div>
            {title && (
              <h2 className="text-xs font-bold uppercase tracking-[0.14em] text-fg">
                {title}
              </h2>
            )}
            {subtitle && (
              <div className="text-xs text-fg-muted mt-1">{subtitle}</div>
            )}
          </div>
          {action}
        </header>
      )}
      <div className={noPadding ? "" : "p-5"}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  accent = false,
  delta,
  deltaLabel,
}: {
  label: string;
  value: string | number;
  hint?: string;
  accent?: boolean;
  delta?: number;
  deltaLabel?: string;
}) {
  const deltaPositive = typeof delta === "number" && delta > 0;
  const deltaNegative = typeof delta === "number" && delta < 0;
  return (
    <div className="rounded-xl border border-bg-border bg-bg-panel p-5 shadow-card scan-line transition-all hover:border-accent/40 hover:shadow-ironman group">
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-[0.14em] font-bold text-fg-muted">
          {label}
        </div>
        {typeof delta === "number" && (
          <span
            className={`text-[10px] font-bold ${
              deltaPositive
                ? "text-status-engaged"
                : deltaNegative
                  ? "text-status-hot"
                  : "text-fg-dim"
            }`}
          >
            {deltaPositive ? "▲" : deltaNegative ? "▼" : "·"}{" "}
            {Math.abs(delta).toFixed(1)}
            {deltaLabel ? ` ${deltaLabel}` : "%"}
          </span>
        )}
      </div>
      <div
        className={`mt-2 text-3xl font-bold tracking-tight tabular-nums ${
          accent ? "text-accent drop-shadow-[0_0_8px_rgba(59,130,246,0.35)]" : "text-fg"
        }`}
      >
        {value}
      </div>
      {hint && <div className="mt-1.5 text-xs text-fg-dim">{hint}</div>}
    </div>
  );
}

export function EmptyState({
  message,
  cta,
}: {
  message: string;
  cta?: ReactNode;
}) {
  return (
    <div className="text-center py-10 text-fg-muted text-sm">
      <div>{message}</div>
      {cta && <div className="mt-4">{cta}</div>}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <header className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-fg flex items-center gap-3">
          {title}
          <span className="h-px w-10 bg-gradient-to-r from-accent to-transparent" aria-hidden />
        </h1>
        {subtitle && (
          <div className="text-sm text-fg-muted mt-1.5">{subtitle}</div>
        )}
      </div>
      {action && <div>{action}</div>}
    </header>
  );
}

export function Tag({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "hot" | "warm" | "engaged" | "info";
}) {
  const tones: Record<string, string> = {
    neutral: "bg-bg-elev text-fg-muted border-bg-border",
    accent: "bg-accent-soft text-accent border-accent/30",
    hot: "bg-status-hot/10 text-status-hot border-status-hot/30",
    warm: "bg-status-warm/10 text-status-warm border-status-warm/30",
    engaged: "bg-status-engaged/10 text-status-engaged border-status-engaged/30",
    info: "bg-status-info/10 text-status-info border-status-info/30",
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-md border text-[10px] font-bold uppercase tracking-wider ${tones[tone]}`}
    >
      {children}
    </span>
  );
}
