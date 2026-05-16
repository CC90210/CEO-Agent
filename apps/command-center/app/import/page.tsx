/**
 * /import — bulk lead import page. Replaces the prior ComingSoon stub.
 *
 * Operator pastes a CSV (or drops a .csv file), confirms the column
 * mapping in the preview, and imports up to 5,000 rows per shot.
 * Server-side dedup against existing tenant leads keeps re-uploads
 * idempotent so an operator can re-run the same file after a partial
 * failure without doubling their pipeline.
 */

import { PageHeader } from "@/components/Card";
import { LeadsImportClient } from "@/components/leads/LeadsImportClient";
import { getActiveProfile } from "@/lib/queries";
import { safe } from "@/lib/api-helpers";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function ImportPage() {
  const profile = await safe("import.profile", getActiveProfile(), null);
  const hasTenant = !!profile?.tenant_id;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Import leads"
        subtitle="Paste a CSV or drop a file. Solara checks for duplicates before adding anything to your pipeline."
      />

      {hasTenant ? (
        <LeadsImportClient />
      ) : (
        <div className="rounded-xl border border-bg-border bg-bg-elev/40 p-8 text-center text-fg-muted text-sm">
          <p>Finish onboarding to connect this workspace before importing leads.</p>
          <Link
            href="/onboarding"
            className="mt-3 inline-block btn-secondary !px-3 !py-1.5 text-xs"
          >
            Go to onboarding →
          </Link>
        </div>
      )}
    </div>
  );
}
