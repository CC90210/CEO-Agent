"use client";

/**
 * ScoreLeadButton — "Score with AI" CTA on the lead detail page.
 *
 * Phase 5a. Hits POST /api/leads/[id]/score → Claude returns a 0-100
 * score + 1-2 sentence rationale → the route writes them back to the
 * lead's data jsonb. After the call returns, we refresh() so the
 * server-rendered form picks up the new ai_score / ai_reasoning /
 * ai_scored_at values.
 *
 * The button shows three faces:
 *   - Idle:    "Score with AI" (sparkles icon)
 *   - Loading: "Scoring..."     (spinner)
 *   - Result:  the most recent score + rationale, persisted until next refresh
 *
 * Errors render inline below the button. Most likely error today is
 * "anthropic_key_missing" — the dashboard's Vercel env doesn't yet have
 * BRAVO_ANTHROPIC_API_KEY. The button surfaces that as a friendly hint
 * with the env-var name so CC can copy-paste the fix.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Sparkles, Loader2, AlertCircle } from "lucide-react";

type ScoreOk = { ok: true; score: number; reasoning: string; scored_at: string };
type ScoreErr = { ok: false; error: string; message?: string };

export function ScoreLeadButton({
  leadId,
  existingScore,
  existingReasoning,
  existingScoredAt,
}: {
  leadId: string;
  existingScore?: number | null;
  existingReasoning?: string | null;
  existingScoredAt?: string | null;
}) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ScoreOk | null>(null);
  const [error, setError] = useState<{ error: string; message?: string } | null>(null);

  const displayScore = result?.score ?? existingScore ?? null;
  const displayReasoning = result?.reasoning ?? existingReasoning ?? null;
  const displayScoredAt = result?.scored_at ?? existingScoredAt ?? null;

  async function runScoring() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/leads/${leadId}/score`, { method: "POST" });
      const json = (await res.json()) as ScoreOk | ScoreErr;
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
    <div className="rounded-lg border border-accent/30 bg-accent/5 p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-accent" />
            <span className="font-bold text-sm text-fg">AI Lead Score</span>
            {displayScore != null && (
              <span className="text-2xl font-bold text-accent">{displayScore}</span>
            )}
          </div>
          {displayScoredAt && (
            <div className="text-[10px] text-fg-faint mt-0.5">
              Scored {new Date(displayScoredAt).toLocaleString()}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={runScoring}
          disabled={loading}
          className="btn-send inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs disabled:opacity-50"
        >
          {loading ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Scoring...
            </>
          ) : (
            <>
              <Sparkles className="w-3.5 h-3.5" />
              {displayScore != null ? "Re-score" : "Score with AI"}
            </>
          )}
        </button>
      </div>

      {displayReasoning && (
        <div className="text-sm text-fg-muted leading-snug">{displayReasoning}</div>
      )}

      {error && (
        <div className="flex items-start gap-2 text-xs text-status-warm bg-status-warm/5 border border-status-warm/30 rounded p-2.5">
          <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <div>
            {error.error === "ai_unavailable" ? (
              <>
                <span className="font-bold">AI key not configured. </span>
                Set <code className="font-mono">BRAVO_ANTHROPIC_API_KEY</code> on the
                dashboard&apos;s Vercel env to enable scoring.
              </>
            ) : (
              <>
                <span className="font-bold">{error.error}: </span>
                {error.message || "scoring failed"}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
