"use client";

/**
 * NextActionButton — "Recommend next move" CTA on the lead detail page.
 *
 * Phase 5b. Same shape as ScoreLeadButton but a different endpoint and
 * a different display (action sentence + rationale, no numeric score).
 */

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Compass, Loader2, AlertCircle } from "lucide-react";

type ActionOk = { ok: true; action: string; rationale: string; generated_at: string };
type ActionErr = { ok: false; error: string; message?: string };

export function NextActionButton({
  leadId,
  existingAction,
  existingRationale,
  existingAt,
}: {
  leadId: string;
  existingAction?: string | null;
  existingRationale?: string | null;
  existingAt?: string | null;
}) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ActionOk | null>(null);
  const [error, setError] = useState<{ error: string; message?: string } | null>(null);

  const displayAction = result?.action ?? existingAction ?? null;
  const displayRationale = result?.rationale ?? existingRationale ?? null;
  const displayAt = result?.generated_at ?? existingAt ?? null;

  async function runRecommend() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/leads/${leadId}/next-action`, { method: "POST" });
      const json = (await res.json()) as ActionOk | ActionErr;
      if (!json.ok) {
        setError({ error: json.error, message: json.message });
      } else {
        setResult(json);
        router.refresh();
      }
    } catch (err) {
      setError({
        error: "network_error",
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-lg border border-status-engaged/30 bg-status-engaged/5 p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Compass className="w-4 h-4 text-status-engaged" />
          <span className="font-bold text-sm text-fg">Recommended next move</span>
          {displayAt && (
            <span className="text-[10px] text-fg-faint">
              · {new Date(displayAt).toLocaleString()}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={runRecommend}
          disabled={loading}
          className="btn-send inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs disabled:opacity-50"
        >
          {loading ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Thinking...
            </>
          ) : (
            <>
              <Compass className="w-3.5 h-3.5" />
              {displayAction ? "Re-recommend" : "Recommend"}
            </>
          )}
        </button>
      </div>

      {displayAction ? (
        <div className="space-y-1.5">
          <div className="text-fg font-medium leading-snug">{displayAction}</div>
          {displayRationale && (
            <div className="text-xs text-fg-muted leading-snug">{displayRationale}</div>
          )}
        </div>
      ) : !error ? (
        <div className="text-xs text-fg-muted italic">
          Click Recommend to have Bravo read this lead&apos;s history and suggest the next step.
        </div>
      ) : null}

      {error && (
        <div className="flex items-start gap-2 text-xs text-status-warm bg-status-warm/5 border border-status-warm/30 rounded p-2.5">
          <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <div>
            {error.error === "ai_unavailable" ? (
              <>
                <span className="font-bold">AI key not configured. </span>
                Set <code className="font-mono">BRAVO_ANTHROPIC_API_KEY</code> on the
                dashboard&apos;s Vercel env to enable next-move recommendations.
              </>
            ) : (
              <>
                <span className="font-bold">{error.error}: </span>
                {error.message || "recommendation failed"}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
