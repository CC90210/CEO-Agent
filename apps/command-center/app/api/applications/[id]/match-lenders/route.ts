/**
 * POST /api/applications/[id]/match-lenders — rank tenant lenders by
 * fit against this application's underwriting data.
 *
 * Phase 10.3 of SunBiz CRM. The Application detail page renders the
 * top results as a "Recommended Lenders" card so the operator can
 * shop the deal to the strongest fits in one click instead of
 * eyeballing every lender's requirements row-by-row.
 *
 * Scoring is rule-based, not LLM-based:
 *   - Each lender carries fields min_monthly_revenue, max_funded_amount,
 *     min_time_in_business_months, fico_floor, product_types[].
 *   - We compare each against the application data (or its
 *     underwriting_jsonb summary, populated by Phase 7's underwrite
 *     chain). Pass = the application meets/exceeds the requirement.
 *   - Score = passes / total_checks. Ties broken by max_funded_amount
 *     descending (bigger lenders win on equal fit).
 *
 * Why not LLM-narrative scoring: rule-based is faster, deterministic,
 * and the operator can reason about WHY a lender ranks high. The
 * sales-angle narrative is generated separately in Phase 7's
 * underwrite chain and surfaces in a different card.
 *
 * Response:
 *   { ok, application_summary: {...}, ranked: [{ lender, score,
 *     checks: [{key, requirement, actual, passed}] }] }
 */

import { NextRequest, NextResponse } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type LenderData = {
  id: string;
  name?: string;
  min_monthly_revenue?: number;
  max_funded_amount?: number;
  min_time_in_business_months?: number;
  fico_floor?: number;
  product_types?: string[] | string;
};

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

function num(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = Number(v.replace(/[^0-9.-]+/g, ""));
    return Number.isNaN(n) ? null : n;
  }
  return null;
}

export async function POST(
  _req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const db = getServiceSupabase();
  const profileRes = await db
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const tenantId = (profileRes.data as { tenant_id: string | null } | null)?.tenant_id ?? null;
  if (!tenantId) return NextResponse.json({ ok: false, error: "no_tenant" }, { status: 401 });

  const { id: applicationId } = await ctx.params;

  // Pull the application row.
  const appRow = await db
    .from("tenant_records")
    .select("id, data")
    .eq("tenant_id", tenantId)
    .eq("entity_type", "application")
    .eq("id", applicationId)
    .maybeSingle();
  if (appRow.error || !appRow.data) {
    return NextResponse.json({ ok: false, error: "application_not_found" }, { status: 404 });
  }
  const appData = (appRow.data as { data: Record<string, unknown> }).data || {};

  // Resolve the underwriting summary. Prefer the Phase 7 underwrite
  // chain's output if present; fall back to whatever's on the
  // application row directly (operator-entered fields).
  const underwriting = (appData.underwriting_jsonb || appData.underwriting || {}) as Record<string, unknown>;
  const monthlyRevenue =
    num(underwriting.monthly_revenue) ??
    num(underwriting.avg_monthly_deposits) ??
    num(appData.monthly_revenue);
  const requestedAmount =
    num(appData.requested_amount) ??
    num(appData.amount) ??
    num(underwriting.requested_amount);
  const timeInBusinessMonths =
    num(appData.time_in_business_months) ??
    num(appData.business_age_months) ??
    num(underwriting.time_in_business_months);
  const ficoScore =
    num(appData.fico) ??
    num(appData.fico_score) ??
    num(underwriting.fico);
  const productType =
    typeof appData.product_type === "string"
      ? (appData.product_type as string).toLowerCase()
      : typeof underwriting.product_type === "string"
        ? (underwriting.product_type as string).toLowerCase()
        : null;

  // Pull every lender for this tenant. Tenants typically have <50
  // lenders so we score in-memory.
  const lendersRes = await db
    .from("tenant_records")
    .select("id, data")
    .eq("tenant_id", tenantId)
    .eq("entity_type", "lender");
  if (lendersRes.error) {
    return NextResponse.json(
      { ok: false, error: "lenders_lookup_failed", detail: lendersRes.error.message },
      { status: 500 },
    );
  }

  const ranked: Ranked[] = (lendersRes.data || []).map((r) => {
    const data = ((r as { data: Record<string, unknown> }).data || {}) as LenderData;
    const checks: CheckResult[] = [];

    // Monthly revenue floor. If application doesn't have monthly
    // revenue, mark this check inconclusive (passed=false but with
    // 'unknown' actual) so the operator sees why the lender ranks low.
    if (typeof data.min_monthly_revenue === "number") {
      const passes = monthlyRevenue !== null && monthlyRevenue >= data.min_monthly_revenue;
      checks.push({
        key: "monthly_revenue",
        label: "Monthly revenue",
        requirement: `≥ $${data.min_monthly_revenue.toLocaleString()}`,
        actual: monthlyRevenue !== null ? `$${monthlyRevenue.toLocaleString()}` : "unknown",
        passed: passes,
      });
    }
    if (typeof data.max_funded_amount === "number" && requestedAmount !== null) {
      const passes = requestedAmount <= data.max_funded_amount;
      checks.push({
        key: "max_amount",
        label: "Funded amount",
        requirement: `≤ $${data.max_funded_amount.toLocaleString()}`,
        actual: `$${requestedAmount.toLocaleString()}`,
        passed: passes,
      });
    }
    if (typeof data.min_time_in_business_months === "number") {
      const passes =
        timeInBusinessMonths !== null && timeInBusinessMonths >= data.min_time_in_business_months;
      checks.push({
        key: "tib",
        label: "Time in business",
        requirement: `≥ ${data.min_time_in_business_months} months`,
        actual:
          timeInBusinessMonths !== null
            ? `${timeInBusinessMonths} months`
            : "unknown",
        passed: passes,
      });
    }
    if (typeof data.fico_floor === "number") {
      const passes = ficoScore !== null && ficoScore >= data.fico_floor;
      checks.push({
        key: "fico",
        label: "FICO",
        requirement: `≥ ${data.fico_floor}`,
        actual: ficoScore !== null ? `${ficoScore}` : "unknown",
        passed: passes,
      });
    }
    if (data.product_types && productType) {
      const allowed = Array.isArray(data.product_types)
        ? data.product_types
        : typeof data.product_types === "string"
          ? data.product_types.split(",").map((s) => s.trim())
          : [];
      const passes = allowed.length === 0 || allowed.includes(productType);
      checks.push({
        key: "product",
        label: "Product type",
        requirement: allowed.length === 0 ? "(any)" : allowed.join(", "),
        actual: productType,
        passed: passes,
      });
    }

    const passes = checks.filter((c) => c.passed).length;
    const total = checks.length;
    const score = total === 0 ? 0 : passes / total;

    return {
      lender_id: r.id,
      name: data.name || "(unnamed lender)",
      score,
      passes,
      checks,
    };
  });

  // Sort: score desc, then tiebreak by max_funded_amount desc (more
  // headroom is better when fit is equal).
  ranked.sort((a, b) => {
    if (a.score !== b.score) return b.score - a.score;
    const aMax = a.checks.find((c) => c.key === "max_amount");
    const bMax = b.checks.find((c) => c.key === "max_amount");
    const aN = aMax ? parseFloat(aMax.requirement.replace(/[^0-9.]/g, "")) : 0;
    const bN = bMax ? parseFloat(bMax.requirement.replace(/[^0-9.]/g, "")) : 0;
    return bN - aN;
  });

  return NextResponse.json({
    ok: true,
    application_summary: {
      monthly_revenue: monthlyRevenue,
      requested_amount: requestedAmount,
      time_in_business_months: timeInBusinessMonths,
      fico: ficoScore,
      product_type: productType,
    },
    ranked: ranked.slice(0, 8),
    total_lenders: ranked.length,
  });
}
