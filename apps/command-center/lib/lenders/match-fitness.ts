/**
 * lenders/match-fitness.ts — score each lender against a specific
 * application's profile so the operator's shop-out UI can rank lenders
 * from "best fit" to "longshot" instead of showing all 50 alphabetically.
 *
 * Phase 6.2 of the SunBiz CRM build (2026-05-15). The actual UI lives in
 * Phase 6.3's Application detail page; this file is the pure-data helper
 * both the dashboard and Solara's tool calls consume.
 *
 * Scoring philosophy:
 *   - Hard gates (zero score): lender's floor exceeds the lead's data.
 *     A lender requiring $50k/month rev shouldn't show for a $20k/month
 *     lead — the offer would always come back as decline.
 *   - Soft penalties: data missing on the lender or the lead. Operator
 *     can still pick the lender, but the score reflects uncertainty.
 *   - Product-match bonus: when the application asks for an MCA and the
 *     lender's product_types includes "mca", that's a strong signal.
 *
 * Returns a score in [0, 100] plus the reasons list so the operator
 * can see WHY a lender ranked where it did ("FICO 580 below 620 floor").
 */

export type LenderProfile = {
  id: string;
  name: string;
  product_types?: string | string[];
  min_monthly_revenue?: number;
  max_funded_amount?: number;
  min_time_in_business_months?: number;
  fico_floor?: number;
  sla_response_days?: number;
  notes?: string;
};

export type ApplicationProfile = {
  id: string;
  /** From the form_submissions or manual operator entry. */
  monthly_revenue?: number;
  time_in_business_months?: number;
  applicant_fico?: number;
  requested_amount?: number;
  /** Operator-set; matches lender product_types. */
  desired_product?: string;
};

export type MatchScore = {
  lender_id: string;
  score: number;
  /** Plain-English bullet points the UI surfaces in a tooltip. */
  reasons: string[];
  /** Hard gate failures (score=0 implies at least one) for operator clarity. */
  blockers: string[];
};

function normalizeProductTypes(v: LenderProfile["product_types"]): string[] {
  if (Array.isArray(v)) return v.map((s) => s.trim()).filter(Boolean);
  if (typeof v === "string" && v.trim()) {
    // Operators sometimes enter as comma-separated text via the JSONB
    // wide-row UI. Tolerate both shapes.
    return v.split(",").map((s) => s.trim()).filter(Boolean);
  }
  return [];
}

/**
 * Score one lender against one application. Pure function — no DB
 * calls. Pass profiles in; get a score out. Caller batches over a
 * list of lenders for the shop-out UI.
 */
export function scoreLenderMatch(
  lender: LenderProfile,
  application: ApplicationProfile,
): MatchScore {
  const reasons: string[] = [];
  const blockers: string[] = [];
  let score = 100;

  // ── Hard gate: revenue floor ──────────────────────────────────────
  if (lender.min_monthly_revenue !== undefined && application.monthly_revenue !== undefined) {
    if (application.monthly_revenue < lender.min_monthly_revenue) {
      blockers.push(
        `Monthly revenue $${application.monthly_revenue.toLocaleString()} below lender floor $${lender.min_monthly_revenue.toLocaleString()}`,
      );
    } else {
      reasons.push(
        `Revenue $${application.monthly_revenue.toLocaleString()} clears $${lender.min_monthly_revenue.toLocaleString()} floor`,
      );
    }
  } else if (lender.min_monthly_revenue !== undefined) {
    score -= 10;
    reasons.push("Lender requires revenue floor; application doesn't report monthly revenue");
  }

  // ── Hard gate: time in business ────────────────────────────────────
  if (
    lender.min_time_in_business_months !== undefined &&
    application.time_in_business_months !== undefined
  ) {
    if (application.time_in_business_months < lender.min_time_in_business_months) {
      blockers.push(
        `Time in business ${application.time_in_business_months}mo below lender floor ${lender.min_time_in_business_months}mo`,
      );
    } else {
      reasons.push(
        `${application.time_in_business_months}mo TIB clears ${lender.min_time_in_business_months}mo floor`,
      );
    }
  } else if (lender.min_time_in_business_months !== undefined) {
    score -= 5;
  }

  // ── Hard gate: FICO floor ──────────────────────────────────────────
  if (lender.fico_floor !== undefined && application.applicant_fico !== undefined) {
    if (application.applicant_fico < lender.fico_floor) {
      blockers.push(
        `FICO ${application.applicant_fico} below ${lender.fico_floor} floor`,
      );
    } else {
      reasons.push(`FICO ${application.applicant_fico} clears ${lender.fico_floor} floor`);
    }
  } else if (lender.fico_floor !== undefined) {
    score -= 5;
  }

  // ── Hard gate: max funded amount ───────────────────────────────────
  if (
    lender.max_funded_amount !== undefined &&
    application.requested_amount !== undefined &&
    application.requested_amount > lender.max_funded_amount
  ) {
    blockers.push(
      `Requested $${application.requested_amount.toLocaleString()} exceeds lender max $${lender.max_funded_amount.toLocaleString()}`,
    );
  }

  // ── Soft signal: product-match bonus ───────────────────────────────
  const lenderProducts = normalizeProductTypes(lender.product_types);
  if (application.desired_product && lenderProducts.length > 0) {
    if (lenderProducts.includes(application.desired_product)) {
      reasons.push(`Product match: lender offers ${application.desired_product}`);
    } else {
      score -= 15;
      reasons.push(
        `Product mismatch: lender offers ${lenderProducts.join(", ")}; deal wants ${application.desired_product}`,
      );
    }
  }

  // ── Soft signal: SLA visibility ────────────────────────────────────
  if (lender.sla_response_days !== undefined) {
    reasons.push(`SLA: ${lender.sla_response_days}d typical response`);
  }

  // If any hard gate fired, score collapses to 0 regardless of soft
  // signals — operator can still override by manually picking, but the
  // rank will be honest about which lenders are likely to decline.
  if (blockers.length > 0) {
    return { lender_id: lender.id, score: 0, reasons, blockers };
  }

  // Clamp below 0 to 0 (defensive against future soft-penalty changes).
  return {
    lender_id: lender.id,
    score: Math.max(0, Math.min(100, score)),
    reasons,
    blockers,
  };
}

/**
 * Batch wrapper — score every lender against an application + sort
 * by score descending. Operator UI consumes the sorted list directly.
 */
export function rankLenders(
  lenders: LenderProfile[],
  application: ApplicationProfile,
): MatchScore[] {
  return lenders
    .map((l) => scoreLenderMatch(l, application))
    .sort((a, b) => b.score - a.score);
}
