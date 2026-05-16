"use client";

/**
 * ApplicationCardActions — "Recommended lenders" + inline panel for
 * application Kanban cards (Phase 10.3 of SunBiz CRM).
 *
 * On click, hits POST /api/applications/<id>/match-lenders which:
 *   - reads the application's underwriting_jsonb (or raw fields)
 *   - scores every tenant lender's fit (rule-based: monthly revenue,
 *     amount, time-in-business, FICO, product type)
 *   - returns the top 8 with per-requirement pass/fail breakdown
 *
 * Renders inline below the card so the operator can scan the list
 * without leaving the Kanban. Each lender row shows the score,
 * pass count, and an Add-to-shop-out button (Phase 6 wiring — uses
 * the existing /api/applications/<id>/shop-out endpoint).
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Sparkles,
  Loader2,
  AlertCircle,
  ChevronDown,
  Check,
  X,
  Send,
} from "lucide-react";

type CheckResult = {
  key: string;
  label: string;
  requirement: string;
  actual: string;
  passed: boolean;
};

type Ranked = {
  lender_id: string;
  name: string;
  score: number;
  passes: number;
  checks: CheckResult[];
};

type MatchResponse = {
  ok: boolean;
  application_summary?: {
    monthly_revenue: number | null;
    requested_amount: number | null;
    time_in_business_months: number | null;
    fico: number | null;
    product_type: string | null;
  };
  ranked?: Ranked[];
  total_lenders?: number;
  error?: string;
};

export function ApplicationCardActions({
  applicationId,
}: {
  applicationId: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<MatchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [shoppingOut, setShoppingOut] = useState<Set<string>>(new Set());
  const [shoppedOut, setShoppedOut] = useState<Set<string>>(new Set());

  async function loadMatches() {
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/applications/${applicationId}/match-lenders`,
        { method: "POST" },
      );
      const j = (await res.json()) as MatchResponse;
      if (!j.ok) {
        setError(j.error || `http_${res.status}`);
        return;
      }
      setData(j);
    } catch (e) {
      setError(e instanceof Error ? e.message : "network_error");
    } finally {
      setLoading(false);
    }
  }

  async function shopOut(lenderId: string) {
    setShoppingOut((s) => new Set(s).add(lenderId));
    try {
      const res = await fetch(`/api/applications/${applicationId}/shop-out`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ lender_ids: [lenderId] }),
      });
      const j = (await res.json()) as { ok: boolean; error?: string };
      if (j.ok) {
        setShoppedOut((s) => new Set(s).add(lenderId));
        router.refresh();
      } else {
        setError(`shop-out failed: ${j.error || `http_${res.status}`}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "network_error");
    } finally {
      setShoppingOut((s) => {
        const n = new Set(s);
        n.delete(lenderId);
        return n;
      });
    }
  }

  return (
    <div className="mt-2 pt-2 border-t border-bg-border">
      <button
        type="button"
        onClick={() => {
          const next = !open;
          setOpen(next);
          if (next && !data && !loading) loadMatches();
        }}
        className="w-full inline-flex items-center justify-between text-[11px] text-fg-muted hover:text-fg group"
      >
        <span className="inline-flex items-center gap-1.5">
          <Sparkles className="w-3 h-3 text-accent" />
          Recommended lenders
        </span>
        <ChevronDown
          className={`w-3 h-3 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          {loading && (
            <div className="text-[11px] text-fg-dim inline-flex items-center gap-1.5">
              <Loader2 className="w-3 h-3 animate-spin" /> Scoring lenders…
            </div>
          )}
          {error && (
            <div className="text-[11px] text-rose-300 inline-flex items-start gap-1">
              <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {data && data.ranked && data.ranked.length === 0 && (
            <div className="text-[11px] text-fg-dim italic">
              No lenders on file yet — add lenders under /lenders to enable scoring.
            </div>
          )}
          {data && data.ranked && data.ranked.length > 0 && (
            <ol className="space-y-1.5">
              {data.ranked.map((r) => (
                <li
                  key={r.lender_id}
                  className="rounded-md border border-bg-border bg-bg-elev/40 p-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-bold text-xs text-fg truncate">
                      {r.name}
                    </div>
                    <ScoreBadge passes={r.passes} total={r.checks.length} score={r.score} />
                  </div>
                  <ul className="mt-1 space-y-0.5 text-[10px]">
                    {r.checks.map((c) => (
                      <li
                        key={c.key}
                        className="inline-flex items-start gap-1.5 mr-3 text-fg-dim"
                      >
                        {c.passed ? (
                          <Check className="w-2.5 h-2.5 mt-0.5 text-status-engaged shrink-0" />
                        ) : (
                          <X className="w-2.5 h-2.5 mt-0.5 text-status-warm shrink-0" />
                        )}
                        <span>
                          <span className="text-fg-muted">{c.label}:</span> {c.actual}{" "}
                          <span className="text-fg-dim/70">({c.requirement})</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                  {shoppedOut.has(r.lender_id) ? (
                    <div className="mt-1.5 text-[10px] text-status-engaged inline-flex items-center gap-1">
                      <Check className="w-3 h-3" /> Shop-out queued
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => shopOut(r.lender_id)}
                      disabled={shoppingOut.has(r.lender_id)}
                      className="mt-1.5 inline-flex items-center gap-1 rounded-md bg-accent/10 hover:bg-accent/20 border border-accent/40 text-accent px-2 py-0.5 text-[10px] font-bold disabled:opacity-50"
                    >
                      {shoppingOut.has(r.lender_id) ? (
                        <Loader2 className="w-2.5 h-2.5 animate-spin" />
                      ) : (
                        <Send className="w-2.5 h-2.5" />
                      )}
                      Shop out
                    </button>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}

function ScoreBadge({
  passes,
  total,
  score,
}: {
  passes: number;
  total: number;
  score: number;
}) {
  const tone =
    score >= 0.8
      ? "border-status-engaged/50 bg-status-engaged/10 text-status-engaged"
      : score >= 0.5
        ? "border-accent/50 bg-accent/10 text-accent"
        : "border-status-warm/50 bg-status-warm/10 text-status-warm";
  return (
    <span
      className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${tone}`}
      title={`${passes} of ${total} requirements met`}
    >
      {passes}/{total}
    </span>
  );
}
