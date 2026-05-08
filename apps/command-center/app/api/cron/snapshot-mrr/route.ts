/**
 * Vercel cron handler: write today's MRR snapshot for every active tenant.
 *
 * Snapshot source for now: user_profiles.mrr_current_usd (the operator-set
 * value). Future expansion: pull live from Stripe via /api/stripe-tool, but
 * the persistence shape is the same.
 *
 * Idempotent — UPSERT on (tenant_id, snapshot_date) so re-runs replace the
 * day's row instead of duplicating.
 *
 * Auth: requires CRON_SECRET in the Authorization header.
 *
 * Schedule (configure in Vercel project → Settings → Cron Jobs OR add to
 * vercel.json crons array):
 *   path: /api/cron/snapshot-mrr
 *   schedule: "0 4 * * *"   (04:00 UTC daily, ~midnight Eastern)
 */

import { NextResponse, type NextRequest } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { checkCronAuth } from "@/lib/cron-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const denied = checkCronAuth(req);
  if (denied) return denied;

  const db = getServiceSupabase();
  const today = new Date().toISOString().slice(0, 10);

  // Pull every tenant + the most-recent profile in that tenant. We snapshot
  // one row per tenant, using whichever profile has the latest update.
  const { data: rows, error: tenantsErr } = await db
    .from("user_profiles")
    .select("tenant_id, mrr_current_usd, mrr_target_usd, updated_at")
    .not("tenant_id", "is", null)
    .order("updated_at", { ascending: false });
  if (tenantsErr) {
    return NextResponse.json({ ok: false, error: tenantsErr.message }, { status: 500 });
  }

  const seen = new Set<string>();
  const inserts: Array<{
    tenant_id: string;
    snapshot_date: string;
    mrr_usd: number;
    target_usd: number | null;
    source: string;
  }> = [];
  for (const r of (rows || []) as Array<{
    tenant_id: string;
    mrr_current_usd: number | string | null;
    mrr_target_usd: number | string | null;
  }>) {
    if (seen.has(r.tenant_id)) continue;
    seen.add(r.tenant_id);
    inserts.push({
      tenant_id: r.tenant_id,
      snapshot_date: today,
      mrr_usd: Number(r.mrr_current_usd) || 0,
      target_usd: r.mrr_target_usd != null ? Number(r.mrr_target_usd) : null,
      source: "profile",
    });
  }

  if (inserts.length === 0) {
    return NextResponse.json({ ok: true, snapshots: 0 });
  }

  const { error } = await db
    .from("mrr_snapshots")
    .upsert(inserts, { onConflict: "tenant_id,snapshot_date" });
  if (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }

  return NextResponse.json({ ok: true, snapshots: inserts.length, date: today });
}
