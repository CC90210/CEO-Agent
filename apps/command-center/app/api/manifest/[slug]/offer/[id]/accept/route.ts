/**
 * POST /api/manifest/[slug]/offer/[id]/accept — accept a lender offer.
 *
 * Two-stroke mutation (Phase 10.2 of SunBiz CRM; stage names updated
 * 2026-05-17 to Salesforce-parity Opportunity Pipeline):
 *   1. Flip the offer's stage from approved_open_offers / contracts_ordered
 *      → funded. updateRecord auto-publishes a BRAVO_RECORD_STATUS_CHANGED
 *      event so any drip sequence triggered on "offer.stage → funded"
 *      fires automatically.
 *   2. Insert a draft funded_deal record carrying the offer's lead_id,
 *      lender_id, amount, term_months, and funded_at = today. The
 *      operator can fine-tune the funded_at date on the funded_deal
 *      detail page once it lands.
 *
 * Tenant scoping: both reads + writes are gated by the resolved
 * tenant_id, so a Sun rep can't accept an offer on a different tenant's
 * application by guessing the offer id.
 *
 * Idempotency: if the offer is already in stage=funded, the response
 * returns ok with `already_accepted: true` and doesn't double-insert
 * the funded_deal. The operator can hit Accept twice without creating
 * two duplicate funded_deal records.
 *
 * Response shape:
 *   { ok, offer: TenantRecord, funded_deal: TenantRecord | null,
 *     already_accepted: boolean }
 *   - funded_deal is null only on the already_accepted path.
 */

import { NextRequest, NextResponse } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { getRecord, updateRecord, createRecord, RecordsError } from "@/lib/manifest/data";
import { getManifest, manifestExists } from "@/lib/manifest/loader";
import { resolveDataTenant } from "@/lib/manifest/tenant-scope";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(
  _req: NextRequest,
  ctx: { params: Promise<{ slug: string; id: string }> },
) {
  const { slug, id } = await ctx.params;
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });

  if (!(await manifestExists(slug))) {
    return NextResponse.json({ ok: false, error: "unknown_tenant" }, { status: 404 });
  }

  const db = getServiceSupabase();
  const profileRes = await db
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const userTenantId = (profileRes.data as { tenant_id: string | null } | null)?.tenant_id ?? null;
  if (!userTenantId) return NextResponse.json({ ok: false, error: "no_tenant" }, { status: 401 });

  // resolveDataTenant returns null if the user isn't the owner of this
  // shell — same gate ManifestRecordForm uses to refuse writes from
  // preview-mode viewers.
  const dataTenantId = await resolveDataTenant(slug, userTenantId);
  if (!dataTenantId) {
    return NextResponse.json({ ok: false, error: "preview_mode_no_writes" }, { status: 403 });
  }

  // Sanity-check that the manifest actually declares an offer entity
  // and a funded_deal entity before we touch records. A SunBiz fork
  // that has dropped funded_deal from its data_model shouldn't crash
  // here; it should refuse with a clear error.
  const manifest = await getManifest(slug);
  const dataModel = manifest.data_model || [];
  if (!dataModel.find((e) => e.name === "offer")) {
    return NextResponse.json(
      { ok: false, error: "entity_not_in_manifest", entity: "offer" },
      { status: 400 },
    );
  }
  const hasFundedDeal = !!dataModel.find((e) => e.name === "funded_deal");

  const offer = await getRecord({ tenant_id: dataTenantId, entity: "offer", id });
  if (!offer) return NextResponse.json({ ok: false, error: "offer_not_found" }, { status: 404 });

  // Idempotent path — already accepted, don't double-write.
  if (offer.data.stage === "funded") {
    return NextResponse.json({
      ok: true,
      offer,
      funded_deal: null,
      already_accepted: true,
    });
  }

  // Flip the offer stage. updateRecord emits the status-change event
  // so any drip on offer.stage → funded fires automatically.
  let updatedOffer;
  try {
    updatedOffer = await updateRecord({
      tenant_id: dataTenantId,
      entity: "offer",
      id,
      patch: { stage: "funded" },
    });
  } catch (err) {
    const code = err instanceof RecordsError ? err.code : "unknown";
    return NextResponse.json(
      { ok: false, error: `update_failed:${code}` },
      { status: 500 },
    );
  }

  // Also flip the parent application's status to "funded" so the
  // Opportunity Pipeline on /applications reflects the deal closing.
  // Best-effort: if the offer doesn't carry application_id (legacy
  // rows from before the application↔offer link was enforced) we
  // silently skip — the funded_deal still gets created below.
  const offerAppId = (offer.data as Record<string, unknown>).application_id;
  if (typeof offerAppId === "string" && offerAppId) {
    try {
      await updateRecord({
        tenant_id: dataTenantId,
        entity: "application",
        id: offerAppId,
        patch: { status: "funded" },
      });
    } catch {
      // application may have been deleted or this offer pre-dates the
      // application↔offer link. The funded_deal is the source of truth
      // for the actual money landed; the missing application sync is a
      // cosmetic gap, not a data-integrity one.
    }
  }

  // Create the draft funded_deal. Fields come straight from the offer
  // where they exist. The operator edits the rest from /funded-deals.
  let fundedDeal = null;
  if (hasFundedDeal) {
    const offerData = updatedOffer.data || {};
    const todayIso = new Date().toISOString().slice(0, 10);
    try {
      fundedDeal = await createRecord({
        tenant_id: dataTenantId,
        entity: "funded_deal",
        data: {
          lead_id: offerData.lead_id,
          lender_id: offerData.lender_id || null,
          amount_funded: offerData.amount || null,
          funded_at: offerData.funded_at || todayIso,
          term_months: offerData.term_months || null,
          // Carry the offer.id so the funded_deal can back-link to
          // which offer was accepted. Used by the renewal cron in
          // Phase 15 to credit the right lender on renewal.
          source_offer_id: id,
        },
      });
    } catch (err) {
      // Funded deal creation failure DOES NOT roll back the offer
      // accept. The accept event already fired; manually creating
      // the funded_deal from /funded-deals is the operator's
      // recourse. Surface the error so the UI can show a 'partial
      // success' message.
      const code = err instanceof RecordsError ? err.code : "unknown";
      return NextResponse.json(
        {
          ok: true,
          offer: updatedOffer,
          funded_deal: null,
          already_accepted: false,
          funded_deal_error: `create_failed:${code}`,
        },
      );
    }
  }

  return NextResponse.json({
    ok: true,
    offer: updatedOffer,
    funded_deal: fundedDeal,
    already_accepted: false,
  });
}
