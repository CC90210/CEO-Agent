import type { ReactNode } from "react";

export function Card({
  title,
  subtitle,
  children,
  action,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-bg-border bg-bg-panel">
      <header className="flex items-start justify-between gap-4 border-b border-bg-border px-5 py-3">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-fg">
            {title}
          </h2>
          {subtitle && (
            <p className="text-xs text-fg-muted mt-0.5">{subtitle}</p>
          )}
        </div>
        {action}
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  accent = false,
}: {
  label: string;
  value: string | number;
  hint?: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-lg border border-bg-border bg-bg-panel p-5">
      <div className="text-xs uppercase tracking-wider text-fg-muted">
        {label}
      </div>
      <div
        className={`mt-2 text-3xl font-bold ${accent ? "text-accent" : "text-fg"}`}
      >
        {value}
      </div>
      {hint && <div className="mt-1 text-xs text-fg-dim">{hint}</div>}
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="text-center py-8 text-fg-muted text-sm">{message}</div>
  );
}
