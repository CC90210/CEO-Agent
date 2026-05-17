"use client";

/**
 * OfferCardActions — Accept / Decline buttons inline on offer Kanban
 * cards (Phase 10.2 of SunBiz CRM).
 *
 * Mounted by ManifestKanban when entity.name === "offer" and the row's
 * stage is one of the "actionable" Opportunity Pipeline stages (post
 * 2026-05-17 Salesforce-parity rework: approved_open_offers /
 * contracts_ordered). Terminal stages (funded / no_offers_available /
 * approved_never_funded / dead_file) don't render this — the operator
 * can still edit via the record detail page, but a one-click flip on a
 * terminal stage is a footgun.
 *
 * Accept = POST /api/manifest/{slug}/offer/{id}/accept which:
 *   1. flips offer.stage → "funded" (fires status-change event)
 *   2. creates a draft funded_deal row carrying the offer's
 *      lead_id + lender_id + amount + term + funded_at=today
 *
 * Decline = quieter PATCH to /api/manifest/{slug}/records/offer to
 * flip stage → "dead_file" (the funding-shop equivalent of "client
 * killed it"; aligns with Adon's Salesforce vocabulary). No downstream
 * record creation.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, X, Loader2, AlertCircle } from "lucide-react";

type Props = {
  tenantSlug: string;
  offerId: string;
  stage: string;
};

export function OfferCardActions({ tenantSlug, offerId, stage }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState<null | "accept" | "decline">(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<null | "accept" | "decline">(null);

  // The two stages where Accept/Decline makes sense. Salesforce-parity
  // 2026-05-17: approved_open_offers (lender returned terms, awaiting
  // client signature) + contracts_ordered (contract sent, awaiting wire).
  const isActionable = stage === "approved_open_offers" || stage === "contracts_ordered";
  if (!isActionable) return null;

  async function accept() {
    setBusy("accept");
    setError(null);
    try {
      const res = await fetch(
        `/api/manifest/${tenantSlug}/offer/${offerId}/accept`,
        { method: "POST" },
      );
      const data = (await res.json()) as {
        ok: boolean;
        error?: string;
        already_accepted?: boolean;
        funded_deal_error?: string;
      };
      if (!data.ok) {
        setError(data.error || `http_${res.status}`);
        return;
      }
      setDone("accept");
      // Refresh the Kanban so the row moves to the Accepted column
      // and the funded_deal appears on /funded-deals.
      router.refresh();
      if (data.funded_deal_error) {
        setError(`Offer accepted, but the funded deal didn't save: ${data.funded_deal_error}. Create it manually from /funded-deals.`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "network_error");
    } finally {
      setBusy(null);
    }
  }

  async function decline() {
    if (!confirm("Mark this offer as declined? The lead can still receive other offers.")) return;
    setBusy("decline");
    setError(null);
    try {
      const res = await fetch(
        `/api/manifest/${tenantSlug}/records/offer?id=${encodeURIComponent(offerId)}`,
        {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ patch: { stage: "dead_file" } }),
        },
      );
      const data = (await res.json()) as { ok: boolean; error?: string };
      if (!data.ok) {
        setError(data.error || `http_${res.status}`);
        return;
      }
      setDone("decline");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "network_error");
    } finally {
      setBusy(null);
    }
  }

  if (done === "accept") {
    return (
      <div className="text-[11px] text-status-engaged inline-flex items-center gap-1 mt-2">
        <Check className="w-3 h-3" /> Accepted · funded deal drafted
      </div>
    );
  }
  if (done === "decline") {
    return (
      <div className="text-[11px] text-fg-dim inline-flex items-center gap-1 mt-2">
        <X className="w-3 h-3" /> Declined
      </div>
    );
  }

  return (
    <div className="mt-2 pt-2 border-t border-bg-border flex items-center gap-1.5">
      <button
        type="button"
        onClick={accept}
        disabled={busy !== null}
        className="inline-flex items-center gap-1 rounded-md bg-status-engaged/15 hover:bg-status-engaged/25 border border-status-engaged/40 text-status-engaged px-2 py-1 text-[11px] font-bold disabled:opacity-50"
        title="Mark accepted + create a draft funded deal"
      >
        {busy === "accept" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
        Accept
      </button>
      <button
        type="button"
        onClick={decline}
        disabled={busy !== null}
        className="inline-flex items-center gap-1 rounded-md bg-bg-deep hover:bg-bg-elev/60 border border-bg-border text-fg-muted px-2 py-1 text-[11px] disabled:opacity-50"
        title="Mark as dead file (client killed it — no funded deal created)"
      >
        {busy === "decline" ? <Loader2 className="w-3 h-3 animate-spin" /> : <X className="w-3 h-3" />}
        Decline
      </button>
      {error && (
        <span className="text-[10px] text-rose-300 inline-flex items-center gap-1 ml-1">
          <AlertCircle className="w-3 h-3 shrink-0" />
          {error}
        </span>
      )}
    </div>
  );
}
