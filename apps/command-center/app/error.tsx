"use client";

/**
 * Root error boundary. Next.js renders this when ANY server component
 * inside the dashboard shell throws — instead of the framework's default
 * stark white page.
 *
 * Most readers in /today, /pipeline, /analytics, etc are wrapped in
 * `safe(p, fallback)` so individual queries can't get here. This catches
 * the residual class: a bug in render code, a misconfigured env, a
 * Supabase outage that takes the whole call down.
 */

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RefreshCw, Home } from "lucide-react";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log to console — Vercel captures this in the Function Logs view.
    // No third-party telemetry yet; this is the diagnostic surface.
    console.error("[error.tsx]", error);
  }, [error]);

  return (
    <div className="min-h-[60vh] flex items-center justify-center px-6 py-16">
      <div className="max-w-md w-full rounded-2xl border border-status-warm/30 bg-bg-elev p-7 space-y-4">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-status-warm/15 border border-status-warm/30 flex items-center justify-center text-status-warm">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <h1 className="text-base font-bold text-fg">Something broke on this page</h1>
        </div>
        <p className="text-sm text-fg-muted leading-relaxed">
          The dashboard caught an unexpected error rendering this view. Other
          pages should still work. If this keeps happening, capture the digest
          below and check the Vercel function logs.
        </p>
        {error.digest && (
          <div className="text-[11px] font-mono text-fg-dim bg-bg-deep border border-bg-border rounded-md px-3 py-2 break-all">
            digest: {error.digest}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <button
            onClick={() => reset()}
            className="btn-primary inline-flex items-center gap-1.5 text-sm"
          >
            <RefreshCw className="w-4 h-4" /> Try again
          </button>
          <Link href="/" className="btn-secondary inline-flex items-center gap-1.5 text-sm">
            <Home className="w-4 h-4" /> Today
          </Link>
        </div>
      </div>
    </div>
  );
}
